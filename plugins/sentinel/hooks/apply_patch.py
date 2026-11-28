"""Read the file paths a Codex `apply_patch` body names.

The tool takes one command string holding a patch. Its headers are the only
place the affected paths appear, so every hook that judges paths reads them
here rather than carrying its own copy of the header pattern.
"""

from __future__ import annotations

import re

_HEADER = re.compile(
    r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (?P<path>.+)$",
    re.MULTILINE,
)


def targets(command: str) -> list[str]:
    """Return the paths named by the patch headers in `command`."""
    return [match.group("path").strip() for match in _HEADER.finditer(command)]
