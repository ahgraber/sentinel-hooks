"""Tests for the Codex-specific tamper-protection hook.

Deliberately parallel to the Claude and Copilot tamper suites: one policy over
three path sets, so a change reaching one hook and not the others shows up as a
diff between the files.
"""

from pathlib import Path

from conftest import HOOKS_DIR, REPO_ROOT, assert_allowed, assert_block_contract, run_hook

HOOK = "block-hook-tampering.py"


def repo_path(*parts: str) -> str:
    return str(Path("modules") / "home" / "ai" / "codex" / Path(*parts))


def user_path(*parts: str) -> str:
    return str(Path("users") / "testuser" / "home-manager" / Path(*parts))


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


def apply_patch(path: str):
    return run_hook(
        HOOK,
        "apply_patch",
        {"command": (f"*** Begin Patch\n*** Update File: {path}\n@@\n-old\n+new\n*** End Patch\n")},
    )


class TestReadAccess:
    """Reads stay unblocked: these paths are Nix store symlinks, and bubblewrap
    aborts a sandboxed command when it cannot mount over one."""

    def test_deployed_codex_config_is_readable(self):
        assert_allowed(read("~/.codex/config.toml"))

    def test_repo_hooks_and_rules_are_readable(self):
        assert_allowed(read(repo_path("hooks", "block-leaks.py")))
        assert_allowed(read(repo_path("rules", "default.rules")))

    def test_repo_platform_configs_are_readable(self):
        for platform in ("darwin", "linux"):
            assert_allowed(read(user_path("codex", f"config.{platform}.toml")))

    def test_read_through_symlink_to_repo_hook_is_allowed(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "block-leaks.py")

        assert_allowed(read(str(alias)))


class TestMutationProtection:
    def test_deployed_config_write_blocks(self):
        assert_block_contract(write("~/.codex/config.toml"), "config.toml")

    def test_deployed_auth_write_blocks(self):
        assert_block_contract(write("~/.codex/auth.json"), "auth.json")

    def test_repo_hook_edit_blocks(self):
        assert_block_contract(edit(repo_path("hooks", "block-leaks.py")), "hooks")

    def test_user_config_write_blocks(self):
        assert_block_contract(
            write(user_path("codex", "config.linux.toml")),
            "config.linux.toml",
        )

    def test_profile_layer_config_write_blocks(self):
        # `-p <name>` layers $CODEX_HOME/<name>.config.toml over the base
        # config, so a layer file can widen anything the base config narrows.
        assert_block_contract(write("~/.codex/review.config.toml"), "config.toml")

    def test_unrelated_write_allowed(self):
        assert_allowed(write("/tmp/notes.txt"))


class TestBashCommandProtection:
    def test_bash_reading_repo_hook_proceeds(self):
        # Recognized reads of guarded hook sources proceed.
        assert_allowed(bash(f"cat {repo_path('hooks', 'block-leaks.py')}"))

    def test_bash_touching_repo_hook_blocks(self):
        # Outside a recognized read, Bash still matches on mention, not intent:
        # a command's effect is not readable off its text.
        assert_block_contract(
            bash(f"sed -i 's/a/b/' {repo_path('hooks', 'block-leaks.py')}"),
            "hooks",
        )

    def test_bash_reading_deployed_codex_settings_proceeds(self):
        assert_allowed(bash("cat ~/.codex/config.toml"))

    def test_bash_referencing_only_instruction_markdown_allowed(self):
        instruction = repo_path("hooks", "instructions", "00-response-style.md")

        assert_allowed(bash(f"cat {instruction}"))

    def test_bash_reading_instructions_and_settings_proceeds(self):
        instruction = repo_path("hooks", "instructions", "00-response-style.md")

        assert_allowed(bash(f"cat {instruction} ~/.codex/config.toml"))

    def test_unrelated_bash_allowed(self):
        assert_allowed(bash("echo hello"))


class TestApplyPatchProtection:
    def test_apply_patch_user_hooks_json_blocks(self):
        assert_block_contract(
            apply_patch(user_path("codex", "hooks.json")),
            "hooks.json",
        )

    def test_apply_patch_repo_rules_blocks(self):
        assert_block_contract(
            apply_patch(repo_path("rules", "default.rules")),
            "rules",
        )

    def test_apply_patch_instruction_markdown_blocks(self):
        assert_block_contract(apply_patch(repo_path("hooks", "instructions", "00-response-style.md")))

    def test_unrelated_apply_patch_allowed(self):
        assert_allowed(apply_patch("/tmp/notes.txt"))


class TestInstructionMarkdownGuard:
    """Instruction text is guarded enforcement."""

    def test_repo_instruction_markdown_write_blocks(self):
        assert_block_contract(write(repo_path("hooks", "instructions", "00-response-style.md")))

    def test_deployed_instruction_markdown_write_blocks(self):
        assert_block_contract(write("~/.codex/hooks/instructions/00-response-style.md"))

    def test_nested_instruction_path_blocks(self):
        assert_block_contract(
            write(repo_path("hooks", "instructions", "nested", "note.md")),
            "hooks",
        )

    def test_non_markdown_in_instructions_blocks(self):
        assert_block_contract(
            write(repo_path("hooks", "instructions", "helper.py")),
            "hooks",
        )


class TestPathResolution:
    """Writes through a symlink retain the target source's protection."""

    CODEX_OWNED_FILE = REPO_ROOT / "modules" / "home" / "ai" / "codex" / "rules" / "default.rules"

    def test_write_through_symlink_to_repo_source_blocks(self, tmp_path: Path):
        alias = tmp_path / "notes.rules"
        alias.symlink_to(self.CODEX_OWNED_FILE)

        assert_block_contract(write(str(alias)), "notes.rules")

    def test_traversal_normalized_repo_source_write_blocks(self):
        codex_dir = REPO_ROOT / "modules" / "home" / "ai" / "codex"
        obfuscated = f"{codex_dir}/../codex/rules/default.rules"
        assert "modules/home/ai/codex/rules/" not in obfuscated

        assert_block_contract(write(obfuscated), "codex")


class TestPayloadHandling:
    def test_unhandled_tool_defers(self):
        assert_allowed(run_hook(HOOK, "Grep", {"path": repo_path("hooks")}))

    def test_unparsable_payload_defers(self):
        assert_allowed(run_hook(HOOK, stdin_text="not json"))
