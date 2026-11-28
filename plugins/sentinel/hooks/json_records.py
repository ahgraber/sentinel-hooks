"""JSON records that harnesses and packages keep, read as each harness reads them.

A record that is missing or does not parse reads as `None`, because the harness
takes nothing from it either.
"""

from __future__ import annotations

from collections.abc import Callable
import glob
import json
import math
import os
from pathlib import Path
import sys
from typing import NoReturn

# The prefixes of a Pi package source that is a local path.
LOCAL_PREFIXES = ("/", "./", "../", "~")


def pi_extensions(package: Path) -> tuple[Path, ...]:
    """Return the directory of each extension Pi loads from the package in `package`.

    Pi reads each `pi.extensions` entry in `package.json` as a path or glob relative to the package,
    with or without a leading `./`, and loads the conventional `extensions/` directory where the
    package names no extensions. A `!` entry is not applied, so the result can hold more than Pi
    loads. Pi's fallbacks for a list that mixes text with other values, and for an empty list under
    a settings filter, are not followed, so the result can also hold less. A file gives its parent directory.
    """
    manifest = read_json(package / "package.json")
    pi = manifest.get("pi") if isinstance(manifest, dict) else None
    entries = pi.get("extensions") if isinstance(pi, dict) else None
    if not isinstance(entries, list):
        entries = ["extensions"]
    paths = (
        Path(os.path.normpath(match))
        for entry in entries
        if isinstance(entry, str) and entry and not entry.startswith("!")
        for match in glob.glob(os.path.join(glob.escape(str(package)), entry), recursive=True)
    )
    return tuple(dict.fromkeys(path if path.is_dir() else path.parent for path in paths))


def read_json(path: Path) -> object:
    """Return a record's parsed contents, or `None` when it is missing or does not parse."""
    try:
        return parse_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def parse_json(text: str, *, comments: bool = False, object_pairs_hook: Callable | None = None) -> object:
    """Parse JSON text, accepting comments and trailing commas when `comments` is set.

    Every JSON reader in Sentinel parses through this function, so each applies one rule.
    Raise `ValueError` when the text is not valid UTF-8, does not parse, holds `NaN` or
    `Infinity`, holds a number outside the range of a double, or is nested too deeply to parse.
    Text from bytes that are not UTF-8 holds surrogates, under `surrogateescape`, and fails the first check.
    """
    text.encode("utf-8")
    try:
        return json.loads(
            _without_trailing_commas(_without_comments(text)) if comments else text,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            parse_int=_finite_int,
            object_pairs_hook=object_pairs_hook,
        )
    except RecursionError as error:
        raise ValueError("nested too deeply to parse") from error


def _reject_constant(name: str) -> NoReturn:
    raise ValueError(f"{name} is not a JSON number")


def _finite_float(text: str) -> float:
    value = float(text)
    if math.isinf(value):
        raise ValueError(f"{text} is outside the range of a double")
    return value


def _finite_int(text: str) -> int:
    value = int(text)
    if abs(value) > sys.float_info.max:
        raise ValueError(f"{text} is outside the range of a double")
    return value


def _without_comments(text: str) -> str:
    """Remove `//` and `/* */` comments outside strings, as VS Code accepts them in settings."""
    kept = []
    index, in_string = 0, False
    while index < len(text):
        char = text[index]
        if in_string:
            kept.append(text[index : index + 2] if char == "\\" else char)
            in_string = char != '"'
            index += 2 if char == "\\" else 1
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
        else:
            kept.append(char)
            in_string = char == '"'
            index += 1
    return "".join(kept)


def _without_trailing_commas(text: str) -> str:
    """Remove a comma outside strings that only whitespace separates from a closing bracket."""
    kept = []
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            in_string = escaped or char != '"'
            escaped = not escaped and char == "\\"
        elif char == '"':
            in_string = True
        elif char == "," and text[index + 1 :].lstrip()[:1] in {"}", "]"}:
            continue
        kept.append(char)
    return "".join(kept)
