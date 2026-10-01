"""Match paths and text against manifest-declared guarded locations.

Declarations support `~/`, `<repo>/`, and single-component `*` patterns. Path
checks use written, expanded, and resolved spellings with filesystem case rules.
Text checks use declaration fragments.

Limits: working-directory changes within one shell command are deferred; name
paths absolutely. Hard links are not identified. A directory declaration follows
its own symlink chain, not links held inside that directory. Routes that present
no path cannot be checked. The operating system sandbox and agent permissions
are the boundary; this matcher supplies defense in depth.
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
from types import MappingProxyType

import tomllib

HOME = os.path.expanduser("~")
# guarded_paths.py -> hooks/ -> shared/ -> ai/ -> home/ -> modules/ -> repo root.
REPO_ROOT = str(Path(__file__).resolve().parents[5])

_HOME_PREFIX = "~/"
_REPO_PREFIX = "<repo>/"

# Keep the manifest beside the module so deployed copies carry it. Callers can
# override it for tests.
MANIFEST_PATH = Path(__file__).parent / "guarded-paths.toml"
TOOL_VOCABULARY_PATH = Path(__file__).parent / "tool-vocabulary.toml"
# `capability-coverage` excuses an agent from running a hook; no hook reads it, only the assessment.
EXCEPTION_SURFACES = frozenset(
    {"sensitive-path-name-heuristic", "sensitive-path-nix-hook-wrapper", "capability-coverage"}
)


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


def load_tool_vocabulary(path: Path | str = TOOL_VOCABULARY_PATH) -> ToolVocabulary:
    """Load and validate the declared tool vocabulary."""
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ToolVocabularyError(str(exc)) from exc

    if set(data) != {"groups", "ask", "mappings", "passthrough"}:
        raise ToolVocabularyError("expected groups, ask, mappings, and passthrough tables")

    groups = _tool_sets(data["groups"], "groups")
    ask = _tool_sets(data["ask"], "ask")
    passthrough = _tool_sets(data["passthrough"], "passthrough")
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

    # A spelling that is both mapped and passthrough would be judged by whichever
    # the adapter consults first, so the declaration refuses to say both.
    for harness, entries in passthrough.items():
        if harness not in mappings:
            raise ToolVocabularyError(f"passthrough.{harness} names a harness with no mapping")
        if overlap := sorted(
            spelling for spelling in mappings[harness] if any(fnmatch.fnmatchcase(spelling, e) for e in entries)
        ):
            raise ToolVocabularyError(f"passthrough.{harness} covers mapped spellings: " + ", ".join(overlap))

    return ToolVocabulary(groups, ask, MappingProxyType(mappings), passthrough)


TOOL_VOCABULARY = load_tool_vocabulary()


def load_manifest(path: Path | str = MANIFEST_PATH) -> dict:
    """Parse the manifest at `path`; raise `ManifestError` on read or parse failure."""
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(str(exc)) from exc


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
        repo_root: str = REPO_ROOT,
        resolve_chain: Callable[[str], tuple[str, ...]] = spellings,
    ) -> None:
        self.declarations = tuple(declarations)
        self.home = home
        self.repo_root = repo_root
        self._chains = {}
        for declaration in self.declarations:
            location = declaration
            if location.startswith(_REPO_PREFIX):
                location = os.path.join(repo_root, location[len(_REPO_PREFIX) :])
            self._chains[declaration] = resolve_chain(expand_user(location, home))
        # Text has no filesystem, so either configured volume can enable case
        # folding. Path checks use the path's volume.
        self.folds_case = folds_case(repo_root) or folds_case(home)

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
        """Each declaration's link chain, resolved once at construction."""
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

    def matches_hop(self, path: str) -> list[Match]:
        """Return covering declarations without following the supplied hop again."""
        candidate, case = self._spelling(path)
        matches = []
        for declaration, chain in self.chains.items():
            forms = list(chain)
            if declaration.startswith(_REPO_PREFIX):
                root = repo_root_of(path)
                if root:
                    forms.append(os.path.join(root, declaration[len(_REPO_PREFIX) :]))
            distances = [
                distance
                for form in forms
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


HOOK_DIRECTORIES = (
    "~/.claude/hooks/",
    "~/.codex/hooks/",
    "~/.copilot/hooks/",
    "~/.pi/agent/extensions/hooks/",
    "~/.pi/agent/hooks/",
    "<repo>/modules/home/ai/shared/hooks/",
    "<repo>/modules/home/ai/claude/hooks/",
    "<repo>/modules/home/ai/codex/hooks/",
    "<repo>/modules/home/ai/copilot/hooks/",
    "<repo>/modules/home/ai/pi/security/",
    "<repo>/modules/home/ai/pi/hooks/",
)
PERMISSION_FILES = (
    "~/.claude/settings.json",
    "~/.claude/settings.local.json",
    "~/.claude/settings*.json",
    "~/.codex/config.toml",
    "~/.codex/*.config.toml",
    "~/.codex/hooks.json",
    "~/.codex/rules/",
    "~/.pi/agent/settings.json",
    "~/.pi/agent/hooks.json",
    "~/Library/Application Support/Code/User/settings.json",
    "~/.config/Code/User/settings.json",
    "<repo>/users/*/home-manager/claude/settings*.json",
    "<repo>/users/*/home-manager/codex/config*.toml",
    "<repo>/users/*/home-manager/codex/*.config.toml",
    "<repo>/users/*/home-manager/codex/hooks.json",
    "<repo>/modules/home/ai/codex/rules/",
    "<repo>/users/*/home-manager/pi/settings.json",
    "<repo>/modules/home/apps/vscode/settings.json",
    "<repo>/users/*/home-manager/vscode/settings.json",
    "<repo>/.claude/settings*.json",
    "<repo>/.codex/config.toml",
    "<repo>/.codex/*.config.toml",
    "<repo>/.codex/hooks.json",
    "<repo>/.codex/rules/",
    "<repo>/.vscode/settings.json",
)


class EnforcementFloor(GuardedLocations):
    """Enforcement locations whose writes and runs no grant can permit."""

    def __init__(
        self,
        declarations: Iterable[str],
        *,
        hook_directories: Iterable[str] = (),
        home: str = HOME,
        repo_root: str = REPO_ROOT,
        resolve_chain: Callable[[str], tuple[str, ...]] = spellings,
    ) -> None:
        super().__init__(declarations, home=home, repo_root=repo_root, resolve_chain=resolve_chain)
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
                    for form in self.chains[match.declaration]
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
        if any(not isinstance(exception.get(key), str) or not exception[key] for key in ("pattern", "why")):
            raise TypeError("exception pattern and why must be nonempty strings")
    if any(not isinstance(path, str) for paths in entries.values() for path in paths):
        raise TypeError("path declarations must be strings")
    return entries


# The grant class that loosens the guarded default for each operation, and the
# order a verdict resolves to when a path's hops disagree.
GRANT_CLASSES = MappingProxyType({"write": "write-through", "run": "exec-through"})
_PRIORITY = MappingProxyType({"undeclared": 0, "exec-through": 1, "write-through": 1, "guarded": 2, "block": 3})

# Permission files a project carries, relative to the working directory or any
# directory above it.
PROJECT_PERMISSION_FILES = (
    ".claude/settings*.json",
    ".codex/config.toml",
    ".codex/*.config.toml",
    ".codex/hooks.json",
    ".codex/rules/",
    ".vscode/settings.json",
)


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
        repo_root: str = REPO_ROOT,
        manifest_path: Path = MANIFEST_PATH,
        invocation_path: str | None = None,
        error: str | None = None,
    ) -> None:
        names = ("guarded", "block", "exec-through", "write-through")
        try:
            entries = _validate_manifest_shape(manifest, names)
        except (KeyError, TypeError) as exc:
            raise ManifestError(str(exc)) from exc
        self.home = home
        self.repo_root = repo_root
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

    def _locations(self, declarations: Iterable[str]) -> GuardedLocations:
        return GuardedLocations(
            declarations,
            home=self.home,
            repo_root=self.repo_root,
            resolve_chain=self._resolve_chain,
        )

    @functools.cached_property
    def _hook_directories(self) -> tuple[Path, ...]:
        """Directories holding hook sources: the manifest's, this module's, the launcher's, and each declared tree."""
        directories = {self._manifest_path.parent, Path(__file__).resolve().parent}
        if self._invocation_path:
            directories.add(Path(os.path.abspath(self._invocation_path)).parent)
        for chain in self._locations(HOOK_DIRECTORIES).chains.values():
            directories.update(Path(path) for path in glob.glob(chain[0]) if os.path.isdir(path))
        return tuple(sorted(directories))

    @functools.cached_property
    def floor(self) -> EnforcementFloor:
        """Enforcement locations, enumerated from the filesystem on first use.

        A read never consults this, so the walk stays off the common path.
        """
        enforcement = dict.fromkeys(
            [
                str(self._manifest_path),
                *(path for directory in self._hook_directories for path in _enforcement_files(directory)),
                *(path for chain in self._locations(PERMISSION_FILES).chains.values() for path in glob.glob(chain[0])),
            ]
        )
        trees = tuple(str(directory) + "/" for directory in self._hook_directories)
        return EnforcementFloor(
            (*HOOK_DIRECTORIES, *PERMISSION_FILES, *enforcement, *trees),
            hook_directories=(*HOOK_DIRECTORIES, *trees),
            home=self.home,
            repo_root=self.repo_root,
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
            for hop in sorted({hop for hop in chain if self.floor.matches_hop(hop)})
        ]

    def _project_floor(self, cwd: str | None) -> EnforcementFloor:
        """Return the permission files of the project at `cwd`, globbed once per directory."""
        if cwd in self._project_floors:
            return self._project_floors[cwd]
        declarations = []
        if cwd:
            project = Path(cwd).absolute()
            for root in (project, *project.parents):
                for suffix in PROJECT_PERMISSION_FILES:
                    pattern = str(root / suffix) + ("/" if suffix.endswith("/") else "")
                    declarations.extend((pattern, *glob.glob(pattern)))
        floor = EnforcementFloor(
            declarations,
            home=self.home,
            repo_root=self.repo_root,
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
            for match in self.classes[grant_class].matches_hop(path):
                self._restrictions[Restriction(grant_class, match.declaration, path)] = None
            return "guarded"
        candidates = [
            (match.distance, name == "guarded", name)
            for name in ("guarded", grant_class)
            for match in self.classes[name].matches_hop(path)
        ]
        return min(candidates)[2] if candidates else "undeclared"

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
                if not declaration.endswith("/") or "*" in declaration:
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


def verdict(
    path: str,
    operation: str,
    *,
    policy: PathPolicy | None = None,
    cwd: str | None = None,
) -> str:
    """Judge a path using a loaded policy, or the deployed manifest."""
    if policy is None:
        policy = PathPolicy(load_manifest())
    return policy.verdict(path, operation, cwd=cwd)


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
