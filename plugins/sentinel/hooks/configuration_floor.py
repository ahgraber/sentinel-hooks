"""Find the settings, in any supported harness, that defeat Sentinel's hooks.

`configuration-floor.toml` names each value and describes its fields. A value
stops the hooks from running, or lets a question a hook put to the user be
answered without the user. This module reads each harness's settings files and
returns one sentence per value it finds; it writes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
import datetime
import json
from pathlib import Path
import re
import shlex
import tomllib

from guarded_paths import expand_user, repo_root_of
from in_place_plugins import LOCAL_PREFIXES, parse_json, read_json

FLOOR_PATH = Path(__file__).with_name("configuration-floor.toml")
# Every hook command the Codex installer writes contains this text.
# It must equal `MISSING_HOOK_NOTICE` in `install-hooks.py`.
CODEX_HOOK_MARKER = "Sentinel: $0 is missing. Run:"
_MISSING = object()
# A settings file of this scope applies only when the user selects it.
PROFILE_SCOPE = "profile"


class FloorError(ValueError):
    """The floor data lacks a field, mistypes one, or names an unknown one."""


class _UnreadableError(Exception):
    """A settings file exists and cannot be read in its format."""


@dataclass(frozen=True)
class _SettingsFile:
    """One settings file's contents, with the scope the harness reads it at."""

    scope: str
    path: Path
    data: dict


@dataclass(frozen=True)
class _Context:
    plugin: str
    package: str
    home: Path


# A found value: the file that supplies it, the setting as the report names it, and the value as written.
_Found = tuple[Path, str, str]


def floor_findings(
    home: Path,
    project: Path,
    environment: Mapping[str, str],
    *,
    root: Path = Path("/"),
) -> list[str]:
    """Return one sentence for each setting, in any supported harness, that defeats Sentinel's hooks.

    `home` is the user's home and `project` the session's working directory.
    `environment` supplies the variables that move a harness's home. An absolute
    settings path is read under `root`. A settings file that is missing is
    skipped, and one that does not parse is reported as unchecked. A sentence
    is returned once. Raises `OSError` when the floor file cannot be read and
    `ValueError` when it does not parse or `check_floor` rejects it.
    """
    floor = tomllib.loads(FLOOR_PATH.read_text(encoding="utf-8"))
    check_floor(floor)
    context = _Context(floor["plugin"], floor["package"], home)
    findings: list[str] = []
    for harness in floor["harnesses"].values():
        findings.extend(_harness_findings(harness, context, project, environment, root))
    return list(dict.fromkeys(findings))


def _harness_findings(
    harness: dict, context: _Context, project: Path, environment: Mapping[str, str], root: Path
) -> Iterator[str]:
    """Yield a sentence for each listed value one harness's settings hold, and for each file that does not parse."""
    name = harness["name"]
    harness_home = _harness_home(harness, context.home, environment)
    settings_files: list[_SettingsFile] = []
    for listed in harness["files"]:
        for path in _paths(listed["path"], harness_home, project, root):
            try:
                data = _read(path, harness["format"])
            except _UnreadableError:
                yield f"{name}: {path} could not be read as {harness['format']}, so its settings are unchecked."
                continue
            if "root" in listed and isinstance(data, dict):
                data = data.get(listed["root"])
            if isinstance(data, dict):
                settings_files.append(_SettingsFile(listed["scope"], path, data))

    for value in harness["values"]:
        scopes = value.get("scopes")
        in_scope = [file for file in settings_files if scopes is None or file.scope in scopes]
        base = [file for file in in_scope if file.scope != PROFILE_SCOPE]
        find = _KINDS[value.get("kind", "setting")]
        for layers in _layerings(in_scope):
            for path, setting, written in find(value, layers, context):
                yield f"{name}: `{setting}` is {written} in {path}, which {value['effect']}."
        if value.get("unset") and harness_home.is_dir() and _is_unset(value, base, settings_files):
            yield f"{name}: `{value['key']}` is unset, and {name} can then choose a value that {value['effect']}."


def _layerings(in_scope: list[_SettingsFile]) -> Iterator[list[_SettingsFile]]:
    """Yield the files a session reads together: those that always apply, then the same files under each profile.

    A profile applies over the other files, and only when the user selects it.
    """
    base = [file for file in in_scope if file.scope != PROFILE_SCOPE]
    yield base
    for file in in_scope:
        if file.scope == PROFILE_SCOPE:
            yield [*base, file]


def _is_unset(value: dict, in_scope: Iterable[_SettingsFile], every_file: Iterable[_SettingsFile]) -> bool:
    """Return whether no file in scope sets the value's key, and no file at all sets the setting that takes its place."""
    if any(_lookup(file.data, value["key"]) is not _MISSING for file in in_scope):
        return False
    stand_in = value.get("unset-unless")
    return stand_in is None or all(_lookup(file.data, stand_in) is _MISSING for file in every_file)


