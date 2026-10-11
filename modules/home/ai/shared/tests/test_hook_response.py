"""How a hook's decision reaches each agent.

The agents assign different meanings to the same exit code, so the decision is
the shared vocabulary and the encoding is not. A decision an agent cannot
express must degrade downward, never into a refusal.
"""

from __future__ import annotations

import json

from hook_response import (
    ABSOLUTE_PATH_INSTRUCTIONS,
    CLAUDE,
    CODEX,
    COPILOT,
    PI,
    RETRY_INSTRUCTIONS,
    STOP_INSTRUCTIONS,
    UNKNOWN,
    Decision,
    Instruction,
    invoking_agent,
    respond,
)
import pytest


def exit_code(
    decision: Decision,
    agent: str,
    message: str = "why",
    tool_name: str | None = None,
) -> int:
    with pytest.raises(SystemExit) as raised:
        respond(decision, message, agent=agent, tool_name=tool_name)
    return raised.value.code


class TestAgentIdentification:
    """The invocation path names the agent, so no hook registration carries it."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/home/user/.claude/hooks/block-hook-tampering.py", CLAUDE),
            ("/home/user/.codex/hooks/block-hook-tampering.py", CODEX),
            ("/home/user/.copilot/hooks/block-hook-tampering.py", COPILOT),
        ],
    )
    def test_deployed_directory_names_the_agent(self, path: str, expected: str) -> None:
        assert invoking_agent(path) == expected

    def test_repository_path_names_no_agent(self) -> None:
        assert invoking_agent("/repo/modules/home/ai/shared/hooks/x.py") == UNKNOWN

    def test_an_adapter_may_declare_itself(self, monkeypatch) -> None:
        """Copilot reaches these scripts through its adapter, not its hook directory."""
        monkeypatch.setenv("AI_HOOK_AGENT", "copilot")
        assert invoking_agent("/repo/modules/home/ai/shared/hooks/x.py") == COPILOT

    def test_pi_is_named_only_by_its_adapter(self, monkeypatch) -> None:
        """Validates: AdapterNamesARecognizedAgent."""
        monkeypatch.setenv("AI_HOOK_AGENT", "pi")
        assert invoking_agent("/repo/modules/home/ai/shared/hooks/x.py") == PI

    @pytest.mark.parametrize(("declared", "expected"), [("copilot", COPILOT), ("pi", PI)])
    def test_a_declaration_outranks_another_agents_payload_field(self, monkeypatch, declared, expected) -> None:
        """VS Code sends `transcript_path` too, so the field cannot name the agent over its adapter."""
        monkeypatch.setenv("AI_HOOK_AGENT", declared)
        payload = {"transcript_path": "/tmp/transcript.jsonl"}
        assert invoking_agent("/repo/modules/home/ai/shared/hooks/x.py", payload) == expected

    def test_an_unrecognized_declaration_is_ignored(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_HOOK_AGENT", "something-else")
        assert invoking_agent("/repo/modules/home/ai/shared/hooks/x.py") == UNKNOWN

    def test_a_transcript_path_names_claude(self) -> None:
        """Claude Code is the only agent that sends one."""
        payload = {"tool_name": "Read", "transcript_path": "/tmp/transcript.jsonl"}
        assert invoking_agent("/repo/modules/home/ai/shared/hooks/x.py", payload) == (CLAUDE)

    def test_the_invocation_path_outranks_the_payload(self) -> None:
        payload = {"transcript_path": "/tmp/transcript.jsonl"}
        assert invoking_agent("/home/user/.codex/hooks/x.py", payload) == CODEX


class TestAllow:
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_allow_proceeds_everywhere(self, agent: str) -> None:
        assert exit_code(Decision.ALLOW, agent) == 0


class TestBlock:
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_block_refuses_everywhere(self, agent: str) -> None:
        assert exit_code(Decision.BLOCK, agent) == 2

    def test_block_carries_the_reason_and_the_ai_instructions(self, capsys) -> None:
        exit_code(Decision.BLOCK, CLAUDE, "Blocked: no.")
        stderr = capsys.readouterr().err
        assert "Blocked: no." in stderr
        assert "AI INSTRUCTIONS:" in stderr
        assert "how the user can help" in stderr.lower()


class TestWarn:
    @pytest.mark.parametrize("agent", [CLAUDE, PI])
    def test_warn_is_visible_where_an_agent_can_show_it(self, capsys, agent: str) -> None:
        assert exit_code(Decision.WARN, agent, "payload unreadable") == 1
        assert "payload unreadable" in capsys.readouterr().err

    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_warn_degrades_to_allow_where_it_cannot(self, agent: str) -> None:
        """Never to block: Copilot denies the tool call on any non-zero exit."""
        assert exit_code(Decision.WARN, agent) == 0


class TestAsk:
    """Prompting is a property of the (agent, tool) pairing, not the agent alone."""

    @pytest.mark.parametrize("tool_name", [None, "Bash", "Write", "Edit"])
    def test_ask_prompts_under_claude_on_every_tool(self, capsys, tool_name) -> None:
        assert exit_code(Decision.ASK, CLAUDE, "credential store", tool_name) == 0
        payload = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
        assert payload["permissionDecision"] == "ask"
        assert payload["permissionDecisionReason"] == "credential store"

    @pytest.mark.parametrize("tool_name", [None, "Bash", "Read", "Write", "Edit"])
    def test_ask_reaches_the_pi_adapter_on_every_tool(self, capsys, tool_name) -> None:
        """Validates: AdapterNamesARecognizedAgent. The adapter, not the hook, knows whether a UI is attached."""
        assert exit_code(Decision.ASK, PI, "enforcement file", tool_name) == 0
        payload = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
        assert payload["permissionDecision"] == "ask"

    @pytest.mark.parametrize(
        ("instruction", "text"),
        [
            (Instruction.STOP, STOP_INSTRUCTIONS),
            (Instruction.RETRY, RETRY_INSTRUCTIONS),
            (Instruction.ABSOLUTE_PATH, ABSOLUTE_PATH_INSTRUCTIONS),
        ],
    )
    def test_a_pi_ask_carries_the_instructions_its_adapter_may_refuse_with(self, capsys, instruction, text) -> None:
        """Validates: AskAnAdapterMayRefuse. Pi's adapter refuses from this reason without a UI or on a decline."""
        with pytest.raises(SystemExit):
            respond(Decision.ASK, "enforcement file", agent=PI, tool_name="Write", instruction=instruction)
        reason = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason == f"enforcement file\n{text}"

    def test_a_claude_ask_carries_the_message_alone(self, capsys) -> None:
        """Claude Code shows the reason in its own prompt and refuses with its own framing."""
        with pytest.raises(SystemExit):
            respond(Decision.ASK, "enforcement file", agent=CLAUDE, tool_name="Write")
        reason = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason == "enforcement file"

    @pytest.mark.parametrize("declared", [None, "something-else"])
    def test_ask_refuses_where_the_adapter_names_no_known_agent(self, capsys, monkeypatch, declared) -> None:
        """Validates: AdapterNamesNothingOrSomethingUnknown."""
        monkeypatch.setattr("sys.argv", ["/repo/modules/home/ai/shared/hooks/x.py"])
        if declared is None:
            monkeypatch.delenv("AI_HOOK_AGENT", raising=False)
        else:
            monkeypatch.setenv("AI_HOOK_AGENT", declared)
        with pytest.raises(SystemExit) as raised:
            respond(Decision.ASK, "why", tool_name="Write")
        assert raised.value.code == 2
        assert capsys.readouterr().out == ""

    @pytest.mark.parametrize("tool_name", ["Write", "Edit"])
    def test_ask_prompts_under_copilot_on_file_mutation_tools(self, capsys, tool_name) -> None:
        """The VS Code surface holds these calls on the wrapped JSON shape."""
        assert exit_code(Decision.ASK, COPILOT, "enforcement file", tool_name) == 0
        payload = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
        assert payload["permissionDecision"] == "ask"
        assert payload["permissionDecisionReason"] == "enforcement file"

    @pytest.mark.parametrize("tool_name", [None, "Bash", "apply_patch"])
    def test_ask_refuses_under_copilot_elsewhere(self, capsys, tool_name) -> None:
        """The shell tool proceeds past the same JSON, so emitting it is fail-open."""
        assert exit_code(Decision.ASK, COPILOT, "why", tool_name) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "why" in captured.err

    @pytest.mark.parametrize("agent", [CODEX, UNKNOWN])
    @pytest.mark.parametrize("tool_name", [None, "Bash", "Write", "Edit"])
    def test_ask_refuses_where_no_prompt_is_honored(self, capsys, agent: str, tool_name) -> None:
        """Codex parses the prompt JSON and proceeds anyway, so stdout stays empty."""
        assert exit_code(Decision.ASK, agent, "why", tool_name) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "why" in captured.err


@pytest.mark.parametrize("text", [RETRY_INSTRUCTIONS, ABSOLUTE_PATH_INSTRUCTIONS])
def test_every_instruction_form_ends_with_the_same_four_reporting_points(text) -> None:
    """Validates: BlockAIGuidance. Each form requests the same account of the same stopped call."""
    points = STOP_INSTRUCTIONS[STOP_INSTRUCTIONS.index("1. ") :]
    assert text.endswith(points)
