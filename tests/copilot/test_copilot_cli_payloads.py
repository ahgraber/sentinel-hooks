"""Copilot CLI payloads, replayed through the adapter, reach the decision their VS Code counterparts reach.

Copilot CLI runs the same registration as VS Code but sends Claude Code's tool
names. Its `create` and `edit` tools arrive as `Write` and `Edit` with a `path`
field, and its `apply_patch` tool arrives as `Edit` with the patch text as the
whole `tool_input`. Each payload below keeps the fields Copilot CLI 1.0 sent to a hook.
"""

from __future__ import annotations

import json
import subprocess
import sys

from conftest import ADAPTER_PATH, REPO_ROOT
import pytest

RECORDED = {
    "hook_event_name": "PreToolUse",
    "session_id": "64ce1b71-0332-44dc-aade-8d81227556d5",
    "timestamp": "2026-11-10T00:42:39.607Z",
    "cwd": str(REPO_ROOT),
}
GUARDED_SOURCE = "plugins/sentinel/hooks/block-leaks.py"
SENSITIVE_FILE = str(REPO_ROOT / "tmp" / "probe" / ".env")


def patch(path: str) -> str:
    return f"*** Begin Patch\n*** Update File: {path}\n@@\n-one\n+two\n*** End Patch\n"


def added(path: str) -> str:
    return f"*** Begin Patch\n*** Add File: {path}\n+one\n*** End Patch\n"


def decision(script: str, payload: dict) -> tuple[int, str | None]:
    """Run the adapter as Copilot does, and return its exit code and permission decision."""
    result = subprocess.run(
        [sys.executable, str(ADAPTER_PATH), script],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        cwd=REPO_ROOT,
    )
    output = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] if result.stdout else None
    return result.returncode, output


CASES = {
    "shell": (
        "block-sensitive-paths.py",
        {"tool_name": "Bash", "tool_input": {"command": "cat tmp/probe/.env", "description": "Read it"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "cat tmp/probe/.env"}},
    ),
    "view": (
        "block-sensitive-paths.py",
        {"tool_name": "Read", "tool_input": {"path": SENSITIVE_FILE}},
        {"tool_name": "read_file", "tool_input": {"filePath": SENSITIVE_FILE}},
    ),
    "apply_patch-sensitive": (
        "block-sensitive-paths.py",
        {"tool_name": "Edit", "tool_input": patch(SENSITIVE_FILE)},
        {"tool_name": "apply_patch", "tool_input": {"input": patch(SENSITIVE_FILE)}},
    ),
    "apply_patch-add": (
        "block-sensitive-paths.py",
        {"tool_name": "Edit", "tool_input": added(SENSITIVE_FILE)},
        {"tool_name": "apply_patch", "tool_input": {"input": added(SENSITIVE_FILE)}},
    ),
    "create": (
        "block-sensitive-paths.py",
        {"tool_name": "Write", "tool_input": {"path": SENSITIVE_FILE, "file_text": "one"}},
        {"tool_name": "create_file", "tool_input": {"filePath": SENSITIVE_FILE, "content": "one"}},
    ),
    "edit": (
        "block-hook-tampering.py",
        {"tool_name": "Edit", "tool_input": {"path": str(REPO_ROOT / GUARDED_SOURCE), "old_str": "a", "new_str": "b"}},
        {
            "tool_name": "replace_string_in_file",
            "tool_input": {"filePath": str(REPO_ROOT / GUARDED_SOURCE), "oldString": "a", "newString": "b"},
        },
    ),
    "apply_patch-guarded": (
        "block-hook-tampering.py",
        {"tool_name": "Edit", "tool_input": patch(GUARDED_SOURCE)},
        {"tool_name": "apply_patch", "tool_input": {"input": patch(GUARDED_SOURCE)}},
    ),
}


@pytest.mark.parametrize(("script", "copilot_cli", "vscode"), CASES.values(), ids=CASES.keys())
def test_a_copilot_cli_payload_reaches_the_vscode_decision(script: str, copilot_cli: dict, vscode: dict) -> None:
    expected = decision(script, {**RECORDED, **vscode})

    assert expected != (0, None), "the VS Code payload must be gated, or the comparison proves nothing"
    assert decision(script, {**RECORDED, **copilot_cli}) == expected
