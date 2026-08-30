"""What each hook does when it cannot judge a call, pinned per hook.

`hook-tampering-blocking` `FailureMode` and the `hook-interface`
`ErrorHandlingByDamagePotential` contract both let a call proceed rather than
refuse it, but they do not agree across hooks: the two that cover read-only
tools alongside sensitive ones fail open, while the Bash-only hook fails closed.
The asymmetry is the point, so each direction is asserted rather than assumed.

Without these, the blind `except Exception` handlers are unreachable from the
suite: a defect that made every check raise would leave the hooks exiting 0 on
every call, with nothing turning red.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"

TAMPERING = "block-hook-tampering.py"
SENSITIVE = "block-sensitive-paths.py"
DESTRUCTIVE = "block-destructive-ops.py"

# A string where the hook expects a mapping. Every hook reaches for `.get` on
# `tool_input`, so this raises inside the judgement rather than at the boundary,
# which is the only route to the blind handlers.
MALFORMED_TOOL_INPUT = "not-a-dict"


@dataclass
class HookResult:
    exit_code: int
    stdout: str
    stderr: str


def run_hook(
    hook: str, payload: dict | None = None, *, raw: str | None = None
) -> HookResult:
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


class TestUnexpectedErrorFailsOpen:
    """A hook covering read-only tools lets the call through when it breaks."""

    @pytest.mark.parametrize("hook", [TAMPERING, SENSITIVE])
    def test_an_error_inside_the_judgement_allows_the_call(self, hook: str) -> None:
        result = run_hook(
            hook, {"tool_name": "Bash", "tool_input": MALFORMED_TOOL_INPUT}
        )

        assert result.exit_code == 0, (
            f"{hook} refused a call it failed to judge; the tool mix here is "
            f"read-only as well as sensitive.\nstderr: {result.stderr}"
        )
        assert result.stdout == "", "an Allow writes nothing to stdout"

    def test_the_tamper_hook_allows_a_malformed_write_payload(self) -> None:
        """Write and Edit take a separate branch from Bash, so it is asserted separately."""
        result = run_hook(
            TAMPERING, {"tool_name": "Write", "tool_input": MALFORMED_TOOL_INPUT}
        )

        assert result.exit_code == 0
        assert result.stdout == ""


class TestUnexpectedErrorFailsClosed:
    """The Bash-only hook refuses instead, because every tool it covers is sensitive."""

    def test_an_error_inside_the_judgement_refuses_the_command(self) -> None:
        result = run_hook(
            DESTRUCTIVE, {"tool_name": "Bash", "tool_input": MALFORMED_TOOL_INPUT}
        )

        assert result.exit_code == 2, (
            "block-destructive-ops covers Bash alone, where an unchecked "
            "command can delete work or rewrite history"
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

        assert result.exit_code == 0, (
            f"{hook} judged an empty command\nstderr: {result.stderr}"
        )
        assert result.stdout == ""
        assert result.stderr == "", "an Allow reports nothing"

    def test_an_empty_apply_patch_allows_the_call(self) -> None:
        result = run_hook(
            SENSITIVE, {"tool_name": "apply_patch", "tool_input": {"command": ""}}
        )

        assert result.exit_code == 0
        assert result.stderr == ""
