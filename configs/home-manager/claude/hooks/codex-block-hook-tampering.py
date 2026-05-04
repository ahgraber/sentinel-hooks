#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Codex hook: block access to Codex safety configuration and hook files."""

import json
import os
import sys

HOME = os.path.expanduser("~")

PROTECTED_PATHS = (
    os.path.join(HOME, ".codex", "config.toml"),
    os.path.join(HOME, ".codex", "hooks.json"),
    os.path.join(HOME, ".codex", "rules"),
    os.path.join(HOME, ".codex", "hooks"),
    os.path.join(HOME, ".codex", "auth.json"),
)

PROTECTED_FRAGMENTS = (
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/rules/",
    ".codex/hooks/",
    ".codex/auth.json",
)

AI_INSTRUCTIONS = """
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find
alternative commands, equivalent steps, or workarounds that achieve the same
result through a different path.

Stop and report:
1. What you were trying to do
2. Which Codex safety/configuration path was blocked
3. Why user confirmation is needed before touching that path
"""


def expand(path: str) -> str:
    return os.path.realpath(os.path.normpath(os.path.expanduser(path)))


def is_protected_path(path: str) -> bool:
    if not path:
        return False

    raw = path.replace("\\", "/")
    if any(fragment in raw for fragment in PROTECTED_FRAGMENTS):
        return True

    resolved = expand(path)
    for protected in PROTECTED_PATHS:
        protected_resolved = expand(protected)
        if resolved == protected_resolved or resolved.startswith(
            protected_resolved + os.sep
        ):
            return True

    return False


def command_mentions_protected_path(command: str) -> bool:
    normalized = command.replace("\\", "/")
    if any(fragment in normalized for fragment in PROTECTED_FRAGMENTS):
        return True
    if "~/.codex/" in normalized:
        return True
    return False


def block(target: str, tool_name: str) -> None:
    sys.stderr.write(
        f"Blocked: {tool_name} targeting Codex safety/configuration path '{target}'.\n"
        "Codex hooks, rules, auth, and main configuration constrain tool behavior; "
        "reading them can help craft bypasses, and writing them can disable guardrails."
        f"\n{AI_INSTRUCTIONS}\n"
    )
    sys.exit(2)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name in ("Read", "Write", "Edit", "apply_patch"):
        paths = []
        for key in ("file_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                paths.append(value)
        for value in tool_input.get("file_paths", []) or []:
            if isinstance(value, str):
                paths.append(value)
        command = tool_input.get("command")
        if isinstance(command, str) and command_mentions_protected_path(command):
            block(command, tool_name)
        for path in paths:
            if is_protected_path(path):
                block(path, tool_name)
        sys.exit(0)

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if command and command_mentions_protected_path(command):
            block(command, tool_name)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
