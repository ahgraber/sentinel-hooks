"""Tests for the Codex destructive-ops hook engine, using synthetic rules."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[2] / "shared" / "hooks"
HOOK_SOURCE = HOOKS_DIR / "block-destructive-ops.py"
RULES_NAME = "block-destructive-ops-patterns.toml"
# The hook reads its rules from its own directory, so these tests run a copy of
# it beside synthetic ones. Its sibling imports have to travel with the copy.
SIBLING_MODULES = ("hook_response.py", "guarded_paths.py", "guarded-paths.toml", "tool-vocabulary.toml")
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


def install_hook(directory: Path) -> Path:
    """Place a runnable copy of the hook in `directory`, siblings included."""
    path = directory / HOOK_SOURCE.name
    shutil.copyfile(HOOK_SOURCE, path)
    for name in SIBLING_MODULES:
        shutil.copyfile(HOOKS_DIR / name, directory / name)
    return path


@pytest.fixture
def hook_path(tmp_path: Path) -> Path:
    path = install_hook(tmp_path)
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


@pytest.mark.parametrize(
    "rules", [None, RULES + '\n[[rules]]\npattern = "x"\ndescription = "d"\nreason = "r"\nmode = "deny"\n']
)
def test_an_unusable_rules_file_blocks_where_no_prompt_can_be_shown(tmp_path: Path, rules: str | None) -> None:
    hook_path = install_hook(tmp_path)
    if rules is not None:
        (tmp_path / RULES_NAME).write_text(rules)

    result = run_hook(hook_path, "safe command")

    assert result.returncode == 2
    assert "blocked instead of prompted" in result.stderr


def test_ask_rule_is_also_blocked(hook_path: Path) -> None:
    result = run_hook(hook_path, "run synthetic-ask now")

    assert result.returncode == 2
    assert "Confirm the test rule" in result.stderr
    assert "blocked instead of prompted" in result.stderr
