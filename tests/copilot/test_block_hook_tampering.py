"""Tests for the Copilot tamper-protection hook.

Deliberately parallel to the Claude and Codex tamper suites: one policy over
three path sets, so a change reaching one hook and not the others shows up as a
diff between the files. Copilot's set is the union of all three agents plus VS
Code, because it runs without the per-agent split the other two rely on.
"""

from pathlib import Path

from conftest import ADAPTER_PATH, REPO_ROOT, assert_allowed, assert_ask, assert_block_contract, run_hook

HOOK = "block-hook-tampering.py"


def plugin_path(*parts: str) -> str:
    """A path in the checkout's plugin directory, which the running hooks put in the floor."""
    return str(Path("plugins") / "sentinel" / Path(*parts))


def project_path(agent: str, *parts: str) -> str:
    """A path in the project's own configuration directory for `agent`."""
    return str(Path(f".{agent}") / Path(*parts))


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

    def test_each_agents_deployed_config_is_readable(self):
        for path in (
            "~/.claude/settings.json",
            "~/.codex/config.toml",
            "~/.copilot/hooks/security-policy.json",
        ):
            assert_allowed(read(path))

    def test_each_agents_repository_config_is_readable(self):
        for path in (
            plugin_path("hooks", "block-leaks.py"),
            project_path("codex", "rules", "default.rules"),
            plugin_path("com.github.copilot", "hooks", "hooks.json"),
            project_path("codex", "linux.config.toml"),
        ):
            assert_allowed(read(path))

    def test_read_through_symlink_to_repo_hook_is_allowed(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(ADAPTER_PATH)

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
            plugin_path("hooks", "block-leaks.py"),
            project_path("codex", "rules", "default.rules"),
            plugin_path("com.github.copilot", "hooks", "hooks.json"),
            project_path("codex", "linux.config.toml"),
        ):
            assert_ask(write(path), Path(path).name)

    def test_credential_write_blocks(self):
        for path in (
            "~/.claude/.credentials.json",
            "~/.codex/auth.json",
            "~/.pi/agent/auth.json",
        ):
            assert_block_contract(write(path), Path(path).name)

    def test_project_vscode_settings_write_asks(self):
        assert_ask(write(project_path("vscode", "settings.json")), "settings.json")

    def test_repo_hook_edit_asks(self):
        assert_ask(
            edit(plugin_path("hooks", "block-leaks.py")),
            "hooks",
        )

    def test_unrelated_write_allowed(self):
        assert_allowed(write("/tmp/notes.txt"))


class TestBashCommandProtection:
    """The shell tool proceeds past the prompt JSON on this surface, so a gated
    Bash command refuses instead of asking: prompting would be fail-open."""

    def test_bash_reading_repo_hook_proceeds(self):
        # The agent module tree is read-through, so a recognized read runs
        # unprompted on the agent whose gate is a refusal rather than a prompt.
        assert_allowed(bash(f"cat {plugin_path('hooks', 'block-leaks.py')}"))

    def test_bash_touching_repo_hook_asks(self):
        # Outside a recognized read the Bash branch matches on mention, not
        # intent: a command's effect is not readable from its text.
        assert_ask(
            bash(f"sed -i 's/a/b/' {plugin_path('hooks', 'block-leaks.py')}"),
            "hooks",
        )

    def test_bash_touching_each_agents_deployed_configuration_blocks(self):
        for command, _ in (
            ("cat ~/.claude/settings.json", "settings.json"),
            ("cat ~/.codex/config.toml", "config.toml"),
        ):
            assert_allowed(bash(command))

    def test_bash_reading_a_deployed_module_file_proceeds(self):
        # A deployed guardrail is a symlink into the agent module tree, so the
        # read-through declaration reaches it through its resolved spelling.
        assert_allowed(bash("cat ~/.copilot/hooks/security-policy.json"))

    def test_bash_naming_a_credential_blocks(self):
        assert_block_contract(bash("cat ~/.codex/auth.json"), "auth.json")

    def test_bash_referencing_only_instruction_markdown_allowed(self):
        instruction = plugin_path("hooks", "instructions", "shell.instructions.md")

        assert_allowed(bash(f"cat {instruction}"))

    def test_bash_mixing_instruction_markdown_and_protected_path_blocks(self):
        instruction = plugin_path("hooks", "instructions", "shell.instructions.md")

        assert_allowed(bash(f"cat {instruction} ~/.codex/config.toml"))

    def test_unrelated_bash_allowed(self):
        assert_allowed(bash("echo hello"))


class TestApplyPatchProtection:
    """A gated patch asks, as the editor shows a hook's ask on `apply_patch`."""

    def test_apply_patch_repo_hook_asks(self):
        assert_ask(
            apply_patch(plugin_path("com.github.copilot", "hooks", "hooks.json")),
            "hooks.json",
        )

    def test_apply_patch_project_config_asks(self):
        assert_ask(
            apply_patch(project_path("codex", "linux.config.toml")),
            "linux.config.toml",
        )

    def test_apply_patch_instruction_markdown_asks(self):
        assert_ask(
            apply_patch(plugin_path("hooks", "instructions", "shell.instructions.md")),
            "shell.instructions.md",
        )

    def test_unrelated_apply_patch_allowed(self):
        assert_allowed(apply_patch("/tmp/notes.txt"))


class TestInstructionMarkdownGuard:
    """Instruction text is guarded enforcement."""

    def test_each_agents_instruction_markdown_write_asks(self):
        for path in (
            plugin_path("hooks", "instructions", "00-response-style.md"),
            plugin_path("hooks", "instructions", "shell.instructions.md"),
            "~/.claude/hooks/instructions/00-response-style.md",
            "~/.codex/hooks/instructions/00-response-style.md",
            "~/.copilot/instructions/shell.instructions.md",
        ):
            assert_ask(write(path))

    def test_nested_instruction_path_asks(self):
        assert_ask(
            write(plugin_path("hooks", "instructions", "nested", "note.md")),
            "instructions",
        )

    def test_non_markdown_in_instructions_asks(self):
        assert_ask(
            write(plugin_path("hooks", "instructions", "helper.py")),
            "instructions",
        )


class TestPathResolution:
    """Exercise the realpath-resolved layer."""

    def test_write_through_symlink_to_repo_hook_asks(self, tmp_path: Path):
        alias = tmp_path / "notes.py"
        alias.symlink_to(ADAPTER_PATH)

        assert_ask(write(str(alias)), "notes.py")

    def test_traversal_normalized_registration_write_asks(self):
        copilot_dir = REPO_ROOT / "plugins" / "sentinel" / "harnesses" / "copilot"
        obfuscated = f"{copilot_dir}/../codex/hooks.json"
        assert "harnesses/codex/hooks.json" not in obfuscated

        assert_ask(write(obfuscated), "hooks.json")


class TestPayloadHandling:
    def test_unhandled_tool_defers(self):
        assert_allowed(run_hook(HOOK, "Grep", {"path": plugin_path("harnesses", "copilot")}))

    def test_unparsable_payload_defers(self):
        assert_allowed(run_hook(HOOK, stdin_text="not json"))
