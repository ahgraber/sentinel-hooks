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
# A relative case is a repository path, judged as a hook judges one from the checkout root.
REPO_ROOT = next(parent for parent in HOOKS_DIR.resolve().parents if (parent / "flake.nix").is_file())


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
    assert should_block(path, cwd=str(REPO_ROOT), reading=True) is case["blocked"], case["why"]


@pytest.mark.parametrize("case", json.loads(CASES_FILE.read_text())["bash_cases"])
def test_bash_word_cases(case, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for name in case["exists"]:
        (tmp_path / name).touch()
    hook = load_hook("block-sensitive-paths")
    assert bool(hook.bash_blocked_target(case["command"], str(tmp_path))) is case["blocked"]


PLACEHOLDER_READS_ACROSS_LINES = [
    ("echo start\ncat .env.example \\\n  notes.txt", "echo start; cat .env.example notes.txt"),
    ("if true; then\ncat .env.example\nfi", "if true; then cat .env.example; fi"),
    ("echo $(date)\ncat .env.example", "echo $(date); cat .env.example"),
]


@pytest.mark.parametrize(("multi_line", "one_line"), PLACEHOLDER_READS_ACROSS_LINES)
def test_a_placeholder_read_proceeds_on_one_line(multi_line, one_line, tmp_path):
    assert not load_hook("block-sensitive-paths").bash_blocked_target(one_line, str(tmp_path))


@pytest.mark.parametrize(
    ("multi_line", "one_line"),
    [
        PLACEHOLDER_READS_ACROSS_LINES[0],
        PLACEHOLDER_READS_ACROSS_LINES[1],
        PLACEHOLDER_READS_ACROSS_LINES[2],
    ],
)
def test_a_placeholder_read_across_lines_reaches_its_one_line_verdict(multi_line, one_line, tmp_path):
    assert not load_hook("block-sensitive-paths").bash_blocked_target(multi_line, str(tmp_path))


@pytest.mark.parametrize(
    ("command", "with_cwd"),
    [
        ("echo x > $DIR/secrets.txt", True),
        ("echo x >> ./$(x)/secrets.txt", True),
        ("echo x > secrets.txt", False),
    ],
)
def test_an_output_target_the_lexer_cannot_resolve_is_judged_as_a_write(command, with_cwd, tmp_path):
    hook = load_hook("block-sensitive-paths")
    assert hook.bash_blocked_target(command, str(tmp_path) if with_cwd else None)
