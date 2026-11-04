from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from types import ModuleType

from conftest import ADAPTER_PATH, HOOKS_DIR, REPO_ROOT
import pytest


def load_adapter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("copilot_hook_adapter", ADAPTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COPILOT_REGISTRATION = REPO_ROOT / "plugins" / "sentinel" / "com.github.copilot" / "hooks" / "hooks.json"


def adapter_invocations() -> set[tuple[str, ...]]:
    """The arguments each command in the Copilot registration passes the adapter."""
    registration = json.loads(COPILOT_REGISTRATION.read_text())
    return {tuple(shlex.split(hook["command"])[1:]) for hooks in registration["hooks"].values() for hook in hooks}


def test_configured_dispatch_targets_exist() -> None:
    """Each configured adapter invocation must resolve to a repository script."""
    adapter = load_adapter()
    invoked = {arguments[0] for arguments in adapter_invocations()}

    assert invoked, "found no adapter invocations in the Copilot registration"

    unknown = invoked - set(adapter.SCRIPT_PATHS)
    assert not unknown, f"the Copilot registration invokes scripts the adapter cannot resolve: {sorted(unknown)}"
    missing = {name: str(adapter.SCRIPT_PATHS[name]) for name in invoked if not adapter.SCRIPT_PATHS[name].is_file()}
    assert not missing, f"configured adapter targets do not exist: {missing}"


def test_lifecycle_payload_without_tool_name_reaches_shared_hook(monkeypatch) -> None:
    """A lifecycle event is not an unmapped tool call."""
    adapter = load_adapter()
    received: list[dict] = []

    def record(_script, _args, payload):
        received.append(payload)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(adapter, "execute_hook", record)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "session-1"})))
    monkeypatch.setattr("sys.argv", ["adapter", "session-tool-checks.sh"])

    assert adapter.main() == 0
    assert received == [{"session_id": "session-1"}]


def _adapter_with_broken_vocabulary(tmp_path: Path) -> Path:
    """Copy the adapter and the shared hooks into the layout it resolves, with an unparsable vocabulary."""
    hooks = tmp_path / "sentinel/hooks"
    shutil.copytree(HOOKS_DIR, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    (hooks / "tool-vocabulary.toml").write_text("not = [valid\n")
    adapter = tmp_path / "sentinel/harnesses/copilot/copilot-vscode-hook-adapter.py"
    adapter.parent.mkdir(parents=True)
    shutil.copy(ADAPTER_PATH, adapter)
    return adapter


def _run_adapter(adapter: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(adapter), "block-dangerous-bash.sh"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def test_an_unreadable_vocabulary_refuses_a_tool_call(tmp_path) -> None:
    """Validates: UnreadableVocabularyRefusesEveryCall, through the adapter."""
    result = _run_adapter(
        _adapter_with_broken_vocabulary(tmp_path), {"tool_name": "read_file", "tool_input": {"filePath": "/tmp/x"}}
    )

    assert result.returncode == 2
    assert "tool-vocabulary.toml" in result.stderr
    assert "AI INSTRUCTIONS" in result.stderr


def test_an_unreadable_vocabulary_still_runs_a_lifecycle_hook(tmp_path) -> None:
    """The vocabulary names tools, so an event that carries none still reaches its hook."""
    result = _run_adapter(_adapter_with_broken_vocabulary(tmp_path), {"hook_event_name": "SessionStart"})

    assert "tool-vocabulary.toml" not in result.stderr
    assert "Traceback" not in result.stderr


def test_unmapped_tool_is_refused_before_shared_hook(monkeypatch, capsys) -> None:
    """An unknown tool cannot bypass the shared hooks' declared vocabulary."""
    adapter = load_adapter()
    received: list[dict] = []

    def record(_script, _args, payload):
        received.append(payload)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(adapter, "execute_hook", record)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"tool_name": "futureTool", "tool_input": {}})),
    )
    monkeypatch.setattr("sys.argv", ["adapter", "block-sensitive-paths.py"])

    assert adapter.main() == 2
    assert received == []
    error = capsys.readouterr().err
    assert "futureTool" in error
    assert "AI INSTRUCTIONS" in error


