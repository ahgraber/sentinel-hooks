#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Normalize VS Code hook payloads and dispatch to shared hook scripts.

Benchmark note: keep this Python adapter as the default. In local measurements it
was faster than the bash adapter because the bash path pays additional shell
plumbing costs plus repeated jq/perl-heavy downstream invocations.
"""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_HOOKS_DIR = REPO_ROOT / "configs" / "home-manager" / "claude" / "hooks"
COPILOT_HOOKS_DIR = REPO_ROOT / "configs" / "home-manager" / "copilot" / "hooks"

SCRIPT_PATHS = {
    "session-tool-checks.sh": CLAUDE_HOOKS_DIR / "session-tool-checks.sh",
    "session-instructions.sh": CLAUDE_HOOKS_DIR / "session-instructions.sh",
    "git-baseline.sh": CLAUDE_HOOKS_DIR / "git-baseline.sh",
    "block-dangerous-bash.sh": CLAUDE_HOOKS_DIR / "block-dangerous-bash.sh",
    "block-sensitive-paths.py": CLAUDE_HOOKS_DIR / "block-sensitive-paths.py",
    "block-destructive-ops.py": CLAUDE_HOOKS_DIR / "block-destructive-ops.py",
    "block-secrets.py": CLAUDE_HOOKS_DIR / "block-secrets.py",
    "bash-command-validator.sh": CLAUDE_HOOKS_DIR / "bash-command-validator.sh",
    "posttooluse-precommit.sh": CLAUDE_HOOKS_DIR / "posttooluse-precommit.sh",
    "copilot-block-hook-tampering.py": COPILOT_HOOKS_DIR
    / "copilot-block-hook-tampering.py",
}

TERMINAL_TOOLS = {
    "Bash": "Bash",
    "runInTerminal": "Bash",
    "run_in_terminal": "Bash",
    "terminal": "Bash",
}

READ_TOOLS = {
    "Read": "Read",
    "readFile": "Read",
    "read_file": "Read",
}

WRITE_TOOLS = {
    "Write": "Write",
    "create_file": "Write",
    "createFile": "Write",
}

EDIT_TOOLS = {
    "Edit": "Edit",
    "editFiles": "Edit",
    "replace_string_in_file": "Edit",
    "insert_edit_into_file": "Edit",
    "delete_file": "Edit",
    "rename_file": "Edit",
}

PATCH_TOOLS = {
    "apply_patch": "apply_patch",
}

MULTI_PATH_TARGETS = {
    "block-sensitive-paths.py",
    "block-secrets.py",
    "copilot-block-hook-tampering.py",
}


def _copy_dict(value: object) -> dict:
    return deepcopy(value) if isinstance(value, dict) else {}


def _extract_first_path(tool_input: dict) -> str:
    for key in ("file_path", "filePath", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value

    for key in ("file_paths", "filePaths", "files"):
        value = tool_input.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    return item

    return ""


def _extract_all_paths(tool_input: dict) -> list[str]:
    paths: list[str] = []

    for key in ("file_path", "filePath", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)

    for key in ("file_paths", "filePaths", "files"):
        value = tool_input.get(key)
        if isinstance(value, list):
            paths.extend(item for item in value if isinstance(item, str) and item)

    seen: set[str] = set()
    unique_paths: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    return unique_paths


def normalize_payload(raw_data: dict) -> dict:
    data = deepcopy(raw_data)
    tool_name = data.get("tool_name")
    if not isinstance(tool_name, str):
        tool_name = ""
    tool_input = _copy_dict(data.get("tool_input"))

    mapped_name = (
        TERMINAL_TOOLS.get(tool_name)
        or READ_TOOLS.get(tool_name)
        or WRITE_TOOLS.get(tool_name)
        or EDIT_TOOLS.get(tool_name)
        or PATCH_TOOLS.get(tool_name)
        or tool_name
    )

    if mapped_name == tool_name and not isinstance(tool_input, dict):
        return data

    normalized_input = deepcopy(tool_input)

    if mapped_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            command = tool_input.get("text")
        normalized_input = {"command": command or ""}

    elif mapped_name in {"Read", "Write", "Edit"}:
        paths = _extract_all_paths(tool_input)
        normalized_input = dict(tool_input)
        if paths:
            normalized_input["file_path"] = paths[0]
            normalized_input["file_paths"] = paths
            normalized_input["path"] = paths[0]

    elif mapped_name == "apply_patch":
        command = tool_input.get("command")
        if not isinstance(command, str):
            command = tool_input.get("input")
        normalized_input = {"command": command or ""}

    data["tool_name"] = mapped_name
    data["tool_input"] = normalized_input
    return data


def execute_hook(
    script_name: str, script_args: list[str], payload: dict
) -> subprocess.CompletedProcess[str]:
    script_path = SCRIPT_PATHS.get(script_name)
    if script_path is None:
        return subprocess.CompletedProcess(
            args=[script_name, *script_args],
            returncode=1,
            stdout="",
            stderr=f"Unknown hook script: {script_name}\n",
        )

    command = hook_command(script_path, script_args)

    return subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )


def hook_command(script_path: Path, script_args: list[str]) -> list[str]:
    if script_path.suffix == ".py":
        return ["uv", "run", "--script", str(script_path), *script_args]
    if script_path.suffix == ".sh":
        return ["bash", str(script_path), *script_args]
    return [str(script_path), *script_args]


def emit_result(result: subprocess.CompletedProcess[str]) -> None:
    stdout = rewrite_agent_name(result.stdout)
    stderr = rewrite_agent_name(result.stderr)
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)


def rewrite_agent_name(text: str) -> str:
    if not text:
        return text

    replacements = (
        ("Claude Code", "GitHub Copilot"),
        ("Claude's context", "Copilot's context"),
        ("Claude", "Copilot"),
    )

    rewritten = text
    for old, new in replacements:
        rewritten = rewritten.replace(old, new)
    return rewritten


def run_hook(script_name: str, script_args: list[str], payload: dict) -> int:
    result = execute_hook(script_name, script_args, payload)
    emit_result(result)
    return result.returncode


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: copilot-vscode-hook-adapter.py <script> [args...]\n")
        return 1

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    try:
        raw_data = json.load(sys.stdin)
    except Exception:
        raw_data = {}

    normalized = normalize_payload(raw_data)
    tool_name = normalized.get("tool_name")
    tool_input = _copy_dict(normalized.get("tool_input"))
    file_paths = tool_input.get("file_paths")

    if (
        script_name in MULTI_PATH_TARGETS
        and tool_name in {"Read", "Write", "Edit"}
        and isinstance(file_paths, list)
        and len(file_paths) > 1
    ):
        for path in file_paths:
            per_path = deepcopy(normalized)
            per_path_input = _copy_dict(per_path.get("tool_input"))
            per_path_input["file_path"] = path
            per_path_input["path"] = path
            per_path["tool_input"] = per_path_input
            result = execute_hook(script_name, script_args, per_path)
            if result.returncode != 0 or result.stdout:
                emit_result(result)
                return result.returncode
        return 0

    return run_hook(script_name, script_args, normalized)


if __name__ == "__main__":
    raise SystemExit(main())
