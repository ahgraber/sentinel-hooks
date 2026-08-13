"""Tests for the Copilot tamper-protection hook.

Kept in the same shape as the Claude and Codex tamper suites, because the three
hooks enforce one policy over different path sets: reads are allowed, mutations
are blocked, and `instructions/*.md` is the only carve-out. A policy change that
reaches one hook and not the others should show up as a diff between these three
files.

Copilot's path set is the union of all three agents plus VS Code, because
Copilot runs without the per-agent split the other two hooks rely on.
"""

from pathlib import Path

from conftest import assert_allowed, assert_block_contract, run_hook

HOOK = "copilot-block-hook-tampering.py"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"
# tests/ -> copilot/ -> apps/ -> home/ -> modules/ -> repo root (5 levels up),
# matching REPO_ROOT in the hook under test.
REPO_ROOT = Path(__file__).resolve().parents[5]


def repo_path(app: str, *parts: str) -> str:
    return str(Path("modules") / "home" / "apps" / app / Path(*parts))


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

    def test_each_agents_deployed_config_is_readable(self):
        for path in (
            "~/.claude/settings.json",
            "~/.codex/config.toml",
            "~/.copilot/hooks/security-policy.json",
        ):
            assert_allowed(read(path))

    def test_each_agents_repository_config_is_readable(self):
        for path in (
            repo_path("claude", "hooks", "block-secrets.py"),
            repo_path("codex", "rules", "default.rules"),
            repo_path("copilot", "hooks", "security-policy.json"),
            user_path("codex", "config.linux.toml"),
        ):
            assert_allowed(read(path))

    def test_read_through_symlink_to_repo_hook_is_allowed(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "copilot-block-hook-tampering.py")

        assert_allowed(read(str(alias)))


class TestMutationProtection:
    def test_each_agents_deployed_config_write_blocks(self):
        for path, needle in (
            ("~/.claude/settings.json", "settings.json"),
            ("~/.codex/config.toml", "config.toml"),
            ("~/.copilot/hooks/security-policy.json", "security-policy.json"),
        ):
            assert_block_contract(write(path), needle)

    def test_deployed_vscode_settings_write_blocks(self):
        for path in (
            "~/Library/Application Support/Code/User/settings.json",
            "~/.config/Code/User/settings.json",
        ):
            assert_block_contract(write(path), "settings.json")

    def test_each_agents_repository_config_write_blocks(self):
        for path in (
            repo_path("claude", "hooks", "block-secrets.py"),
            repo_path("codex", "rules", "default.rules"),
            repo_path("copilot", "hooks", "security-policy.json"),
            user_path("codex", "config.linux.toml"),
            user_path("vscode", "settings.json"),
        ):
            assert_block_contract(write(path), Path(path).name)

    def test_repo_hook_edit_blocks(self):
        assert_block_contract(
            edit(repo_path("claude", "hooks", "block-secrets.py")),
            "hooks",
        )

    def test_unrelated_write_allowed(self):
        assert_allowed(write("/tmp/notes.txt"))


class TestBashCommandProtection:
    def test_bash_touching_repo_hook_blocks(self):
        # The Bash branch matches on mention, not on intent: the effect of a
        # shell command cannot be read off its text, so any reference blocks.
        assert_block_contract(
            bash(f"cat {repo_path('claude', 'hooks', 'block-secrets.py')}"),
            "hooks",
        )

    def test_bash_touching_each_agents_deployed_home_blocks(self):
        for command, needle in (
            ("cat ~/.claude/settings.json", "settings.json"),
            ("cat ~/.codex/config.toml", "config.toml"),
            ("cat ~/.copilot/hooks/security-policy.json", "security-policy.json"),
        ):
            assert_block_contract(bash(command), needle)

    def test_bash_referencing_only_instruction_markdown_allowed(self):
        instruction = repo_path("copilot", "instructions", "shell.instructions.md")

        assert_allowed(bash(f"cat {instruction}"))

    def test_bash_mixing_instruction_markdown_and_protected_path_blocks(self):
        instruction = repo_path("copilot", "instructions", "shell.instructions.md")

        assert_block_contract(
            bash(f"cat {instruction} ~/.codex/config.toml"),
            "config.toml",
        )

    def test_unrelated_bash_allowed(self):
        assert_allowed(bash("echo hello"))


class TestApplyPatchProtection:
    def test_apply_patch_repo_hook_blocks(self):
        assert_block_contract(
            apply_patch(repo_path("copilot", "hooks", "security-policy.json")),
            "security-policy.json",
        )

    def test_apply_patch_user_config_blocks(self):
        assert_block_contract(
            apply_patch(user_path("codex", "config.linux.toml")),
            "config.linux.toml",
        )

    def test_apply_patch_instruction_markdown_allowed(self):
        assert_allowed(
            apply_patch(repo_path("copilot", "instructions", "shell.instructions.md"))
        )

    def test_unrelated_apply_patch_allowed(self):
        assert_allowed(apply_patch("/tmp/notes.txt"))


class TestInstructionMarkdownAllowlist:
    """`instructions/*.md` is prompt text rather than enforcement, so it stays
    writable; anything else under the same directory does not."""

    def test_each_agents_instruction_markdown_write_allowed(self):
        for path in (
            repo_path("claude", "hooks", "instructions", "00-response-style.md"),
            repo_path("codex", "hooks", "instructions", "00-response-style.md"),
            repo_path("copilot", "instructions", "shell.instructions.md"),
            "~/.claude/hooks/instructions/00-response-style.md",
            "~/.codex/hooks/instructions/00-response-style.md",
            "~/.copilot/instructions/shell.instructions.md",
        ):
            assert_allowed(write(path))

    def test_nested_instruction_path_blocks(self):
        assert_block_contract(
            write(repo_path("copilot", "instructions", "nested", "note.md")),
            "instructions",
        )

    def test_non_markdown_in_instructions_blocks(self):
        assert_block_contract(
            write(repo_path("copilot", "instructions", "helper.py")),
            "instructions",
        )


class TestPathResolution:
    """Exercise the realpath-resolved PROTECTED_PATHS layer."""

    def test_write_through_symlink_to_repo_hook_blocks(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "copilot-block-hook-tampering.py")

        assert_block_contract(write(str(alias)), "Copilot")

    def test_traversal_normalized_repo_rules_write_blocks(self):
        copilot_dir = REPO_ROOT / "modules" / "home" / "apps" / "copilot"
        obfuscated = f"{copilot_dir}/../codex/rules/default.rules"
        assert "modules/home/apps/codex/rules/" not in obfuscated

        assert_block_contract(write(obfuscated), "rules")


class TestPayloadHandling:
    def test_unhandled_tool_defers(self):
        assert_allowed(run_hook(HOOK, "Grep", {"path": repo_path("copilot", "hooks")}))

    def test_unparsable_payload_defers(self):
        assert_allowed(run_hook(HOOK, stdin_text="not json"))