def test_declared_passthrough_tool_reaches_shared_hooks_unchanged(monkeypatch) -> None:
    """A tool the declaration lists as passthrough is forwarded, not refused."""
    adapter = load_adapter()
    received: list[dict] = []

    class DeclaredVocabulary:
        group = staticmethod(adapter.TOOL_VOCABULARY.group)

        @staticmethod
        def normalize(_harness: str, _spelling: str) -> str | None:
            return None

        @staticmethod
        def is_passthrough(harness: str, spelling: str) -> bool:
            return harness == "copilot" and spelling.startswith("mcp_")

    def record(_script, _args, payload):
        received.append(payload)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    payload = {"tool_name": "mcp_context7_query-docs", "tool_input": {"query": "x"}}
    monkeypatch.setattr(adapter, "TOOL_VOCABULARY", DeclaredVocabulary(), raising=False)
    monkeypatch.setattr(adapter, "execute_hook", record)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.argv", ["adapter", "block-sensitive-paths.py"])

    assert adapter.main() == 0
    assert received == [payload]


def test_declared_tool_mapping_reaches_shared_gate(monkeypatch, capsys) -> None:
    """A mapping supplied by the declaration controls the shared hook verdict."""
    adapter = load_adapter()

    class DeclaredVocabulary:
        group = staticmethod(adapter.TOOL_VOCABULARY.group)

        @staticmethod
        def normalize(harness: str, spelling: str) -> str | None:
            assert harness == "copilot"
            return "Write" if spelling == "futureWrite" else None

    monkeypatch.setattr(adapter, "TOOL_VOCABULARY", DeclaredVocabulary(), raising=False)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "futureWrite",
                    "tool_input": {"filePath": "~/.codex/auth.json"},
                }
            )
        ),
    )
    monkeypatch.setattr("sys.argv", ["adapter", "block-sensitive-paths.py"])

    assert adapter.main() == 2
    error = capsys.readouterr().err
    assert "credential" in error.lower()
    assert "AI INSTRUCTIONS" in error


class TestMultiPathFanOut:
    """A multi-path edit reaches every path, and only the hooks that need it.

    Fanning out `block-hook-tampering.py` would return on the first path's ask,
    so a credential later in the same edit would never be judged.
    """

    def test_the_tamper_hook_is_not_fanned_out(self) -> None:
        adapter = load_adapter()
        assert "block-hook-tampering.py" not in adapter.MULTI_PATH_TARGETS

    def test_a_fanned_out_call_carries_one_path(self, monkeypatch) -> None:
        """The list must not ride along, or each call judges the set again."""
        adapter = load_adapter()
        seen: list[dict] = []

        def record(_script, _args, payload):
            seen.append(payload["tool_input"])
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(adapter, "execute_hook", record)
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                json.dumps(
                    {
                        "tool_name": "editFiles",
                        "tool_input": {"filePaths": ["/tmp/one.txt", "/tmp/two.txt"]},
                    }
                )
            ),
        )
        monkeypatch.setattr("sys.argv", ["adapter", "block-sensitive-paths.py"])

        assert adapter.main() == 0
        assert [call["file_path"] for call in seen] == ["/tmp/one.txt", "/tmp/two.txt"]
        assert not any("file_paths" in call for call in seen)

    def test_a_multi_replace_names_every_file_it_edits(self) -> None:
        """Each replacement carries its own `filePath`, and every one is judged."""
        adapter = load_adapter()
        normalized = adapter.normalize_payload(
            {
                "tool_name": "multi_replace_string_in_file",
                "tool_input": {
                    "replacements": [
                        {"filePath": "/tmp/one.txt", "oldString": "a", "newString": "b"},
                        {"filePath": "/tmp/two.txt", "oldString": "c", "newString": "d"},
                    ]
                },
            }
        )
        assert normalized["tool_name"] == "Edit"
        assert normalized["tool_input"]["file_paths"] == ["/tmp/one.txt", "/tmp/two.txt"]

    def test_a_created_directory_is_judged_as_a_write(self) -> None:
        adapter = load_adapter()
        normalized = adapter.normalize_payload(
            {"tool_name": "create_directory", "tool_input": {"dirPath": "/tmp/new-dir"}}
        )
        assert normalized["tool_name"] == "Write"
        assert normalized["tool_input"]["file_path"] == "/tmp/new-dir"

    def test_a_mixed_class_multi_path_edit_refuses(self) -> None:
        """The credential wins over the enforcement path, whichever comes first."""
        payload = json.dumps(
            {
                "tool_name": "editFiles",
                "tool_input": {"filePaths": ["~/.claude/settings.json", "~/.codex/auth.json"]},
            }
        )
        result = subprocess.run(
            ["uv", "run", "--script", str(ADAPTER_PATH), "block-hook-tampering.py"],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 2, f"expected a refusal, got exit {result.returncode}\nstdout: {result.stdout}"
        assert result.stdout == "", "a refusal must write nothing to stdout"
        assert "credential" in result.stderr.lower()


def test_ask_response_passes_through_intact(monkeypatch, capsys) -> None:
    """An ask survives the adapter: exit code preserved, JSON parseable after rewrite."""
    adapter = load_adapter()
    ask_json = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    "Claude Code may not change this enforcement file without your approval."
                ),
            }
        }
    )
    hook_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=ask_json, stderr="")
    monkeypatch.setattr(adapter, "execute_hook", lambda *args, **kwargs: hook_result)

    exit_code = adapter.run_hook("block-hook-tampering.py", [], {"tool_name": "Write"})

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert payload["permissionDecision"] == "ask"
    assert "Copilot" in payload["permissionDecisionReason"]
    assert "Claude" not in payload["permissionDecisionReason"]


