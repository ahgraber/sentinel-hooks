from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)
HOOK = (
    REPO_ROOT
    / "modules"
    / "home"
    / "apps"
    / "copilot"
    / "hooks"
    / "copilot-block-hook-tampering.py"
)


def run_hook(tool_name: str, tool_input: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--script", str(HOOK)],
        input=json.dumps({"tool_name": tool_name, "tool_input": tool_input}),
        capture_output=True,
        text=True,
        check=False,
    )


def assert_blocked(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 2
    assert "do not attempt" in result.stderr.lower()


def test_blocks_each_agents_deployed_security_config() -> None:
    for path in (
        "~/.claude/settings.json",
        "~/.codex/config.toml",
        "~/.copilot/hooks/security-policy.json",
    ):
        assert_blocked(run_hook("Read", {"file_path": path}))


def test_blocks_each_agents_repository_security_config() -> None:
    for path in (
        "modules/home/apps/claude/hooks/block-secrets.py",
        "modules/home/apps/codex/rules/default.rules",
        "users/mithras/home-manager/codex/config.linux.toml",
        "users/alex.graber/home-manager/vscode/settings.json",
    ):
        assert_blocked(run_hook("Write", {"file_path": path}))


def test_blocks_normalized_repository_security_path() -> None:
    path = REPO_ROOT / "modules/home/apps/copilot/../codex/rules/default.rules"

    assert_blocked(run_hook("Edit", {"file_path": str(path)}))


def test_allows_instruction_markdown_and_unrelated_files() -> None:
    for path in (
        "modules/home/apps/claude/hooks/instructions/00-response-style.md",
        "modules/home/apps/copilot/instructions/shell.instructions.md",
        "/tmp/notes.txt",
    ):
        result = run_hook("Write", {"file_path": path})
        assert result.returncode == 0, result.stderr
