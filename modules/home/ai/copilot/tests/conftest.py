"""Shared fixtures and helpers for Copilot hook tests."""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

AGENT_HOOKS_DIR = Path(__file__).parent.parent / "hooks"
SHARED_HOOKS_DIR = Path(__file__).parents[2] / "shared" / "hooks"

# The adapter declares the agent this way, so the suite exercises Copilot's encodings.
HOOK_ENV = {**os.environ, "AI_HOOK_AGENT": "copilot"}


def resolve_hook(name: str) -> Path:
    """Resolve a hook filename, preferring this agent's own copy over the shared one."""
    own = AGENT_HOOKS_DIR / name
    return own if own.is_file() else SHARED_HOOKS_DIR / name


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
    """Run a hook as a subprocess with the given tool_name and tool_input."""
    hook_path = resolve_hook(hook_filename)

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
        check=False,
        timeout=timeout,
        env=HOOK_ENV if env is None else env,
    )
    return HookResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def assert_allowed(result: HookResult) -> None:
    assert result.exit_code == 0, (
        f"Expected allow (exit 0), got exit {result.exit_code}.\nstderr: {result.stderr}"
    )
    assert "permissionDecision" not in result.stdout, (
        f"Expected no approval JSON, got: {result.stdout}"
    )


def assert_blocked(result: HookResult, message_substring: str = "") -> None:
    assert result.exit_code == 2, (
        f"Expected block (exit 2), got exit {result.exit_code}.\nstderr: {result.stderr}\nstdout: {result.stdout}"
    )
    if message_substring:
        assert message_substring.lower() in result.stderr.lower(), (
            f"Expected '{message_substring}' in stderr, got: {result.stderr}"
        )


_AI_BLOCK_CHECKS = [
    ("section delimiter", "---"),
    ("AI INSTRUCTIONS header", "ai instructions:"),
    ("workaround prohibition", "do not attempt"),
    ("current-task directive", "your current task"),
    ("intended-step directive", "your intended step"),
    ("what-was-blocked directive", "what was blocked"),
    ("user-action directive", "how the user can help"),
]


def assert_block_contract(result: HookResult, message_substring: str = "") -> None:
    """Assert exit 2 and the standard AI guidance block contract."""
    assert_blocked(result, message_substring)
    stderr_lower = result.stderr.lower()
    for label, needle in _AI_BLOCK_CHECKS:
        assert needle.lower() in stderr_lower, (
            f"Block contract violation — missing {label}.\nstderr: {result.stderr}"
        )


def assert_ask(result: HookResult, reason_substring: str = "") -> None:
    """Assert exit 0 and the wrapped ask JSON the VS Code surface honors."""
    assert result.exit_code == 0, (
        f"Expected ask (exit 0), got exit {result.exit_code}.\nstderr: {result.stderr}"
    )
    data = json.loads(result.stdout)
    decision = data["hookSpecificOutput"]["permissionDecision"]
    assert decision == "ask", f"Expected permissionDecision 'ask', got '{decision}'"
    if reason_substring:
        reason = data["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason_substring.lower() in reason.lower(), (
            f"Expected '{reason_substring}' in reason, got: {reason}"
        )
