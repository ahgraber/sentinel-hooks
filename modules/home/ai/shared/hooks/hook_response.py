"""Encode shared hook decisions for Claude, Codex, and Copilot.

Unsupported warnings allow. Unsupported asks block. Prompt JSON is emitted only
for agent and tool pairs known to honor it.
"""

from __future__ import annotations

import enum
import json
import os
import sys
from typing import NoReturn

CLAUDE = "claude"
CODEX = "codex"
COPILOT = "copilot"
UNKNOWN = "unknown"

_PATH_MARKERS = ((CLAUDE, "/.claude/"), (CODEX, "/.codex/"), (COPILOT, "/.copilot/"))
_KNOWN_AGENTS = frozenset(agent for agent, _ in _PATH_MARKERS)

_WARN_CAPABLE = frozenset({CLAUDE})
# Copilot honors ask responses for file tools only; other asks block.
_COPILOT_ASK_TOOLS = frozenset({"Write", "Edit"})

AI_INSTRUCTIONS = """
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
"""


class Decision(enum.StrEnum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    ASK = "ask"


def invoking_agent(
    invocation_path: str | None = None, payload: dict | None = None
) -> str:
    """Name the agent this hook is running for."""
    path = sys.argv[0] if invocation_path is None else invocation_path
    normalized = path.replace("\\", "/")
    for agent, marker in _PATH_MARKERS:
        if marker in normalized:
            return agent

    if payload is not None and "transcript_path" in payload:
        return CLAUDE

    declared = os.environ.get("AI_HOOK_AGENT", "").strip().lower()
    return declared if declared in _KNOWN_AGENTS else UNKNOWN


def supports_ask(agent: str, tool_name: str | None = None) -> bool:
    """Return whether `agent` honors an ask response for `tool_name`.

    Without a tool, require support for every tool.
    """
    if agent == CLAUDE:
        return True
    if agent == COPILOT:
        return tool_name in _COPILOT_ASK_TOOLS
    return False


def respond(
    decision: Decision,
    message: str = "",
    *,
    agent: str | None = None,
    tool_name: str | None = None,
) -> NoReturn:
    """Encode `decision` for the invoking agent and exit."""
    who = invoking_agent() if agent is None else agent

    if decision is Decision.ASK and supports_ask(who, tool_name):
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": message,
                }
            },
            sys.stdout,
        )
        sys.exit(0)

    if decision in (Decision.BLOCK, Decision.ASK):
        sys.stderr.write(f"{message}\n{AI_INSTRUCTIONS}\n")
        sys.exit(2)

    if decision is Decision.WARN:
        sys.stderr.write(f"{message}\n")
        sys.exit(1 if who in _WARN_CAPABLE else 0)

    sys.exit(0)
