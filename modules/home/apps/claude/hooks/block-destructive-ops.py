#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Claude Code / Codex Hook: Block destructive operations.

Shared (symlinked) between Claude Code and Codex.

PreToolUse hook for the Bash tool.
Loads rules from block-destructive-ops-patterns.toml and matches each command
against them, producing a hard block (exit 2) or — for `ask` rules — a
confirmation prompt (exit 0 + JSON).

Confirmation prompts only work under Claude, which supports PreToolUse prompts.
Codex does not, so `ask` rules are blocked instead (fail closed). The agent is
detected from the payload: Claude sends `transcript_path`; when it is absent
(Codex, or an unknown agent) the hook blocks rather than prompt.

If the pattern file is missing or unreadable, the hook exits 0 (fail-open on
own configuration errors rather than blocking all Bash commands).
"""

import json
import re
import sys
from pathlib import Path

import tomllib


def load_rules() -> list[dict]:
    """Load rules from the co-located TOML file. Return [] on any error.

    Supports both flat (``[[rules]]``) and nested (``[[category.rules]]``)
    TOML structures. Nested categories are flattened into a single list.
    """
    patterns_file = Path(__file__).parent / "block-destructive-ops-patterns.toml"
    try:
        with open(patterns_file, "rb") as f:
            data = tomllib.load(f)
    except Exception:  # noqa: BLE001
        return []

    # Flat structure: [[rules]]
    if "rules" in data and isinstance(data["rules"], list):
        return data["rules"]

    # Nested structure: [[category.rules]]
    all_rules: list[dict] = []
    for section in data.values():
        if isinstance(section, dict) and "rules" in section:
            all_rules.extend(section["rules"])
    return all_rules


_AI_INSTRUCTIONS = """
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed"""


def supports_ask(data: dict) -> bool:
    """Whether the running agent can honour a PreToolUse confirmation prompt.

    Claude Code sends `transcript_path` in the hook payload; Codex does not
    (it sends `turn_id`). Fail safe: when we cannot confirm Claude, treat the
    agent as unable to prompt and block instead of asking.
    """
    return "transcript_path" in data


def make_ask_json(reason: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(2)  # fail-closed: this hook only handles Bash (sensitive tool)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    can_ask = supports_ask(data)

    rules = load_rules()
    if not rules:
        sys.exit(0)

    # Two-pass: collect the first `block` and first `ask` match separately. A
    # `block` rule must win over an `ask` rule regardless of file order —
    # otherwise an earlier ask rule (e.g. `git add -A`) masks a later
    # catastrophic block (`rm -rf /`) in a chained command, downgrading it to a
    # mere prompt. First-match-within-a-mode preserves the existing message.
    first_block: str | None = None
    first_ask: str | None = None

    for rule in rules:
        pattern = rule.get("pattern", "")
        if not pattern:
            continue

        flags = re.IGNORECASE if rule.get("case_insensitive", False) else 0
        try:
            compiled = re.compile(pattern, flags)
        except re.error:
            continue

        if not compiled.search(command):
            continue

        description = rule.get("description", "")
        reason = rule.get("reason", "")
        mode = rule.get("mode", "block")

        explanation = description
        if reason:
            explanation += f"\n\n{reason}"

        if mode == "block" and first_block is None:
            first_block = explanation
        elif mode == "ask" and first_ask is None:
            first_ask = explanation

    if first_block is not None:
        sys.stderr.write(f"Blocked: {first_block}\n{_AI_INSTRUCTIONS}\n")
        sys.exit(2)

    if first_ask is not None:
        if can_ask:
            sys.stdout.write(make_ask_json(first_ask))
            sys.exit(0)
        # The agent cannot require confirmation from a PreToolUse hook
        # (e.g. Codex): fail closed and block instead of prompting.
        first_ask += (
            "\n\nThis agent cannot require confirmation from a PreToolUse "
            "hook, so this command is blocked instead of prompted."
        )
        sys.stderr.write(f"Blocked: {first_ask}\n{_AI_INSTRUCTIONS}\n")
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        # ErrorHandlingByDamagePotential: this hook only handles Bash
        # (a sensitive tool), so always fail-closed on internal error.
        sys.exit(2)
