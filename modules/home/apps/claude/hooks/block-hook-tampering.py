#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Claude Code Hook: Block reads and writes to Claude's own hooks and settings.

PreToolUse hook for Read, Write, Edit, and Bash tools.
Hard-blocks (exit 2) any attempt to read or modify the files that constrain
Claude's behaviour: hook scripts and settings files. Reading enables crafting
bypasses; writing disables enforcement outright. Both must be blocked even when
the access appears routine.

Protected surfaces:
  - ~/.claude/hooks/**           hook scripts (this file lives here too)
  - ~/.claude/settings.json      main harness settings
  - ~/.claude/settings.local.json local overrides
  - modules/home/apps/claude/hooks/**  repo source for the symlinked hooks
  - users/*/home-manager/claude-settings.json  repo source for settings
"""

import json
import os
import shlex
import sys

# ── Risk explanation ──────────────────────────────────────────────────────────
_TAMPERING_RISK = (
    "Hook scripts and settings files enforce safety constraints on Claude. "
    "Reading them enables crafting bypasses; writing to them disables "
    "enforcement outright. Both are blocked unconditionally."
)

# ── Protected path fragments ──────────────────────────────────────────────────
# Substring match on the (expanded) path or raw bash command. Fragments are
# specific enough that incidental collisions are negligible.
PROTECTED_SUBSTRINGS = (
    ".claude.json",
    ".claude/hooks/",
    ".claude/settings.json",
    ".claude/settings.local.json",
    "modules/home/apps/claude/hooks/",  # shared cfg
    "home-manager/claude/settings.json",  # user cfg
    "home-manager/claude/settings.user.json",  # user cfg
)


def _expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def _resolved(path: str) -> str:
    try:
        return os.path.realpath(_expand(path))
    except Exception:
        return _expand(path)


def _matches(text: str) -> bool:
    return any(frag in text for frag in PROTECTED_SUBSTRINGS)


def _is_allowed_instruction_markdown_path(path: str) -> bool:
    for candidate in (path, _expand(path), _resolved(path)):
        normalized = candidate.replace(os.sep, "/")
        if not normalized.endswith(".md"):
            continue
        for base in (
            ".claude/hooks/instructions/",
            "modules/home/apps/claude/hooks/instructions/",
        ):
            if base not in normalized:
                continue
            name = normalized.rsplit(base, 1)[1]
            if name and "/" not in name:
                return True
    return False


def _matches_only_allowed_instruction_markdown(text: str) -> bool:
    try:
        tokens = shlex.split(text)
    except ValueError:
        return False

    protected_tokens = [token for token in tokens if _matches(token)]
    return bool(protected_tokens) and all(
        _is_allowed_instruction_markdown_path(token) for token in protected_tokens
    )


def is_protected_path(path: str) -> bool:
    """True if `path` (raw, expanded, or symlink-resolved) hits a protected fragment."""
    if not path:
        return False
    if _is_allowed_instruction_markdown_path(path):
        return False
    if _matches(path):
        return True
    expanded = _expand(path)
    if _matches(expanded):
        return True
    resolved = _resolved(path)
    return _matches(resolved)


_AI_INSTRUCTIONS = """
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed"""


def block(target: str, tool: str) -> None:
    sys.stderr.write(
        f"Blocked: {tool} targeting Claude hook or settings path '{target}'.\n"
        f"{_TAMPERING_RISK}\n"
        f"{_AI_INSTRUCTIONS}\n"
    )
    sys.exit(2)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ("Bash", "Read", "Write", "Edit"):
        sys.exit(0)

    if tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path") or tool_input.get("path", "")
        if path and is_protected_path(path):
            block(path, tool_name)
        sys.exit(0)

    command = tool_input.get("command", "")
    if (
        command
        and _matches(command)
        and not _matches_only_allowed_instruction_markdown(command)
    ):
        block(command, "Bash")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail-open per hook-interface spec: this hook covers Read (read-only)
        # alongside Bash/Write/Edit, and substring matching is unlikely to crash.
        sys.exit(0)
