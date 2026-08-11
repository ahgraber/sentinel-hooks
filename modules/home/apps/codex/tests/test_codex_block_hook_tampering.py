"""Tests for the Codex-specific tamper-protection hook."""

from pathlib import Path

from conftest import assert_allowed, assert_block_contract, run_hook

HOOK = "codex-block-hook-tampering.py"
# tests/ -> codex/ -> apps/ -> home/ -> modules/ -> repo root (5 levels up),
# matching REPO_ROOT in the hook under test.
REPO_ROOT = Path(__file__).resolve().parents[5]


def repo_path(*parts: str) -> str:
    return str(Path("modules") / "home" / "apps" / "codex" / Path(*parts))


def user_path(*parts: str) -> str:
    return str(Path("users") / "mithras" / "home-manager" / Path(*parts))


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


def read(path: str):
    return run_hook(HOOK, "Read", {"file_path": path})


def write(path: str):
    return run_hook(HOOK, "Write", {"file_path": path})


def edit(path: str):
    return run_hook(
        HOOK,
        "Edit",
        {"file_path": path, "old_string": "old", "new_string": "new"},
    )


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


class TestCodexReadAccess:
    def test_deployed_codex_config_is_readable(self):
        assert_allowed(read("~/.codex/config.toml"))

    def test_repo_hooks_and_rules_are_readable(self):
        assert_allowed(read(repo_path("hooks", "block-secrets.py")))
        assert_allowed(read(repo_path("rules", "default.rules")))

    def test_repo_platform_configs_are_readable(self):
        for platform in ("darwin", "linux"):
            assert_allowed(read(user_path("codex", f"config.{platform}.toml")))


class TestRepoBackedLiveConfigProtection:
    def test_direct_mutation_tools_block(self):
        assert_block_contract(write("~/.codex/config.toml"), "config.toml")
        assert_block_contract(
            edit(repo_path("hooks", "block-secrets.py")),
            "hooks",
        )
        assert_block_contract(
            write(user_path("codex", "config.linux.toml")),
            "config.linux.toml",
        )

    def test_apply_patch_repo_hooks_json_blocks(self):
        assert_block_contract(
            apply_patch_command(user_path("codex", "hooks.json")),
            "hooks.json",
        )

    def test_managed_opt_in_recipe_blocks(self):
        assert_block_contract(write("justfiles/nix.just"), "nix.just")

    def test_bash_repo_hook_path_blocks(self):
        assert_block_contract(
            bash(f"cat {repo_path('hooks', 'block-secrets.py')}"),
            "hooks",
        )

    def test_unrelated_write_allowed(self):
        assert_allowed(write("/tmp/notes.txt"))


class TestProtectedPathResolution:
    """Exercise the realpath-resolved PROTECTED_PATHS layer."""

    def test_realpath_resolved_repo_hook_write_blocks(self):
        codex_dir = REPO_ROOT / "modules" / "home" / "apps" / "codex"
        obfuscated = f"{codex_dir}/../codex/hooks/block-secrets.py"
        assert "modules/home/apps/codex/hooks/" not in obfuscated
        assert_block_contract(write(obfuscated), "codex")
