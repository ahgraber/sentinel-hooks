"""Validate the deployed Claude configurations with Claude itself."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)
SETTINGS_PATHS = sorted(REPO_ROOT.glob("users/*/home-manager/claude/settings*.json"))


def _settings_id(settings_path: Path) -> str:
    user = settings_path.parents[2].name
    return f"{user}/{settings_path.name}"


def test_claude_configs_are_discovered() -> None:
    assert SETTINGS_PATHS, "found no deployed Claude settings files to validate"


@pytest.mark.parametrize("settings_path", SETTINGS_PATHS, ids=_settings_id)
def test_claude_config_is_valid(settings_path: Path, tmp_path: Path) -> None:
    claude_config_dir = tmp_path / "claude-config"
    claude_config_dir.mkdir()
    shutil.copyfile(settings_path, claude_config_dir / "settings.json")

    env = os.environ.copy()
    env["CLAUDE_CONFIG_DIR"] = str(claude_config_dir)
    result = subprocess.run(
        ["claude", "doctor"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=30,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "Invalid settings" not in output, output
