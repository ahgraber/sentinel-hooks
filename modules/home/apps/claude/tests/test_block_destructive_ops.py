"""Tests for the destructive-ops hook engine, using synthetic rules."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SOURCE = Path(__file__).resolve().parents[1] / "hooks/block-destructive-ops.py"
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

[[rules]]
pattern = "case-sensitive-source"
description = "Case-insensitive rule"
reason = "Matched without case"
mode = "block"
case_insensitive = true

[[rules]]
pattern = "["
description = "Invalid regular expression"
reason = "This rule must be skipped"
mode = "block"
"""


@pytest.fixture
def hook_path(tmp_path: Path) -> Path:
    path = tmp_path / HOOK_SOURCE.name
    shutil.copyfile(HOOK_SOURCE, path)
    (tmp_path / RULES_NAME).write_text(RULES)
    return path


def run_hook(
    hook_path: Path,
    command: str = "",
    *,
    tool_name: str = "Bash",
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = stdin_text
    if payload is None:
        payload = json.dumps(
            {
                "tool_name": tool_name,
                "tool_input": {"command": command},
                # Claude includes transcript_path; its presence marks an
                # ask-capable agent so `ask` rules prompt rather than block.
                "transcript_path": "/tmp/transcript.jsonl",
            }
        )
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=payload,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def test_non_bash_tools_and_unmatched_commands_are_allowed(hook_path: Path) -> None:
    assert run_hook(hook_path, "synthetic-block", tool_name="Write").returncode == 0
    assert run_hook(hook_path, "safe command").returncode == 0


def test_block_rule_blocks_with_reason_and_contract(hook_path: Path) -> None:
    result = run_hook(hook_path, "run synthetic-block now")

    assert result.returncode == 2
    assert "Blocked by the test rule" in result.stderr
    assert "AI INSTRUCTIONS:" in result.stderr


def test_ask_rule_returns_claude_confirmation(hook_path: Path) -> None:
    result = run_hook(hook_path, "run synthetic-ask now")

    assert result.returncode == 0
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    assert "Confirm the test rule" in output["permissionDecisionReason"]


def test_case_insensitive_rules_match_and_invalid_regexes_are_skipped(
    hook_path: Path,
) -> None:
    assert run_hook(hook_path, "CASE-SENSITIVE-SOURCE").returncode == 2
    assert run_hook(hook_path, "[").returncode == 0


def test_missing_rules_fail_open(tmp_path: Path) -> None:
    hook_path = tmp_path / HOOK_SOURCE.name
    shutil.copyfile(HOOK_SOURCE, hook_path)

    assert run_hook(hook_path, "synthetic-block").returncode == 0


def test_malformed_hook_input_fails_closed(hook_path: Path) -> None:
    assert run_hook(hook_path, stdin_text="not json").returncode == 2


def test_nested_rule_sections_are_loaded(tmp_path: Path) -> None:
    hook_path = tmp_path / HOOK_SOURCE.name
    shutil.copyfile(HOOK_SOURCE, hook_path)
    (tmp_path / RULES_NAME).write_text(
        r"""
[[synthetic.rules]]
pattern = "nested-rule"
description = "Nested rule"
reason = "Loaded from a nested section"
mode = "block"
"""
    )

    assert run_hook(hook_path, "nested-rule").returncode == 2


def test_block_wins_over_earlier_ask_rule(hook_path: Path) -> None:
    """A block rule must win even when an ask rule matches earlier in the file.

    'synthetic-ask' (ask, rule index 1) and 'case-sensitive-source' (block, rule
    index 2) both match. First-match-wins would downgrade the block to a prompt;
    the two-pass engine blocks.
    """
    result = run_hook(hook_path, "synthetic-ask and case-sensitive-source together")

    assert result.returncode == 2
    assert "Matched without case" in result.stderr  # the block rule's reason
    assert "permissionDecision" not in result.stdout  # not downgraded to ask
