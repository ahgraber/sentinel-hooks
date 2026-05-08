"""Tests for the Codex-specific block-secrets hook."""

import os
from pathlib import Path

from conftest import assert_allowed, assert_block_contract, run_hook

HOOK = "block-secrets.py"
HOME = os.path.expanduser("~")


def repo_path(*parts: str) -> str:
    return str(Path("configs") / "home-manager" / "codex" / Path(*parts))


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


def read(path: str):
    return run_hook(HOOK, "Read", {"file_path": path})


def apply_patch_command(path: str):
    return run_hook(
        HOOK,
        "apply_patch",
        {
            "command": (
                "*** Begin Patch\n"
                f"*** Update File: {path}\n"
                "@@\n"
                "-old\n"
                "+new\n"
                "*** End Patch\n"
            )
        },
    )


class TestCodexSpecificBlocking:
    def test_safe_bash_allowed(self):
        assert_allowed(bash("echo hello"))

    def test_credential_store_read_blocks(self):
        assert_block_contract(
            bash("security find-generic-password -w -s myservice"),
            "credential store",
        )

    def test_credential_directory_read_blocks(self):
        assert_block_contract(read(f"{HOME}/.ssh/id_rsa"), "credential directory")

    def test_apply_patch_credential_file_blocks(self):
        assert_block_contract(
            apply_patch_command(f"{HOME}/.ssh/id_ed25519"), "credential directory"
        )


class TestSpecificityExemptions:
    def test_codex_hook_filename_not_flagged_by_name(self):
        assert_allowed(read(repo_path("hooks", "block-secrets.py")))

    def test_codex_test_filename_not_flagged_by_name(self):
        assert_allowed(read(repo_path("tests", "test_codex_block_secrets.py")))
