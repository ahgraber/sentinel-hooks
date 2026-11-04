"""Match paths and text against manifest-declared guarded locations.

Declarations support `~/`, `<repo>/`, and single-component `*` patterns; an
enforcement-floor declaration may also use `<project>/`. Path
checks use written, expanded, and resolved spellings with filesystem case rules.
Text checks use declaration fragments.

Limits: a directory change the lexer does not follow (a substituted operand,
`cd -`, `cd -P`, `popd`, a `pushd` stack position, a `cd` in a loop or a
function, after `eval`, `source`, or `trap`, or under `CDPATH`) leaves a later
relative path unresolvable; name paths absolutely. Hard links are not
identified. A directory declaration follows its own symlink chain, not the
links held inside that directory. Routes that present no path cannot be
checked. The operating system sandbox and agent permissions are the boundary;
this matcher supplies defense in depth.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import fnmatch
import functools
import glob
import os
from pathlib import Path
import re
import tomllib
from types import MappingProxyType

HOME = os.path.expanduser("~")

_HOME_PREFIX = "~/"
_REPO_PREFIX = "<repo>/"
_PROJECT_PREFIX = "<project>/"

# Keep the manifest beside the module so deployed copies carry it. Callers can
# override it for tests.
MANIFEST_PATH = Path(__file__).parent / "guarded-paths.toml"
TOOL_VOCABULARY_PATH = Path(__file__).parent / "tool-vocabulary.toml"
# `capability-coverage` excuses an agent from running a hook; no hook reads it, only the assessment.
EXCEPTION_SURFACES = frozenset(
    {
        "sensitive-path-name-heuristic",
        "sensitive-path-dotenv-placeholder",
        "capability-coverage",
    }
)
# A placeholder exception is compared as a literal file name. A separator, home
# notation, or a glob shows its author expected path or glob semantics the
# surface does not have, and a name other than `.env.<suffix>`, `.env` itself
# above all, would excuse a file the dotenv rule exists to refuse.
_PLACEHOLDER_NAME = re.compile(r"\.env\.[^\s/\\~*?\[\]{}<>$]+", re.IGNORECASE)


class ManifestError(Exception):
    """The manifest could not be read or parsed."""


class ToolVocabularyError(Exception):
    """The tool vocabulary could not be read, parsed, or validated."""


@dataclass(frozen=True)
class ToolVocabulary:
    """Canonical tool groups and harness-specific spellings."""

    groups: Mapping[str, frozenset[str]]
    ask: Mapping[str, frozenset[str]]
    mappings: Mapping[str, Mapping[str, str]]
    passthrough: Mapping[str, frozenset[str]]
    refused: Mapping[str, frozenset[str]]

    def group(self, name: str) -> frozenset[str]:
        """Return the canonical tools in `name`."""
        return self.groups[name]

    def normalize(self, harness: str, spelling: str) -> str | None:
        """Return the canonical name for a harness spelling, or `None`."""
        mapping = self.mappings.get(harness)
        return mapping.get(spelling) if mapping is not None else None

    def is_passthrough(self, harness: str, spelling: str) -> bool:
        """Return whether `harness` declares `spelling` as a tool no hook checks.

        An entry is a name or an `fnmatch` pattern, matched case-sensitively.
        """
        return any(fnmatch.fnmatchcase(spelling, entry) for entry in self.passthrough.get(harness, ()))

    def supports_ask(self, harness: str, tool_name: str) -> bool:
        """Return whether `harness` honors an ask for the canonical tool."""
        return tool_name in self.ask.get(harness, ())


def _tool_sets(table: object, table_name: str) -> Mapping[str, frozenset[str]]:
    if not isinstance(table, dict):
        raise ToolVocabularyError(f"{table_name} must be a table")
    result: dict[str, frozenset[str]] = {}
    for name, values in table.items():
        if not isinstance(name, str) or not isinstance(values, list):
            raise ToolVocabularyError(f"{table_name} entries must map names to lists")
        if not values or any(not isinstance(value, str) or not value for value in values):
            raise ToolVocabularyError(f"{table_name}.{name} must contain nonempty strings")
        result[name] = frozenset(values)
    return MappingProxyType(result)


def _tool_records(table: object, table_name: str) -> Mapping[str, frozenset[str]]:
    """Read `[<table>.<harness>]` tables, each holding `[[...tools]]` records with a `tool` and a `reason`."""
    if not isinstance(table, dict):
        raise ToolVocabularyError(f"{table_name} must be a table")
    result: dict[str, frozenset[str]] = {}
    for harness, body in table.items():
        if not isinstance(body, dict) or not isinstance(body.get("tools"), list) or not body["tools"]:
            raise ToolVocabularyError(f"{table_name}.{harness} must hold a nonempty `tools` list")
        if set(body) - {"source", "tools"}:
            raise ToolVocabularyError(f"{table_name}.{harness} holds keys other than `source` and `tools`")
        for entry in body["tools"]:
            if not isinstance(entry, dict) or set(entry) != {"tool", "reason"}:
                raise ToolVocabularyError(f"each {table_name}.{harness} record needs exactly `tool` and `reason`")
            if any(not isinstance(entry[key], str) or not entry[key].strip() for key in ("tool", "reason")):
                raise ToolVocabularyError(f"{table_name}.{harness} records need a nonempty `tool` and `reason`")
        result[harness] = frozenset(entry["tool"] for entry in body["tools"])
    return MappingProxyType(result)


def load_tool_vocabulary(path: Path | str = TOOL_VOCABULARY_PATH) -> ToolVocabulary:
    """Load and validate the declared tool vocabulary."""
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ToolVocabularyError(str(exc)) from exc

    if set(data) != {"groups", "ask", "mappings", "passthrough", "refused"}:
        raise ToolVocabularyError("expected groups, ask, mappings, passthrough, and refused tables")

    groups = _tool_sets(data["groups"], "groups")
    ask = _tool_sets(data["ask"], "ask")
    passthrough = _tool_records(data["passthrough"], "passthrough")
    refused = _tool_records(data["refused"], "refused")
    raw_mappings = data["mappings"]
    if not isinstance(raw_mappings, dict):
        raise ToolVocabularyError("mappings must be a table")

    mappings: dict[str, Mapping[str, str]] = {}
    for harness, raw_mapping in raw_mappings.items():
        if not isinstance(harness, str) or not isinstance(raw_mapping, dict):
            raise ToolVocabularyError("mappings entries must be tables")
        if any(
            not isinstance(spelling, str) or not spelling or not isinstance(canonical, str) or not canonical
            for spelling, canonical in raw_mapping.items()
        ):
            raise ToolVocabularyError(f"mappings.{harness} must map nonempty strings")
        mappings[harness] = MappingProxyType(dict(raw_mapping))

    canonical_tools = {canonical for mapping in mappings.values() for canonical in mapping.values()}
    referenced_tools = {tool for tools in (*groups.values(), *ask.values()) for tool in tools}
    if unknown := referenced_tools - canonical_tools:
        raise ToolVocabularyError("unknown canonical tools: " + ", ".join(sorted(unknown)))

    # A spelling in two tables would be judged by whichever a reader consults
    # first, so the declaration refuses to say both.
    for table_name, table in (("passthrough", passthrough), ("refused", refused)):
        for harness, entries in table.items():
            if harness not in mappings:
                raise ToolVocabularyError(f"{table_name}.{harness} names a harness with no mapping")
            if overlap := sorted(
                spelling for spelling in mappings[harness] if any(fnmatch.fnmatchcase(spelling, e) for e in entries)
            ):
                raise ToolVocabularyError(f"{table_name}.{harness} covers mapped spellings: " + ", ".join(overlap))
    for harness, entries in refused.items():
        patterns = passthrough.get(harness, frozenset())
        if overlap := sorted(tool for tool in entries if any(fnmatch.fnmatchcase(tool, p) for p in patterns)):
            raise ToolVocabularyError(f"refused.{harness} names passthrough tools: " + ", ".join(overlap))

    return ToolVocabulary(groups, ask, MappingProxyType(mappings), passthrough, refused)


TOOL_VOCABULARY = load_tool_vocabulary()


def load_manifest(path: Path | str = MANIFEST_PATH) -> dict:
    """Parse the manifest at `path` into path lists per class; raise `ManifestError` on any failure."""
    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(str(exc)) from exc
    return _from_records(raw)


def _require_record(entry: object, keys: set[str], where: str) -> dict:
    if not isinstance(entry, dict) or set(entry) != keys:
        raise ManifestError(f"each {where} record needs exactly " + ", ".join(f"`{key}`" for key in sorted(keys)))
    if any(not isinstance(value, str) or not value.strip() for value in entry.values()):
        raise ManifestError(f"each {where} record needs nonempty " + ", ".join(f"`{key}`" for key in sorted(keys)))
    return entry


_TABLES = ("guarded", "enforcement-floor", "block", "exec-through", "write-through")


def _record_path(record: object, name: str) -> str:
    """Return a record's path; an enforcement-floor record may also carry `plugins = true`."""
    if name == "enforcement-floor" and isinstance(record, dict) and "plugins" in record:
        if record["plugins"] is not True:
            raise ManifestError("an enforcement-floor record's `plugins` must be `true`")
        record = {key: value for key, value in record.items() if key != "plugins"}
    return _require_record(record, {"path", "reason"}, f"{name}.paths")["path"]


