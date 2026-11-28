"""Properties of the read classifier over generated command text.

The example suites encode the commands somebody thought of. This file states
what must hold for every command, and lets Hypothesis look for the ones nobody
thought of.

The classifier uses `shell_words` output. Differential lexing tests compare
that output with Bash in `test_shell_words_properties.py`.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys

import bash_commands
import guarded_paths
from hermetic import HOOKS_DIR
from hypothesis import assume, given, settings, strategies as st
import pytest
from shell_strategies import commands
import shell_words
from shellprobe import ShellProbe


def _load_gate():
    """Import the tamper hook; its filename is not a Python identifier."""
    spec = importlib.util.spec_from_file_location("tamper_gate_under_test", HOOKS_DIR / "block-hook-tampering.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

# A guarded path whose reads are allowed.
GUARDED = "~/.claude/skills/sdd-sync/references/sdd-spec-formats.md"
GUARDED_DIR = "~/.claude/skills/sdd-sync"
ORDINARY = "notes.md"

# A brace group holding an unquoted space is lexed into several words, so no one
# word states the whole group. The classifier must still refuse it.
GUARDED_SPACED = "~/.claude/skills/sdd-sync/a b.md"

RECORDED_PROGRAMS = set(bash_commands.READ_ONLY_UTILITIES) | set(bash_commands.INTERPRETERS) | {
    "rm", "tee", "cp", "mv", "install", "dd", "truncate",
}  # fmt: skip


@pytest.fixture(scope="module")
def probe(tmp_path_factory) -> ShellProbe:
    return ShellProbe(tmp_path_factory.mktemp("shellprobe"), RECORDED_PROGRAMS)


def allows(command: str) -> bool:
    """True if the command would run with no prompt."""
    return gate.command_protected_class(command, os.getcwd()) is None


class TestMetamorphicRelations:
    """Relations between verdicts on related commands."""

    @given(command=commands())
    @settings(max_examples=200, deadline=None)
    def test_naming_a_guarded_path_never_becomes_more_permissive(self, command: str) -> None:
        """Adding a guarded operand cannot turn a gate into an allow.

        Stated as an implication rather than a filtered case: most generated
        commands are allowed, so assuming the gate would discard nearly all of
        them and leave the relation barely exercised.
        """
        if allows(f"{command} {GUARDED}"):
            assert allows(command)

    @given(command=commands(), suffix=st.sampled_from(["", "/", "/."]))
    @settings(max_examples=200, deadline=None)
    def test_a_trailing_separator_does_not_change_the_verdict(self, command: str, suffix: str) -> None:
        """A directory is the same location however its name ends."""
        spelled = command.replace(GUARDED_DIR, GUARDED_DIR + suffix)
        assume(spelled != command)
        assert allows(spelled) == allows(command)


def boom(*args, **kwargs):
    """Stand in for any step of the hook that can fail."""
    raise RuntimeError("injected fault")


def _fail_at_executable_lookup(patch: pytest.MonkeyPatch) -> None:
    """Reach the executable test, which only a file already on disk reaches."""
    patch.setattr(gate.os.path, "isfile", lambda path: True)
    patch.setattr(gate.os, "access", boom)


# Each pairs a step of the hook with a payload that reaches it.
FAULT_SITES = [
    pytest.param(
        lambda patch: patch.setattr(guarded_paths, "spellings", boom),
        "Write",
        {"file_path": GUARDED},
        id="path-resolution",
    ),
    pytest.param(
        lambda patch: patch.setattr(gate.POLICY.classes["block"], "matches_hop", boom),
        "Bash",
        {"command": f"cat {GUARDED}"},
        id="containment",
    ),
    pytest.param(
        lambda patch: patch.setattr(shell_words.glob, "glob", boom),
        "Bash",
        {"command": f"cat {GUARDED_DIR}/*"},
        id="pathname-expansion",
    ),
    pytest.param(
        lambda patch: patch.setattr(gate.os.path, "isfile", boom),
        "Bash",
        {"command": f"{GUARDED_DIR}/helper.sh"},
        id="filesystem-metadata",
    ),
    pytest.param(
        _fail_at_executable_lookup,
        "Bash",
        {"command": f"{GUARDED_DIR}/helper"},
        id="executable-lookup",
    ),
]


def decide(patch: pytest.MonkeyPatch, tool_name: str, tool_input: dict, agent: str):
    """Run the hook over one payload in this process, returning its exit and output."""
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    # The hook records the call's tool and agent at module level; a run starts with none.
    patch.setitem(gate._CALL, "tool_name", "")
    patch.setitem(gate._CALL, "agent", "")
    patch.setenv("AI_HOOK_AGENT", agent)
    patch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out, err = io.StringIO(), io.StringIO()
    patch.setattr(sys, "stdout", out)
    patch.setattr(sys, "stderr", err)
    with pytest.raises(SystemExit) as exit_info:
        gate.run()
    return exit_info.value.code or 0, out.getvalue(), err.getvalue()


class TestFailClosedOnInternalError:
    """A step of the hook failing does not let the call through.

    `hook-interface` `ErrorHandlingByDamagePotential` sets the direction: a tool
    that can modify state must not proceed because the hook judging it crashed.
    The hook is registered for `Read` as well, which is why the direction is
    chosen per tool rather than per hook.
    """

    @pytest.mark.parametrize(("inject", "tool_name", "tool_input"), FAULT_SITES)
    def test_a_failure_reaches_the_user_under_claude(
        self, monkeypatch: pytest.MonkeyPatch, inject, tool_name: str, tool_input: dict
    ) -> None:
        inject(monkeypatch)
        code, out, _ = decide(monkeypatch, tool_name, tool_input, "claude")
        assert code == 0
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"
        assert "injected fault" in decision["permissionDecisionReason"]

    @pytest.mark.parametrize(("inject", "tool_name", "tool_input"), FAULT_SITES)
    def test_a_failure_refuses_where_no_prompt_can_be_shown(
        self, monkeypatch: pytest.MonkeyPatch, inject, tool_name: str, tool_input: dict
    ) -> None:
        inject(monkeypatch)
        code, out, err = decide(monkeypatch, tool_name, tool_input, "codex")
        assert code == 2
        assert out == ""
        assert "injected fault" in err

    @pytest.mark.parametrize("agent", ["claude", "codex"])
    def test_a_failure_naming_the_agent_refuses_a_mutating_call(self, monkeypatch: pytest.MonkeyPatch, agent) -> None:
        """With no agent named, no prompt can be shown, so the call is refused."""
        monkeypatch.setattr(gate, "invoking_agent", boom)
        code, out, err = decide(monkeypatch, "Bash", {"command": f"cat {GUARDED}"}, agent)
        assert code == 2
        assert out == ""
        assert "injected fault" in err

    def test_a_failure_judging_a_read_still_lets_it_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Blocking a read on a hook defect is disruption without a gain.

        It proceeds and the failure is reported, rather than proceeding in
        silence: a hook that checks nothing and says nothing is how a defect
        lasts.
        """
        monkeypatch.setattr(gate, "invoking_agent", boom)
        code, out, err = decide(monkeypatch, "Read", {"file_path": GUARDED}, "claude")
        assert (code, out) == (0, "")
        assert "injected fault" in err

    def test_an_unparsable_payload_warns_rather_than_refusing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The tool is unnamed, and this hook is registered for reads too."""
        monkeypatch.setenv("AI_HOOK_AGENT", "claude")
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        out, err = io.StringIO(), io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", err)
        with pytest.raises(SystemExit) as exit_info:
            gate.run()
        assert exit_info.value.code in (0, 1)
        assert "not checked" in err.getvalue()
