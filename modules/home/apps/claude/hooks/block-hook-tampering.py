#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Claude Code Hook: Block writes to Claude's own hooks and settings.

PreToolUse hook for Write, Edit, and Bash tools.
Hard-blocks (exit 2) any attempt to modify the files that constrain Claude's
behaviour: hook scripts and settings files. Writing disables enforcement
outright, so it is blocked even when the change appears routine.

Reads are deliberately not blocked. The OS sandbox cannot enforce a read-deny
on these paths here: they are Home Manager symlinks into the Nix store, and
bubblewrap resolves a mount destination against its setup-time root, where an
absolute symlink target does not exist. A directory read-deny therefore aborts
every sandboxed command with "Can't mount tmpfs on <path>". Write protection is
unaffected, because write-denies are symlink-resolved before mounting.

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
    "Writing to them disables enforcement outright, so writes are blocked "
    "unconditionally."
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
    "home-manager/claude/settings.darwin.json",  # user cfg
    "home-manager/claude/settings.linux.json",  # user cfg
    "home-manager/claude/settings.user.json",  # user cfg
)


def _expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def _resolved(path: str) -> str:
    try:
        return os.path.realpath(_expand(path))
    except (OSError, ValueError):
        # ValueError covers a path carrying an embedded null byte, OSError the
        # resolution itself. Either way the unresolved path is still worth
        # matching against, so fall back rather than let the caller through.
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
    except (OSError, ValueError):
        # JSONDecodeError and UnicodeDecodeError are both ValueError; a payload
        # this hook cannot parse is one it cannot judge, so it defers.
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ("Bash", "Write", "Edit"):
        sys.exit(0)

    if tool_name in ("Write", "Edit"):
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
    except Exception:  # noqa: BLE001
        # Fail-open per hook-interface spec: this hook covers Bash/Write/Edit,
        # and substring matching is unlikely to crash. The catch is
        # deliberately blind — narrowing it would let an unforeseen error
        # escape as a non-zero exit and block the tool call instead.
        sys.exit(0)
