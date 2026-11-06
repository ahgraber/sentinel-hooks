"""The Codex hook installer: it writes the plugin's Codex registration into the user's hook file.

Each case installs a copy of the plugin in a Codex plugin cache under a temporary
`CODEX_HOME` and runs the installer from that copy, as a user would.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from conftest import REPO_ROOT
import pytest

PLUGIN_DIR = REPO_ROOT / "plugins" / "sentinel"
REGISTRATION = json.loads((PLUGIN_DIR / "harnesses" / "codex" / "hooks.json").read_text())
USER_HOOK = {"type": "command", "command": "echo user-hook"}


def install_plugin(codex_home: Path, version: str = "0.1.0") -> Path:
    """Copy the plugin where Codex installs it, and return the copy's root."""
    root = codex_home / "plugins" / "cache" / "sentinel-hooks" / "sentinel" / version
    shutil.copytree(PLUGIN_DIR, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def run_installer(plugin_root: Path, codex_home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    installer = plugin_root / "harnesses" / "codex" / "install-hooks.py"
    return subprocess.run(
        [sys.executable, str(installer), *args],
        env={"CODEX_HOME": str(codex_home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def commands(hooks_file: Path) -> list[str]:
    hooks = json.loads(hooks_file.read_text())["hooks"]
    return [handler["command"] for groups in hooks.values() for group in groups for handler in group["hooks"]]


def write_user_hooks(codex_home: Path) -> Path:
    hooks_file = codex_home / "hooks.json"
    hooks_file.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": [USER_HOOK]}]}}))
    return hooks_file


@pytest.fixture
def codex_home(tmp_path: Path) -> Path:
    home = tmp_path / ".codex"
    home.mkdir()
    return home


def test_install_writes_the_registration_from_the_installed_copy(codex_home: Path) -> None:
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    written = json.loads((codex_home / "hooks.json").read_text())["hooks"]
    assert {event: [group.get("matcher") for group in groups] for event, groups in written.items()} == {
        event: [group.get("matcher") for group in groups] for event, groups in REGISTRATION["hooks"].items()
    }
    installed = commands(codex_home / "hooks.json")
    assert len(installed) == sum(len(group["hooks"]) for groups in REGISTRATION["hooks"].values() for group in groups)
    assert all(f"{plugin_root}/hooks/" in command for command in installed)
    assert not any("${PLUGIN_ROOT}" in command for command in installed)


def test_install_and_uninstall_keep_the_users_own_hooks(codex_home: Path) -> None:
    hooks_file = write_user_hooks(codex_home)
    plugin_root = install_plugin(codex_home)

    run_installer(plugin_root, codex_home)
    assert USER_HOOK["command"] in commands(hooks_file)

    result = run_installer(plugin_root, codex_home, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert commands(hooks_file) == [USER_HOOK["command"]]


def test_a_later_install_replaces_the_earlier_entries(codex_home: Path) -> None:
    old_root = install_plugin(codex_home, "0.0.9")
    run_installer(old_root, codex_home)
    shutil.rmtree(old_root)
    new_root = install_plugin(codex_home, "0.1.0")

    run_installer(new_root, codex_home)

    installed = commands(codex_home / "hooks.json")
    assert not any("/0.0.9/" in command for command in installed)
    assert len(installed) == sum(len(group["hooks"]) for groups in REGISTRATION["hooks"].values() for group in groups)


def test_the_installer_refuses_to_run_outside_a_plugin_install_location(codex_home: Path) -> None:
    hooks_file = write_user_hooks(codex_home)
    before = hooks_file.read_text()

    result = run_installer(PLUGIN_DIR, codex_home)

    assert result.returncode != 0
    assert "plugin install location" in result.stderr
    assert hooks_file.read_text() == before


def test_an_unreadable_hook_file_is_reported_and_left_unchanged(codex_home: Path) -> None:
    hooks_file = codex_home / "hooks.json"
    hooks_file.write_text("{ not json")
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert str(hooks_file) in result.stderr
    assert hooks_file.read_text() == "{ not json"


def test_a_written_entry_refuses_with_the_installer_command_when_its_hook_is_missing(codex_home: Path) -> None:
    plugin_root = install_plugin(codex_home)
    hook = plugin_root / "hooks" / "block-leaks.py"
    run_installer(plugin_root, codex_home)
    entry = next(command for command in commands(codex_home / "hooks.json") if str(hook) in command)

    hook.write_text("#!/bin/sh\necho stand-in ran\n")
    present = subprocess.run(["/bin/sh", "-c", entry], capture_output=True, text=True, check=False)
    hook.unlink()
    missing = subprocess.run(["/bin/sh", "-c", entry], capture_output=True, text=True, check=False)

    assert present.returncode == 0
    assert present.stdout == "stand-in ran\n"
    assert missing.returncode == 2
    assert "install-hooks.py" in missing.stderr
    assert str(hook) in missing.stderr
