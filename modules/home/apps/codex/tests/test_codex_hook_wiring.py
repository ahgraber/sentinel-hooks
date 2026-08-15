"""Every hook command wired into a deployed Codex hooks.json must resolve.

Codex gates hooks on a trust-on-first-use hash of the command string, so a
command naming a missing script still prompts for trust and then fails at exec
time — the check silently stops running rather than announcing itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)
HOOKS_DIR = REPO_ROOT / "modules" / "home" / "apps" / "codex" / "hooks"
HOOKS_FILES = sorted(REPO_ROOT.glob("users/*/home-manager/codex/hooks.json"))

HOOK_REFERENCE_RE = re.compile(r"~/\.codex/hooks/([A-Za-z0-9._-]+)")


def _hook_commands(hooks_path: Path) -> list[tuple[str, str]]:
    """Return (event, command) for every hook command in a hooks.json."""
    hooks = json.loads(hooks_path.read_text()).get("hooks", {})
    return [
        (event, hook["command"])
        for event, matchers in hooks.items()
        for matcher in matchers
        for hook in matcher.get("hooks", [])
        if isinstance(hook.get("command"), str)
    ]


def test_hooks_files_are_discovered() -> None:
    """Guards the glob itself: an empty set would make every test below vacuous."""
    assert HOOKS_FILES, "found no deployed Codex hooks.json files to check"


@pytest.mark.parametrize(
    "hooks_path", HOOKS_FILES, ids=lambda p: p.parent.parent.parent.name
)
def test_wired_hook_commands_exist(hooks_path: Path) -> None:
    missing = [
        (event, name)
        for event, command in _hook_commands(hooks_path)
        for name in HOOK_REFERENCE_RE.findall(command)
        if not (HOOKS_DIR / name).exists()
    ]

    assert not missing, (
        f"{hooks_path.relative_to(REPO_ROOT)} wires hooks that do not exist in "
        f"{HOOKS_DIR.relative_to(REPO_ROOT)}: {missing}"
    )
