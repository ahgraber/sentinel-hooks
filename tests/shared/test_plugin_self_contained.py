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


@pytest.mark.parametrize("target", ["plugins/sentinel/hooks/guarded_paths.py", "extensions/pi/extension.ts"])
def test_each_copy_gates_its_own_directory(installed, session, target) -> None:
    """Validates: ThePluginIsSelfContained EachCopyGatesItsOwnDirectory."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(REPO_ROOT / target), "content": "x"},
    }
    hook = "hooks/block-hook-tampering.py"
    assert decision(PLUGIN_DIR / hook, [], payload, session) == "ask"
    assert decision(installed / hook, [], payload, session) == "allow"


def test_no_sentinel_file_matches_a_name_pattern() -> None:
    """Validates: NoSentinelFileMatchesANamePattern.

    No exemption covers Sentinel's own files, so a file named like a secret
    would be refused in a checkout and in every installed copy. A name that
    asks is refused too, on an agent that cannot show the question. The strong
    rules, such as `.env` and `*.pem`, refuse whatever the directory.
    """
    hook = load_hook("block-sensitive-paths")
    listed = subprocess.run(
        ["git", "ls-files", "plugins", "extensions", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert listed
    named = [str(REPO_ROOT / file) for file in listed]
    matched = [
        path for path in named if hook.is_zero_access(path) or hook.is_named_for_secrets(path) or hook.ask_reason(path)
    ]
    assert matched == []


def test_the_session_check_reports_in_a_copy_as_in_the_checkout(installed, tmp_path) -> None:
    """The session check reads its floor data and runs its policy check from the plugin directory."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"disableAllHooks": true}')
    session = (tmp_path, {**os.environ, "HOME": str(home), "AI_HOOK_AGENT": "claude"})

    def report(plugin: Path) -> str:
        cwd, env = session
        result = subprocess.run(
            ["bash", str(plugin / "hooks/session-tool-checks.sh")],
            input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(cwd)}),
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    expected = report(PLUGIN_DIR)
    assert "disableAllHooks" in expected
    assert report(installed) == expected


def test_the_git_baseline_reports_drift_in_a_copy_as_in_the_checkout(installed, tmp_path) -> None:
    """The baseline hook records HEAD at a prompt and reports a moved HEAD before the next tool call."""
    work = tmp_path / "work"
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Baseline Test\n\temail = baseline@example.invalid\n")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}
    env.pop("GIT_DIR", None)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=work, env=env, check=True, capture_output=True)

    def run(plugin: Path, stage: str, session_id: str) -> str:
        result = subprocess.run(
            ["bash", str(plugin / "hooks/git-baseline.sh"), stage],
            input=json.dumps({"session_id": session_id, "cwd": str(work)}),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    work.mkdir()
    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "first")
    for plugin, session_id in ((PLUGIN_DIR, "checkout"), (installed, "copy")):
        run(plugin, "init", session_id)
    git("commit", "-q", "--allow-empty", "-m", "second")

    expected = run(PLUGIN_DIR, "check", "checkout")
    assert "Git HEAD changed" in expected
    assert run(installed, "check", "copy") == expected


MARKER = "decided by the copy's stub"
# A refusal by exit status 2 with the reason on standard error, which every entry point reads.
STUB = f"import sys\nsys.stderr.write({MARKER!r})\nsys.exit(2)\n"
# Each entry point with its arguments and payload, the hook it finds next to itself, and the stub that replaces that hook in the copy.
ENTRIES_AND_HOOKS = {
    "copilot adapter": (*HARNESS_CALLS["copilot adapter"], "hooks/block-hook-tampering.py", STUB),
    # A call every real hook allows, so the stub's answer is the only refusal.
    "pi dispatcher": (
        "harnesses/pi/hook-dispatch.py",
        [],
        {"tool_name": "bash", "tool_input": {"command": "ls"}},
        "hooks/block-hook-tampering.py",
        STUB,
    ),
    "session tool checks": (
        "hooks/session-tool-checks.sh",
        [],
        {"hook_event_name": "SessionStart"},
        "hooks/session-policy-checks.py",
        f"print({MARKER!r})\n",
    ),
}


@pytest.mark.parametrize("entry", ENTRIES_AND_HOOKS)
def test_each_entry_point_runs_the_hooks_in_its_own_copy(tmp_path, session, entry) -> None:
    """Validates: HooksRunFromTheInstalledPlugin. A copy's entry point runs that copy's hook, not the checkout's."""
    script, args, payload, hook, stub = ENTRIES_AND_HOOKS[entry]
    copy = tmp_path / "sentinel"
    shutil.copytree(PLUGIN_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    (copy / hook).write_text(stub)
    cwd, env = session
    env = {key: value for key, value in env.items() if key != "AI_HOOK_AGENT"}
    interpreter = ["bash"] if script.endswith(".sh") else [sys.executable]

    result = subprocess.run(
        [*interpreter, str(copy / script), *args],
        input=json.dumps({**payload, "cwd": str(cwd)}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=60,
        check=False,
    )

    assert MARKER in result.stdout + result.stderr


@pytest.mark.parametrize("entry", HARNESS_CALLS)
def test_each_harness_entry_decides_in_a_copy_as_in_the_checkout(installed, session, entry) -> None:
    script, args, payload = HARNESS_CALLS[entry]
    cwd, env = session
    env = {key: value for key, value in env.items() if key != "AI_HOOK_AGENT"}
    expected = decision(PLUGIN_DIR / script, args, payload, (cwd, env))
    assert expected in {"block", "ask"}
    assert decision(installed / script, args, payload, (cwd, env)) == expected
