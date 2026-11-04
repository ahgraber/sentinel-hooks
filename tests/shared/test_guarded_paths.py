"""The path-guarding predicate every hook shares.

A guarded location stays guarded whatever spelling reaches it, and a path the
operating system refuses to resolve does not become permission.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile

import guarded_paths
from guarded_paths import GuardedLocations, folds_case, repo_root_of, spellings
import pytest


def make_repo(root: Path) -> Path:
    """A repository-shaped tree, recognized by its `.git` entry."""
    (root / ".git").mkdir(parents=True)
    guarded = root / "plugins" / "sentinel" / "hooks"
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
        ["<repo>/plugins/sentinel/hooks/", "~/.codex/rules/"],
        home=str(tree / "home"),
    )


class TestSingleDeclaration:
    def test_fragment_derives_from_declaration(self, guarded: GuardedLocations) -> None:
        assert guarded.fragments == ("plugins/sentinel/hooks/", ".codex/rules/")

    def test_wildcard_segment_needs_no_directory_listing(self, tree: Path) -> None:
        """The user directory need not exist: the pattern is matched, not enumerated."""
        locations = GuardedLocations(
            ["<repo>/projects/*/.codex/config.toml"],
            home=str(tree / "home"),
        )
        absent = tree / "repo" / "projects" / "example" / ".codex"
        assert bool(locations.contains(str(absent / "config.toml"))) is True

    def test_wildcard_within_a_segment_matches_under_home(self, tree: Path) -> None:
        """A profile layer file need not exist yet, so the pattern is matched, not enumerated."""
        locations = GuardedLocations(
            ["~/.codex/*.config.toml"],
            home=str(tree / "home"),
        )
        assert locations.fragments == (".codex/*.config.toml",)
        assert bool(locations.contains("~/.codex/work.config.toml")) is True

    def test_that_wildcard_does_not_reach_a_file_of_the_same_name_elsewhere(self, tree: Path) -> None:
        locations = GuardedLocations(
            ["~/.codex/*.config.toml"],
            home=str(tree / "home"),
        )
        elsewhere = tree / "work" / "app" / "review.config.toml"
        elsewhere.parent.mkdir(parents=True)
        assert bool(locations.contains(str(elsewhere))) is False


class TestSpellingIndependence:
    def test_plain_path_is_guarded(self, guarded: GuardedLocations, tree: Path) -> None:
        target = tree / "repo" / "plugins" / "sentinel" / "hooks" / "x.py"
        assert bool(guarded.contains(str(target))) is True

    def test_traversal_components_do_not_defeat_it(self, guarded: GuardedLocations, tree: Path) -> None:
        target = tree / "repo" / "plugins" / ".." / "plugins" / "sentinel"
        assert bool(guarded.contains(str(target / "hooks" / "x.py"))) is True

    def test_symbolic_link_alias_does_not_defeat_it(self, guarded: GuardedLocations, tree: Path) -> None:
        alias = tree / "alias"
        alias.symlink_to(tree / "repo" / "plugins" / "sentinel" / "hooks")
        assert bool(guarded.contains(str(alias / "x.py"))) is True

    def test_home_notation_does_not_defeat_it(self, tree: Path) -> None:
        locations = GuardedLocations(["~/.codex/rules/"], home=str(tree / "home"))
        assert bool(locations.contains("~/.codex/rules/default.rules")) is True

    def test_a_file_leading_out_of_a_guarded_directory_is_guarded(self, tree: Path) -> None:
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

        locations = GuardedLocations(["~/.codex/rules/"], home=str(home))
        assert bool(locations.contains(str(deployed))) is True

    def test_a_symlinked_home_directory_does_not_defeat_it(self, tmp_path: Path) -> None:
        """Both spellings of home must be judged, since a path written through a
        symlinked home resolves somewhere the declarations do not name.
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
            ["~/.claude/settings.json", "~/.claude/"],
            home=str(home_link),
        )
        probe = home_link / ".claude" / "projects" / "session.jsonl"
        assert bool(locations.contains(str(probe))) is True

    def test_unrelated_path_is_not_guarded(self, guarded: GuardedLocations) -> None:
        assert bool(guarded.contains("/etc/hosts")) is False


