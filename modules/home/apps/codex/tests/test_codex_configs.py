"""Validate the deployed Codex configurations with Codex itself."""

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
CONFIG_PATHS = sorted(REPO_ROOT.glob("users/*/home-manager/codex/config*.toml"))


def _config_id(config_path: Path) -> str:
    user = config_path.parents[2].name
    return f"{user}/{config_path.name}"


def test_codex_configs_are_discovered() -> None:
    assert CONFIG_PATHS, "found no deployed Codex config files to validate"


@pytest.mark.parametrize("config_path", CONFIG_PATHS, ids=_config_id)
def test_codex_config_is_valid(config_path: Path, tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    shutil.copyfile(config_path, codex_home / "config.toml")

    hooks_path = config_path.parent / "hooks.json"
    if hooks_path.is_file():
        shutil.copyfile(hooks_path, codex_home / "hooks.json")

    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    result = subprocess.run(
        ["codex", "--strict-config", "mcp-server"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
