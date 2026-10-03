"""What each hook does when it cannot judge a call, pinned per hook.

`hook-interface` `ErrorHandlingByDamagePotential` picks the direction from the
tool named in the payload, not from the hook, and the three hooks here land
differently: the Bash-only hook refuses, and the tamper and sensitive-path hooks
gate the tools that can modify state and let a read through. Each direction is
asserted rather than assumed.

Without these, the blind `except Exception` handlers are unreachable from the
suite: a defect that made every check raise would leave each hook taking its
failure path on every call, with nothing turning red.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"

TAMPERING = "block-hook-tampering.py"
SENSITIVE = "block-sensitive-paths.py"
SECRETS = "block-secrets.py"
DESTRUCTIVE = "block-destructive-ops.py"

# A string where the hook expects a mapping. Every hook reaches for `.get` on
# `tool_input`, so this raises inside the judgment rather than at the boundary,
# which is the only route to the blind handlers.
MALFORMED_TOOL_INPUT = "not-a-dict"


@dataclass
class HookResult:
    exit_code: int
    stdout: str
    stderr: str


def run_hook(hook: str, payload: dict | None = None, *, raw: str | None = None) -> HookResult:
    """Run `hook` over a payload, or over `raw` bytes when the payload must not parse."""
    result = subprocess.run(
        ["python3", str(HOOKS_DIR / hook)],
        input=json.dumps(payload) if raw is None else raw,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return HookResult(result.returncode, result.stdout, result.stderr)


class TestSensitivePathHookFollowsTheNamedTool:
    """The sensitive-path hook covers reads and mutations, so the named tool picks the direction."""

    def test_an_error_judging_a_mutation_refuses_where_no_prompt_is_shown(self) -> None:
        result = run_hook(SENSITIVE, {"tool_name": "Bash", "tool_input": MALFORMED_TOOL_INPUT})

        assert result.exit_code == 2, result.stderr
        assert "block-sensitive-paths failed" in result.stderr

    def test_an_error_judging_a_read_proceeds_with_a_warning(self) -> None:
        result = run_hook(SENSITIVE, {"tool_name": "Read", "tool_input": MALFORMED_TOOL_INPUT})

        assert result.exit_code == 0, result.stderr
        assert "proceed unchecked" in result.stdout + result.stderr

    def test_an_unparsable_payload_proceeds_with_a_warning(self) -> None:
        result = run_hook(SENSITIVE, raw="{not json")

        assert result.exit_code == 0, result.stderr
        assert "was not checked" in result.stdout + result.stderr


class TestSecretHookFollowsTheNamedTool:
    """An error inside the secret hook's judgment refuses a mutation and lets a read through."""

    def test_an_error_judging_a_mutation_refuses(self) -> None:
        result = run_hook(SECRETS, {"tool_name": "Bash", "tool_input": MALFORMED_TOOL_INPUT})

        assert result.exit_code == 2, result.stderr
        assert "block-secrets failed" in result.stderr

    def test_an_error_judging_a_read_proceeds_with_a_warning(self) -> None:
        result = run_hook(SECRETS, {"tool_name": "Read", "tool_input": MALFORMED_TOOL_INPUT})

        assert result.exit_code == 0, result.stderr
        assert "was not checked" in result.stdout + result.stderr


class TestTamperHookGatesWhatItCannotJudge:
    """Every tool the tamper hook gates can modify state, so a failure reaches the user.

    The payload names the tool, so damage potential is known even when nothing
    else about the call is. A read stays allowed, because the hook is registered
    for `Read` as well and refusing one buys nothing.
    """

    @pytest.mark.parametrize("tool_name", ["Bash", "Write", "Edit", "apply_patch"])
    def test_an_error_inside_the_judgment_refuses_the_call(self, tool_name: str) -> None:
        """No agent is named here, so the ask degrades to the refusal."""
        result = run_hook(TAMPERING, {"tool_name": tool_name, "tool_input": MALFORMED_TOOL_INPUT})

        assert result.exit_code == 2, (
            f"{TAMPERING} allowed a {tool_name} call it failed to judge\nstdout: {result.stdout}"
        )
        assert result.stdout == "", "a refusal writes nothing to stdout"
        assert "block-hook-tampering failed" in result.stderr

    def test_a_read_is_allowed_whatever_its_payload_holds(self) -> None:
        """A read is passed before anything in the payload is reached."""
        result = run_hook(TAMPERING, {"tool_name": "Read", "tool_input": MALFORMED_TOOL_INPUT})

        assert result.exit_code == 0
        assert result.stdout == ""

    def test_an_unparsable_payload_allows_the_call(self) -> None:
        """The tool is unnamed, and an unnamed tool cannot be assumed a mutation."""
        result = run_hook(TAMPERING, raw="{not json")

        assert result.exit_code == 0
        assert result.stdout == ""
        assert "not checked" in result.stderr


class TestUnexpectedErrorFailsClosed:
    """The Bash-only hook refuses instead, because every tool it covers is sensitive."""

    def test_an_error_inside_the_judgment_refuses_the_command(self) -> None:
        result = run_hook(DESTRUCTIVE, {"tool_name": "Bash", "tool_input": MALFORMED_TOOL_INPUT})

        assert result.exit_code == 2, (
            "block-destructive-ops covers Bash alone, where an unchecked command can delete work or rewrite history"
        )
        assert "never checked" in result.stderr

    def test_an_unparsable_payload_refuses_the_command(self) -> None:
        result = run_hook(DESTRUCTIVE, raw="{not json")

        assert result.exit_code == 2
        assert result.stdout == ""


class TestEmptyCommandIsAllowed:
    """An empty command names no path, so every hook passes it without a verdict."""

    @pytest.mark.parametrize("hook", [TAMPERING, SENSITIVE, DESTRUCTIVE])
    def test_an_empty_bash_command_allows_the_call(self, hook: str) -> None:
        result = run_hook(hook, {"tool_name": "Bash", "tool_input": {"command": ""}})

        assert result.exit_code == 0, f"{hook} judged an empty command\nstderr: {result.stderr}"
        assert result.stdout == ""
        assert result.stderr == "", "an Allow reports nothing"

    def test_an_empty_apply_patch_allows_the_call(self) -> None:
        result = run_hook(SENSITIVE, {"tool_name": "apply_patch", "tool_input": {"command": ""}})

        assert result.exit_code == 0
        assert result.stderr == ""
