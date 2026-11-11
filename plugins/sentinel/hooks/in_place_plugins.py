"""Plugin directories that a harness loads in place, read from each harness's own records.

Codex copies every plugin it installs. Claude Code, VS Code, Copilot CLI, and Pi
run a local plugin where it is, and record where in a user-level file. Pi also
loads the extensions a package's `package.json` names under `pi.extensions`. A record
that is missing or does not parse names nothing, because the harness loads no
plugin from it either.
"""

from __future__ import annotations

from collections.abc import Iterable
import json
import os
from pathlib import Path

PLUGIN_MANIFESTS = ("plugin.json", ".claude-plugin/plugin.json")
CATALOGS = (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json", ".github/plugin/marketplace.json")
VSCODE_SETTINGS = ("Library/Application Support/Code/User/settings.json", ".config/Code/User/settings.json")
LOCAL_PREFIXES = ("/", "./", "../", "~")


def in_place_plugins(home: str) -> tuple[Path, ...]:
    """Return each plugin directory a supported harness's records under `home` name as loaded in place.

    A recorded location is the plugin when it holds a plugin manifest; otherwise
    its catalogs name the plugins, by relative path; otherwise it is covered whole.
    """
    home_directory = Path(home)
    locations = (
        *_claude_locations(home_directory),
        *_vscode_locations(home_directory),
        *_pi_locations(home_directory),
        *_copilot_locations(home_directory),
    )
    return tuple(dict.fromkeys(plugin for location in locations for plugin in _plugins_at(location)))


def in_place_pi_extensions(home: str) -> tuple[Path, ...]:
    """Return the directory of each extension named by a Pi package that Pi's records under `home` load in place."""
    return tuple(
        dict.fromkeys(directory for package in _pi_locations(Path(home)) for directory in pi_extensions(package))
    )


def pi_extensions(package: Path) -> tuple[Path, ...]:
    """Return the directory of each extension the `package.json` in `package` names under `pi.extensions`.

    An entry counts only when it is a `./` path that exists. A file entry gives its parent directory.
    """
    manifest = read_json(package / "package.json")
    pi = manifest.get("pi") if isinstance(manifest, dict) else None
    entries = pi.get("extensions") if isinstance(pi, dict) else None
    paths = (
        Path(os.path.normpath(package / entry))
        for entry in (entries if isinstance(entries, list) else ())
        if isinstance(entry, str) and entry.startswith("./")
    )
    return tuple(dict.fromkeys(path if path.is_dir() else path.parent for path in paths if path.exists()))


def _claude_locations(home: Path) -> Iterable[Path]:
    """Claude Code: each known marketplace added from a directory or a file, at its install location."""
    records = read_json(home / ".claude/plugins/known_marketplaces.json")
    for record in records.values() if isinstance(records, dict) else ():
        source = record.get("source") if isinstance(record, dict) else None
        if isinstance(source, dict) and source.get("source") in {"directory", "file"}:
            yield from _location(record.get("installLocation"), home)


def _vscode_locations(home: Path) -> Iterable[Path]:
    """VS Code: each key of `chat.pluginLocations` in the user settings."""
    for relative in VSCODE_SETTINGS:
        settings = read_json(home / relative, comments=True)
        locations = settings.get("chat.pluginLocations") if isinstance(settings, dict) else None
        for key in locations if isinstance(locations, dict) else ():
            yield from _location(key, home)


def _pi_locations(home: Path) -> Iterable[Path]:
    """Pi: each local path in the `packages` list, resolved from the settings file's directory."""
    settings_path = home / ".pi/agent/settings.json"
    settings = read_json(settings_path)
    packages = settings.get("packages") if isinstance(settings, dict) else None
    for package in packages if isinstance(packages, list) else ():
        source = package.get("source") if isinstance(package, dict) else package
        if isinstance(source, str) and (source == "." or source.startswith(LOCAL_PREFIXES)):
            yield from _location(source, home, relative_to=settings_path.parent)


def _copilot_locations(home: Path) -> Iterable[Path]:
    """Copilot CLI: each extra known marketplace added from a directory."""
    settings = read_json(home / ".copilot/settings.json")
    marketplaces = settings.get("extraKnownMarketplaces") if isinstance(settings, dict) else None
    for record in marketplaces.values() if isinstance(marketplaces, dict) else ():
        source = record.get("source") if isinstance(record, dict) else None
        if isinstance(source, dict) and source.get("source") == "directory":
            yield from _location(source.get("path"), home)


def _location(value: object, home: Path, relative_to: Path | None = None) -> Iterable[Path]:
    """Yield the directory a recorded path names, with `~` meaning `home`."""
    if not isinstance(value, str) or not value:
        return
    if value == "~" or value.startswith("~/"):
        value = str(home / value[2:])
    elif not os.path.isabs(value):
        if relative_to is None:
            return
        value = str(relative_to / value)
    location = Path(os.path.normpath(value))
    if location.is_dir():
        yield location


def _plugins_at(location: Path) -> tuple[Path, ...]:
    """Return the plugin directories a recorded location holds."""
    if any((location / manifest).is_file() for manifest in PLUGIN_MANIFESTS):
        return (location,)
    named = tuple(
        Path(os.path.normpath(location / relative))
        for catalog in CATALOGS
        for relative in _relative_plugins(read_json(location / catalog))
    )
    return named or (location,)


def _relative_plugins(catalog: object) -> Iterable[str]:
    """Yield each plugin path a catalog gives relative to its own root."""
    plugins = catalog.get("plugins") if isinstance(catalog, dict) else None
    for entry in plugins if isinstance(plugins, list) else ():
        source = entry.get("source") if isinstance(entry, dict) else None
        path = source.get("path") if isinstance(source, dict) else source
        if isinstance(path, str) and path.startswith("./"):
            yield path


def read_json(path: Path, *, comments: bool = False) -> object:
    """Return a record's parsed contents, or `None` when it is missing or does not parse."""
    try:
        return parse_json(path.read_text(encoding="utf-8"), comments=comments)
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def parse_json(text: str, *, comments: bool = False) -> object:
    """Parse JSON text, accepting comments and trailing commas when `comments` is set; raise `ValueError` otherwise."""
    return json.loads(_without_trailing_commas(_without_comments(text)) if comments else text)


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
