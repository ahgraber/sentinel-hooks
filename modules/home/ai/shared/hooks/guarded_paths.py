"""Match paths and text against manifest-declared guarded locations.

Declarations support `~/`, `<repo>/`, and single-component `*` patterns. Path
checks use written, expanded, and resolved spellings with filesystem case rules.
Text checks use declaration fragments.
"""

from __future__ import annotations

import functools
import os
import re
from collections.abc import Iterable
from fnmatch import fnmatchcase
from pathlib import Path

import tomllib

HOME = os.path.expanduser("~")
# guarded_paths.py -> hooks/ -> shared/ -> ai/ -> home/ -> modules/ -> repo root.
REPO_ROOT = str(Path(__file__).resolve().parents[5])

_HOME_PREFIX = "~/"
_REPO_PREFIX = "<repo>/"

# Keep the manifest beside the module so deployed copies carry it. Callers can
# override it for tests.
MANIFEST_PATH = Path(__file__).parent / "guarded-paths.toml"


class ManifestError(Exception):
    """The manifest could not be read or parsed."""


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


def spellings(path: str) -> tuple[str, ...]:
    """Return the written, expanded, and resolved path spellings.

    Omit the resolved spelling if resolution fails.
    """
    expanded = expand(path)
    try:
        return (path, expanded, os.path.realpath(expanded))
    except (OSError, ValueError):
        return (path, expanded)


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
    """The trailing portion of a declaration that identifies it in arbitrary text."""
    star = declaration.rfind("*")
    if star != -1:
        return declaration[star + 1 :].lstrip("/")
    for prefix in (_HOME_PREFIX, _REPO_PREFIX):
        if declaration.startswith(prefix):
            return declaration[len(prefix) :]
    return declaration


def _patterns(relative: str) -> tuple[str, ...]:
    """Glob patterns a declaration's relative part matches."""
    if relative.endswith("/"):
        base = relative.rstrip("/")
        return (base, f"{base}/*")
    return (relative,)


def _home_location(declaration: str, home: str) -> str | None:
    """The absolute location a `~` declaration names, or None if it names a shape."""
    relative = declaration[len(_HOME_PREFIX) :]
    if "*" in relative:
        return None
    return os.path.realpath(os.path.join(home, relative.rstrip("/")))


def _forward(text: str) -> str:
    return text.replace("\\", "/")


