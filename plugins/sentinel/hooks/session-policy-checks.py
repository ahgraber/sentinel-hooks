#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report shell-pin warnings, manifest defects, and settings that defeat the hooks at session start."""

import json
import os
from pathlib import Path
import shutil
import sys

from configuration_floor import floor_findings
from guarded_paths import ManifestError, validate
from hook_response import CLAUDE, CODEX, COPILOT, PI, invoking_agent

# These agents show the user a session hook's `systemMessage`, and not its standard error on exit 0.
# Pi does so through the extension that runs its hooks.
SYSTEM_MESSAGE_AGENTS = frozenset({CLAUDE, CODEX, PI})
# `COPILOT` names VS Code and Copilot CLI. VS Code shows the user none of a session hook's output and
# gives the model its `additionalContext`, so the model is asked to pass the report on. Copilot CLI
# shows the user nothing and gives the model nothing.
RELAY_REQUEST = (
    "Sentinel's session check found the settings below. Tell the user each warning in full in your next reply."
)


def shell_pin_warnings() -> list[str]:
    """Return one warning when Claude Code's shell pin does not name a bash, else an empty list."""
    pin = os.environ.get("CLAUDE_CODE_SHELL", "")
    executable = shutil.which(pin) if pin else None
    if executable and "bash" in Path(executable).name:
        return []
    return [f"CLAUDE_CODE_SHELL is {pin or 'unset'}. Set it to a bash so tool commands match the Bash lexer."]


def main() -> int:
    """Read the SessionStart payload from stdin and report each warning by the route the agent shows the user."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    agent = invoking_agent(payload=payload)
    warnings = shell_pin_warnings() if agent == CLAUDE else []
    try:
        findings = validate()
    except (ManifestError, OSError) as exc:
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        print(
            f"Error: guarded-paths.toml could not be loaded: {exc}. "
            "Mutating calls will ask for approval until it is repaired, "
            "or be refused where the agent cannot prompt.",
            file=sys.stderr,
        )
        return 2
    warnings.extend(f"guarded-paths.toml: {finding}" for finding in findings)
    project = payload.get("cwd")
    try:
        warnings.extend(
            floor_findings(Path.home(), Path(project if isinstance(project, str) else os.getcwd()), os.environ)
        )
    except (OSError, ValueError) as exc:
        warnings.append(f"configuration-floor.toml could not be read: {exc}. No harness settings were checked.")
    report = "\n".join(f"Warning: {warning}" for warning in warnings)
    if report:
        print(report, file=sys.stderr)
        if agent in SYSTEM_MESSAGE_AGENTS:
            print(json.dumps({"systemMessage": report}))
        elif agent == COPILOT:
            context = {"hookEventName": "SessionStart", "additionalContext": f"{RELAY_REQUEST}\n{report}"}
            print(json.dumps({"hookSpecificOutput": context}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