class TestRepositoryContainment:
    """`<repo>` declarations name a place in a repository, not one checkout of it."""

    def test_a_second_checkout_is_guarded(self, guarded: GuardedLocations, tmp_path: Path) -> None:
        other = make_repo(tmp_path / "elsewhere")
        target = other / "plugins" / "sentinel" / "hooks" / "x.py"
        assert bool(guarded.contains(str(target))) is True

    def test_a_worktree_is_guarded(self, guarded: GuardedLocations, tmp_path: Path) -> None:
        """A worktree marks its root with a `.git` file rather than a directory."""
        worktree = tmp_path / "worktree"
        (worktree / "plugins" / "sentinel" / "hooks").mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
        target = worktree / "plugins" / "sentinel" / "hooks" / "x.py"
        assert repo_root_of(str(target)) == str(worktree)
        assert bool(guarded.contains(str(target))) is True

    def test_the_same_shape_outside_a_repository_is_not_guarded(
        self, guarded: GuardedLocations, tmp_path: Path
    ) -> None:
        """A copy of the tree is not the tree: shape alone does not guard it."""
        backup = tmp_path / "backups" / "plugins" / "sentinel" / "hooks"
        backup.mkdir(parents=True)
        assert bool(guarded.contains(str(backup / "x.py"))) is False

    def test_a_relative_path_of_that_shape_is_guarded(self, guarded: GuardedLocations) -> None:
        """It means whatever the working directory makes it mean, so it is refused."""
        assert bool(guarded.contains("plugins/sentinel/hooks/x.py")) is True

    def test_hooks_loaded_outside_any_checkout_guard_every_checkout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An installed copy sits in a shallow directory that no checkout contains."""
        shallow = (
            Path(d).resolve()
            for d in ("/tmp", tempfile.gettempdir())
            if os.access(d, os.W_OK) and len(Path(d).resolve().parents) < 4
        )
        base = next(shallow, None)
        if base is None:
            pytest.skip("no writable directory with fewer than five parents")
        installed = Path(tempfile.mkdtemp(prefix="sentinel-", dir=base)).resolve()
        try:
            assert len(installed.parents) < 5
            assert repo_root_of(str(installed)) is None
            hooks = Path(guarded_paths.__file__).parent
            shutil.copytree(hooks, installed, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
            spec = importlib.util.spec_from_file_location("installed_guarded_paths", installed / "guarded_paths.py")
            module = importlib.util.module_from_spec(spec)
            monkeypatch.setitem(sys.modules, spec.name, module)
            spec.loader.exec_module(module)

            locations = module.GuardedLocations(["<repo>/.claude/settings.json"], home=str(tmp_path / "home"))
            checkout = make_repo(tmp_path / "checkout")
            assert locations.contains(str(checkout / ".claude" / "settings.json"))
            assert not locations.contains(str(tmp_path / "loose" / ".claude" / "settings.json"))
        finally:
            shutil.rmtree(installed)


class TestBroadDeclarations:
    """Resolved paths use location checks, including broad declarations."""

    @pytest.fixture
    def guarded(self, tree: Path) -> GuardedLocations:
        return GuardedLocations(
            ["~/.claude/settings.json", "~/.claude/"],
            home=str(tree / "home"),
        )

    def test_contributes_a_fragment(self, guarded: GuardedLocations) -> None:
        assert guarded.fragments == (".claude/settings.json", ".claude/")

    def test_anything_resolving_inside_it_is_guarded(self, guarded: GuardedLocations, tree: Path) -> None:
        session = tree / "home" / ".claude" / "projects"
        session.mkdir(parents=True)
        assert bool(guarded.contains(str(session / "log.jsonl"))) is True

    def test_a_same_named_directory_elsewhere_is_not(self, guarded: GuardedLocations, tree: Path) -> None:
        project = tree / "work" / "app" / ".claude" / "agents"
        project.mkdir(parents=True)
        assert bool(guarded.contains(str(project / "reviewer.md"))) is False


class TestLetterCase:
    def test_case_variant_is_guarded_where_the_filesystem_folds_case(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        if not folds_case(str(tree)):
            pytest.skip("filesystem under test is case-sensitive")
        target = tree / "repo" / "Plugins" / "Sentinel" / "Hooks" / "x.py"
        assert bool(guarded.contains(str(target))) is True

    def test_case_variant_is_a_different_file_where_the_filesystem_does_not(
        self, guarded: GuardedLocations, tree: Path
    ) -> None:
        if folds_case(str(tree)):
            pytest.skip("filesystem under test is case-insensitive")
        target = tree / "repo" / "Plugins" / "Sentinel" / "Hooks" / "x.py"
        assert bool(guarded.contains(str(target))) is False


class TestUnresolvablePath:
    def test_written_form_still_decides(self, guarded: GuardedLocations, tree: Path) -> None:
        unresolvable = f"{tree}/repo/plugins/sentinel/hooks/x\x00.py"
        assert bool(guarded.contains(unresolvable)) is True

    def test_resolution_failure_does_not_escape(self, guarded: GuardedLocations) -> None:
        assert bool(guarded.contains("/tmp/nothing\x00here")) is False

    def test_spellings_omits_the_form_it_could_not_produce(self) -> None:
        assert len(spellings("/tmp/x\x00y")) == 2
        assert len(spellings("/tmp/xy")) == 3


class TestArbitraryText:
    def test_command_naming_a_guarded_location(self, guarded: GuardedLocations) -> None:
        command = "cp /dev/null plugins/sentinel/hooks/block-dangerous-bash.sh"
        assert guarded.mentioned_in(command) is True

    def test_command_naming_nothing_guarded(self, guarded: GuardedLocations) -> None:
        assert guarded.mentioned_in("git status") is False

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("rm -rf plugins/sentinel/hooks", id="bare-directory"),
            pytest.param("ls plugins/sentinel/hooks/", id="trailing-separator"),
            pytest.param("cd plugins/sentinel/hooks && ls", id="before-operator"),
            pytest.param("cat 'plugins/sentinel/hooks/x.py'", id="quoted"),
        ],
    )
    def test_a_directory_is_named_with_or_without_its_separator(self, guarded: GuardedLocations, command: str) -> None:
        """The declaration's trailing separator is a boundary, not text to match."""
        assert guarded.mentioned_in(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("cat my-plugins/sentinel/hooks/x", id="longer-prefix"),
            pytest.param("cat plugins/sentinel/hooks-old/x", id="longer-suffix"),
            pytest.param("cat vendor/x-plugins/sentinel/hooks", id="both"),
        ],
    )
    def test_a_longer_name_holding_the_fragment_is_not_guarded(self, guarded: GuardedLocations, command: str) -> None:
        """A component matches whole; a backup beside a guarded tree is its own path."""
        assert guarded.mentioned_in(command) is False


