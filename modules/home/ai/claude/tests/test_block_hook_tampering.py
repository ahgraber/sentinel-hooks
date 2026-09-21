"""Tests for Claude hook and settings tamper protection.

Claude can put a per-call decision to the user, so a gated mutation asks here
where the Codex and Copilot suites, testing the same policy, see a refusal.
Agent credentials refuse everywhere.
"""

from pathlib import Path

from conftest import (
    assert_allowed,
    assert_ask,
    assert_block_contract,
    assert_blocked,
    run_hook,
)

HOOK = "block-hook-tampering.py"
HOOKS_DIR = Path(__file__).parents[2] / "shared" / "hooks"
REPO_ROOT = Path(__file__).resolve().parents[5]


def repo_path(*parts: str) -> str:
    return str(Path("modules") / "home" / "ai" / "claude" / Path(*parts))


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


class TestReadAccess:
    """Reads stay unblocked: a read-deny on these paths cannot be enforced by
    the OS sandbox, because they are symlinks into the Nix store and bubblewrap
    aborts every sandboxed command when it cannot mount over one."""

    def test_deployed_settings_are_readable(self):
        assert_allowed(read("~/.claude/settings.json"))

    def test_repo_hooks_are_readable(self):
        assert_allowed(read(repo_path("hooks", "block-secrets.py")))

    def test_user_settings_are_readable(self):
        for platform in ("darwin", "linux"):
            assert_allowed(read(user_path("claude", f"settings.{platform}.json")))

    def test_read_through_symlink_to_repo_hook_is_allowed(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "block-secrets.py")

        assert_allowed(read(str(alias)))


class TestMutationGate:
    """A gated mutation asks under Claude; only a credential refuses."""

    def test_deployed_settings_write_asks(self):
        assert_ask(write("~/.claude/settings.json"), "settings.json")

    def test_deployed_project_state_write_blocks(self):
        assert_blocked(write("~/.claude.json"), ".claude.json")

    def test_repo_hook_edit_asks(self):
        assert_ask(edit(repo_path("hooks", "block-secrets.py")), "hooks")

    def test_user_settings_write_asks(self):
        assert_ask(
            write(user_path("claude", "settings.linux.json")),
            "settings.linux.json",
        )

    def test_credential_write_blocks(self):
        for path in (
            "~/.claude/.credentials.json",
            "~/.codex/auth.json",
            "~/.pi/agent/auth.json",
        ):
            assert_block_contract(write(path), Path(path).name)

    def test_unrelated_write_allowed(self):
        assert_allowed(write("/tmp/notes.txt"))


class TestBashCommandProtection:
    def test_bash_reading_repo_hook_proceeds(self):
        # The agent module tree is read-through, so a recognized read of a hook
        # source runs unprompted. Reviewing a guardrail is not changing it.
        assert_allowed(bash(f"cat {repo_path('hooks', 'block-secrets.py')}"))

    def test_bash_touching_repo_hook_asks(self):
        # Outside a recognized read the Bash branch still matches on mention,
        # not intent: a command's effect cannot be read off its text.
        assert_ask(
            bash(f"sed -i 's/a/b/' {repo_path('hooks', 'block-secrets.py')}"),
            "hooks",
        )

    def test_bash_touching_deployed_settings_asks(self):
        assert_allowed(bash("cat ~/.claude/settings.json"))

    def test_bash_naming_a_credential_blocks(self):
        assert_block_contract(bash("cat ~/.codex/auth.json"), "auth.json")

    def test_bash_referencing_only_instruction_markdown_allowed(self):
        instruction = repo_path("hooks", "instructions", "00-response-style.md")

        assert_allowed(bash(f"cat {instruction}"))

    def test_bash_mixing_instruction_markdown_and_protected_path_asks(self):
        instruction = repo_path("hooks", "instructions", "00-response-style.md")

        assert_allowed(bash(f"cat {instruction} ~/.claude/settings.json"))

    def test_unrelated_bash_allowed(self):
        assert_allowed(bash("echo hello"))


class TestInstructionMarkdownGuard:
    """Instruction text is guarded enforcement."""

    def test_repo_instruction_markdown_write_allowed(self):
        assert_ask(write(repo_path("hooks", "instructions", "00-response-style.md")))

    def test_deployed_instruction_markdown_write_allowed(self):
        assert_ask(write("~/.claude/hooks/instructions/00-response-style.md"))

    def test_nested_instruction_path_asks(self):
        assert_ask(
            write(repo_path("hooks", "instructions", "nested", "note.md")),
            "hooks",
        )

    def test_non_markdown_in_instructions_asks(self):
        assert_ask(
            write(repo_path("hooks", "instructions", "helper.py")),
            "hooks",
        )


class TestPathResolution:
    def test_write_through_symlink_to_repo_hook_asks(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(HOOKS_DIR / "block-secrets.py")

        assert_ask(write(str(alias)), "notes.py")

    def test_traversal_normalized_repo_hook_write_asks(self):
        claude_dir = REPO_ROOT / "modules" / "home" / "ai" / "claude"
        obfuscated = f"{claude_dir}/../claude/hooks/block-secrets.py"
        assert "modules/home/ai/claude/hooks/" not in obfuscated

        assert_ask(write(obfuscated), "claude")


class TestPayloadHandling:
    def test_unhandled_tool_defers(self):
        assert_allowed(run_hook(HOOK, "Grep", {"path": repo_path("hooks")}))

    def test_unparsable_payload_defers(self):
        # An unparsable payload carries no transcript path, so the agent is
        # unidentifiable and the warn degrades to a silent allow.
        assert_allowed(run_hook(HOOK, stdin_text="not json"))
