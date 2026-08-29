"""The gate's outcome across agents and protected classes.

The per-agent suites pin each agent's encoding in isolation; this file pins the
matrix — the same payload, judged per (agent, tool) pairing.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from guarded_paths import folds_case

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
HOOK = HOOKS_DIR / "block-hook-tampering.py"
REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)

CLAUDE = "claude"
CODEX = "codex"
COPILOT = "copilot"
UNKNOWN = "unknown"

REPO_SOURCE = "modules/home/ai/codex/rules/default.rules"
CREDENTIAL_PATHS = (
    "~/.claude/.credentials.json",
    "~/.codex/auth.json",
    "~/.pi/agent/auth.json",
)


@dataclass
class GateResult:
    exit_code: int
    stdout: str
    stderr: str


def run_gate(tool_name: str, tool_input: dict, agent: str) -> GateResult:
    """Run the hook as `agent` would invoke it: Claude Code by the transcript
    path its payloads carry, the others by the declaration their adapters set."""
    payload: dict = {"tool_name": tool_name, "tool_input": tool_input}
    env = {**os.environ}
    env.pop("AI_HOOK_AGENT", None)
    if agent == CLAUDE:
        payload["transcript_path"] = "/tmp/transcript.jsonl"
    elif agent != UNKNOWN:
        env["AI_HOOK_AGENT"] = agent

    result = subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env=env,
    )
    return GateResult(result.returncode, result.stdout, result.stderr)


def write(path: str, agent: str) -> GateResult:
    return run_gate("Write", {"file_path": path}, agent)


def edit(path: str, agent: str) -> GateResult:
    return run_gate(
        "Edit", {"file_path": path, "old_string": "a", "new_string": "b"}, agent
    )


def bash(command: str, agent: str) -> GateResult:
    return run_gate("Bash", {"command": command}, agent)


def ask_reason(result: GateResult) -> str:
    assert result.exit_code == 0, (
        f"Expected ask (exit 0), got {result.exit_code}.\nstderr: {result.stderr}"
    )
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    return output["permissionDecisionReason"]


def assert_refused(result: GateResult, substring: str = "") -> None:
    assert result.exit_code == 2, (
        f"Expected refusal (exit 2), got {result.exit_code}.\nstdout: {result.stdout}"
    )
    assert result.stdout == "", (
        f"A refusal must write nothing to stdout, got: {result.stdout}"
    )
    if substring:
        assert substring.lower() in result.stderr.lower(), (
            f"Expected '{substring}' in stderr, got: {result.stderr}"
        )


class TestGatedClassesByAgent:
    def test_edit_of_deployed_enforcement_asks_under_claude(self) -> None:
        reason = ask_reason(edit("~/.claude/settings.json", CLAUDE))
        assert "settings.json" in reason

    def test_edit_of_deployed_enforcement_refuses_under_codex(self) -> None:
        assert_refused(edit("~/.claude/settings.json", CODEX), "settings.json")

    def test_bash_naming_a_repository_source_asks_under_claude(self) -> None:
        reason = ask_reason(bash(f"echo x >> {REPO_SOURCE}", CLAUDE))
        assert "default.rules" in reason

    def test_operand_attached_spelling_reaches_the_same_outcome(self) -> None:
        spaced = bash(f"echo x >> {REPO_SOURCE}", CLAUDE)
        attached = bash(f"echo x >>{REPO_SOURCE}", CLAUDE)
        assert (spaced.exit_code, attached.exit_code) == (0, 0)
        assert ask_reason(attached)

    def test_edit_of_another_users_configuration_asks_under_claude(self) -> None:
        target = "users/testuser/home-manager/claude/settings.json"
        reason = ask_reason(edit(target, CLAUDE))
        assert "settings.json" in reason

    def test_gated_write_refuses_under_copilot_shell(self) -> None:
        """Copilot's shell tool proceeds past the prompt JSON, so Bash refuses."""
        assert_refused(bash(f"echo x >> {REPO_SOURCE}", COPILOT))

    def test_gated_write_asks_under_copilot_file_tools(self) -> None:
        assert ask_reason(write("~/.claude/settings.json", COPILOT))


class TestCredentialClass:
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    @pytest.mark.parametrize("credential", CREDENTIAL_PATHS)
    def test_credential_write_refuses_under_every_agent(
        self, agent: str, credential: str
    ) -> None:
        assert_refused(write(credential, agent), Path(credential).name)

    @pytest.mark.parametrize("credential", CREDENTIAL_PATHS)
    def test_mixed_class_command_refuses(self, credential: str) -> None:
        """The most restrictive class wins, even where the agent could prompt."""
        assert_refused(
            bash(f"cat {REPO_SOURCE} {credential}", CLAUDE), Path(credential).name
        )


class TestSpellingReachesTheGate:
    def test_case_variant_spelling_reaches_the_gate(self) -> None:
        if not folds_case(os.path.expanduser("~")):
            pytest.skip("filesystem under test is case-sensitive")
        assert ask_reason(write("~/.CLAUDE/settings.json", CLAUDE))

    def test_unresolvable_protected_path_reaches_the_gate(self) -> None:
        """A path resolution cannot follow is judged from the path as written."""
        target = f"{REPO_ROOT}/modules/home/ai/shared/hooks/x\x00.py"
        assert ask_reason(write(target, CLAUDE))


class TestInstructionMarkdownCarveOut:
    def test_direct_instruction_markdown_stays_writable(self) -> None:
        result = write(
            "modules/home/ai/claude/hooks/instructions/00-response-style.md", CLAUDE
        )
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_nested_path_under_instructions_is_gated(self) -> None:
        assert ask_reason(
            write("modules/home/ai/claude/hooks/instructions/nested/note.md", CLAUDE)
        )

    def test_non_markdown_in_instructions_is_gated(self) -> None:
        assert ask_reason(
            write("modules/home/ai/claude/hooks/instructions/helper.py", CLAUDE)
        )

    def test_markdown_name_leading_to_enforcement_is_gated(self, tmp_path: Path):
        """A write to a link is a write to what the link leads to."""
        (tmp_path / ".git").mkdir()
        hooks = tmp_path / "modules" / "home" / "ai" / "shared" / "hooks"
        (hooks / "instructions").mkdir(parents=True)
        (hooks / "block-destructive-ops.py").write_text("original\n")
        alias = hooks / "instructions" / "notes.md"
        alias.symlink_to("../block-destructive-ops.py")

        assert ask_reason(write(str(alias), CLAUDE))


class TestAskReasonContract:
    def test_reason_names_the_file_and_states_the_enforcement_consequence(
        self,
    ) -> None:
        reason = ask_reason(edit("~/.claude/settings.json", CLAUDE))
        assert "settings.json" in reason
        assert "enforcement" in reason.lower()
        assert "guardrail" in reason.lower()
