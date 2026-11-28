"""The Codex hook installer: it writes the plugin's Codex registration into the user's hook file.

Each case installs a copy of the plugin in a Codex plugin cache under a temporary
`CODEX_HOME` and runs the installer from that copy, as a user would.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
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
    codex_home.mkdir(parents=True, exist_ok=True)
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
    """Validates: CodexHookInstallKeepsTheUsersHooks, InstallKeepsTheUsersHooks."""
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


def test_a_user_group_with_no_handlers_is_kept(codex_home: Path) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, InstallKeepsTheUsersHooks."""
    hooks_file = codex_home / "hooks.json"
    empty = {"matcher": "^Edit$", "hooks": []}
    hooks_file.write_text(json.dumps({"hooks": {"PostToolUse": [empty]}}))
    plugin_root = install_plugin(codex_home)

    run_installer(plugin_root, codex_home)
    result = run_installer(plugin_root, codex_home, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert json.loads(hooks_file.read_text())["hooks"] == {"PostToolUse": [empty]}


@pytest.mark.parametrize(
    "contents",
    [
        "{ not json",
        '{"hooks": {"PreToolUse": "echo"}}',
        '{"hooks": {"PreToolUse": [{"hooks": ["echo"]}]}}',
        '{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": 5}]}]}}',
        b'{"hooks": {}, "note": "\xff"}',
        '{"hooks": {}, "note": ' + "[" * 100_000 + "]" * 100_000 + "}",
        '{"hooks": {}, "note": NaN}',
        '{"hooks": {}, "note": 1e400}',
    ],
    ids=[
        "not json",
        "event not a list",
        "handler not an object",
        "command not text",
        "not utf-8",
        "nested too deeply",
        "not a number",
        "outside the range of a double",
    ],
)
def test_an_unreadable_hook_file_is_reported_and_left_unchanged(codex_home: Path, contents: str | bytes) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, UnreadableHookFileIsLeftUnchanged."""
    hooks_file = codex_home / "hooks.json"
    original = contents if isinstance(contents, bytes) else contents.encode()
    hooks_file.write_bytes(original)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert str(hooks_file) in result.stderr
    assert "Traceback" not in result.stderr
    assert hooks_file.read_bytes() == original


def test_a_registration_in_the_copy_that_does_not_parse_is_reported_and_the_hook_file_left_unchanged(
    codex_home: Path,
) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks."""
    hooks_file = write_user_hooks(codex_home)
    original = hooks_file.read_bytes()
    plugin_root = install_plugin(codex_home)
    registration = plugin_root / "harnesses" / "codex" / "hooks.json"
    registration.write_text('{"hooks": ')

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert str(registration) in result.stderr
    assert "Traceback" not in result.stderr
    assert hooks_file.read_bytes() == original


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


def test_a_linked_hook_file_is_written_through_the_link(codex_home: Path, tmp_path: Path) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, LinkedHookFileKeepsItsLink."""
    source = write_user_hooks(tmp_path / "dotfiles")
    link = codex_home / "hooks.json"
    link.symlink_to(source)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    assert link.readlink() == source
    assert USER_HOOK["command"] in commands(source)
    assert len(commands(source)) > 1
    assert str(source) in result.stdout

    uninstalled = run_installer(plugin_root, codex_home, "--uninstall")

    assert uninstalled.returncode == 0, uninstalled.stderr
    assert link.readlink() == source
    assert commands(source) == [USER_HOOK["command"]]


def test_a_chain_of_relative_links_is_followed_to_its_end(codex_home: Path, tmp_path: Path) -> None:
    source = write_user_hooks(tmp_path / "dotfiles")
    (tmp_path / "middle.json").symlink_to(Path("dotfiles") / "hooks.json")
    link = codex_home / "hooks.json"
    link.symlink_to(Path("..") / "middle.json")
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    assert (tmp_path / "middle.json").is_symlink()
    assert len(commands(source)) > 1


def test_the_hook_file_keeps_its_permissions(codex_home: Path) -> None:
    hooks_file = write_user_hooks(codex_home)
    hooks_file.chmod(0o640)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    assert len(commands(hooks_file)) > 1
    assert stat.S_IMODE(hooks_file.stat().st_mode) == 0o640


@pytest.mark.parametrize(("umask", "mode"), [(0o027, 0o640), (0o002, 0o664)])
def test_a_new_hook_file_gets_the_umask_mode_and_no_staged_file_remains(
    codex_home: Path, umask: int, mode: int
) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, NewHookFileGetsTheUsersDefaultPermissions."""
    plugin_root = install_plugin(codex_home)
    previous = os.umask(umask)
    try:
        result = run_installer(plugin_root, codex_home)
    finally:
        os.umask(previous)

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE((codex_home / "hooks.json").stat().st_mode) == mode
    assert not [name for name in os.listdir(codex_home) if name.startswith(".hooks.json")]


def test_a_run_that_changes_nothing_succeeds_on_a_read_only_file(codex_home: Path) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, RunThatChangesNothingSucceedsOnAReadOnlyFile."""
    hooks_file = write_user_hooks(codex_home)
    original = hooks_file.read_bytes()
    hooks_file.chmod(0o400)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert "Nothing changed" in result.stdout
    assert hooks_file.read_bytes() == original


def test_a_second_install_from_the_same_copy_succeeds_on_a_read_only_file(codex_home: Path) -> None:
    write_user_hooks(codex_home)
    plugin_root = install_plugin(codex_home)
    run_installer(plugin_root, codex_home)
    hooks_file = codex_home / "hooks.json"
    installed = hooks_file.read_bytes()
    hooks_file.chmod(0o400)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    assert "Nothing changed" in result.stdout
    assert hooks_file.read_bytes() == installed


@pytest.mark.parametrize(
    "inside_a_sentinel_group", [False, True], ids=["after-sentinels-groups", "inside-a-sentinel-group"]
)
def test_a_reinstall_keeps_a_user_hook_placed_among_sentinels(codex_home: Path, inside_a_sentinel_group: bool) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, ReinstallKeepsTheOrderOfTheHooks."""
    plugin_root = install_plugin(codex_home)
    run_installer(plugin_root, codex_home)
    hooks_file = codex_home / "hooks.json"
    data = json.loads(hooks_file.read_text())
    if inside_a_sentinel_group:
        data["hooks"]["PreToolUse"][0]["hooks"].insert(0, USER_HOOK)
    else:
        data["hooks"]["PreToolUse"].append({"matcher": "^Bash$", "hooks": [USER_HOOK]})
    hooks_file.write_text(json.dumps(data, indent=2) + "\n")
    ordered = hooks_file.read_bytes()
    hooks_file.chmod(0o400)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    assert "Nothing changed" in result.stdout
    assert hooks_file.read_bytes() == ordered


def test_a_reinstall_keeps_sentinels_groups_in_the_order_the_user_gave_them(codex_home: Path) -> None:
    """Validates: ReinstallKeepsTheOrderOfTheHooks."""
    plugin_root = install_plugin(codex_home)
    run_installer(plugin_root, codex_home)
    hooks_file = codex_home / "hooks.json"
    data = json.loads(hooks_file.read_text())
    groups = data["hooks"]["PreToolUse"]
    group_with_handlers = next(group for group in groups if len(group["hooks"]) > 1)
    group_with_handlers["hooks"].reverse()
    data["hooks"]["PreToolUse"] = [groups[-1], {"matcher": "^Bash$", "hooks": [USER_HOOK]}, *groups[:-1]]
    hooks_file.write_text(json.dumps(data, indent=2) + "\n")
    ordered = hooks_file.read_bytes()
    hooks_file.chmod(0o400)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    assert "Nothing changed" in result.stdout
    assert hooks_file.read_bytes() == ordered


def test_an_uninstall_with_no_hook_file_creates_none(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert "Nothing changed" in result.stdout
    assert not (codex_home / "hooks.json").exists()


def test_an_event_the_user_left_empty_is_kept(codex_home: Path) -> None:
    hooks_file = codex_home / "hooks.json"
    hooks_file.write_text(json.dumps({"hooks": {"Stop": [], "PreToolUse": [{"hooks": [USER_HOOK]}]}}))
    original = hooks_file.read_bytes()
    hooks_file.chmod(0o400)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert hooks_file.read_bytes() == original


def test_an_uninstall_that_cannot_write_advises_removing_the_hooks(codex_home: Path) -> None:
    write_user_hooks(codex_home)
    plugin_root = install_plugin(codex_home)
    run_installer(plugin_root, codex_home)
    hooks_file = codex_home / "hooks.json"
    installed = hooks_file.read_bytes()
    hooks_file.chmod(0o400)

    result = run_installer(plugin_root, codex_home, "--uninstall")

    assert result.returncode != 0
    assert "remove Sentinel's hooks" in result.stderr
    assert hooks_file.read_bytes() == installed


def test_a_hook_file_in_a_directory_that_cannot_be_searched_is_reported(codex_home: Path, tmp_path: Path) -> None:
    plugin_root = install_plugin(codex_home)
    closed = tmp_path / "closed"
    write_user_hooks(closed)
    closed.chmod(0o600)
    try:
        result = run_installer(plugin_root, closed)
    finally:
        closed.chmod(0o700)

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert str(closed / "hooks.json") in result.stderr


def test_a_staged_file_is_removed_when_the_rename_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location(
        "install_hooks", PLUGIN_DIR / "harnesses" / "codex" / "install-hooks.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)

    def fail(self: Path, target: Path) -> Path:
        raise OSError(errno.EXDEV, "rename refused")

    monkeypatch.setattr(Path, "replace", fail)

    with pytest.raises(SystemExit, match="rename refused"):
        installer.write_hook_file(tmp_path / "hooks.json", {"hooks": {}}, "advice")
    assert list(tmp_path.iterdir()) == []


def test_a_read_only_hook_file_is_reported_and_left_unchanged(codex_home: Path) -> None:
    hooks_file = write_user_hooks(codex_home)
    original = hooks_file.read_bytes()
    hooks_file.chmod(0o400)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert str(hooks_file) in result.stderr
    assert "add Sentinel's hooks" in result.stderr
    assert hooks_file.read_bytes() == original


@pytest.mark.parametrize(
    ("contents", "key"),
    [
        pytest.param(
            '{"hooks": {"PreToolUse": [{"hooks": []}], "PreToolUse": [{"hooks": []}]}}', "PreToolUse", id="event"
        ),
        pytest.param(
            '{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "a", "command": "b"}]}]}}',
            "command",
            id="handler",
        ),
    ],
)
def test_a_hook_file_with_a_repeated_key_is_reported_and_left_unchanged(
    codex_home: Path, contents: str, key: str
) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, HookFileThatNamesAKeyTwiceIsLeftUnchanged."""
    hooks_file = codex_home / "hooks.json"
    hooks_file.write_text(contents)
    original = hooks_file.read_bytes()
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert key in result.stderr
    assert str(hooks_file) in result.stderr
    assert hooks_file.read_bytes() == original


def test_a_file_at_the_staging_name_is_not_followed(codex_home: Path, tmp_path: Path) -> None:
    hooks_file = write_user_hooks(codex_home)
    other = tmp_path / "other"
    other.write_text("keep")
    (codex_home / "hooks.json.tmp").symlink_to(other)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode == 0, result.stderr
    assert other.read_text() == "keep"
    assert not hooks_file.is_symlink()
    assert USER_HOOK["command"] in commands(hooks_file)


def test_a_link_loop_is_reported_as_one(codex_home: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    first.symlink_to(second)
    second.symlink_to(first)
    (codex_home / "hooks.json").symlink_to(first)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert "form a loop" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_link_to_a_missing_file_is_reported_and_left_unchanged(codex_home: Path, tmp_path: Path) -> None:
    missing = tmp_path / "dotfiles" / "hooks.json"
    link = codex_home / "hooks.json"
    link.symlink_to(missing)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert str(missing) in result.stderr
    assert "Traceback" not in result.stderr
    assert link.readlink() == missing
    assert not missing.parent.exists()


def test_a_link_chain_to_a_missing_file_names_the_missing_file(codex_home: Path, tmp_path: Path) -> None:
    """Validates: CodexHookInstallKeepsTheUsersHooks, LinkChainThatEndsAtNoFileNamesTheMissingFile."""
    missing = tmp_path / "missing.json"
    middle = tmp_path / "middle.json"
    middle.symlink_to(missing)
    (codex_home / "hooks.json").symlink_to(middle)
    plugin_root = install_plugin(codex_home)

    result = run_installer(plugin_root, codex_home)

    assert result.returncode != 0
    assert f"links to {missing}, which does not exist" in result.stderr


def test_a_link_target_that_cannot_be_reached_reports_the_cause(codex_home: Path, tmp_path: Path) -> None:
    source = write_user_hooks(tmp_path / "closed")
    (codex_home / "hooks.json").symlink_to(source)
    plugin_root = install_plugin(codex_home)
    source.parent.chmod(0)
    try:
        result = run_installer(plugin_root, codex_home)
    finally:
        source.parent.chmod(0o700)

    assert result.returncode != 0
    assert "Permission denied" in result.stderr
    assert "does not exist" not in result.stderr


def test_a_hook_file_that_cannot_be_written_is_reported_and_left_unchanged(codex_home: Path, tmp_path: Path) -> None:
    source = write_user_hooks(tmp_path / "store")
    original = source.read_bytes()
    (codex_home / "hooks.json").symlink_to(source)
    plugin_root = install_plugin(codex_home)
    source.parent.chmod(0o500)
    try:
        result = run_installer(plugin_root, codex_home)
    finally:
        source.parent.chmod(0o700)

    assert result.returncode != 0
    assert str(source) in result.stderr
    assert "Traceback" not in result.stderr
    assert source.read_bytes() == original
