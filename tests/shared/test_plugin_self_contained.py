"""Validates: ThePluginIsSelfContained, by running each hook from a copy of the plugin directory.

A harness installs only `plugins/sentinel/`, so a hook that reads or runs a file
outside it decides differently, or fails, in every installed copy.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from guarded_paths import repo_root_of
from hermetic import HOOKS_DIR, REPO_ROOT, load_hook
import pytest
from verdict_conformance import decode

PLUGIN_DIR = HOOKS_DIR.parent

# Every hook that decides a tool call.
HOOKS = (
    "hooks/block-dangerous-bash.sh",
    "hooks/bash-command-validator.sh",
    "hooks/block-sensitive-paths.py",
    "hooks/block-hook-tampering.py",
    "hooks/block-destructive-ops.py",
    "hooks/block-leaks.py",
    "hooks/refuse-unlisted-tools.py",
)
# Assembled at run time so no secret-shaped literal sits in the file.
TOKEN = "ghp_" + "R7kq2Lm9Xv4Bn8Tw3Yc6Pd1Hs5Jf0Ga2Ke7Q"
CALLS = {
    "ordinary command": ("Bash", {"command": "ls"}),
    "destructive command": ("Bash", {"command": "rm -rf ~"}),
    "credential read": ("Bash", {"command": "cat ~/.ssh/id_rsa"}),
    "validator rule": ("Bash", {"command": "python3 script.py"}),
    "settings write": ("Write", {"file_path": "~/.claude/settings.json", "content": "{}"}),
    "dotenv read": ("Read", {"file_path": ".env"}),
    "credential content": ("Write", {"file_path": "notes.txt", "content": f"token {TOKEN}"}),
    "unlisted tool": ("FrobnicateEverything", {}),
}
# The harness entry points that reach the hooks.
HARNESS_CALLS = {
    "copilot adapter": (
        "harnesses/copilot/copilot-vscode-hook-adapter.py",
        ["block-hook-tampering.py"],
        {"tool_name": "run_in_terminal", "tool_input": {"command": "rm -rf ~/.claude/plugins"}},
    ),
    "pi dispatcher": (
        "harnesses/pi/hook-dispatch.py",
        [],
        {"tool_name": "bash", "tool_input": {"command": "rm -rf ~/.claude/plugins"}},
    ),
}


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    copy = tmp_path_factory.mktemp("install") / "sentinel"
    shutil.copytree(PLUGIN_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    assert repo_root_of(str(copy)) is None
    return copy


@pytest.fixture(scope="module")
def session(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    """A working directory and environment both copies run in, outside any checkout."""
    root = tmp_path_factory.mktemp("session")
    (root / "home").mkdir()
    (root / "work").mkdir()
    env = {**os.environ, "HOME": str(root / "home"), "AI_HOOK_AGENT": "claude"}
    return root / "work", env


def decision(script: Path, args: list[str], payload: dict, session: tuple[Path, dict[str, str]]) -> str:
    cwd, env = session
    interpreter = ["bash"] if script.suffix == ".sh" else [sys.executable]
    result = subprocess.run(
        [*interpreter, str(script), *args],
        input=json.dumps({**payload, "cwd": str(cwd)}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=60,
        check=False,
    )
    assert result.returncode in (0, 1, 2), result.stderr
    return decode(result.returncode, result.stdout)


@pytest.mark.parametrize("call", CALLS)
@pytest.mark.parametrize("hook", HOOKS)
def test_each_hook_decides_in_a_copy_as_in_the_checkout(installed, session, hook, call) -> None:
    tool_name, tool_input = CALLS[call]
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    assert decision(installed / hook, [], payload, session) == decision(PLUGIN_DIR / hook, [], payload, session)


def test_no_sentinel_file_matches_a_name_pattern() -> None:
    """Validates: NoSentinelFileMatchesANamePattern.

    No exemption covers Sentinel's own files, so a file named like a secret
    would be refused in a checkout and in every installed copy.
    """
    is_named_for_secrets = load_hook("block-sensitive-paths").is_named_for_secrets
    listed = subprocess.run(
        ["git", "ls-files", "plugins", "extensions", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert listed
    assert [file for file in listed if is_named_for_secrets(str(REPO_ROOT / file))] == []


@pytest.mark.parametrize("entry", HARNESS_CALLS)
def test_each_harness_entry_decides_in_a_copy_as_in_the_checkout(installed, session, entry) -> None:
    script, args, payload = HARNESS_CALLS[entry]
    cwd, env = session
    env = {key: value for key, value in env.items() if key != "AI_HOOK_AGENT"}
    expected = decision(PLUGIN_DIR / script, args, payload, (cwd, env))
    assert expected in {"block", "ask"}
    assert decision(installed / script, args, payload, (cwd, env)) == expected
