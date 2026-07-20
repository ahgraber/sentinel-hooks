"""Tests for Claude hook and settings tamper protection."""

from pathlib import Path

from conftest import assert_block_contract, run_hook

HOOK = "block-hook-tampering.py"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"


def test_read_through_symlink_to_repo_hook_blocks(tmp_path: Path) -> None:
    alias = tmp_path / "notes.py"
    alias.symlink_to(HOOKS_DIR / "block-secrets.py")

    result = run_hook(HOOK, "Read", {"file_path": str(alias)})

    assert_block_contract(result, "Hook scripts")