def _both_cases(items: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Each item as written and case-folded, so a comparison can pick per path."""
    exact = tuple(_forward(item) for item in items)
    return exact, tuple(item.casefold() for item in exact)


# A path component contains only these characters.
_COMPONENT_CHAR = r"A-Za-z0-9_.\-"
_BOUNDARY = rf"[^{_COMPONENT_CHAR}]"


def _fragment_pattern(declaration: str) -> str:
    """Return a regex that matches a declaration fragment on path boundaries.

    Wildcard declarations match only the fragment's right boundary because
    `fragment()` returns the suffix after `*`.
    """
    stem = _forward(fragment(declaration)).rstrip("/")
    right = rf"(?:$|{_BOUNDARY})"
    if "*" in declaration:
        return rf"{re.escape(stem)}{right}"
    return rf"(?:^|{_BOUNDARY}){re.escape(stem)}{right}"


class GuardedLocations:
    """Match path and text inputs against guarded declarations."""

    def __init__(
        self,
        declarations: Iterable[str],
        *,
        location_only: Iterable[str] = (),
        home: str = HOME,
        repo_root: str = REPO_ROOT,
    ) -> None:
        self.declarations = tuple(declarations)
        self.location_only = tuple(location_only)
        self.home = home
        # Text has no filesystem, so either configured volume can enable case
        # folding. Path checks use the path's volume.
        self.folds_case = folds_case(repo_root) or folds_case(home)

        home_declarations = tuple(
            d
            for d in self.declarations + self.location_only
            if d.startswith(_HOME_PREFIX)
        )
        self.fragments = tuple(fragment(d) for d in self.declarations)
        # `normalize` case-folds where the volume does, so the expressions carry
        # the matching flag rather than a second folded copy of each pattern.
        flags = re.IGNORECASE if self.folds_case else 0
        self._fragment_expressions = tuple(
            re.compile(_fragment_pattern(d), flags) for d in self.declarations
        )
        self._repo_patterns = _both_cases(
            pattern
            for declaration in self.declarations
            if declaration.startswith(_REPO_PREFIX)
            for pattern in _patterns(declaration[len(_REPO_PREFIX) :])
        )
        self._home_patterns = _both_cases(
            pattern
            for declaration in home_declarations
            for pattern in _patterns(declaration[len(_HOME_PREFIX) :])
        )
        # Ancestor checks need unglobbed declaration components.
        self._home_relatives = _both_cases(
            declaration[len(_HOME_PREFIX) :].rstrip("/")
            for declaration in home_declarations
        )
        self._repo_relatives = _both_cases(
            declaration[len(_REPO_PREFIX) :].rstrip("/")
            for declaration in self.declarations
            if declaration.startswith(_REPO_PREFIX)
        )
        self._home_prefixes = _both_cases({home, os.path.realpath(home)})
        self._locations = _both_cases(
            location
            for declaration in home_declarations
            if (location := _home_location(declaration, home)) is not None
        )

    def normalize(self, text: str) -> str:
        """Put arbitrary text in the form comparisons against it are made in."""
        forward = _forward(text)
        return forward.casefold() if self.folds_case else forward

    def mentioned_in(self, text: str) -> bool:
        """Return whether text contains a guarded declaration fragment.

        Use `contains()` for a path.
        """
        normalized = self.normalize(text)
        return any(
            expression.search(normalized) for expression in self._fragment_expressions
        )

    @staticmethod
    def _spelling(path: str) -> tuple[str, int]:
        """`path` in comparable form, and which case of a pattern set to compare it against."""
        forward = _forward(path)
        if folds_case(path):
            return forward.casefold(), 1
        return forward, 0

    def _within_home(self, resolved: str) -> bool:
        candidate, case = self._spelling(resolved)
        if any(
            candidate == location or candidate.startswith(f"{location}/")
            for location in self._locations[case]
        ):
            return True
        for prefix in self._home_prefixes[case]:
            if candidate.startswith(f"{prefix}/"):
                relative = candidate[len(prefix) + 1 :]
                if any(fnmatchcase(relative, p) for p in self._home_patterns[case]):
                    return True
        return False

    def _within_repository(self, resolved: str) -> bool:
        root = repo_root_of(resolved)
        if root is None:
            return False
        relative, case = self._spelling(os.path.relpath(resolved, root))
        return any(fnmatchcase(relative, p) for p in self._repo_patterns[case])

    def _expand(self, path: str) -> str:
        """Apply this caller's home notation, which need not be the process's own."""
        if path == _HOME_PREFIX[:-1]:
            return self.home
        if path.startswith(_HOME_PREFIX):
            return os.path.normpath(os.path.join(self.home, path[len(_HOME_PREFIX) :]))
        return expand(path)

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
            if all(fnmatchcase(part, glob) for part, glob in zip(parts, pattern)):
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

    def encloses(self, path: str) -> bool:
        """Return whether `path` is an ancestor of a guarded location."""
        if not path:
            return False
        return any(
            self._encloses_home(spelling) or self._encloses_repository(spelling)
            for spelling in spellings(self._expand(path))
        )

    def contains(self, path: str) -> bool:
        """True if `path` denotes a guarded location, however it is spelled."""
        if not path:
            return False
        expanded = self._expand(path)
        if not os.path.isabs(expanded) and self.mentioned_in(path):
            # The hook lacks the caller's working directory, so judge relative
            # paths by shape. Judge absolute paths by destination.
            return True
        return any(
            self._within_home(spelling) or self._within_repository(spelling)
            for spelling in spellings(expanded)
        )


# Exempt package and hook trees from name-only credential checks. Do not exempt
# bare `env` directories because they can contain credentials.
NAME_HEURISTIC_EXEMPT_RE = re.compile(
    r"(?:^|[/\\])"
    r"(?:\.venv|venv|site-packages|node_modules|\.claude"
    r"|(?:claude|codex|copilot|pi|shared)[/\\](?:hooks|security|tests))"
    r"(?:[/\\]|$)",
    re.IGNORECASE,
)
