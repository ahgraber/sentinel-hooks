"""The tamper-protection verdicts every surface that reaches a verdict must agree on.

`pi/tests/registration.test.mjs` judges Pi's hook runner against this same table.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

CASES_FILE = Path(__file__).parent / "guarded-path-cases.json"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"


def load_is_protected_path():
    """Import the hook by location; its filename is not a valid identifier."""
    spec = importlib.util.spec_from_file_location("block_hook_tampering", HOOKS_DIR / "block-hook-tampering.py")
    module = importlib.util.module_from_spec(spec)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec.loader.exec_module(module)
    return module.is_protected_path


CASES = json.loads(CASES_FILE.read_text())["cases"]
is_protected_path = load_is_protected_path()


def test_cases_are_loaded() -> None:
    """Guards the table itself: an empty one would make every test below vacuous."""
    assert len(CASES) > 20
    assert any(case["blocked"] for case in CASES)
    assert any(not case["blocked"] for case in CASES)


def test_instruction_markdown_is_guarded() -> None:
    instructions = [case for case in CASES if "/instructions/" in case["path"]]
    assert instructions
    assert all(case["blocked"] for case in instructions)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["path"])
def test_verdict_matches_the_shared_table(case: dict) -> None:
    path = os.path.expanduser(case["path"])
    assert is_protected_path(path) is case["blocked"], case["why"]
