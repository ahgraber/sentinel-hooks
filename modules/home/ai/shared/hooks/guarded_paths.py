"""Decide whether a path denotes a location the caller must not modify.

Declarations take one form — `~/.codex/rules/`,
`<repo>/modules/home/ai/shared/hooks/`, `<repo>/users/*/home-manager/codex/` —
and `<repo>` means the repository containing the path under test, found by
walking up to a `.git` entry, which is what covers a worktree or a second clone.

A path is judged by containment in every form it can take: as written, home
expanded, and fully resolved. All three are needed. A declaratively managed file
sits inside a guarded directory as written while resolving outside it (Home
Manager keeps the real file in the Nix store, sops-nix in its secrets mount), so
the resolved form alone would miss it; the written form alone would miss a path
reaching a guarded directory through a link.

Matching text against the declarations is a separate question, asked only of
text that may hold no path at all, such as a whole shell command. Asking it of a
path would refuse a backup directory that merely shares a name with a guarded
one. A `location_only` declaration contributes no text to match: a directory as
broad as `~/.claude/` has no written form specific enough to match as text
without also refusing every command that names a session file.

Letter case is significant where the volume makes it significant, not the
operating system, so each path is judged against its own volume — a checkout, a
worktree, and a home directory need not share one.

Limits, all accepted: a relative path resolves against the working directory the
hook runs in, so one named against a different directory is judged there; a
working-directory change within one shell command; hard links; a tree that is
not a repository, such as an unpacked archive; and any route that presents no
path. This is defence in depth; the sandbox and the agent permission layer are
the boundary.
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

# Beside this module, so every deployed copy of the hooks directory carries its
# own. A caller may override the location to run against a substituted manifest.
MANIFEST_PATH = Path(__file__).parent / "guarded-paths.toml"


class ManifestError(Exception):
    """The manifest could not be read or parsed."""


def load_manifest(path: Path | str = MANIFEST_PATH) -> dict:
    """Parse the guarded-paths manifest at `path`. Raises `ManifestError` on any failure.

    The caller owns the failure mode: a hook that cannot load its declarations
    judges nothing, so the tool call proceeds and the failure is reported where
    the agent can show it.
    """
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(str(exc)) from exc


def expand(path: str) -> str:
    """Apply home notation and traversal components, without following links."""
    return os.path.normpath(os.path.expanduser(path))


def spellings(path: str) -> tuple[str, ...]:
    """Every form `path` must be judged in: as written, expanded, and resolved.

    Resolution is the layer that can fail; the tuple ends early rather than
    letting the failure discard what the earlier forms established.
    """
    expanded = expand(path)
    try:
        return (path, expanded, os.path.realpath(expanded))
    except (OSError, ValueError):
        return (path, expanded)


@functools.cache
def folds_case(path: str) -> bool:
    """True where the filesystem holding `path` treats two spellings that differ only in case as one file."""
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
    """The repository holding `path`, or None. A worktree's `.git` is a file, not a directory."""
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


class GuardedLocations:
    """The locations one caller guards, and the question it asks about a path."""

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
        # For the text layer only: command text has no filesystem of its own to
        # probe, so either volume folding is enough. A path is judged against
        # its own volume instead.
        self.folds_case = folds_case(repo_root) or folds_case(home)

        home_declarations = tuple(
            d
            for d in self.declarations + self.location_only
            if d.startswith(_HOME_PREFIX)
        )
        self.fragments = tuple(fragment(d) for d in self.declarations)
        self._fragments = _both_cases(self.fragments)
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
        """True if `text` names a guarded location anywhere within it, including a whole shell command.

        For text that may hold no path at all; a path is judged by `contains`,
        which asks where it leads rather than what it looks like.
        """
        normalized = self.normalize(text)
        fragments = self._fragments[1 if self.folds_case else 0]
        return any(fragment in normalized for fragment in fragments)

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

    def contains(self, path: str) -> bool:
        """True if `path` denotes a guarded location, however it is spelled."""
        if not path:
            return False
        expanded = self._expand(path)
        if not os.path.isabs(expanded) and self.mentioned_in(path):
            # A relative path means whatever the working directory makes it
            # mean, and the hook is not told that directory, so it is refused on
            # shape. An absolute one is judged by where it leads instead, which
            # leaves a backup directory of the same name alone.
            return True
        return any(
            self._within_home(spelling) or self._within_repository(spelling)
            for spelling in spellings(expanded)
        )


# Name-based credential heuristics ('secret', 'credentials') are unreliable
# inside these directories: package trees name modules after what they wrap, and
# this repository's hook sources are named for what they guard against. A bare
# `env` component is deliberately absent — a directory named `env/` can hold
# real secrets.
NAME_HEURISTIC_EXEMPT_RE = re.compile(
    r"(?:^|[/\\])"
    r"(?:\.venv|venv|site-packages|node_modules|\.claude"
    r"|(?:claude|codex|copilot|shared)[/\\](?:hooks|tests))"
    r"(?:[/\\]|$)",
    re.IGNORECASE,
)
