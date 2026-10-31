"""Where a path leads decides the verdict, not what the path is called.

Both cases pin real bypasses: a link named for the instruction carve-out, and a
redirection written flush against its operand.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

from guarded_paths import folds_case
import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"


def load_hook():
    """Import the hook by location; its filename is not a valid identifier."""
    spec = importlib.util.spec_from_file_location("block_hook_tampering", HOOKS_DIR / "block-hook-tampering.py")
    module = importlib.util.module_from_spec(spec)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec.loader.exec_module(module)
    return module


HOOK = load_hook()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A second checkout, judged by the repository that contains it."""
    (tmp_path / ".git").mkdir()
    hooks = tmp_path / "modules" / "home" / "ai" / "shared" / "hooks"
    (hooks / "instructions").mkdir(parents=True)
    (hooks / "block-destructive-ops.py").write_text("original\n")
    (hooks / "instructions" / "00-style.md").write_text("prompt text\n")
    return tmp_path


def hooks_of(repo: Path) -> Path:
    return repo / "modules" / "home" / "ai" / "shared" / "hooks"


def test_ancestor_uses_payload_working_directory(repo):
    assert HOOK.destroys_a_guarded_ancestor("rm -rf modules/home/ai", cwd=str(repo)) == "modules/home/ai"


def test_relative_ancestor_without_cwd_does_not_use_process_directory(repo, monkeypatch):
    monkeypatch.chdir(repo)
    assert HOOK.destroys_a_guarded_ancestor("rm -rf modules/home/ai") is None


def test_newline_does_not_hide_a_destroyed_ancestor(repo):
    ancestor = str(repo / "modules/home/ai")
    command = f"cat ordinary\nrm -rf {ancestor}"
    assert HOOK.destroys_a_guarded_ancestor(command, cwd=str(repo)) == ancestor


class TestInstructionGuard:
    def test_instruction_markdown_is_guarded(self, repo: Path):
        markdown = hooks_of(repo) / "instructions" / "00-style.md"

        assert HOOK.is_protected_path(str(markdown))

    def test_markdown_link_to_a_hook_is_a_write_to_that_hook(self, repo: Path):
        alias = hooks_of(repo) / "instructions" / "notes.md"
        alias.symlink_to("../block-destructive-ops.py")

        assert HOOK.is_protected_path(str(alias))

    def test_markdown_link_blocks_even_where_the_target_does_not_exist(self, repo: Path):
        alias = hooks_of(repo) / "instructions" / "notes.md"
        alias.symlink_to("../block-leaks.py")

        assert HOOK.is_protected_path(str(alias))

    def test_markdown_outside_any_instruction_directory_is_not_carved_out(self, repo: Path):
        markdown = hooks_of(repo) / "README.md"

        assert HOOK.is_protected_path(str(markdown))


class TestLetterCase:
    """A case variant is the same file only where the volume folds case, so the
    expected verdict follows the volume, not the platform."""

    def test_case_variant_of_a_guarded_source(self, repo: Path) -> None:
        target = repo / "Modules/Home/AI/Shared/Hooks/block-destructive-ops.py"

        assert HOOK.is_protected_path(str(target)) is folds_case(str(repo))

    def test_case_variant_of_a_deployed_location(self) -> None:
        target = os.path.expanduser("~/.CLAUDE/settings.json")

        assert HOOK.is_protected_path(target) is folds_case(os.path.expanduser("~"))

    # LONG S folds to `s` and KELVIN SIGN to `k` on a case-folding volume. Elsewhere
    # the hook may still match them, which guards a file that is not the declared one.
    @pytest.mark.parametrize("spelling", ["~/.claude/\u017fettings.json", "~/.claude/hoo\u212as/x.py"])
    def test_unicode_case_fold_of_a_deployed_location(self, spelling: str) -> None:
        if not folds_case(os.path.expanduser("~")):
            pytest.skip("home is on a case-sensitive volume")

        assert HOOK.is_protected_path(os.path.expanduser(spelling)) is True


class TestAttachedOperands:
    """A guarded location reached through a link that hides its name."""

    @pytest.fixture
    def alias(self, repo: Path, tmp_path: Path) -> Path:
        link = tmp_path / "alias"
        link.symlink_to(hooks_of(repo))
        return link

    @pytest.mark.parametrize(
        "command",
        [
            "echo x > {target}",
            "echo x >{target}",
            "echo x >>{target}",
            "echo x 2>{target}",
            "echo x &>{target}",
            "cat <>{target}",
            "tee --append={target}",
            "install --target={target}",
        ],
    )
    def test_operand_is_resolved_however_it_is_attached(self, alias: Path, command: str):
        target = alias / "block-destructive-ops.py"

        assert HOOK.command_mentions_protected_path(command.format(target=target))

    def test_unguarded_redirection_still_passes(self, alias: Path, tmp_path: Path):
        assert not HOOK.command_mentions_protected_path(f"echo x >{tmp_path}/notes.txt")

    def test_redirecting_instruction_markdown_elsewhere_stays_allowed(self, repo: Path, tmp_path: Path):
        markdown = hooks_of(repo) / "instructions" / "00-style.md"
        command = f"cat {markdown} >{tmp_path}/copy.md"

        assert not HOOK.command_mentions_protected_path(command)

    def test_reading_a_guarded_file_through_an_attached_input_redirection_proceeds(self, alias: Path):
        assert not HOOK.command_mentions_protected_path(f"cat <{alias / 'block-destructive-ops.py'}")
