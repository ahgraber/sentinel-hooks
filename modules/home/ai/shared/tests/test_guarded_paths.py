"""The path-guarding predicate every hook shares.

A guarded location stays guarded whatever spelling reaches it, and a path the
operating system refuses to resolve does not become permission.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from guarded_paths import GuardedLocations, folds_case, repo_root_of, spellings


def make_repo(root: Path) -> Path:
    """A repository-shaped tree, recognised by its `.git` entry."""
    (root / ".git").mkdir(parents=True)
    guarded = root / "modules" / "home" / "ai" / "shared" / "hooks"
    guarded.mkdir(parents=True)
    (guarded / "block-dangerous-bash.sh").write_text("#!/usr/bin/env bash\n")
    return root


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    make_repo(tmp_path / "repo")
    (tmp_path / "home").mkdir()
    return tmp_path


@pytest.fixture
def guarded(tree: Path) -> GuardedLocations:
    return GuardedLocations(
        ["<repo>/modules/home/ai/shared/hooks/", "~/.codex/rules/"],
        home=str(tree / "home"),
        repo_root=str(tree / "repo"),
    )


class TestSingleDeclaration:
    def test_fragment_derives_from_declaration(self, guarded: GuardedLocations) -> None:
        assert guarded.fragments == ("modules/home/ai/shared/hooks/", ".codex/rules/")

    def test_wildcard_segment_needs_no_directory_listing(self, tree: Path) -> None:
        """The user directory need not exist: the pattern is matched, not enumerated."""
        locations = GuardedLocations(
            ["<repo>/users/*/home-manager/codex/config.toml"],
            home=str(tree / "home"),
            repo_root=str(tree / "repo"),
        )
        absent = tree / "repo" / "users" / "testuser" / "home-manager" / "codex"
        assert locations.contains(str(absent / "config.toml")) is True

    def test_wildcard_within_a_segment_matches_under_home(self, tree: Path) -> None:
        """A profile layer file need not exist yet, so the pattern is matched, not enumerated."""
        locations = GuardedLocations(
            ["~/.codex/*.config.toml"],
            home=str(tree / "home"),
            repo_root=str(tree / "repo"),
        )
        assert locations.fragments == (".config.toml",)
        assert locations.contains("~/.codex/work.config.toml") is True

    def test_that_wildcard_does_not_reach_a_file_of_the_same_name_elsewhere(
        self, tree: Path
    ) -> None:
        locations = GuardedLocations(
            ["~/.codex/*.config.toml"],
            home=str(tree / "home"),
            repo_root=str(tree / "repo"),
        )
        elsewhere = tree / "work" / "app" / "review.config.toml"
        elsewhere.parent.mkdir(parents=True)
        assert locations.contains(str(elsewhere)) is False


class TestSpellingIndependence:
    def test_plain_path_is_guarded(self, guarded: GuardedLocations, tree: Path) -> None:
        target = tree / "repo" / "modules" / "home" / "ai" / "shared" / "hooks" / "x.py"
        assert guarded.contains(str(target)) is True

    def test_traversal_components_do_not_defeat_it(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        target = tree / "repo" / "modules" / ".." / "modules" / "home" / "ai"
        assert guarded.contains(str(target / "shared" / "hooks" / "x.py")) is True

    def test_symbolic_link_alias_does_not_defeat_it(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        alias = tree / "alias"
        alias.symlink_to(tree / "repo" / "modules" / "home" / "ai" / "shared" / "hooks")
        assert guarded.contains(str(alias / "x.py")) is True

    def test_home_notation_does_not_defeat_it(self, tree: Path) -> None:
        locations = GuardedLocations(
            ["~/.codex/rules/"], home=str(tree / "home"), repo_root=str(tree / "repo")
        )
        assert locations.contains("~/.codex/rules/default.rules") is True

    def test_a_file_leading_out_of_a_guarded_directory_is_guarded(
        self, tree: Path
    ) -> None:
        """Home Manager and sops-nix deploy links whose targets sit outside the
        guarded directory, so the resolved form alone would guard nothing."""
        home = tree / "home"
        elsewhere = tree / "store"
        elsewhere.mkdir()
        target = elsewhere / "config-abc123"
        target.write_text("")
        (home / ".codex" / "rules").mkdir(parents=True)
        deployed = home / ".codex" / "rules" / "default.rules"
        deployed.symlink_to(target)

        locations = GuardedLocations(
            ["~/.codex/rules/"], home=str(home), repo_root=str(tree / "repo")
        )
        assert locations.contains(str(deployed)) is True

    def test_a_symlinked_home_directory_does_not_defeat_it(
        self, tmp_path: Path
    ) -> None:
        """Both spellings of home must be judged, since a path written through a
        symlinked home resolves somewhere the declarations do not name.

        `index.test.mjs` pins the same case for the
        TypeScript port, which cannot import this.
        """
        root = Path(os.path.realpath(tmp_path))
        real_home = root / "real-home"
        home_link = root / "home"
        store = root / "store"
        (real_home / ".claude" / "projects").mkdir(parents=True)
        store.mkdir()
        home_link.symlink_to(real_home)

        target = store / "session-abc.jsonl"
        target.write_text("")
        (real_home / ".claude" / "projects" / "session.jsonl").symlink_to(target)

        locations = GuardedLocations(
            ["~/.claude/settings.json"],
            location_only=["~/.claude/"],
            home=str(home_link),
            repo_root=str(root),
        )
        probe = home_link / ".claude" / "projects" / "session.jsonl"
        assert locations.contains(str(probe)) is True

    def test_unrelated_path_is_not_guarded(self, guarded: GuardedLocations) -> None:
        assert guarded.contains("/etc/hosts") is False


class TestRepositoryContainment:
    """`<repo>` declarations name a place in a repository, not one checkout of it."""

    def test_a_second_checkout_is_guarded(
        self, guarded: GuardedLocations, tmp_path: Path
    ) -> None:
        other = make_repo(tmp_path / "elsewhere")
        target = other / "modules" / "home" / "ai" / "shared" / "hooks" / "x.py"
        assert guarded.contains(str(target)) is True

    def test_a_worktree_is_guarded(
        self, guarded: GuardedLocations, tmp_path: Path
    ) -> None:
        """A worktree marks its root with a `.git` file rather than a directory."""
        worktree = tmp_path / "worktree"
        (worktree / "modules" / "home" / "ai" / "shared" / "hooks").mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
        target = worktree / "modules" / "home" / "ai" / "shared" / "hooks" / "x.py"
        assert repo_root_of(str(target)) == str(worktree)
        assert guarded.contains(str(target)) is True

    def test_the_same_shape_outside_a_repository_is_not_guarded(
        self, guarded: GuardedLocations, tmp_path: Path
    ) -> None:
        """A copy of the tree is not the tree: shape alone does not guard it."""
        backup = tmp_path / "backups" / "modules" / "home" / "ai" / "shared" / "hooks"
        backup.mkdir(parents=True)
        assert guarded.contains(str(backup / "x.py")) is False

    def test_a_relative_path_of_that_shape_is_guarded(
        self, guarded: GuardedLocations
    ) -> None:
        """It means whatever the working directory makes it mean, so it is refused."""
        assert guarded.contains("modules/home/ai/shared/hooks/x.py") is True


class TestLocationOnlyDeclarations:
    """A directory too broad to match as text is matched by resolution alone."""

    @pytest.fixture
    def guarded(self, tree: Path) -> GuardedLocations:
        return GuardedLocations(
            ["~/.claude/settings.json"],
            location_only=["~/.claude/"],
            home=str(tree / "home"),
            repo_root=str(tree / "repo"),
        )

    def test_contributes_no_fragment(self, guarded: GuardedLocations) -> None:
        assert guarded.fragments == (".claude/settings.json",)

    def test_anything_resolving_inside_it_is_guarded(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        session = tree / "home" / ".claude" / "projects"
        session.mkdir(parents=True)
        assert guarded.contains(str(session / "log.jsonl")) is True

    def test_a_same_named_directory_elsewhere_is_not(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        project = tree / "work" / "app" / ".claude" / "agents"
        project.mkdir(parents=True)
        assert guarded.contains(str(project / "reviewer.md")) is False


class TestLetterCase:
    def test_case_variant_is_guarded_where_the_filesystem_folds_case(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        if not folds_case(str(tree)):
            pytest.skip("filesystem under test is case-sensitive")
        target = tree / "repo" / "Modules" / "Home" / "AI" / "Shared" / "Hooks" / "x.py"
        assert guarded.contains(str(target)) is True

    def test_case_variant_is_a_different_file_where_the_filesystem_does_not(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        if folds_case(str(tree)):
            pytest.skip("filesystem under test is case-insensitive")
        target = tree / "repo" / "Modules" / "Home" / "AI" / "Shared" / "Hooks" / "x.py"
        assert guarded.contains(str(target)) is False


class TestUnresolvablePath:
    def test_written_form_still_decides(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        unresolvable = f"{tree}/repo/modules/home/ai/shared/hooks/x\x00.py"
        assert guarded.contains(unresolvable) is True

    def test_resolution_failure_does_not_escape(
        self, guarded: GuardedLocations
    ) -> None:
        assert guarded.contains("/tmp/nothing\x00here") is False

    def test_spellings_omits_the_form_it_could_not_produce(self) -> None:
        assert len(spellings("/tmp/x\x00y")) == 2
        assert len(spellings("/tmp/xy")) == 3


class TestArbitraryText:
    def test_command_naming_a_guarded_location(self, guarded: GuardedLocations) -> None:
        command = "cp /dev/null modules/home/ai/shared/hooks/block-dangerous-bash.sh"
        assert guarded.mentioned_in(command) is True

    def test_command_naming_nothing_guarded(self, guarded: GuardedLocations) -> None:
        assert guarded.mentioned_in("git status") is False
