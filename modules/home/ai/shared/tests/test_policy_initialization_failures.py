"""Errors building the enforcement floor reach the same decisions as errors during a call."""

import io
import json

import guarded_paths
from hermetic import load_hook
import pytest

# Each payload names a path, so the call reaches the enforcement floor rather
# than returning before any verdict is taken.
MUTATING_PAYLOADS = {
    "Bash": {"command": "rm /tmp/notes.txt"},
    "Write": {"file_path": "/tmp/notes.txt"},
    "Edit": {"file_path": "/tmp/notes.txt"},
    "apply_patch": {"command": "*** Begin Patch\n*** Update File: /tmp/notes.txt\n*** End Patch"},
}


def _run(monkeypatch, agent, tool, tool_input):
    def fail_scan(_directory):
        raise PermissionError("cannot scan enforcement directory")

    monkeypatch.setattr(guarded_paths, "_enforcement_files", fail_scan)
    hook = load_hook("block-hook-tampering")
    monkeypatch.setenv("AI_HOOK_AGENT", agent)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps({"tool_name": tool, "tool_input": tool_input})))
    with pytest.raises(SystemExit) as stopped:
        hook.run()
    return stopped.value.code


@pytest.mark.parametrize("agent", ["claude", "codex", "copilot"])
@pytest.mark.parametrize("tool", sorted(MUTATING_PAYLOADS))
def test_enforcement_scan_failure_uses_tool_specific_response(monkeypatch, capsys, agent, tool):
    code = _run(monkeypatch, agent, tool, MUTATING_PAYLOADS[tool])
    result = capsys.readouterr()
    assert "cannot scan enforcement directory" in result.out + result.err
    if agent == "claude" or (agent == "copilot" and tool in {"Write", "Edit"}):
        assert code == 0
        assert json.loads(result.out)["hookSpecificOutput"]["permissionDecision"] == "ask"
    else:
        assert code == 2


READ_ROUTES = [
    # The path resolves, so the verdict returns before consulting the floor.
    pytest.param("/tmp/notes.txt", False, id="path-resolves"),
    # No working directory resolves this one, so the verdict falls through to
    # the text check over `guarded`, which carries the floor's declarations.
    pytest.param("notes.txt", True, id="path-reaches-the-text-check"),
]


@pytest.mark.parametrize("agent", ["claude", "codex", "copilot"])
@pytest.mark.parametrize(("path", "reaches_floor"), READ_ROUTES)
def test_a_failing_floor_scan_does_not_gate_a_read(monkeypatch, capsys, agent, path, reaches_floor):
    """The floor restricts no read, so a floor that cannot be built stops neither route."""
    code = _run(monkeypatch, agent, "Read", {"file_path": path})

    result = capsys.readouterr()
    assert result.out == "", f"A read reached a decision: {result.out}"
    if reaches_floor:
        assert code == (1 if agent == "claude" else 0)
        assert "cannot scan enforcement directory" in result.err
    else:
        assert (code, result.err) == (0, "")