class TestDeclarationChains:
    def test_declaration_covers_its_intermediate_and_final_targets(self, tree):
        target = tree / "target"
        target.mkdir()
        middle = tree / "middle"
        middle.symlink_to(target)
        declared = tree / "home" / "guarded"
        declared.symlink_to(middle)
        locations = GuardedLocations(["~/guarded/"], home=str(tree / "home"))

        matches = locations.contains(str(middle / "file"))

        assert [(match.declaration, match.distance) for match in matches] == [("~/guarded/", 1)]
        assert locations.contains(str(target / "file"))
        assert str(middle / "file") in spellings(str(declared / "file"))

    def test_relative_path_uses_supplied_cwd(self, guarded, tree):
        outside = tree / "outside"
        outside.mkdir()

        matches = guarded.contains("plugins/sentinel/hooks/file", cwd=str(outside))

        assert not matches

    @pytest.mark.parametrize(
        ("path", "matches"),
        [
            ("~/instructions/x.md", True),
            ("~/instructions/nested/x.md", False),
            ("~/instructions/x.py", False),
        ],
    )
    def test_last_component_glob_does_not_span_directories(self, tree, path, matches):
        locations = GuardedLocations(["~/instructions/*.md"], home=str(tree / "home"))

        result = locations.contains(path)

        assert bool(result) is matches

    def test_fragment_keeps_the_glob_component(self, tree):
        locations = GuardedLocations(["~/instructions/*.md"], home=str(tree / "home"))

        assert locations.mentioned_in("${X:-instructions/x.md}")
        assert not locations.mentioned_in("${X:-elsewhere.md}")