def _from_records(raw: dict) -> dict:
    """Reduce each class's `[[<class>.paths]]` records to its paths, checking every record states a reason."""
    manifest = dict(raw)
    for name in _TABLES:
        table = raw.get(name)
        if not isinstance(table, dict):
            continue
        if set(table) - {"description", "paths"}:
            raise ManifestError(f"{name} holds keys other than `description` and `paths`")
        records = table.get("paths", [])
        if not isinstance(records, list):
            raise ManifestError(f"{name}.paths must be a list of records")
        manifest[name] = {"paths": [_record_path(r, name) for r in records]}
        if name == "enforcement-floor":
            manifest[name]["plugins"] = [r["path"] for r in records if "plugins" in r]
    if isinstance(raw.get("exceptions"), list):
        for exception in raw["exceptions"]:
            _require_record(exception, {"surface", "pattern", "reason"}, "exceptions")
    return manifest


def expand(path: str) -> str:
    """Expand home notation and normalize traversal without following links.

    Return paths containing a null byte unchanged.
    """
    try:
        return os.path.normpath(os.path.expanduser(path))
    except ValueError:
        return path


def expand_user(path: str, home: str) -> str:
    """Apply a caller's home notation, which need not be the process's own."""
    if path == "~":
        return home
    if path.startswith(_HOME_PREFIX):
        return os.path.join(home, path[len(_HOME_PREFIX) :])
    try:
        return os.path.expanduser(path)
    except ValueError:
        return path


