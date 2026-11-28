"""A refused guardrail edit tells the agent to stop and report to the user, and offers no other way to make it.

Validates: GuardrailEditsRouteToTheUser. Where a harness cannot honor a hook's
`ask`, the report to the user is the route Sentinel controls. Each case runs the
tamper hook on an edit to agent enforcement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from conftest import HOOKS_DIR
from hook_response import ABSOLUTE_PATH_INSTRUCTIONS, RETRY_INSTRUCTIONS, STOP_INSTRUCTIONS
import pytest

# Text only the instruction forms that offer the agent another attempt carry.
RETRY_TEXT = RETRY_INSTRUCTIONS.split("\n\n")[1]
RESTATE_TEXT = ABSOLUTE_PATH_INSTRUCTIONS.split("\n\n")[0]

EDITS = {
    "disables-enforcement": '{"disableAllHooks": true}',
    "changes-enforcement": '{"hooks": {"PreToolUse": []}}',
}


def refuse(home: Path, agent: str | None, content: str) -> subprocess.CompletedProcess:
    """Run the tamper hook, for `agent`, on a write to Claude Code's settings under `home`."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(home),
        "tool_input": {"file_path": str(home / ".claude/settings.json"), "content": content},
    }
    environment = {"PATH": os.environ["PATH"], "HOME": str(home)}
    if agent is not None:
        environment["AI_HOOK_AGENT"] = agent
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "block-hook-tampering.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=environment,
    )


@pytest.mark.parametrize("agent", ["codex", None], ids=["codex", "undeclared"])
@pytest.mark.parametrize("content", EDITS.values(), ids=EDITS.keys())
def test_a_refusal_tells_the_agent_to_stop_and_report(tmp_path, agent, content) -> None:
    """Validates: WholesaleBypassRequested, NoSurfaceSeesTheRefusal. The edit is refused, with no prompt to answer."""
    result = refuse(tmp_path, agent, content)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.rstrip().endswith(STOP_INSTRUCTIONS.rstrip())
    assert RETRY_TEXT not in result.stderr
    assert RESTATE_TEXT not in result.stderr


def test_an_ask_pi_may_refuse_carries_the_same_instructions(tmp_path) -> None:
    """Validates: NoSurfaceSeesTheRefusal. Pi's runner refuses with this reason when no UI is attached."""
    result = refuse(tmp_path, "pi", EDITS["disables-enforcement"])

    reply = json.loads(result.stdout)["hookSpecificOutput"]
    assert reply["permissionDecision"] == "ask"
    assert reply["permissionDecisionReason"].rstrip().endswith(STOP_INSTRUCTIONS.rstrip())
