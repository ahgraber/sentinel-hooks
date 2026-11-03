"""Shared fixtures and helpers for Codex hook tests."""

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".specs").is_dir())
HOOKS_DIR = REPO_ROOT / "plugins" / "sentinel" / "hooks"


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
    hook_path = HOOKS_DIR / hook_filename

    cmd = ["bash", str(hook_path)] if hook_path.suffix == ".sh" else ["python3", str(hook_path)]

    if stdin_text is None:
        payload = {"cwd": str(Path.cwd())}
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
        env=env,
    )
    return HookResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def assert_allowed(result: HookResult) -> None:
    assert result.exit_code == 0, f"Expected allow (exit 0), got exit {result.exit_code}.\nstderr: {result.stderr}"
    assert "permissionDecision" not in result.stdout, f"Expected no approval JSON, got: {result.stdout}"


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
    ("current-task directive", "your current task"),
    ("intended-step directive", "your intended step"),
    ("what-was-blocked directive", "what was blocked"),
    ("user-action directive", "how the user can help"),
]

# A refusal closes with one instruction of two: stop where the policy refused
# the operation, retry where the classifier did not recognize the command and
# the message names commands that would work. Requiring the stop form of every
# refusal contradicts a message that lists accepted commands.
_CLOSING_INSTRUCTIONS = {
    "stop": "do not attempt",
    "retry": "the classifier stopped this call",
    "absolute path": "restate every relative path",
}


def assert_block_contract(result: HookResult, message_substring: str = "") -> None:
    """Assert exit 2 and the standard AI guidance block contract."""
    assert_blocked(result, message_substring)
    stderr_lower = result.stderr.lower()
    for label, needle in _AI_BLOCK_CHECKS:
        assert needle.lower() in stderr_lower, f"Block contract violation — missing {label}.\nstderr: {result.stderr}"
    found = [name for name, needle in _CLOSING_INSTRUCTIONS.items() if needle in stderr_lower]
    assert len(found) == 1, (
        f"Block contract violation — expected exactly one closing instruction, found {found or 'none'}."
        f"\nstderr: {result.stderr}"
    )