def spellings(path: str) -> tuple[str, ...]:
    """Return the written, expanded, and resolved path spellings.

    Omit the resolved spelling if resolution fails.
    """
    expanded = expand(path)
    result = [path, expanded]
    if "\x00" in path:
        return tuple(result)
    try:
        pending = os.path.expanduser(path)
        if not os.path.isabs(pending):
            pending = os.path.join(os.getcwd(), pending)
        components = pending.split("/")
        current = "/"
        seen = set()
        while components:
            component = components.pop(0)
            if component in ("", "."):
                continue
            if component == "..":
                current = os.path.dirname(current)
                continue
            candidate = os.path.join(current, component)
            if os.path.islink(candidate):
                state = (candidate, tuple(components))
                if state in seen or len(seen) >= 40:
                    break
                seen.add(state)
                target = os.readlink(candidate)
                if os.path.isabs(target):
                    current = "/"
                components = target.split("/") + components
                hop = os.path.normpath(os.path.join(current, *components))
                if hop not in result:
                    result.append(hop)
            else:
                current = candidate
        resolved = os.path.realpath(os.path.expanduser(path))
        if len(result) == 2 or result[-1] != resolved:
            result.append(resolved)
    except (OSError, ValueError):
        pass
    return tuple(result)


@functools.cache
def folds_case(path: str) -> bool:
    """Return whether `path` resides on a case-insensitive filesystem."""
    current = os.path.abspath(path)
    while True:
        parent, name = os.path.split(current)
        if not name or parent == current:
            return False
        swapped = name.swapcase()
        if swapped != name and os.path.lexists(current):
            try:
                return os.path.samefile(current, os.path.join(parent, swapped))
            except OSError:
                return False
        current = parent


@functools.cache
def repo_root_of(path: str) -> str | None:
    """Return the repository containing `path`, including worktrees, or `None`."""
    current = path if os.path.isdir(path) else os.path.dirname(path)
    while current:
        if os.path.lexists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


def fragment(declaration: str) -> str:
    """Return the trailing portion of a declaration that identifies it in arbitrary text."""
    for prefix in (_HOME_PREFIX, _REPO_PREFIX):
        if declaration.startswith(prefix):
            return declaration[len(prefix) :]
    return declaration


def _forward(text: str) -> str:
    return text.replace("\\", "/")


