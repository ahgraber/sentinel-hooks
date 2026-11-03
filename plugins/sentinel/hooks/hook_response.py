"""Encode shared hook decisions for Claude, Codex, Copilot, and Pi.

Unsupported warnings allow. Unsupported asks block. Prompt JSON is emitted only
for agent and tool pairs known to honor it.
"""

from __future__ import annotations

import enum
import json
import os
import sys
from typing import NoReturn

try:
    from guarded_paths import TOOL_VOCABULARY
except Exception:  # noqa: BLE001
    # Only Copilot's ask support reads it. A hook that needs the vocabulary
    # reports the failure itself, and still needs the instruction text below.
    TOOL_VOCABULARY = None

CLAUDE = "claude"
CODEX = "codex"
COPILOT = "copilot"
PI = "pi"
UNKNOWN = "unknown"

_PATH_MARKERS = ((CLAUDE, "/.claude/"), (CODEX, "/.codex/"), (COPILOT, "/.copilot/"))
# Pi's registration and its dispatcher name it through `AI_HOOK_AGENT`, not a path marker.
_KNOWN_AGENTS = frozenset({*(agent for agent, _ in _PATH_MARKERS), PI})

# Pi's hook runner shows a hook's stderr on exit 1 and lets the call proceed.
_WARN_CAPABLE = frozenset({CLAUDE, PI})

_REPORT_POINTS = """1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed"""

STOP_INSTRUCTIONS = f"""
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
{_REPORT_POINTS}
"""

# For a refusal the classifier caused rather than the policy.
RETRY_INSTRUCTIONS = f"""
---
AI INSTRUCTIONS:
The classifier stopped this call because the command does not match any form it can check. Reading this path is allowed with the commands listed above.

If one of the commands listed above under "Recognized reads use" does what you need, run that instead.

If none of them does, stop and report the following to the user:
{_REPORT_POINTS}
"""


ABSOLUTE_PATH_INSTRUCTIONS = f"""
---
AI INSTRUCTIONS:
This call names a relative path in a directory the hook cannot determine, so it could not check which file the path reaches. Restate every relative path in the command as an absolute path and run the command again; the restated command is checked in full.

If the restated command is refused too, stop and report the following to the user:
{_REPORT_POINTS}
"""


class Decision(enum.StrEnum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    ASK = "ask"


class Instruction(enum.StrEnum):
    """Which closing instruction a refusal carries."""

    STOP = "stop"
    RETRY = "retry"
    ABSOLUTE_PATH = "absolute path"


_INSTRUCTION_TEXT = {
    Instruction.STOP: STOP_INSTRUCTIONS,
    Instruction.RETRY: RETRY_INSTRUCTIONS,
    Instruction.ABSOLUTE_PATH: ABSOLUTE_PATH_INSTRUCTIONS,
}


def invoking_agent(invocation_path: str | None = None, payload: dict | None = None) -> str:
    """Name the agent this hook is running for."""
    path = sys.argv[0] if invocation_path is None else invocation_path
    normalized = path.replace("\\", "/")
    for agent, marker in _PATH_MARKERS:
        if marker in normalized:
            return agent

    # An adapter's declaration comes first: VS Code also sends `transcript_path`.
    declared = os.environ.get("AI_HOOK_AGENT", "").strip().lower()
    if declared in _KNOWN_AGENTS:
        return declared

    if payload is not None and "transcript_path" in payload:
        return CLAUDE
    return UNKNOWN


def supports_ask(agent: str, tool_name: str | None = None) -> bool:
    """Return whether `agent` honors an ask response for `tool_name`.

    Without a tool, require support for every tool.
    """
    # Pi's adapter decides per call whether a prompt can be shown, and refuses where none can.
    if agent in (CLAUDE, PI):
        return True
    if agent == COPILOT:
        return tool_name is not None and TOOL_VOCABULARY.supports_ask(COPILOT, tool_name)
    return False


def respond(
    decision: Decision,
    message: str = "",
    *,
    agent: str | None = None,
    tool_name: str | None = None,
    instruction: Instruction = Instruction.STOP,
) -> NoReturn:
    """Encode `decision` for the invoking agent and exit."""
    who = invoking_agent() if agent is None else agent

    if decision is Decision.ASK and supports_ask(who, tool_name):
        # Pi's adapter refuses from this reason when it cannot show the prompt or the
        # user declines, so the reason carries the instructions a refusal needs.
        reason = f"{message}\n{_INSTRUCTION_TEXT[instruction]}" if who == PI else message
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            },
            sys.stdout,
        )
        sys.exit(0)

    if decision in (Decision.BLOCK, Decision.ASK):
        sys.stderr.write(f"{message}\n{_INSTRUCTION_TEXT[instruction]}\n")
        sys.exit(2)

    if decision is Decision.WARN:
        sys.stderr.write(f"{message}\n")
        sys.exit(1 if who in _WARN_CAPABLE else 0)

    sys.exit(0)
