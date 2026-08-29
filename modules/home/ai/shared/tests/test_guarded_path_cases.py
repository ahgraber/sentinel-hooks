"""The tamper-protection verdicts every implementation of the policy must agree on.

pi's security extension is a TypeScript port that cannot import
`block-hook-tampering.py`; `security-extension-index.test.mjs` asserts this same
table, which is what keeps the two honest.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

CASES_FILE = Path(__file__).parent / "guarded-path-cases.json"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"


def load_is_protected_path():
    """Import the hook by location; its filename is not a valid identifier."""
    spec = importlib.util.spec_from_file_location(
        "block_hook_tampering", HOOKS_DIR / "block-hook-tampering.py"
    )
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


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["path"])
def test_verdict_matches_the_shared_table(case: dict) -> None:
    path = os.path.expanduser(case["path"])
    assert is_protected_path(path) is case["blocked"], case["why"]
