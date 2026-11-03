#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Normalize VS Code hook payloads and dispatch to shared hook scripts.

Kept as the default: the bash adapter measured slower, paying shell orchestration
on top of jq/perl-heavy downstream hook invocations.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

# harnesses/copilot/ -> harnesses/ -> the plugin directory, which holds hooks/.
SHARED_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(SHARED_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HOOKS_DIR))

from hook_response import STOP_INSTRUCTIONS  # noqa: E402

VOCABULARY_FILE = SHARED_HOOKS_DIR / "tool-vocabulary.toml"
# An unreadable vocabulary refuses every tool call in `main`, rather than ending this
# script with a traceback the editor does not treat as a refusal.
try:
    from guarded_paths import TOOL_VOCABULARY
except Exception as _vocabulary_error:  # noqa: BLE001
    TOOL_VOCABULARY = None
    VOCABULARY_ERROR: Exception | None = _vocabulary_error
else:
    VOCABULARY_ERROR = None

# The shared hooks infer the agent from their invocation path, which this adapter bypasses.
HOOK_ENV = {**os.environ, "AI_HOOK_AGENT": "copilot"}

SCRIPT_PATHS = {
    "session-tool-checks.sh": SHARED_HOOKS_DIR / "session-tool-checks.sh",
    "git-baseline.sh": SHARED_HOOKS_DIR / "git-baseline.sh",
    "block-dangerous-bash.sh": SHARED_HOOKS_DIR / "block-dangerous-bash.sh",
    "block-hook-tampering.py": SHARED_HOOKS_DIR / "block-hook-tampering.py",
    "block-sensitive-paths.py": SHARED_HOOKS_DIR / "block-sensitive-paths.py",
    "block-destructive-ops.py": SHARED_HOOKS_DIR / "block-destructive-ops.py",
    "block-leaks.py": SHARED_HOOKS_DIR / "block-leaks.py",
    "bash-command-validator.sh": SHARED_HOOKS_DIR / "bash-command-validator.sh",
}

# Hooks that judge one path per call, so a multi-path edit must be fanned out.
# `block-hook-tampering.py` is absent deliberately: it judges the whole set and
# answers with the most restrictive class in it, which fanning out would defeat.
MULTI_PATH_TARGETS = {
    "block-sensitive-paths.py",
    "block-leaks.py",
}


# VS Code runs every registered hook on every call and ignores `matcher`, so the
# adapter selects the calls a tool-specific hook receives. Each key is the hook and
# its arguments; each value names a declared tool group. A hook not listed here
# receives every call.
HOOK_SCOPES: dict[tuple[str, ...], str] = {
    ("block-dangerous-bash.sh",): "shell",
    ("bash-command-validator.sh",): "shell",
    ("git-baseline.sh", "check"): "mutating",
    ("git-baseline.sh", "update"): "shell",
}


class UnmappedToolError(ValueError):
    """A tool call has no mapping to the shared hook vocabulary."""

    def __init__(self, tool_name: object) -> None:
        self.tool_name = tool_name
        super().__init__(f"Unmapped Copilot tool: {tool_name!r}")


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

    for key in ("file_path", "filePath", "path", "dirPath"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)

    for key in ("file_paths", "filePaths", "files"):
        value = tool_input.get(key)
        if isinstance(value, list):
            paths.extend(item for item in value if isinstance(item, str) and item)

    # `multi_replace_string_in_file` names one file per replacement.
    replacements = tool_input.get("replacements")
    if isinstance(replacements, list):
        for item in replacements:
            value = item.get("filePath") if isinstance(item, dict) else None
            if isinstance(value, str) and value:
                paths.append(value)

    seen: set[str] = set()
    unique_paths: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    return unique_paths


def normalize_payload(raw_data: dict) -> dict:
    """Remap a VS Code tool name and input into Claude Code's shape."""
    data = deepcopy(raw_data)
    if "tool_name" not in data:
        return data

    tool_name = data["tool_name"]
    if not isinstance(tool_name, str) or not tool_name:
        raise UnmappedToolError(tool_name)

    mapped_name = TOOL_VOCABULARY.normalize("copilot", tool_name)
    if mapped_name is None:
        # A declared passthrough tool reaches the hooks under its own name, which none of them gates.
        if TOOL_VOCABULARY.is_passthrough("copilot", tool_name):
            return data
        raise UnmappedToolError(tool_name)

    tool_input = _copy_dict(data.get("tool_input"))

    normalized_input = deepcopy(tool_input)

    if mapped_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            command = tool_input.get("text")
        # The other fields stay, so a hook that scans the whole call still sees them.
        normalized_input = {**tool_input, "command": command or ""}

    elif mapped_name in TOOL_VOCABULARY.group("file"):
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
        normalized_input = {**tool_input, "command": command or ""}

    data["tool_name"] = mapped_name
    data["tool_input"] = normalized_input
    return data


