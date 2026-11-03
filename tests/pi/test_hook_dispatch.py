"""The Pi dispatcher: one process that runs the four Python hooks and answers Pi's hook runner.

Stand-in hooks under the four names isolate how outcomes decode and combine; the
cases at the end run the real shared hooks over Pi-shaped payloads.
"""

from __future__ import annotations

import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from types import ModuleType
from unittest.mock import patch

from hypothesis import given, settings, strategies as st
import pytest

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".specs").is_dir())
PLUGIN_DIR = REPO_ROOT / "plugins" / "sentinel"
DISPATCHER = PLUGIN_DIR / "harnesses" / "pi" / "hook-dispatch.py"
SHARED_HOOKS = PLUGIN_DIR / "hooks"
HOOK_NAMES = ("block-sensitive-paths.py", "block-hook-tampering.py", "block-destructive-ops.py", "block-leaks.py")

ALLOW = "import sys\nsys.exit(0)\n"
WARN = "import sys\nsys.stderr.write('lint unavailable')\nsys.exit(1)\n"
CRASH = "raise RuntimeError('broken import')\n"


def ask(reason: str) -> str:
    reply = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    return f"import json, sys\njson.dump({reply!r}, sys.stdout)\nsys.exit(0)\n"


def block(reason: str) -> str:
    return f"import sys\nsys.stderr.write({reason!r})\nsys.exit(2)\n"


def record(marker: Path) -> str:
    return f"import pathlib, sys\npathlib.Path({str(marker)!r}).write_text(sys.stdin.read())\nsys.exit(0)\n"


def load_dispatcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pi_hook_dispatch", DISPATCHER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dispatcher() -> ModuleType:
    return load_dispatcher()


@pytest.fixture(scope="module")
def dispatcher_module() -> ModuleType:
    return load_dispatcher()


@pytest.fixture
def stand_ins(tmp_path: Path):
    """Write stand-in hooks with the given bodies under the four names; unnamed ones allow."""

    def write(*bodies: str) -> Path:
        for index, name in enumerate(HOOK_NAMES):
            (tmp_path / name).write_text(bodies[index] if index < len(bodies) else ALLOW)
        return tmp_path

    return write


WRITE = {"tool_name": "Write", "tool_input": {"file_path": "/home/user/x"}}


class TestCombine:
    """Every hook runs, and the most restrictive decision wins."""

    def test_every_hook_allowing_is_an_allow(self, dispatcher, stand_ins) -> None:
        assert dispatcher.dispatch(WRITE, stand_ins()) == {"decision": "allow", "reasons": [], "notices": []}

    def test_an_ask_is_read_from_stdout_not_the_exit_status(self, dispatcher, stand_ins) -> None:
        """Validates: AskIsNotReadAsAllow."""
        verdict = dispatcher.dispatch(WRITE, stand_ins(ALLOW, ask("guarded write")))
        assert (verdict["decision"], verdict["reasons"]) == ("ask", ["guarded write"])

    def test_every_hook_after_an_ask_still_judges_the_call(self, dispatcher, stand_ins, tmp_path) -> None:
        """Validates: EveryHookRunsAfterAnAsk."""
        marker = tmp_path / "ran.json"
        payload = {"tool_name": "Bash", "tool_input": {"command": "true"}}
        verdict = dispatcher.dispatch(payload, stand_ins(ask("first"), ALLOW, ALLOW, record(marker)))
        assert verdict["decision"] == "ask"
        assert json.loads(marker.read_text()) == payload

    def test_a_refusal_after_an_ask_decides_the_call(self, dispatcher, stand_ins) -> None:
        """Validates: BlockOutranksAsk."""
        verdict = dispatcher.dispatch(WRITE, stand_ins(ask("guarded write"), ALLOW, ALLOW, block("credential")))
        assert (verdict["decision"], verdict["reasons"]) == ("block", ["credential"])

    def test_an_ask_after_a_refusal_does_not_soften_it(self, dispatcher, stand_ins) -> None:
        """Validates: BlockOutranksAsk."""
        verdict = dispatcher.dispatch(WRITE, stand_ins(block("credential"), ask("guarded write")))
        assert (verdict["decision"], verdict["reasons"]) == ("block", ["credential"])

    def test_a_warning_allows_and_is_kept_as_a_notice(self, dispatcher, stand_ins) -> None:
        verdict = dispatcher.dispatch(WRITE, stand_ins(WARN))
        assert verdict == {"decision": "allow", "reasons": [], "notices": ["lint unavailable"]}


