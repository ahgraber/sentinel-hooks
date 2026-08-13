"""Tests for the Codex-specific tamper-protection hook.

Kept in the same shape as the Claude and Copilot tamper suites, because the
three hooks enforce one policy over different path sets: reads are allowed,
mutations are blocked, and `instructions/*.md` is the only carve-out. A policy
change that reaches one hook and not the others should show up as a diff
between these three files.
"""

from pathlib import Path

from conftest import assert_allowed, assert_block_contract, run_hook

HOOK = "codex-block-hook-tampering.py"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"
# tests/ -> codex/ -> apps/ -> home/ -> modules/ -> repo root (5 levels up),
# matching REPO_ROOT in the hook under test.
REPO_ROOT = Path(__file__).resolve().parents[5]


def repo_path(*parts: str) -> str:
    return str(Path("modules") / "home" / "apps" / "codex" / Path(*parts))


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


class TestReadAccess:
    """Reads stay unblocked: a read-deny on these paths cannot be enforced by
    the OS sandbox, because they are symlinks into the Nix store and bubblewrap
    aborts every sandboxed command when it cannot mount over one."""

    def test_deployed_codex_config_is_readable(self):
        assert_allowed(read("~/.codex/config.toml"))

    def test_repo_hooks_and_rules_are_readable(self):
        assert_allowed(read(repo_path("hooks", "block-secrets.py")))
        assert_allowed(read(repo_path("rules", "default.rules")))

    def test_repo_platform_configs_are_readable(self):
        for platform in ("darwin", "linux"):
            assert_allowed(read(user_path("codex", f"config.{platform}.toml")))

    def test_read_through_symlink_to_repo_hook_is_allowed(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "block-secrets.py")

        assert_allowed(read(str(alias)))


class TestMutationProtection:
    def test_deployed_config_write_blocks(self):
        assert_block_contract(write("~/.codex/config.toml"), "config.toml")

    def test_deployed_auth_write_blocks(self):
        assert_block_contract(write("~/.codex/auth.json"), "auth.json")

    def test_repo_hook_edit_blocks(self):
        assert_block_contract(edit(repo_path("hooks", "block-secrets.py")), "hooks")

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
    def test_bash_touching_repo_hook_blocks(self):
        # The Bash branch matches on mention, not on intent: the effect of a
        # shell command cannot be read off its text, so any reference blocks.
        assert_block_contract(
            bash(f"cat {repo_path('hooks', 'block-secrets.py')}"),
            "hooks",
        )

    def test_bash_touching_deployed_codex_home_blocks(self):
        assert_block_contract(bash("cat ~/.codex/config.toml"), "config.toml")

    def test_bash_referencing_only_instruction_markdown_allowed(self):
        instruction = repo_path("hooks", "instructions", "00-response-style.md")

        assert_allowed(bash(f"cat {instruction}"))

    def test_bash_mixing_instruction_markdown_and_protected_path_blocks(self):
        instruction = repo_path("hooks", "instructions", "00-response-style.md")

        assert_block_contract(
            bash(f"cat {instruction} ~/.codex/config.toml"),
            "config.toml",
        )

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

    def test_apply_patch_instruction_markdown_allowed(self):
        assert_allowed(
            apply_patch(repo_path("hooks", "instructions", "00-response-style.md"))
        )

    def test_unrelated_apply_patch_allowed(self):
        assert_allowed(apply_patch("/tmp/notes.txt"))


class TestInstructionMarkdownAllowlist:
    """`instructions/*.md` is prompt text rather than enforcement, so it stays
    writable; anything else under the same directory does not."""

    def test_repo_instruction_markdown_write_allowed(self):
        assert_allowed(
            write(repo_path("hooks", "instructions", "00-response-style.md"))
        )

    def test_deployed_instruction_markdown_write_allowed(self):
        assert_allowed(write("~/.codex/hooks/instructions/00-response-style.md"))

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
    """Exercise the realpath-resolved PROTECTED_PATHS layer."""

    def test_write_through_symlink_to_repo_hook_blocks(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "block-secrets.py")

        assert_block_contract(write(str(alias)), "Codex")

    def test_traversal_normalized_repo_hook_write_blocks(self):
        codex_dir = REPO_ROOT / "modules" / "home" / "apps" / "codex"
        obfuscated = f"{codex_dir}/../codex/hooks/block-secrets.py"
        assert "modules/home/apps/codex/hooks/" not in obfuscated

        assert_block_contract(write(obfuscated), "codex")


class TestPayloadHandling:
    def test_unhandled_tool_defers(self):
        assert_allowed(run_hook(HOOK, "Grep", {"path": repo_path("hooks")}))

    def test_unparsable_payload_defers(self):
        assert_allowed(run_hook(HOOK, stdin_text="not json"))
