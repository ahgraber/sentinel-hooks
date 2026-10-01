"""The zero-access verdicts every surface that reaches a verdict must agree on.

`pi/tests/registration.test.mjs` judges Pi's hook runner against this same table.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from hermetic import load_hook
import pytest

CASES_FILE = Path(__file__).parent / "sensitive-path-cases.json"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"


def load_should_block():
    """Import the hook by location; its filename is not a valid identifier."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("block_sensitive_paths", HOOKS_DIR / "block-sensitive-paths.py")
    module = importlib.util.module_from_spec(spec)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec.loader.exec_module(module)
    return module.should_block


CASES = json.loads(CASES_FILE.read_text())["cases"]
should_block = load_should_block()


def test_cases_are_loaded() -> None:
    """Guards the table itself: an empty one would make every test below vacuous."""
    assert len(CASES) > 20
    assert any(case["blocked"] for case in CASES)
    assert any(not case["blocked"] for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["path"])
def test_verdict_matches_the_shared_table(case: dict) -> None:
    path = os.path.expanduser(case["path"])
    assert should_block(path) is case["blocked"], case["why"]


@pytest.mark.parametrize("case", json.loads(CASES_FILE.read_text())["bash_cases"])
def test_bash_word_cases(case, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for name in case["exists"]:
        (tmp_path / name).touch()
    hook = load_hook("block-sensitive-paths")
    assert bool(hook.bash_blocked_target(case["command"], str(tmp_path))) is case["blocked"]