@pytest.mark.parametrize("order", [("ask", "block"), ("block", "ask")])
def test_a_refusal_on_any_fanned_out_path_decides_the_call(monkeypatch, capsys, order) -> None:
    """Validates: OutcomesAreDecodedInFull, across the paths one edit names."""
    adapter = load_adapter()
    ask = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps({"hookSpecificOutput": {"permissionDecision": "ask"}}), stderr=""
    )
    block = subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="Blocked: b\n")
    outcomes = dict(zip(("/tmp/a", "/tmp/b"), (ask if name == "ask" else block for name in order), strict=True))
    monkeypatch.setattr(adapter, "execute_hook", lambda _s, _a, payload: outcomes[payload["tool_input"]["file_path"]])
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_name": "editFiles", "tool_input": {"files": ["/tmp/a", "/tmp/b"]}}))
    )
    monkeypatch.setattr("sys.argv", ["adapter", "block-sensitive-paths.py"])

    assert adapter.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Blocked: b" in captured.err


@pytest.mark.parametrize(
    ("argv", "tool_name", "runs"),
    [
        (["block-dangerous-bash.sh"], "run_in_terminal", True),
        (["block-dangerous-bash.sh"], "create_file", False),
        (["block-dangerous-bash.sh"], "list_dir", False),
        (["bash-command-validator.sh"], "run_in_terminal", True),
        (["bash-command-validator.sh"], "read_file", False),
        (["git-baseline.sh", "update"], "run_in_terminal", True),
        (["git-baseline.sh", "update"], "run_task", False),
        (["git-baseline.sh", "check"], "create_file", True),
        (["git-baseline.sh", "check"], "read_file", False),
        (["block-sensitive-paths.py"], "read_file", True),
    ],
)
def test_a_scoped_hook_receives_only_the_calls_of_its_group(monkeypatch, argv, tool_name, runs) -> None:
    """VS Code ignores `matcher`, so the adapter selects the calls a tool-specific hook receives."""
    adapter = load_adapter()
    received: list[dict] = []

    def record(_script, _args, payload):
        received.append(payload)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    payload = {
        "session_id": "s",
        "tool_name": tool_name,
        "tool_input": {"command": "true", "filePath": "/home/user/a"},
    }
    monkeypatch.setattr(adapter, "execute_hook", record)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.argv", ["adapter", *argv])

    assert adapter.main() == 0
    assert bool(received) is runs


def test_every_hook_scope_names_a_configured_invocation() -> None:
    """A scope keyed on an invocation the policy does not make would filter nothing."""
    adapter = load_adapter()
    invocations = adapter_invocations()

    for key, group in adapter.HOOK_SCOPES.items():
        assert key in invocations, key
        assert adapter.TOOL_VOCABULARY.group(group)
