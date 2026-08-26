"""Tests for the Codex destructive-ops hook engine, using synthetic rules."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SOURCE = (
    Path(__file__).resolve().parents[2] / "shared/hooks/block-destructive-ops.py"
)
RULES_NAME = "block-destructive-ops-patterns.toml"
RULES = r"""
[[rules]]
pattern = "synthetic-block"
description = "Synthetic block"
reason = "Blocked by the test rule"
mode = "block"

[[rules]]
pattern = "synthetic-ask"
description = "Synthetic ask"
reason = "Confirm the test rule"
mode = "ask"
"""


@pytest.fixture
def hook_path(tmp_path: Path) -> Path:
    path = tmp_path / HOOK_SOURCE.name
    shutil.copyfile(HOOK_SOURCE, path)
    (tmp_path / RULES_NAME).write_text(RULES)
    return path


def run_hook(hook_path: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def test_unmatched_command_is_allowed(hook_path: Path) -> None:
    assert run_hook(hook_path, "safe command").returncode == 0


def test_block_rule_blocks_with_reason_and_contract(hook_path: Path) -> None:
    result = run_hook(hook_path, "run synthetic-block now")

    assert result.returncode == 2
    assert "Blocked by the test rule" in result.stderr
    assert "AI INSTRUCTIONS:" in result.stderr


def test_ask_rule_is_also_blocked(hook_path: Path) -> None:
    result = run_hook(hook_path, "run synthetic-ask now")

    assert result.returncode == 2
    assert "Confirm the test rule" in result.stderr
    assert "blocked instead of prompted" in result.stderr