def execute_hook(script_name: str, script_args: list[str], payload: dict) -> subprocess.CompletedProcess[str]:
    """Run the named shared hook script with the given payload on stdin."""
    script_path = SCRIPT_PATHS.get(script_name)
    if script_path is None:
        return subprocess.CompletedProcess(
            args=[script_name, *script_args],
            returncode=1,
            stdout="",
            stderr=f"Unknown hook script: {script_name}\n",
        )

    command = hook_command(script_path, script_args)

    return subprocess.run(  # noqa: S603
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=HOOK_ENV,
    )


def hook_command(script_path: Path, script_args: list[str]) -> list[str]:
    """Build the argv to invoke a hook script by its file extension."""
    if script_path.suffix == ".py":
        return ["uv", "run", "--script", str(script_path), *script_args]
    if script_path.suffix == ".sh":
        return ["bash", str(script_path), *script_args]
    return [str(script_path), *script_args]


def emit_result(result: subprocess.CompletedProcess[str]) -> None:
    """Write a hook's stdout and stderr through, with the agent name rewritten."""
    stdout = rewrite_agent_name(result.stdout)
    stderr = rewrite_agent_name(result.stderr)
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)


def rewrite_agent_name(text: str) -> str:
    """Replace references to Claude with Copilot in hook output text."""
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
    """Run a hook script and emit its output, returning its exit code."""
    result = execute_hook(script_name, script_args, payload)
    emit_result(result)
    return result.returncode


def main() -> int:
    """Dispatch the CLI-invoked hook, fanning out over multi-path edits."""
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: copilot-vscode-hook-adapter.py <script> [args...]\n")
        return 1

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    try:
        raw_data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        raw_data = {}

    if TOOL_VOCABULARY is None:
        if "tool_name" not in raw_data:
            return run_hook(script_name, script_args, raw_data)
        sys.stderr.write(
            f"Blocked: the tool vocabulary at {VOCABULARY_FILE} could not be read ({VOCABULARY_ERROR}), "
            "so no tool call can be checked. The user has to repair the file by hand.\n"
            f"{STOP_INSTRUCTIONS}"
        )
        return 2

    try:
        normalized = normalize_payload(raw_data)
    except UnmappedToolError as error:
        sys.stderr.write(
            f"GitHub Copilot refused tool {error.tool_name!r} because it has no declared mapping "
            f"to the shared security hooks.\n{STOP_INSTRUCTIONS}"
        )
        return 2
    tool_name = normalized.get("tool_name")
    scope = HOOK_SCOPES.get((script_name, *script_args))
    if scope is not None and tool_name not in TOOL_VOCABULARY.group(scope):
        return 0
    tool_input = _copy_dict(normalized.get("tool_input"))
    file_paths = tool_input.get("file_paths")

    if (
        script_name in MULTI_PATH_TARGETS
        and tool_name in TOOL_VOCABULARY.group("file")
        and isinstance(file_paths, list)
        and len(file_paths) > 1
    ):
        results = []
        for path in file_paths:
            per_path = deepcopy(normalized)
            per_path_input = _copy_dict(per_path.get("tool_input"))
            per_path_input["file_path"] = path
            per_path_input["path"] = path
            # Leaving the list behind would make every fanned-out call judge the whole set.
            per_path_input.pop("file_paths", None)
            per_path["tool_input"] = per_path_input
            results.append(execute_hook(script_name, script_args, per_path))
        # A refusal on any path decides the call; an earlier ask cannot soften it.
        decisive = next((result for result in results if result.returncode == 2), None) or next(
            (result for result in results if result.returncode != 0 or result.stdout), None
        )
        if decisive is None:
            return 0
        emit_result(decisive)
        return decisive.returncode

    return run_hook(script_name, script_args, normalized)


if __name__ == "__main__":
    raise SystemExit(main())
