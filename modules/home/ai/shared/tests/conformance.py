"""What the conformance suites share: the manifest, the surfaces, and how a pattern is judged.

The guarded-source floor and the secret floor both ask whether a pattern covers
a path; a second copy of that answer is a second place for it to be wrong.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import tomllib

REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)
MANIFEST = Path(__file__).parent.parent / "hooks" / "guarded-paths.toml"

CLAUDE_SETTINGS = sorted(REPO_ROOT.glob("users/*/home-manager/claude/settings*.json"))
CODEX_CONFIGS = sorted(REPO_ROOT.glob("users/*/home-manager/codex/config*.toml"))
# The module file is the deployed source (mkRepoSymlink); per-user profiles may
# carry their own copy alongside it.
VSCODE_SETTINGS = sorted(
    REPO_ROOT.glob("users/*/home-manager/vscode/settings.json")
) + sorted(REPO_ROOT.glob("modules/home/apps/vscode/settings.json"))


def load_manifest() -> dict:
    with open(MANIFEST, "rb") as handle:
        return tomllib.load(handle)


def representative(declaration: str) -> str:
    """A concrete path standing for `declaration`.

    Coverage is judged by matching a path, not by comparing pattern text: a
    pattern that looks right and does not match is the failure being checked for.
    """
    if declaration.endswith("/"):
        return f"{declaration}example"
    if "*" in declaration:
        return declaration.replace("*", "example")
    return declaration


def glob_covers(pattern: str, path: str) -> bool:
    """True if a surface's pattern covers the concrete path.

    `fnmatch`'s `*` crosses `/`, matching how the permission layer and the
    sandbox treat `**`; a directory pattern also covers what is below it.
    """
    flattened = pattern.replace("**", "*")
    return (
        fnmatchcase(path, flattened)
        or fnmatchcase(path, f"{flattened.rstrip('/')}/*")
        or path == pattern.rstrip("/")
        or path.startswith(f"{pattern.rstrip('/')}/")
    )
