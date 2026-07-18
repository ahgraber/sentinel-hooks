"""Tests for the Codex-specific tamper-protection hook."""

from pathlib import Path

from conftest import assert_allowed, assert_block_contract, run_hook

HOOK = "codex-block-hook-tampering.py"


def repo_path(*parts: str) -> str:
    return str(Path("modules") / "home" / "apps" / "codex" / Path(*parts))


def user_path(*parts: str) -> str:
    return str(Path("users") / "mithras" / "home-manager" / Path(*parts))


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


class TestCodexHomeProtection:
    def test_read_codex_config_blocks(self):
        dot_codex = "~/" + ".codex"
        assert_block_contract(read(f"{dot_codex}/config.toml"), "config.toml")


class TestRepoBackedLiveConfigProtection:
    def test_read_repo_hook_blocks(self):
        assert_block_contract(read(repo_path("hooks", "block-secrets.py")), "hooks")

    def test_read_repo_rules_block(self):
        assert_block_contract(read(repo_path("rules", "default.rules")), "rules")

    def test_read_repo_config_blocks(self):
        assert_block_contract(read(user_path("codex", "config.toml")), "config.toml")

    def test_apply_patch_repo_hooks_json_blocks(self):
        assert_block_contract(
            apply_patch_command(user_path("codex", "hooks.json")),
            "hooks.json",
        )

    def test_bash_repo_hook_path_blocks(self):
        assert_block_contract(
            bash(f"cat {repo_path('hooks', 'block-secrets.py')}"),
            "hooks",
        )

    def test_unrelated_read_allowed(self):
        assert_allowed(read("/tmp/notes.txt"))