def _both_cases(items: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Each item as written and case-folded, so a comparison can pick per path."""
    exact = tuple(_forward(item) for item in items)
    return exact, tuple(item.casefold() for item in exact)


# A path component contains only these characters.
_COMPONENT_CHAR = r"A-Za-z0-9_.\-"
_BOUNDARY = rf"[^{_COMPONENT_CHAR}]"

# `*` in a declaration stands for part of one path component. Against a path
# already split on separators the exclusion is redundant; against free text the
# match must also stop at whitespace.
_COMPONENT_GLOB = "[^/]*"
_TEXT_GLOB = r"[^/\s]*"


def _glob_expression(pattern: str, wildcard: str = _COMPONENT_GLOB) -> str:
    """Translate a declaration's `*` into a regular expression; `?` and `[` stay literal."""
    return re.escape(pattern).replace(r"\*", wildcard)


def _fragment_pattern(declaration: str) -> str:
    """Match declaration fragments on path boundaries, preserving glob components."""
    stem = _forward(fragment(declaration)).rstrip("/")
    right = rf"(?:$|{_BOUNDARY})"
    return rf"(?:^|{_BOUNDARY}|(?<=:-)){_glob_expression(stem, _TEXT_GLOB)}{right}"


@dataclass(frozen=True)
class Match:
    """A covering declaration and its distance above a supplied path."""

    declaration: str
    distance: int


def _distance(candidate: str, declaration: str, directory: bool) -> int | None:
    if "*" not in declaration:
        base = declaration.rstrip("/")
        candidate = candidate.rstrip("/")
        if candidate == base:
            return 0
        if directory and candidate.startswith(base + "/"):
            return candidate[len(base) + 1 :].count("/") + 1
        return None
    candidate_parts = candidate.rstrip("/").split("/")
    declared_parts = declaration.rstrip("/").split("/")
    distance = len(candidate_parts) - len(declared_parts)
    if distance < 0 or (distance and not directory):
        return None
    for part, pattern in zip(candidate_parts, declared_parts, strict=False):
        if re.fullmatch(_glob_expression(pattern), part) is None:
            return None
    return distance


class GuardedLocations:
    """Match path and text inputs against guarded declarations."""

    def __init__(
        self,
        declarations: Iterable[str],
        *,
        home: str = HOME,
        resolve_chain: Callable[[str], tuple[str, ...]] = spellings,
    ) -> None:
        self.declarations = tuple(declarations)
        self.home = home
        # A `<repo>/` declaration names a location in whichever checkout holds the
        # supplied path, so it has no chain until a path is matched against it.
        self._chains = {
            declaration: () if declaration.startswith(_REPO_PREFIX) else resolve_chain(expand_user(declaration, home))
            for declaration in self.declarations
        }
        # Text has no filesystem, so the home volume decides case folding for it.
        # Path checks use the path's volume.
        self.folds_case = folds_case(home)

        home_declarations = tuple(d for d in self.declarations if d.startswith(_HOME_PREFIX))
        self.fragments = tuple(fragment(d) for d in self.declarations)
        # `normalize` case-folds where the volume does, so the expressions carry
        # the matching flag rather than a second folded copy of each pattern.
        flags = re.IGNORECASE if self.folds_case else 0
        self._fragment_expressions = tuple(re.compile(_fragment_pattern(d), flags) for d in self.declarations)
        # Ancestor checks need unglobbed declaration components.
        self._home_relatives = _both_cases(
            declaration[len(_HOME_PREFIX) :].rstrip("/") for declaration in home_declarations
        )
        self._repo_relatives = _both_cases(
            declaration[len(_REPO_PREFIX) :].rstrip("/")
            for declaration in self.declarations
            if declaration.startswith(_REPO_PREFIX)
        )
        self._home_prefixes = _both_cases({home, os.path.realpath(home)})

    @property
    def chains(self) -> Mapping[str, tuple[str, ...]]:
        """Each declaration's link chain, resolved once at construction; a `<repo>/` declaration's is empty."""
        return MappingProxyType(self._chains)

    def normalize(self, text: str) -> str:
        """Put arbitrary text in the form comparisons against it are made in."""
        forward = _forward(text)
        return forward.casefold() if self.folds_case else forward

    def mentioned_in(self, text: str) -> bool:
        """Return whether text contains a guarded declaration fragment.

        Use `contains()` for a path.
        """
        normalized = self.normalize(text)
        return any(expression.search(normalized) for expression in self._fragment_expressions)

    @staticmethod
    def _spelling(path: str) -> tuple[str, int]:
        """`path` in comparable form, and which case of a pattern set to compare it against."""
        forward = _forward(path)
        if folds_case(path):
            return forward.casefold(), 1
        return forward, 0

    @staticmethod
    def _components(relative: str) -> list[str]:
        return [part for part in relative.split("/") if part and part != "."]

    def _proper_ancestor_of(self, relative: str, declarations: tuple[str, ...]) -> bool:
        """Return whether `relative` is a strict component-wise ancestor of a declaration."""
        parts = self._components(relative)
        for declaration in declarations:
            pattern = self._components(declaration)
            if len(parts) >= len(pattern):
                continue
            if all(
                re.fullmatch(_glob_expression(component), part) is not None
                for part, component in zip(parts, pattern, strict=False)
            ):
                return True
        return False

    def _encloses_home(self, resolved: str) -> bool:
        candidate, case = self._spelling(resolved)
        for prefix in self._home_prefixes[case]:
            if candidate == prefix:
                relative = ""
            elif candidate.startswith(f"{prefix}/"):
                relative = candidate[len(prefix) + 1 :]
            else:
                continue
            if self._proper_ancestor_of(relative, self._home_relatives[case]):
                return True
        return False

    def _encloses_repository(self, resolved: str) -> bool:
        root = repo_root_of(resolved)
        if root is None:
            return False
        relative, case = self._spelling(os.path.relpath(resolved, root))
        return self._proper_ancestor_of(relative, self._repo_relatives[case])

    def encloses(self, path: str, *, cwd: str | None = None) -> bool:
        """Return whether `path` is an ancestor of a guarded location."""
        if not path:
            return False
        expanded = expand_user(path, self.home)
        if not os.path.isabs(expanded):
            if cwd is None:
                return False
            expanded = os.path.join(cwd, expanded)
        return any(
            self._encloses_home(spelling) or self._encloses_repository(spelling) for spelling in spellings(expanded)
        )

    def locations_for(self, declaration: str, path: str) -> tuple[str, ...]:
        """Return the locations `declaration` names for a supplied path."""
        if not declaration.startswith(_REPO_PREFIX):
            return self._chains[declaration]
        root = repo_root_of(path)
        return (os.path.join(root, declaration[len(_REPO_PREFIX) :]),) if root else ()

    def matches_hop(self, path: str) -> list[Match]:
        """Return covering declarations without following the supplied hop again."""
        candidate, case = self._spelling(path)
        matches = []
        for declaration in self.declarations:
            distances = [
                distance
                for form in self.locations_for(declaration, path)
                if (
                    distance := _distance(
                        candidate,
                        _forward(form).casefold() if case else _forward(form),
                        declaration.endswith("/"),
                    )
                )
                is not None
            ]
            if distances:
                matches.append(Match(declaration, min(distances)))
        return matches

    def contains(self, path: str, *, cwd: str | None = None) -> list[Match]:
        """Return the declarations covering any spelling of `path`."""
        if not path:
            return []
        expanded = expand_user(path, self.home)
        if not os.path.isabs(expanded):
            if cwd is None:
                return [
                    Match(declaration, 0)
                    for declaration, expression in zip(self.declarations, self._fragment_expressions, strict=True)
                    if expression.search(self.normalize(path))
                ]
            expanded = os.path.join(cwd, expanded)
        found = {}
        for spelling in spellings(expanded):
            for match in self.matches_hop(spelling):
                found[match.declaration] = min(found.get(match.declaration, match.distance), match.distance)
        return [Match(declaration, distance) for declaration, distance in found.items()]


class EnforcementFloor(GuardedLocations):
    """Enforcement locations whose writes and runs no grant can permit."""

    def __init__(
        self,
        declarations: Iterable[str],
        *,
        hook_directories: Iterable[str] = (),
        home: str = HOME,
        resolve_chain: Callable[[str], tuple[str, ...]] = spellings,
    ) -> None:
        super().__init__(declarations, home=home, resolve_chain=resolve_chain)
        self.hook_directories = frozenset(hook_directories)

    def matches_hop(self, path: str) -> list[Match]:
        """Return the covering declarations, excluding a hook's own instructions directory."""
        matches = super().matches_hop(path)
        candidate, case = self._spelling(path)
        if not candidate.endswith(".md"):
            return matches
        return [
            match
            for match in matches
            if not (
                match.declaration in self.hook_directories
                and any(
                    _distance(
                        candidate,
                        (_forward(form).casefold() if case else _forward(form)).rstrip("/") + "/instructions/",
                        True,
                    )
                    is not None
                    for form in self.locations_for(match.declaration, path)
                )
            )
        ]


def _enforcement_files(directory: Path) -> Iterable[str]:
    """Enumerate hook sources through directory links, excluding bytecode caches."""
    seen = set()

    def visit(folder: Path) -> Iterable[str]:
        metadata = folder.stat()
        identity = metadata.st_dev, metadata.st_ino
        if identity in seen:
            return
        seen.add(identity)
        with os.scandir(folder) as entries:
            for entry in entries:
                if (
                    entry.name == "__pycache__"
                    or entry.name.endswith((".pyc", ".pyo"))
                    or (
                        Path(entry.path).relative_to(directory).parts[0] == "instructions"
                        and entry.name.lower().endswith(".md")
                    )
                ):
                    continue
                if entry.is_dir():
                    yield from visit(Path(entry.path))
                elif entry.is_file():
                    yield entry.path

    yield from visit(directory)


def _link_declarations(directory: Path) -> Iterable[str]:
    """Declare each link under a plugin install location, as a tree when it leads to a directory.

    A directory link is followed once, so a link inside a linked directory is declared too.
    """
    seen = set()

    def visit(folder: Path) -> Iterable[str]:
        metadata = folder.stat()
        identity = metadata.st_dev, metadata.st_ino
        if identity in seen:
            return
        seen.add(identity)
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_symlink():
                    leads_to_directory = entry.is_dir()
                    yield entry.path + "/" if leads_to_directory else entry.path
                    if leads_to_directory:
                        yield from visit(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    yield from visit(Path(entry.path))

    yield from visit(directory)


def _validate_manifest_shape(manifest: dict, names: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Return each class's path tuple, or raise TypeError if the manifest is malformed."""
    required = {*names, "exceptions"}
    if missing := required - set(manifest):
        raise TypeError("missing tables: " + ", ".join(sorted(missing)))
    if extra := set(manifest) - required:
        raise TypeError("unknown tables: " + ", ".join(sorted(extra)))
    if any(not isinstance(manifest[name]["paths"], list) for name in names):
        raise TypeError("class paths must be lists")
    entries = {name: tuple(manifest[name]["paths"]) for name in names}
    if not isinstance(manifest["exceptions"], list):
        raise TypeError("exceptions must be a list")
    for exception in manifest["exceptions"]:
        if not isinstance(exception, dict) or exception.get("surface") not in EXCEPTION_SURFACES:
            raise TypeError("unknown exception surface")
        if any(not isinstance(exception.get(key), str) or not exception[key] for key in ("pattern", "reason")):
            raise TypeError("exception pattern and reason must be nonempty strings")
        if exception["surface"] == "sensitive-path-dotenv-placeholder" and not _PLACEHOLDER_NAME.fullmatch(
            exception["pattern"]
        ):
            raise TypeError(
                f"a dotenv placeholder exception must be a file name `.env.<suffix>`: {exception['pattern']}"
            )
    if any(not isinstance(path, str) for paths in entries.values() for path in paths):
        raise TypeError("path declarations must be strings")
    return entries


# The grant class that loosens the guarded default for each operation, and the
# order a verdict resolves to when a path's hops disagree.
GRANT_CLASSES = MappingProxyType({"write": "write-through", "run": "exec-through"})
_PRIORITY = MappingProxyType({"undeclared": 0, "exec-through": 1, "write-through": 1, "guarded": 2, "block": 3})


@dataclass(frozen=True)
class Restriction:
    """A grant the enforcement floor keeps from reaching one path."""

    grant_class: str
    declaration: str
    path: str

    def __str__(self) -> str:
        return f"{self.grant_class} grant {self.declaration} does not apply to enforcement floor path: {self.path}"


class PathPolicy:
    """Class outcomes with explicit carve-outs and guarded defaults."""

    def __init__(
        self,
        manifest: dict,
        *,
        home: str = HOME,
        manifest_path: Path = MANIFEST_PATH,
        invocation_path: str | None = None,
        error: str | None = None,
    ) -> None:
        try:
            entries = _validate_manifest_shape(manifest, _TABLES)
        except (KeyError, TypeError) as exc:
            raise ManifestError(str(exc)) from exc
        floor = entries.pop("enforcement-floor")
        if misplaced := [p for paths in entries.values() for p in paths if p.startswith(_PROJECT_PREFIX)]:
            raise ManifestError(f"only the enforcement floor may use {_PROJECT_PREFIX}: " + ", ".join(misplaced))
        self._project_declarations = tuple(
            p.removeprefix(_PROJECT_PREFIX) for p in floor if p.startswith(_PROJECT_PREFIX)
        )
        self._floor_declarations = tuple(p for p in floor if not p.startswith(_PROJECT_PREFIX))
        self._floor_trees = tuple(p for p in self._floor_declarations if p.endswith("/"))
        self._floor_files = tuple(p for p in self._floor_declarations if not p.endswith("/"))
        plugin_locations = manifest["enforcement-floor"].get("plugins", [])
        if not isinstance(plugin_locations, list) or any(p not in self._floor_trees for p in plugin_locations):
            raise ManifestError("each plugin install location must be an enforcement-floor directory")
        self._plugin_locations = tuple(plugin_locations)
        # An exec-through declaration of the `skills/` directories inside a plugin
        # install location keeps its effect on runs inside the floor.
        self._plugin_skills = frozenset(
            declaration
            for declaration in entries["exec-through"]
            if declaration.endswith("/skills/")
            and any(declaration.startswith(location) for location in self._plugin_locations)
        )
        self.home = home
        self.error = error
        self._manifest_path = manifest_path
        self._invocation_path = invocation_path
        self._restrictions: dict[Restriction, None] = {}
        self._project_floors: dict[str | None, EnforcementFloor] = {}
        # This cache belongs to declarations only. Verdicts resolve supplied
        # paths afresh so a changed symlink cannot retain its earlier outcome.
        self._resolve_chain = functools.cache(spellings)
        entries["guarded"] += entries["exec-through"] + entries["write-through"]
        self.classes = {name: self._locations(paths) for name, paths in entries.items()}
        self._floor_locations = self._locations(self._floor_declarations)

    def _locations(self, declarations: Iterable[str]) -> GuardedLocations:
        return GuardedLocations(
            declarations,
            home=self.home,
            resolve_chain=self._resolve_chain,
        )

    @functools.cached_property
    def _floor_directories(self) -> tuple[Path, ...]:
        """Directories whose files are enforcement.

        They are the manifest's, this module's, the launcher's, the plugin directory
        holding this module, and each floor tree that is not a plugin install location.
        """
        module_directory = Path(__file__).resolve().parent
        directories = {self._manifest_path.parent, module_directory}
        if (module_directory.parent / ".claude-plugin" / "plugin.json").is_file():
            directories.add(module_directory.parent)
        if self._invocation_path:
            directories.add(Path(os.path.abspath(self._invocation_path)).parent)
        hook_trees = (tree for tree in self._floor_trees if tree not in self._plugin_locations)
        for chain in self._locations(hook_trees).chains.values():
            directories.update(Path(path) for form in chain[:1] for path in glob.glob(form) if os.path.isdir(path))
        return tuple(sorted(directories))

    @functools.cached_property
    def floor(self) -> EnforcementFloor:
        """Enforcement locations, enumerated from the filesystem on first use.

        A read never consults this, so the walk stays off the common path.
        """
        enforcement = dict.fromkeys(
            [
                str(self._manifest_path),
                *(path for directory in self._floor_directories for path in _enforcement_files(directory)),
                *(
                    path
                    for chain in self._locations(self._floor_files).chains.values()
                    for form in chain[:1]
                    for path in glob.glob(form)
                ),
            ]
        )
        links = (
            link
            for chain in self._locations(self._plugin_locations).chains.values()
            for form in chain[:1]
            for location in glob.glob(form)
            if os.path.isdir(location)
            for link in _link_declarations(Path(location))
        )
        trees = tuple(str(directory) + "/" for directory in self._floor_directories)
        return EnforcementFloor(
            (*self._floor_declarations, *enforcement, *links, *trees),
            hook_directories=(*self._floor_trees, *trees),
            home=self.home,
            resolve_chain=self._resolve_chain,
        )

    @functools.cached_property
    def guarded(self) -> GuardedLocations:
        """Every declared and enforced location, for text that does not resolve to a path."""
        return self._locations((*self.classes["guarded"].declarations, *self.floor.declarations))

    @property
    def findings(self) -> list[str]:
        """The floor restrictions the verdicts taken so far have reached."""
        return [str(restriction) for restriction in self._restrictions]

    def restricted_grants(self) -> list[Restriction]:
        """Grants whose own declared locations the enforcement floor covers."""
        return [
            Restriction(name, declaration, hop)
            for name in GRANT_CLASSES.values()
            for declaration, chain in self.classes[name].chains.items()
            if declaration not in self._plugin_skills
            for hop in sorted({hop for hop in chain if self.floor.matches_hop(hop)})
        ]

    def _project_floor(self, cwd: str | None) -> EnforcementFloor:
        """Return the project-anchored floor at `cwd` and each directory above it, globbed once per directory."""
        if cwd in self._project_floors:
            return self._project_floors[cwd]
        declarations = []
        if cwd:
            project = Path(cwd).absolute()
            for root in (project, *project.parents):
                for suffix in self._project_declarations:
                    pattern = str(root / suffix) + ("/" if suffix.endswith("/") else "")
                    declarations.extend((pattern, *glob.glob(pattern)))
        floor = EnforcementFloor(
            declarations,
            home=self.home,
            resolve_chain=self._resolve_chain,
        )
        self._project_floors[cwd] = floor
        return floor

    def _hop_verdict(self, path: str, operation: str, project_floor: EnforcementFloor | None = None) -> str:
        if self.classes["block"].matches_hop(path):
            return "block"
        if operation == "read":
            return "undeclared"
        grant_class = GRANT_CLASSES[operation]
        if self.floor.matches_hop(path) or (project_floor and project_floor.matches_hop(path)):
            grants = self.classes[grant_class].matches_hop(path)
            if operation == "run" and any(match.declaration in self._plugin_skills for match in grants):
                return grant_class
            for match in grants:
                self._restrictions[Restriction(grant_class, match.declaration, path)] = None
            return "guarded"
        candidates = [
            (match.distance, name == "guarded", name)
            for name in ("guarded", grant_class)
            for match in self.classes[name].matches_hop(path)
        ]
        if candidates:
            return min(candidates)[2]
        # The instruction text the floor leaves out still asks when no declaration covers it.
        return "guarded" if self._floor_locations.matches_hop(path) else "undeclared"

    def verdict(self, path: str, operation: str, *, cwd: str | None = None) -> str:
        """Return the strictest class reached by any hop of a supplied path."""
        if operation not in {"read", *GRANT_CLASSES}:
            raise ValueError(f"unknown operation: {operation}")
        expanded = expand_user(path, self.home)
        if not os.path.isabs(expanded):
            if cwd is None:
                if self.classes["block"].mentioned_in(path):
                    return "block"
                return "guarded" if self.guarded.mentioned_in(path) else "undeclared"
            expanded = os.path.join(cwd, expanded)
        project_floor = self._project_floor(cwd) if operation != "read" else None
        return max(
            (self._hop_verdict(hop, operation, project_floor) for hop in spellings(expanded)),
            key=_PRIORITY.__getitem__,
        )

    def validate(self) -> list[str]:
        """Report restricted grants and conflicts, and inspect carve-out children."""
        findings = [str(restriction) for restriction in self.restricted_grants()]
        blocked = self.classes["block"]
        for operation, name in GRANT_CLASSES.items():
            locations = self.classes[name]
            for declaration, chain in locations.chains.items():
                for blocked_declaration, blocked_chain in blocked.chains.items():
                    if any(
                        match.declaration == blocked_declaration and match.distance == 0
                        for hop in chain
                        for match in blocked.matches_hop(hop)
                    ) or any(
                        match.declaration == declaration and match.distance == 0
                        for hop in blocked_chain
                        for match in locations.matches_hop(hop)
                    ):
                        findings.append(
                            f"{name} declaration {declaration} conflicts with block declaration {blocked_declaration}"
                        )
                if not declaration.endswith("/") or "*" in declaration or not chain:
                    continue
                directory = Path(chain[-1])
                if not directory.is_dir():
                    continue
                for entry in directory.iterdir():
                    if not entry.is_symlink():
                        continue
                    target = os.path.realpath(entry)
                    if self._hop_verdict(target, operation) in {"guarded", "block"}:
                        advice = (
                            "a grant cannot override block or the enforcement floor"
                            if self.floor.matches_hop(target) or blocked.matches_hop(target)
                            else "declare the target explicitly to permit it"
                        )
                        findings.append(
                            f"{name} declaration {declaration}: link {entry} reaches stricter target {target}; {advice}"
                        )
        return findings


_EMPTY_MANIFEST = {
    "guarded": {"paths": []},
    "enforcement-floor": {"paths": []},
    "block": {"paths": []},
    "exec-through": {"paths": []},
    "write-through": {"paths": []},
    "exceptions": [],
}


def load_policy(manifest_path: Path = MANIFEST_PATH, *, invocation_path: str | None = None) -> PathPolicy:
    """Build the policy for `manifest_path`, or an empty one naming why it could not be built.

    A caller that holds the result alone knows both whether the manifest loaded
    and what it declares, so no second binding can go stale against it.
    """
    try:
        return PathPolicy(
            load_manifest(manifest_path),
            manifest_path=manifest_path,
            invocation_path=invocation_path,
        )
    except Exception as exc:  # noqa: BLE001 -- the caller decides what a failed load does to a tool call
        return PathPolicy(_EMPTY_MANIFEST, manifest_path=manifest_path, error=str(exc))


def validate(manifest: Path | str = MANIFEST_PATH) -> list[str]:
    """Load and validate a manifest, returning floor restrictions and conflicts."""
    path = Path(manifest)
    return PathPolicy(load_manifest(path), manifest_path=path).validate()


# Exempt package and hook trees from name-only credential checks. Do not exempt
# bare `env` directories because they can contain credentials.
NAME_HEURISTIC_EXEMPT_RE = re.compile(
    r"(?:^|[/\\])"
    r"(?:\.venv|venv|site-packages|node_modules|\.claude"
    r"|(?:claude|codex|copilot|pi|shared)[/\\](?:hooks|security|tests))"
    r"(?:[/\\]|$)",
    re.IGNORECASE,
)
