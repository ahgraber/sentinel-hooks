#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Codex hook: block access to Codex safety configuration and live repo sources."""

import json
import os
import re
import shlex
import sys
from pathlib import Path

HOME = os.path.expanduser("~")
# hooks/ -> codex/ -> apps/ -> home/ -> modules/ -> repo root (5 levels up).
REPO_ROOT = Path(__file__).resolve().parents[5]
PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (?P<path>.+)$",
    re.MULTILINE,
)

PROTECTED_SUBSTRINGS = (
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/rules/",
    ".codex/hooks/",
    ".codex/auth.json",
    "modules/home/apps/codex/hooks/",  # shared cfg
    "modules/home/apps/codex/rules/",  # shared cfg
    "home-manager/codex/hooks.json",  # user cfg
    "home-manager/codex/config.toml",  # user cfg
)

ALLOWED_INSTRUCTION_BASES = (
    ".codex/hooks/instructions/",
    "modules/home/apps/codex/hooks/instructions/",
)

_AI_INSTRUCTIONS = """
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
"""


def expand(path: str) -> str:
    return os.path.realpath(os.path.normpath(os.path.expanduser(path)))


def build_protected_paths() -> tuple[str, ...]:
    paths = [
        os.path.join(HOME, ".codex", "config.toml"),
        os.path.join(HOME, ".codex", "hooks.json"),
        os.path.join(HOME, ".codex", "rules"),
        os.path.join(HOME, ".codex", "hooks"),
        os.path.join(HOME, ".codex", "auth.json"),
        str(REPO_ROOT / "modules" / "home" / "apps" / "codex" / "hooks"),
        str(REPO_ROOT / "modules" / "home" / "apps" / "codex" / "rules"),
    ]

    users_dir = REPO_ROOT / "users"
    if users_dir.is_dir():
        for user_dir in users_dir.iterdir():
            home_manager_dir = user_dir / "home-manager"
            paths.append(str(home_manager_dir / "codex" / "hooks.json"))
            paths.append(str(home_manager_dir / "codex" / "config.toml"))

    return tuple(paths)


PROTECTED_PATHS = tuple(expand(path) for path in build_protected_paths())


def matches_protected_fragment(text: str) -> bool:
    normalized = text.replace("\\", "/")
    return any(fragment in normalized for fragment in PROTECTED_SUBSTRINGS)


def is_allowed_instruction_markdown_path(path: str) -> bool:
    if not path:
        return False

    candidates = (
        path,
        os.path.normpath(os.path.expanduser(path)),
        expand(path),
    )

    for candidate in candidates:
        normalized = candidate.replace("\\", "/")
        if not normalized.endswith(".md"):
            continue

        for base in ALLOWED_INSTRUCTION_BASES:
            if base not in normalized:
                continue

            name = normalized.rsplit(base, 1)[1]
            if name and "/" not in name:
                return True

    return False


def is_protected_path(path: str) -> bool:
    if not path:
        return False

    if is_allowed_instruction_markdown_path(path):
        return False

    if matches_protected_fragment(path):
        return True

    resolved = expand(path)
    for protected in PROTECTED_PATHS:
        if resolved == protected or resolved.startswith(protected + os.sep):
            return True

    return False


def command_mentions_protected_path(command: str) -> bool:
    return matches_protected_fragment(command) or ("~/.codex/") in command


def command_references_only_allowed_instruction_markdown(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False

    protected_tokens = [
        token for token in tokens if command_mentions_protected_path(token)
    ]

    return bool(protected_tokens) and all(
        is_allowed_instruction_markdown_path(token) for token in protected_tokens
    )


def extract_apply_patch_targets(command: str) -> list[str]:
    return [match.group("path").strip() for match in PATCH_PATH_RE.finditer(command)]


def apply_patch_targets_only_allowed_instruction_markdown(command: str) -> bool:
    targets = extract_apply_patch_targets(command)
    if not targets:
        return False

    protected_targets = [
        target for target in targets if matches_protected_fragment(target)
    ]

    return bool(protected_targets) and all(
        is_allowed_instruction_markdown_path(target) for target in protected_targets
    )


def block(target: str, tool_name: str) -> None:
    sys.stderr.write(
        f"Blocked: {tool_name} targeting Codex safety/configuration path '{target}'.\n"
        "Codex hooks, rules, auth, and main configuration constrain tool behavior; "
        "reading them can help craft bypasses, and writing them can disable guardrails."
        f"\n{_AI_INSTRUCTIONS}\n"
    )
    sys.exit(2)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name in ("Read", "Write", "Edit"):
        paths = []
        for key in ("file_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                paths.append(value)
        for value in tool_input.get("file_paths", []) or []:
            if isinstance(value, str):
                paths.append(value)
        for path in paths:
            if is_protected_path(path):
                block(path, tool_name)
        sys.exit(0)

    if tool_name == "apply_patch":
        command = tool_input.get("command", "")
        if not isinstance(command, str):
            sys.exit(0)

        if command_mentions_protected_path(
            command
        ) and not apply_patch_targets_only_allowed_instruction_markdown(command):
            block(command, tool_name)

        for path in extract_apply_patch_targets(command):
            if is_protected_path(path):
                block(path, tool_name)
        sys.exit(0)

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if (
            command
            and command_mentions_protected_path(command)
            and not command_references_only_allowed_instruction_markdown(command)
        ):
            block(command, tool_name)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
