"""Every hook command wired into a deployed Claude settings file must resolve.

A settings entry naming a hook that does not exist is fail-open: the command
cannot run, so the check it was protecting silently stops happening. Nothing
about the deployed JSON is type-checked, so a rename or typo is otherwise caught
only by noticing the absence of a hook that never announces itself.
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
HOOKS_DIR = REPO_ROOT / "modules" / "home" / "apps" / "claude" / "hooks"
SETTINGS_FILES = sorted(REPO_ROOT.glob("users/*/home-manager/claude/settings*.json"))

# Matches the deployed path in a command string, e.g.
# "uv run --script ~/.claude/hooks/block-secrets.py" -> "block-secrets.py"
HOOK_REFERENCE_RE = re.compile(r"~/\.claude/hooks/([A-Za-z0-9._-]+)")


def _hook_commands(settings_path: Path) -> list[tuple[str, str]]:
    """Return (event, command) for every hook command in a settings file."""
    hooks = json.loads(settings_path.read_text()).get("hooks", {})
    return [
        (event, hook["command"])
        for event, matchers in hooks.items()
        for matcher in matchers
        for hook in matcher.get("hooks", [])
        if isinstance(hook.get("command"), str)
    ]


def test_settings_files_are_discovered() -> None:
    """Guards the glob itself: an empty set would make every test below vacuous."""
    assert SETTINGS_FILES, "found no deployed Claude settings files to check"


@pytest.mark.parametrize(
    "settings_path",
    SETTINGS_FILES,
    ids=lambda p: f"{p.parent.parent.parent.name}/{p.name}",
)
def test_wired_hook_commands_exist(settings_path: Path) -> None:
    missing = [
        (event, name)
        for event, command in _hook_commands(settings_path)
        for name in HOOK_REFERENCE_RE.findall(command)
        if not (HOOKS_DIR / name).exists()
    ]

    assert not missing, (
        f"{settings_path.relative_to(REPO_ROOT)} wires hooks that do not exist in "
        f"{HOOKS_DIR.relative_to(REPO_ROOT)}: {missing}"
    )
