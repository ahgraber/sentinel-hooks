"""Shared fixtures and helpers for security hook tests."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"


@dataclass
class HookResult:
    exit_code: int
    stdout: str
    stderr: str


def run_hook(
    hook_filename: str,
    tool_name: str | None = None,
    tool_input: dict | None = None,
    *,
    stdin_text: str | None = None,
    env: dict | None = None,
    timeout: int = 10,
) -> HookResult:
    """Run a hook as a subprocess with the given tool_name and tool_input.

    For SessionStart hooks, pass stdin_text="" and omit tool_name/tool_input.
    """
    hook_path = HOOKS_DIR / hook_filename

    if hook_path.suffix == ".sh":
        cmd = ["bash", str(hook_path)]
    else:
        cmd = ["python3", str(hook_path)]

    if stdin_text is None:
        payload = {}
        if tool_name is not None:
            payload["tool_name"] = tool_name
        if tool_input is not None:
            payload["tool_input"] = tool_input
        stdin_text = json.dumps(payload)

    result = subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return HookResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def assert_allowed(result: HookResult) -> None:
    assert result.exit_code == 0, f"Expected allow (exit 0), got exit {result.exit_code}.\nstderr: {result.stderr}"
    assert "permissionDecision" not in result.stdout, f"Expected no ask JSON, got: {result.stdout}"


def assert_blocked(result: HookResult, message_substring: str = "") -> None:
    assert result.exit_code == 2, f"Expected block (exit 2), got exit {result.exit_code}.\nstderr: {result.stderr}\nstdout: {result.stdout}"
    if message_substring:
        assert message_substring.lower() in result.stderr.lower(), (
            f"Expected '{message_substring}' in stderr, got: {result.stderr}"
        )


def assert_ask(result: HookResult, reason_substring: str = "") -> None:
    assert result.exit_code == 0, f"Expected ask (exit 0), got exit {result.exit_code}.\nstderr: {result.stderr}"
    data = json.loads(result.stdout)
    decision = data["hookSpecificOutput"]["permissionDecision"]
    assert decision == "ask", f"Expected permissionDecision 'ask', got '{decision}'"
    if reason_substring:
        reason = data["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason_substring.lower() in reason.lower(), (
            f"Expected '{reason_substring}' in reason, got: {reason}"
        )


@pytest.fixture
def bash_hook():
    """Returns a callable that runs a hook with a Bash tool call."""
    def run(hook_filename: str, command: str) -> HookResult:
        return run_hook(hook_filename, "Bash", {"command": command})
    return run
