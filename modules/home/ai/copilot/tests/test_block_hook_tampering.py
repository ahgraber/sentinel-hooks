"""Tests for the Copilot tamper-protection hook.

Deliberately parallel to the Claude and Codex tamper suites: one policy over
three path sets, so a change reaching one hook and not the others shows up as a
diff between the files. Copilot's set is the union of all three agents plus VS
Code, because it runs without the per-agent split the other two rely on.
"""

from pathlib import Path

from conftest import assert_allowed, assert_ask, assert_block_contract, run_hook

HOOK = "block-hook-tampering.py"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"
# Matches REPO_ROOT in the hook under test.
REPO_ROOT = Path(__file__).resolve().parents[5]


def repo_path(app: str, *parts: str) -> str:
    return str(Path("modules") / "home" / "ai" / app / Path(*parts))


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
    """Reads stay unblocked: these paths are Nix store symlinks, and bubblewrap
    aborts a sandboxed command when it cannot mount over one."""

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
        alias.symlink_to(HOOKS_DIR / "copilot-vscode-hook-adapter.py")

        assert_allowed(read(str(alias)))


class TestMutationGate:
    """A gated file-tool mutation asks; a credential refuses on every tool."""

    def test_each_agents_deployed_config_write_asks(self):
        for path, needle in (
            ("~/.claude/settings.json", "settings.json"),
            ("~/.codex/config.toml", "config.toml"),
            ("~/.copilot/hooks/security-policy.json", "security-policy.json"),
        ):
            assert_ask(write(path), needle)

    def test_deployed_vscode_settings_write_asks(self):
        for path in (
            "~/Library/Application Support/Code/User/settings.json",
            "~/.config/Code/User/settings.json",
        ):
            assert_ask(write(path), "settings.json")

    def test_each_agents_repository_config_write_asks(self):
        for path in (
            repo_path("claude", "hooks", "block-secrets.py"),
            repo_path("codex", "rules", "default.rules"),
            repo_path("copilot", "hooks", "security-policy.json"),
            user_path("codex", "config.linux.toml"),
        ):
            assert_ask(write(path), Path(path).name)

    def test_credential_write_blocks(self):
        for path in (
            "~/.claude/.credentials.json",
            "~/.codex/auth.json",
            "~/.pi/agent/auth.json",
        ):
            assert_block_contract(write(path), Path(path).name)

    def test_vscode_settings_write_is_not_gated_here(self):
        """A preference file rather than enforcement, so the permission layer prompts.

        Copilot has no permission surface, so nothing prompts there: the accepted
        cost of not refusing it outright.
        """
        assert_allowed(write(user_path("vscode", "settings.json")))

    def test_repo_hook_edit_asks(self):
        assert_ask(
            edit(repo_path("claude", "hooks", "block-secrets.py")),
            "hooks",
        )

    def test_unrelated_write_allowed(self):
        assert_allowed(write("/tmp/notes.txt"))


class TestBashCommandProtection:
    """The shell tool proceeds past the prompt JSON on this surface, so a gated
    Bash command refuses instead of asking: prompting would be fail-open."""

    def test_bash_touching_repo_hook_blocks(self):
        # The Bash branch matches on mention, not intent: a command's effect is
        # not readable from its text, so any reference is gated.
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

    def test_bash_naming_a_credential_blocks(self):
        assert_block_contract(bash("cat ~/.codex/auth.json"), "auth.json")

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
    """Only the probed file-mutation tools ask; a gated patch refuses."""

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
    """`instructions/*.md` is prompt text rather than enforcement, so it stays writable."""

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

    def test_nested_instruction_path_asks(self):
        assert_ask(
            write(repo_path("copilot", "instructions", "nested", "note.md")),
            "instructions",
        )

    def test_non_markdown_in_instructions_asks(self):
        assert_ask(
            write(repo_path("copilot", "instructions", "helper.py")),
            "instructions",
        )


class TestPathResolution:
    """Exercise the realpath-resolved layer."""

    def test_write_through_symlink_to_repo_hook_asks(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "copilot-vscode-hook-adapter.py")

        assert_ask(write(str(alias)), "notes.py")

    def test_traversal_normalized_repo_rules_write_asks(self):
        copilot_dir = REPO_ROOT / "modules" / "home" / "ai" / "copilot"
        obfuscated = f"{copilot_dir}/../codex/rules/default.rules"
        assert "modules/home/ai/codex/rules/" not in obfuscated

        assert_ask(write(obfuscated), "rules")


class TestPayloadHandling:
    def test_unhandled_tool_defers(self):
        assert_allowed(run_hook(HOOK, "Grep", {"path": repo_path("copilot", "hooks")}))

    def test_unparsable_payload_defers(self):
        assert_allowed(run_hook(HOOK, stdin_text="not json"))
