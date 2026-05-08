"""Tests for the Codex-specific destructive-ops hook."""

from conftest import assert_allowed, assert_block_contract, run_hook

HOOK = "block-destructive-ops.py"


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


class TestToolScope:
    def test_non_bash_tool_allowed(self):
        result = run_hook(HOOK, "Write", {"file_path": "/tmp/test"})
        assert_allowed(result)

    def test_safe_command_allowed(self):
        assert_allowed(bash("echo hello"))


class TestFormerAskModeNowBlocks:
    def test_reset_hard_blocks(self):
        assert_block_contract(bash("git reset --hard HEAD~1"), "uncommitted")

    def test_git_add_all_blocks(self):
        assert_block_contract(bash("git add ."), "stages all")


class TestBlockModeStillBlocks:
    def test_force_push_without_lease_blocks(self):
        assert_block_contract(bash("git push --force origin main"), "force")
