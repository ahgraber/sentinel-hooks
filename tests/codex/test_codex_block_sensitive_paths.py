"""Credential paths under Codex, which cannot show a hook prompt: block-sensitive-paths.py judges them."""

import os

from conftest import assert_allowed, assert_block_contract, run_hook

HOOK = "block-sensitive-paths.py"
HOME = os.path.expanduser("~")


def read(path: str):
    return run_hook(HOOK, "Read", {"file_path": path})


def apply_patch_command(path: str):
    return run_hook(
        HOOK, "apply_patch", {"command": f"*** Begin Patch\n*** Update File: {path}\n@@\n-a\n+b\n*** End Patch\n"}
    )


class TestCredentialPathsAreRefused:
    def test_credential_directory_read_blocks(self):
        assert_block_contract(read(f"{HOME}/.ssh/id_rsa"), "zero-access")

    def test_apply_patch_credential_file_blocks(self):
        assert_block_contract(apply_patch_command(f"{HOME}/.ssh/id_ed25519"), "zero-access")

    def test_claude_oauth_store_read_blocks(self):
        assert_block_contract(read(f"{HOME}/.claude/.credentials.json"), "zero-access")


class TestSuggestiveNamesRefuseWhereNoPromptIsShown:
    def test_a_suggestive_name_is_refused_without_an_approval_line(self):
        result = read("/project/auth_token.json")
        assert_block_contract(result, "cannot show a confirmation prompt")
        assert "approve" not in result.stderr.lower()

    def test_a_dotenv_placeholder_read_proceeds(self):
        assert_allowed(read("/project/apps/web/.env.example"))
