"""Every place a guarded repository source is named must name the same set.

The hook, Claude deny rules, Codex permission entries, and VS Code edit
auto-approval globs cannot import each other, and each spells a location
differently, so comparison is by what a pattern matches on disk. What the hook
guards is a floor: a permission layer may gate more, never less.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import tomllib
from conformance import (
    CLAUDE_SETTINGS,
    CODEX_CONFIGS,
    REPO_ROOT,
    VSCODE_SETTINGS,
    glob_covers,
    load_manifest,
    representative,
)

REPO_SOURCE_ROOTS = ("modules/", "users/")
CLAUDE_RULE_RE = re.compile(r"^Edit\(~/\.nixconfig/(?P<pattern>.+?)\)$")
CLAUDE_HOME_RULE_RE = re.compile(r"^Edit\((?P<pattern>~/(?!\.nixconfig/).+?)\)$")

DEPLOYED = [
    (declaration, representative(declaration))
    for declaration in load_manifest()["gated"]["deployed"]
]

# An instruction layer is enforcement too: text placed in one steers whichever
# agent loads it, so its location needs the same permission floor a gated file
# has. The repository-side locations are already covered as sources, so only the
# deployed `~/` half is added here.
DEPLOYED_LAYERS = [
    (location, representative(location))
    for location, _fragment in load_manifest()["instruction-layers"]["layers"]
    if location.startswith("~/")
]


def _matched(patterns: list[str]) -> set[str]:
    """Resolve repository-relative patterns to the paths they match now."""
    found: set[str] = set()
    for pattern in patterns:
        trimmed = pattern.rstrip("/").removesuffix("/**")
        found.update(
            str(match.relative_to(REPO_ROOT)) for match in REPO_ROOT.glob(trimmed)
        )
    return found


def _is_repo_source(pattern: str) -> bool:
    return pattern.startswith(REPO_SOURCE_ROOTS)


def hook_sources() -> set[str]:
    """Every declaration the manifest names, in the notation the hooks judge by.

    Mirrors how `block-hook-tampering.py` builds `GuardedLocations`: an
    instruction layer's location is guarded even though its markdown is not.
    """
    manifest = load_manifest()
    declarations = (
        manifest["gated"]["deployed"]
        + manifest["gated"]["sources"]
        + [location for location, _layer in manifest["instruction-layers"]["layers"]]
    )
    return _matched(
        [d.removeprefix("<repo>/") for d in declarations if d.startswith("<repo>/")]
    )


def declared_exceptions(surface: str) -> set[str]:
    """The patterns the manifest excepts for `surface`."""
    return {
        exception["pattern"]
        for exception in load_manifest().get("exceptions", [])
        if exception["surface"] == surface
    }


def claude_guarded_sources(settings_path: Path) -> set[str]:
    """Repository sources a Claude settings file gates, by refusing or by asking."""
    permissions = json.loads(settings_path.read_text()).get("permissions", {})
    rules = permissions.get("deny", []) + permissions.get("ask", [])
    patterns = [
        match.group("pattern")
        for rule in rules
        if (match := CLAUDE_RULE_RE.match(rule))
    ]
    return _matched([p for p in patterns if _is_repo_source(p)])


def codex_guarded_sources(config_path: Path) -> set[str]:
    config = tomllib.loads(config_path.read_text())
    roots = config["permissions"]["guarded_workspace"]["filesystem"][":workspace_roots"]
    return _matched([pattern for pattern in roots if _is_repo_source(pattern)])


def vscode_autoapprove(settings_path: Path) -> dict[str, bool]:
    """The `chat.tools.edits.autoApprove` map, read from JSONC with comments stripped."""
    text = re.sub(r"^\s*//.*$", "", settings_path.read_text(), flags=re.MULTILINE)
    return json.loads(text).get("chat.tools.edits.autoApprove", {})


def vscode_gated_sources(settings_path: Path) -> set[str]:
    """Repository sources whose Copilot edits require explicit approval.

    A `false` glob makes VS Code show its diff-and-approve prompt, the fallback
    layer for a tamper hook that fails open.
    """
    approvals = vscode_autoapprove(settings_path)
    patterns = [
        pattern.removeprefix("**/")
        for pattern, approved in approvals.items()
        if approved is False
    ]
    return _matched([p for p in patterns if _is_repo_source(p)])


def vscode_undeclared_loosenings(
    approvals: dict[str, bool], exceptions: set[str]
) -> set[str]:
    """`true` globs the manifest does not except for this surface — drift, not intent."""
    return {
        pattern for pattern, approved in approvals.items() if approved is True
    } - exceptions


@pytest.fixture(scope="module")
def expected() -> set[str]:
    """The guarded repository sources, as the manifest declares them."""
    sources = hook_sources()
    assert sources, "the manifest declares no repository sources"
    return sources


def test_configuration_files_are_discovered() -> None:
    """Guards the globs themselves: an empty set would make every test below vacuous."""
    assert CLAUDE_SETTINGS, "found no Claude settings files to check"
    assert CODEX_CONFIGS, "found no Codex configuration files to check"
    assert VSCODE_SETTINGS, "found no VS Code settings files to check"


@pytest.mark.parametrize(
    "settings_path", CLAUDE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
)
def test_claude_permission_rules_cover_the_guarded_sources(
    settings_path: Path, expected: set[str]
) -> None:
    missing = expected - claude_guarded_sources(settings_path)
    assert not missing, (
        f"{settings_path.relative_to(REPO_ROOT)} gates none of these, which the "
        f"hook refuses: {sorted(missing)}"
    )


@pytest.mark.parametrize(
    "config_path", CODEX_CONFIGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
)
def test_codex_permissions_cover_the_guarded_sources(
    config_path: Path, expected: set[str]
) -> None:
    missing = expected - codex_guarded_sources(config_path)
    assert not missing, (
        f"{config_path.relative_to(REPO_ROOT)} lists none of these, which the "
        f"hook refuses: {sorted(missing)}"
    )


@pytest.mark.parametrize(
    "settings_path", VSCODE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
)
def test_vscode_edit_approvals_cover_the_guarded_sources(
    settings_path: Path, expected: set[str]
) -> None:
    missing = expected - vscode_gated_sources(settings_path)
    assert not missing, (
        f"{settings_path.relative_to(REPO_ROOT)} auto-approves edits to these, "
        f"which the hook gates: {sorted(missing)}"
    )


class TestVscodeExceptions:
    """A `true` glob is drift unless the manifest declares it an exception."""

    @staticmethod
    @pytest.fixture(scope="class")
    def exceptions() -> set[str]:
        return declared_exceptions("vscode-edit-approvals")

    def test_a_declared_exception_exists(self, exceptions: set[str]) -> None:
        assert "**/Code/User/workspaceStorage/**" in exceptions

    @pytest.mark.parametrize(
        "settings_path", VSCODE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
    )
    def test_real_settings_have_no_undeclared_loosening(
        self, settings_path: Path, exceptions: set[str]
    ) -> None:
        undeclared = vscode_undeclared_loosenings(
            vscode_autoapprove(settings_path), exceptions
        )
        assert not undeclared, (
            f"{settings_path.relative_to(REPO_ROOT)} auto-approves {sorted(undeclared)} "
            "with no declared exception"
        )

    @pytest.mark.parametrize(
        "settings_path", VSCODE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
    )
    def test_the_declared_exception_is_honored_while_globalstorage_stays_gated(
        self, settings_path: Path, exceptions: set[str]
    ) -> None:
        approvals = vscode_autoapprove(settings_path)
        assert approvals.get("**/Code/User/workspaceStorage/**") is True
        assert approvals.get("**/Code/User/globalStorage/**") is False

    def test_an_undeclared_true_glob_fails_conformance(
        self, exceptions: set[str]
    ) -> None:
        """Exercised against a fixture, so the detection itself is checked rather
        than whichever loosenings the real settings files happen to carry."""
        fixture = {"**/Code/User/globalStorage/**": True}
        undeclared = vscode_undeclared_loosenings(fixture, exceptions)
        assert undeclared == {"**/Code/User/globalStorage/**"}


def claude_gated_home_rules(settings_path: Path) -> list[str]:
    """The `~/` patterns a Claude settings file gates, by refusing or by asking."""
    permissions = json.loads(settings_path.read_text()).get("permissions", {})
    rules = permissions.get("deny", []) + permissions.get("ask", [])
    return [
        match.group("pattern")
        for rule in rules
        if (match := CLAUDE_HOME_RULE_RE.match(rule))
    ]


def codex_gated_home_entries(config_path: Path) -> list[str]:
    """The `~/` paths a Codex profile makes non-writable, by `read` or by `deny`."""
    filesystem = tomllib.loads(config_path.read_text())["permissions"][
        "guarded_workspace"
    ]["filesystem"]
    return [
        path
        for path, mode in filesystem.items()
        if path.startswith("~/") and mode in ("read", "deny")
    ]


def vscode_gated_globs(settings_path: Path) -> list[str]:
    return [
        pattern
        for pattern, approved in vscode_autoapprove(settings_path).items()
        if approved is False
    ]


def assert_covered(
    surface: str, patterns: list[str], declaration: str, path: str, complaint: str
) -> None:
    """A declaration must be covered by this surface, or excepted for it by name.

    Without a named exception, a gap and a deliberate decision look identical.
    """
    if any(glob_covers(pattern, path) for pattern in patterns):
        return
    assert declaration in declared_exceptions(surface), complaint


class TestDeployedDeclarationsAreCovered:
    """The deployed half of the manifest needs the same floor the sources have.

    Every file is checked against every deployed declaration and every deployed
    instruction-layer location, including the other platform's spelling: a rule
    naming a path absent on this platform is inert, while inferring a file's
    platform from its name is wrong for the settings files that carry no
    platform suffix.
    """

    def test_both_declaration_sets_are_populated(self) -> None:
        """Guards the parametrisation: an empty list makes every test below vacuous."""
        assert DEPLOYED, "the manifest declares no deployed gated paths"
        assert DEPLOYED_LAYERS, "the manifest declares no deployed instruction layers"

    @pytest.mark.parametrize(
        "declaration,path", DEPLOYED + DEPLOYED_LAYERS, ids=lambda v: v
    )
    @pytest.mark.parametrize(
        "settings_path", CLAUDE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
    )
    def test_claude_permission_rules_cover_it(
        self, settings_path: Path, declaration: str, path: str
    ) -> None:
        assert_covered(
            "claude-permissions",
            claude_gated_home_rules(settings_path),
            declaration,
            path,
            f"{settings_path.relative_to(REPO_ROOT)} has no Edit rule covering "
            f"'{declaration}', which the hook gates",
        )

    @pytest.mark.parametrize(
        "declaration,path", DEPLOYED + DEPLOYED_LAYERS, ids=lambda v: v
    )
    @pytest.mark.parametrize(
        "config_path", CODEX_CONFIGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
    )
    def test_codex_permissions_cover_it(
        self, config_path: Path, declaration: str, path: str
    ) -> None:
        assert_covered(
            "codex-guarded-workspace",
            codex_gated_home_entries(config_path),
            declaration,
            path,
            f"{config_path.relative_to(REPO_ROOT)} leaves '{declaration}' "
            "writable, which the hook gates",
        )

    @pytest.mark.parametrize(
        "declaration,path", DEPLOYED + DEPLOYED_LAYERS, ids=lambda v: v
    )
    @pytest.mark.parametrize(
        "settings_path", VSCODE_SETTINGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
    )
    def test_vscode_edit_approvals_cover_it(
        self, settings_path: Path, declaration: str, path: str
    ) -> None:
        assert_covered(
            "vscode-edit-approvals",
            vscode_gated_globs(settings_path),
            declaration,
            path,
            f"{settings_path.relative_to(REPO_ROOT)} auto-approves edits to "
            f"'{declaration}', which the hook gates",
        )