def _setting(value: dict, layers: list[_SettingsFile], _context: _Context) -> Iterator[_Found]:
    """Yield the highest file's value for a setting, when it is one that has the effect."""
    for file in reversed(layers):
        found = _lookup(file.data, value["key"])
        if found is _MISSING:
            continue
        if any(found == listed and type(found) is type(listed) for listed in value["is"]):
            yield file.path, value["key"], json.dumps(found)
        return


def _plugin_entry(value: dict, layers: list[_SettingsFile], context: _Context) -> Iterator[_Found]:
    """Yield each plugin entry that switches Sentinel off, or the default entry when Sentinel has no entry."""
    field = value.get("field")
    default_name = value.get("default-entry")
    entries: dict[str, tuple[Path, object]] = {}
    for file in layers:
        table = _lookup(file.data, value["key"])
        for name, entry in table.items() if isinstance(table, dict) else ():
            if field is None:
                entries[name] = (file.path, entry)
            elif isinstance(entry, dict) and field in entry:
                entries[name] = (file.path, entry[field])
    own = {
        name: entry
        for name, entry in entries.items()
        if name == context.plugin or name.startswith(f"{context.plugin}@")
    }
    judged = own or {name: entry for name, entry in entries.items() if name == default_name}
    for name, (path, state) in judged.items():
        if state is False:
            yield path, f'{value["key"]}."{name}"' + (f".{field}" if field else ""), "false"


def _codex_hook_state(value: dict, layers: list[_SettingsFile], _context: _Context) -> Iterator[_Found]:
    """Yield each Codex hook state that switches off a hook the Sentinel installer wrote."""
    states: dict[str, tuple[Path, object]] = {}
    for file in layers:
        table = _lookup(file.data, value["key"])
        for name, state in table.items() if isinstance(table, dict) else ():
            if isinstance(state, dict) and "enabled" in state:
                states[name] = (file.path, state["enabled"])
    for name, (path, enabled) in states.items():
        if enabled is False and (hook := _sentinel_codex_hook(name)):
            yield path, f'{value["key"]}."{name}".enabled', f"false for {hook}"


def _sentinel_codex_hook(state_name: str) -> str | None:
    """Return the hook file a Codex hook state names, when the Sentinel installer wrote that entry.

    Codex names a state `<hook file>:<event>:<group index>:<hook index>`, with the event in snake case.
    """
    try:
        file, event, group, index = state_name.rsplit(":", 3)
        hooks = json.loads(Path(file).read_text(encoding="utf-8"))["hooks"]
        groups = next(entries for name, entries in hooks.items() if _snake_case(name) == event)
        command = groups[int(group)]["hooks"][int(index)]["command"]
        if CODEX_HOOK_MARKER not in command:
            return None
        # The installer writes `sh -c <script> <hook> <arguments>`.
        return Path(shlex.split(command)[3]).name
    except (OSError, ValueError, KeyError, IndexError, TypeError, StopIteration):
        return None


def _pi_package_filter(value: dict, layers: list[_SettingsFile], context: _Context) -> Iterator[_Found]:
    """Yield the Sentinel package entry whose `extensions` filter loads none, or excludes one by path.

    A project's entry for a package replaces the user's. `pi config` writes an
    excluded extension as its path with a `-` prefix.
    """
    entry_at: tuple[Path, object] | None = None
    for file in layers:
        packages = file.data.get(value["key"])
        for entry in packages if isinstance(packages, list) else ():
            package_source = entry.get("source") if isinstance(entry, dict) else entry
            if isinstance(package_source, str) and _is_sentinel_package(package_source, file.path.parent, context):
                entry_at = (file.path, entry)
    if entry_at is None or not isinstance(entry_at[1], dict):
        return
    extensions = entry_at[1].get("extensions")
    if isinstance(extensions, list) and (
        not extensions or any(isinstance(item, str) and item.startswith("-") for item in extensions)
    ):
        yield entry_at[0], f"{value['key']}.extensions", json.dumps(extensions)


def _is_sentinel_package(source: str, settings_directory: Path, context: _Context) -> bool:
    """Return whether a Pi package source names Sentinel: by its `package.json` for a local path, else by its text."""
    if source != "." and not source.startswith(LOCAL_PREFIXES):
        return context.package in source
    manifest = read_json(settings_directory / expand_user(source, str(context.home)) / "package.json")
    return isinstance(manifest, dict) and manifest.get("name") == context.package


_KINDS = {
    "setting": _setting,
    "plugin-entry": _plugin_entry,
    "codex-hook-state": _codex_hook_state,
    "pi-package-filter": _pi_package_filter,
}