class TestFailsClosed:
    """Validates: HookFailsInsideASharedProcess."""

    @pytest.mark.parametrize("body", [CRASH, "import sys\nsys.exit('bad state')\n", "import sys\nsys.exit(3)\n"])
    def test_a_hook_that_fails_refuses_the_call(self, dispatcher, stand_ins, body) -> None:
        verdict = dispatcher.dispatch(WRITE, stand_ins(ALLOW, body))
        assert verdict["decision"] == "block"
        assert "block-hook-tampering.py" in verdict["reasons"][0]
        assert "AI INSTRUCTIONS" in verdict["reasons"][0]

    def test_a_failure_in_the_dispatcher_itself_exits_2_not_1(self, dispatcher, monkeypatch, capsys) -> None:
        def broken(_payload):
            raise OSError("tool-vocabulary.toml unreadable")

        monkeypatch.setattr(dispatcher, "normalize", broken)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(WRITE)))
        assert dispatcher.main() == 2
        error = capsys.readouterr().err
        assert "tool-vocabulary.toml unreadable" in error
        assert "AI INSTRUCTIONS" in error

    def test_a_payload_that_does_not_parse_is_refused(self, dispatcher, monkeypatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{ not json"))
        assert dispatcher.main() == 2


class TestAnswer:
    """The combined verdict reaches the runner in the hook contract."""

    def test_a_refusal_exits_2_with_the_reasons(self, dispatcher, capsys) -> None:
        assert dispatcher.answer({"decision": "block", "reasons": ["a", "b"], "notices": []}) == 2
        assert capsys.readouterr().err == "a\n\nb\n"

    def test_an_ask_exits_0_with_the_ask_json(self, dispatcher, capsys) -> None:
        assert dispatcher.answer({"decision": "ask", "reasons": ["why"], "notices": []}) == 0
        reply = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
        assert (reply["permissionDecision"], reply["permissionDecisionReason"]) == ("ask", "why")

    def test_notices_exit_1_as_a_warning(self, dispatcher, capsys) -> None:
        assert dispatcher.answer({"decision": "allow", "reasons": [], "notices": ["note"]}) == 1
        assert capsys.readouterr().err == "note\n"

    def test_a_quiet_allow_exits_0(self, dispatcher, capsys) -> None:
        assert dispatcher.answer({"decision": "allow", "reasons": [], "notices": []}) == 0
        assert capsys.readouterr() == ("", "")


class TestNormalize:
    """Pi's tool names and input reach the hooks on the declared vocabulary."""

    def test_a_mapped_tool_reaches_the_gate_with_a_resolved_file_path(self, dispatcher) -> None:
        """Validates: MappedToolReachesTheGate on Pi."""
        payload = {
            "tool_name": "write",
            "cwd": "/home/user/project",
            "tool_input": {"path": "notes.md", "content": "x"},
        }
        normalized = dispatcher.normalize(payload)
        assert normalized["tool_name"] == "Write"
        assert normalized["tool_input"] == {
            "path": "notes.md",
            "content": "x",
            "file_path": "/home/user/project/notes.md",
        }

    def test_an_absolute_path_is_kept(self, dispatcher) -> None:
        payload = {"tool_name": "read", "cwd": "/home/user/project", "tool_input": {"path": "/etc/hosts"}}
        assert dispatcher.normalize(payload)["tool_input"]["file_path"] == "/etc/hosts"

    def test_the_shell_tool_keeps_its_command(self, dispatcher) -> None:
        normalized = dispatcher.normalize({"tool_name": "bash", "tool_input": {"command": "ls"}})
        assert (normalized["tool_name"], normalized["tool_input"]) == ("Bash", {"command": "ls"})

    def test_a_passthrough_tool_is_not_judged(self, dispatcher) -> None:
        """Validates: DeclaredPassthroughToolProceeds on Pi."""
        assert dispatcher.normalize({"tool_name": "find", "tool_input": {"pattern": "x"}}) is None

    @pytest.mark.parametrize("tool_name", ["futureTool", "", None])
    def test_an_unmapped_tool_is_refused(self, dispatcher, tool_name) -> None:
        """Validates: UnmappedToolIsRefused on Pi."""
        with pytest.raises(LookupError):
            dispatcher.normalize({"tool_name": tool_name, "tool_input": {}})


def _declared_paths() -> list[str]:
    """Every location the manifest declares, spelled as a tool call would supply it."""
    manifest = tomllib.loads((SHARED_HOOKS / "guarded-paths.toml").read_text())
    declared = [
        entry["path"] for table in manifest.values() if isinstance(table, dict) for entry in table.get("paths", [])
    ]
    declared += [entry["path"] for entry in manifest.get("exceptions", []) if "path" in entry]
    return sorted({path.replace("<repo>/", "").replace("*", "testuser") for path in declared})


PI_FILE_TOOLS = {"read": "Read", "write": "Write", "edit": "Edit"}


@given(
    tool=st.sampled_from(sorted(PI_FILE_TOOLS)),
    base=st.sampled_from([*_declared_paths(), "notes.md", "src/app.py"]),
    tail=st.sampled_from(["", "SKILL.md", "hooks/local.py", "a b.md", "settings.json"]),
    cwd=st.sampled_from([str(REPO_ROOT), str(Path.home())]),
)
@settings(max_examples=60, deadline=None)
def test_a_pi_file_call_reaches_the_decision_of_the_same_claude_call(dispatcher_module, tool, base, tail, cwd) -> None:
    """The generated counterpart of the verdict-table cases: mapping Pi's call changes no decision."""
    path = f"{base.rstrip('/')}/{tail}" if tail else base
    pi_input = {"path": path, "content": "x"} if tool == "write" else {"path": path}
    claude_input = {"file_path": str(Path(cwd) / Path(path).expanduser())}
    if tool == "write":
        claude_input["content"] = "x"
    with patch.dict(os.environ, {"AI_HOOK_AGENT": "pi"}):
        pi = dispatcher_module.dispatch(
            dispatcher_module.normalize({"tool_name": tool, "cwd": cwd, "tool_input": pi_input})
        )
        claude = dispatcher_module.dispatch({"tool_name": PI_FILE_TOOLS[tool], "cwd": cwd, "tool_input": claude_input})
    assert pi["decision"] == claude["decision"], (pi, claude)


PI_TOOLS = {"Write": "write", "Read": "read", "Bash": "bash"}


def test_the_dispatcher_reaches_every_table_outcome(dispatcher_module, tmp_path) -> None:
    """Validates: SharedTableAgrees on Pi, each table's hook run alone through the dispatcher's mapping.

    `shipped-registration.test.mjs` judges the whole registration through the hook runner.
    """
    sys.path.insert(0, str(REPO_ROOT / "tests" / "shared"))
    from verdict_conformance import conformance, load_cases, workdir

    scratch = (tmp_path / str(n) for n in itertools.count())

    def pi(case) -> str:
        cwd = workdir(case, next(scratch))
        if case.tool == "Bash":
            tool_input = {"command": case.target}
        else:
            tool_input = {"path": case.target, "content": "x"} if case.tool == "Write" else {"path": case.target}
        payload = {"tool_name": PI_TOOLS[case.tool], "cwd": str(cwd), "tool_input": tool_input}
        with patch.dict(os.environ, {"AI_HOOK_AGENT": "pi"}):
            return dispatcher_module.dispatch(dispatcher_module.normalize(payload), hooks=(case.hook,))["decision"]

    assert conformance(load_cases(), {"pi dispatcher": pi}) == []


def run_dispatcher(payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DISPATCHER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


class TestSharedHooks:
    """The real shared hooks judge Pi-shaped payloads through the dispatcher."""

    def test_a_write_to_a_private_key_is_refused(self) -> None:
        result = run_dispatcher(
            {"tool_name": "write", "cwd": "/home/user", "tool_input": {"path": ".ssh/id_ed25519", "content": "x"}}
        )
        assert result.returncode == 2, result.stderr
        assert "AI INSTRUCTIONS" in result.stderr

    def test_a_destructive_command_is_refused(self) -> None:
        result = run_dispatcher({"tool_name": "bash", "cwd": "/home/user", "tool_input": {"command": "rm -rf /"}})
        assert result.returncode == 2, result.stderr

    def test_an_ordinary_read_is_allowed(self, tmp_path) -> None:
        (tmp_path / "notes.md").write_text("hello")
        result = run_dispatcher({"tool_name": "read", "cwd": str(tmp_path), "tool_input": {"path": "notes.md"}})
        assert (result.returncode, result.stdout) == (0, ""), result.stderr

    def test_a_grep_of_a_credential_is_refused_as_a_read(self) -> None:
        """Pi's grep reads file contents, so it is judged as a Read of the path it names."""
        result = run_dispatcher(
            {"tool_name": "grep", "cwd": "/home/user", "tool_input": {"pattern": "KEY", "path": ".ssh/id_ed25519"}}
        )
        assert result.returncode == 2, result.stderr
        assert "AI INSTRUCTIONS" in result.stderr

    def test_a_grep_of_an_ordinary_file_is_allowed(self, tmp_path) -> None:
        (tmp_path / "notes.md").write_text("hello")
        result = run_dispatcher(
            {"tool_name": "grep", "cwd": str(tmp_path), "tool_input": {"pattern": "hello", "path": "notes.md"}}
        )
        assert (result.returncode, result.stdout) == (0, ""), result.stderr

    def test_an_unmapped_tool_is_refused_with_the_stop_form(self) -> None:
        result = run_dispatcher({"tool_name": "futureTool", "tool_input": {}})
        assert result.returncode == 2
        assert "'futureTool' has no declared mapping" in result.stderr
        assert "AI INSTRUCTIONS" in result.stderr

    def test_a_read_of_a_suggestive_name_reaches_the_runner_as_an_ask(self, tmp_path) -> None:
        """Validates: SuggestiveNamesAsk, through the dispatcher."""
        result = run_dispatcher({"tool_name": "read", "cwd": str(tmp_path), "tool_input": {"path": "auth_token.json"}})
        assert result.returncode == 0, result.stderr
        reply = json.loads(result.stdout)["hookSpecificOutput"]
        assert reply["permissionDecision"] == "ask"
        assert "auth_token.json" in reply["permissionDecisionReason"]


RULES_NAME = "block-destructive-ops-patterns.toml"
INVALID_RULE = '[[rules]]\npattern = "invalid-rule"\ndescription = "Unknown mode"\nreason = "r"\nmode = "deny"\n'
PATTERN_FILE_FAULTS = {
    "missing": (None, RULES_NAME),
    "unparsable": ("[[rules]\n", RULES_NAME),
    "invalid rule": (INVALID_RULE, "invalid-rule"),
}


def _dispatcher_beside_rules(tmp_path: Path, rules: str | None) -> Path:
    """Copy the dispatcher and the shared hooks into the layout it resolves, with `rules` as the pattern file.

    `None` removes the pattern file. The real rules file is never touched.
    """
    hooks = tmp_path / "sentinel" / "hooks"
    shutil.copytree(SHARED_HOOKS, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    if rules is None:
        (hooks / RULES_NAME).unlink()
    else:
        (hooks / RULES_NAME).write_text(rules)
    dispatcher = tmp_path / "sentinel" / "harnesses" / "pi" / DISPATCHER.name
    dispatcher.parent.mkdir(parents=True)
    shutil.copy(DISPATCHER, dispatcher)
    return dispatcher


@pytest.mark.parametrize(("rules", "named"), PATTERN_FILE_FAULTS.values(), ids=PATTERN_FILE_FAULTS.keys())
@pytest.mark.parametrize("command", ["ls", "rm -rf build"])
def test_a_pattern_file_fault_reaches_the_runner_as_an_ask_naming_the_fault(tmp_path, rules, named, command) -> None:
    """Validates: ExternalPatternFile faults, through the dispatcher, whether or not the command is destructive."""
    dispatcher = _dispatcher_beside_rules(tmp_path, rules)
    result = subprocess.run(
        [sys.executable, str(dispatcher)],
        input=json.dumps({"tool_name": "bash", "cwd": str(tmp_path), "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    reply = json.loads(result.stdout)["hookSpecificOutput"]
    assert reply["permissionDecision"] == "ask"
    assert named in reply["permissionDecisionReason"]
