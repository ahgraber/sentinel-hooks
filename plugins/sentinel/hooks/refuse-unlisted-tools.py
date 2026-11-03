#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Refuse a tool the tool vocabulary does not list for the invoking harness (PreToolUse hook).

Registered for every tool call on a harness that sends its tool names to the
hooks directly. An adapter makes the same refusal for the harness it serves.
"""

import json
from pathlib import Path
import sys
from typing import NoReturn

from hook_response import STOP_INSTRUCTIONS, Decision, invoking_agent, respond

# Resolved, so a refusal names the repository file a person edits rather than
# the deployed link.
VOCABULARY_FILE = Path(__file__).resolve().parent / "tool-vocabulary.toml"


def _refuse(message: str) -> NoReturn:
    sys.stderr.write(f"{message}\n{STOP_INSTRUCTIONS}\n")
    sys.exit(2)


def main() -> None:
    """Read the hook payload from stdin and refuse an unlisted tool."""
    try:
        from guarded_paths import TOOL_VOCABULARY
    except Exception as exc:  # noqa: BLE001
        # No other layer knows which tools exist, so an unreadable list refuses
        # every call rather than letting every unlisted tool through.
        _refuse(
            f"Blocked: the tool vocabulary at {VOCABULARY_FILE} could not be read "
            f"({exc}), so no tool call can be checked. The user has to repair the "
            "file by hand; this agent cannot read or edit it while it is broken."
        )

    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        # A payload that names no tool takes the read-only direction.
        respond(Decision.WARN, "refuse-unlisted-tools could not parse the hook payload.")

    tool_name = data.get("tool_name", "") if isinstance(data, dict) else ""
    agent = invoking_agent(payload=data if isinstance(data, dict) else None)
    mapped = TOOL_VOCABULARY.normalize(agent, tool_name)
    if mapped == tool_name or TOOL_VOCABULARY.is_passthrough(agent, tool_name):
        sys.exit(0)
    if mapped is not None:
        # The hooks judge the name a harness sends, and only an adapter converts
        # it, so a mapping to another name would pass here and be judged by none.
        _refuse(
            f"Blocked: the tool '{tool_name}' is mapped to '{mapped}' for {agent} in "
            f"{VOCABULARY_FILE}, but {agent} has no adapter to convert the name, so no "
            "hook would check it. The user can list it as passthrough or remove the mapping."
        )
    _refuse(
        f"Blocked: the tool '{tool_name}' is not listed for {agent} in {VOCABULARY_FILE}, "
        "so no hook can check it. The user can map it onto a checked tool, list it as "
        "passthrough, or leave it refused."
    )


def run() -> None:
    """Judge one tool call; refuse on an unexpected failure."""
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _refuse(f"Blocked: refuse-unlisted-tools failed ({type(exc).__name__}: {exc}), so the call is refused.")


if __name__ == "__main__":
    run()
