"""Secret material must be refused by every read-gating layer, for every user.

The permission rules and the OS sandbox are the boundary and the hooks are
defence in depth, so a floor entry missing from one layer is a real hole.
Coverage is judged against concrete representative paths, so a glob that looks
right but does not match — `**/secrets/**` against a store spelled `secrets.d` —
fails here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import tomllib
from conformance import (
    CLAUDE_SETTINGS,
    CODEX_CONFIGS,
    REPO_ROOT,
    glob_covers,
    load_manifest,
)

READ_RULE_RE = re.compile(r"^Read\((?P<pattern>.+)\)$")

_MANIFEST = load_manifest()

SECRET_FLOOR = tuple(_MANIFEST["credentials"]["paths"]) + tuple(
    _MANIFEST["secret-floor"]["paths"]
)


def claude_read_deny_patterns(settings_path: Path) -> list[str]:
    permissions = json.loads(settings_path.read_text()).get("permissions", {})
    return [
        match.group("pattern")
        for rule in permissions.get("deny", [])
        if (match := READ_RULE_RE.match(rule))
    ]


def claude_sandbox_deny(settings_path: Path) -> list[str]:
    sandbox = json.loads(settings_path.read_text()).get("sandbox", {})
    return sandbox.get("filesystem", {}).get("denyRead", [])


def codex_deny_paths(config_path: Path) -> list[str]:
    filesystem = tomllib.loads(config_path.read_text())["permissions"][
        "guarded_workspace"
    ]["filesystem"]
    return [path for path, mode in filesystem.items() if mode == "deny"]


def test_configuration_files_are_discovered() -> None:
    """Guards the globs themselves: an empty set would make every test vacuous."""
    assert CLAUDE_SETTINGS, "found no Claude settings files to check"
    assert CODEX_CONFIGS, "found no Codex configuration files to check"


@pytest.mark.parametrize("floor_path", SECRET_FLOOR)
@pytest.mark.parametrize(
    "settings_path", CLAUDE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
)
def test_claude_permission_layer_refuses_the_floor(
    settings_path: Path, floor_path: str
) -> None:
    patterns = claude_read_deny_patterns(settings_path)
    assert any(glob_covers(pattern, floor_path) for pattern in patterns), (
        f"{settings_path.relative_to(REPO_ROOT)} has no Read deny covering {floor_path}"
    )


@pytest.mark.parametrize("floor_path", SECRET_FLOOR)
@pytest.mark.parametrize(
    "settings_path", CLAUDE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
)
def test_claude_sandbox_layer_refuses_the_floor(
    settings_path: Path, floor_path: str
) -> None:
    entries = claude_sandbox_deny(settings_path)
    assert any(glob_covers(entry, floor_path) for entry in entries), (
        f"{settings_path.relative_to(REPO_ROOT)} has no sandbox denyRead "
        f"covering {floor_path}"
    )


@pytest.mark.parametrize("floor_path", SECRET_FLOOR)
@pytest.mark.parametrize(
    "config_path", CODEX_CONFIGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
)
def test_codex_sandbox_refuses_the_floor(config_path: Path, floor_path: str) -> None:
    entries = codex_deny_paths(config_path)
    assert any(glob_covers(entry, floor_path) for entry in entries), (
        f"{config_path.relative_to(REPO_ROOT)} has no deny covering {floor_path}"
    )
