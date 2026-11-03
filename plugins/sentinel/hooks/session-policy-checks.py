#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report shell-pin warnings and manifest defects at session start."""

import json
import os
from pathlib import Path
import shutil
import sys

from guarded_paths import ManifestError, validate
from hook_response import CLAUDE, invoking_agent


def main() -> int:
    """Read the SessionStart payload from stdin and report shell-pin and manifest warnings."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    if invoking_agent(payload=payload) == CLAUDE:
        pin = os.environ.get("CLAUDE_CODE_SHELL", "")
        executable = shutil.which(pin) if pin else None
        if not executable or "bash" not in Path(executable).name:
            print(
                f"Warning: CLAUDE_CODE_SHELL is {pin or 'unset'}. "
                "Set CLAUDE_CODE_SHELL=/run/current-system/sw/bin/bash so tool commands match the Bash lexer.",
                file=sys.stderr,
            )
    try:
        findings = validate()
    except (ManifestError, OSError) as exc:
        print(
            f"Error: guarded-paths.toml could not be loaded: {exc}. "
            "Mutating calls will ask for approval until it is repaired, "
            "or be refused where the agent cannot prompt.",
            file=sys.stderr,
        )
        return 2
    for finding in findings:
        print(f"Warning: guarded-paths.toml: {finding}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