_FORMATS = frozenset({"json", "jsonc", "toml"})
_SCOPES = frozenset({"managed", "user", PROFILE_SCOPE, "project", "shared"})
_EVIDENCE = frozenset({"probe", "source", "documentation"})
_HARNESS_FIELDS = {"name": str, "version": str, "home": str, "format": str, "files": list, "values": list}
_VALUE_FIELDS = {"key": str, "effect": str, "evidence": str, "source": str, "checked": datetime.date}
# The fields a value of each kind may carry beyond `_VALUE_FIELDS`, `kind`, and `scopes`.
_KIND_FIELDS = {
    "setting": {"is": list, "unset": bool, "unset-unless": str},
    "plugin-entry": {"field": str, "default-entry": str},
    "codex-hook-state": {},
    "pi-package-filter": {},
}


def check_floor(floor: dict) -> None:
    """Raise `FloorError`, naming the entry, when the floor data lacks a field, mistypes one, or names an unknown one."""
    _check_fields("the floor", floor, {"plugin": str, "package": str, "harnesses": dict}, {})
    for identifier, harness in floor["harnesses"].items():
        where = f"harness `{identifier}`"
        _check_fields(where, harness, _HARNESS_FIELDS, {"home-variable": str})
        _check_member(where, "format", harness["format"], _FORMATS)
        for file in harness["files"]:
            _check_fields(f"{where} file", file, {"scope": str, "path": str}, {"root": str})
            _check_member(f"{where} file `{file['path']}`", "scope", file["scope"], _SCOPES)
        for value in harness["values"]:
            _check_value(where, value)


def _check_value(where: str, value: object) -> None:
    key = value.get("key") if isinstance(value, dict) else None
    where = f"{where} value `{key}`"
    kind = value.get("kind", "setting") if isinstance(value, dict) else None
    _check_member(where, "kind", kind, _KINDS)
    optional = {"kind": str, "scopes": list, **_KIND_FIELDS[kind]}
    _check_fields(where, value, _VALUE_FIELDS, optional)
    _check_member(where, "evidence", value["evidence"], _EVIDENCE)
    for scope in value.get("scopes", ()):
        _check_member(where, "scopes", scope, _SCOPES)
    if kind == "setting" and "is" not in value:
        raise FloorError(f"{where} has no `is` list")
    if "unset-unless" in value and not value.get("unset"):
        raise FloorError(f"{where} has `unset-unless` without `unset`")


def _check_fields(where: str, table: object, required: Mapping[str, type], optional: Mapping[str, type]) -> None:
    """Raise unless `table` is a table that holds every required field, no unknown field, and each at its type."""
    if not isinstance(table, dict):
        raise FloorError(f"{where} is not a table")
    for field in required:
        if field not in table:
            raise FloorError(f"{where} has no `{field}`")
    for field, held in table.items():
        expected = required.get(field) or optional.get(field)
        if expected is None:
            raise FloorError(f"{where} has an unknown field `{field}`")
        if not isinstance(held, expected):
            raise FloorError(f"{where} field `{field}` is not {expected.__name__}")


def _check_member(where: str, field: str, held: object, allowed: object) -> None:
    if held not in allowed:
        raise FloorError(f"{where} has an unknown {field} `{held}`")


def _harness_home(harness: dict, home: Path, environment: Mapping[str, str]) -> Path:
    variable = harness.get("home-variable")
    if variable and environment.get(variable):
        return Path(environment[variable])
    return Path(expand_user(harness["home"], str(home)))


def _paths(template: str, harness_home: Path, project: Path, root: Path) -> list[Path]:
    """Return the files a `files` path names, in the order the harness reads them."""
    if template.startswith("{home}/"):
        bases = [harness_home / template.removeprefix("{home}/")]
    elif template.startswith("{project}/"):
        bases = [directory / template.removeprefix("{project}/") for directory in _project_directories(project)]
    else:
        bases = [root / template.lstrip("/")]
    return [path for base in bases for path in (sorted(base.parent.glob(base.name)) if "*" in base.name else [base])]


def _project_directories(project: Path) -> list[Path]:
    """Return each directory from the repository root down to `project`, or `project` alone outside a repository."""
    repository = repo_root_of(str(project))
    chain = [project, *project.parents]
    if repository is None or Path(repository) not in chain:
        return [project]
    return list(reversed(chain[: chain.index(Path(repository)) + 1]))


def _read(path: Path, file_format: str) -> object:
    """Return a settings file's parsed contents, or `None` when it is missing; raise when it cannot be read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise _UnreadableError from exc
    try:
        return tomllib.loads(text) if file_format == "toml" else parse_json(text, comments=file_format == "jsonc")
    except ValueError as exc:
        raise _UnreadableError from exc


def _lookup(data: dict, key: str) -> object:
    """Return the value at a dotted key, written whole as one key or as nested tables; `_MISSING` when absent."""
    if key in data:
        return data[key]
    found: object = data
    for part in key.split("."):
        if not isinstance(found, dict) or part not in found:
            return _MISSING
        found = found[part]
    return found


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
