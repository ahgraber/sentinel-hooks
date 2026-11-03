"""Shared-hook outcomes that must reach VS Code through the adapter in Copilot's encoding.

Each case runs the real adapter as VS Code does, so the payload translation, the
agent declaration, and the output rewrite all lie between the hook and the result.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from conftest import ADAPTER_PATH, HOOKS_DIR
import pytest

RULES_NAME = "block-destructive-ops-patterns.toml"


def run_adapter(script: str, payload: dict, adapter: Path = ADAPTER_PATH) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(adapter), script],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


class TestSuggestiveNames:
    """Validates: SuggestiveNamesAsk, through the Copilot adapter."""

    def test_a_write_to_a_suggestive_name_reaches_vscode_as_an_ask(self, tmp_path) -> None:
        target = tmp_path / "auth_token.json"
        result = run_adapter(
            "block-sensitive-paths.py",
            {"tool_name": "create_file", "tool_input": {"filePath": str(target), "content": "{}"}},
        )

        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)["hookSpecificOutput"]
        assert output["permissionDecision"] == "ask"
        assert "auth_token.json" in output["permissionDecisionReason"]

    def test_a_read_of_a_suggestive_name_is_refused_without_an_approval_line(self, tmp_path) -> None:
        """VS Code cannot prompt for a read, so the ask degrades to a refusal (AgentThatCannotPrompt)."""
        target = tmp_path / "auth_token.json"
        result = run_adapter(
            "block-sensitive-paths.py", {"tool_name": "read_file", "tool_input": {"filePath": str(target)}}
        )

        assert result.returncode == 2, result.stdout
        assert result.stdout == ""
        assert "auth_token.json" in result.stderr
        assert "approve" not in result.stderr.lower()


def _adapter_beside_rules(tmp_path: Path, rules: str | None) -> Path:
    """Copy the adapter and the shared hooks into the layout it resolves, with `rules` as the pattern file.

    `None` removes the pattern file. The real rules file is never touched.
    """
    hooks = tmp_path / "sentinel/hooks"
    shutil.copytree(HOOKS_DIR, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    if rules is None:
        (hooks / RULES_NAME).unlink()
    else:
        (hooks / RULES_NAME).write_text(rules)
    adapter = tmp_path / "sentinel/harnesses/copilot/copilot-vscode-hook-adapter.py"
    adapter.parent.mkdir(parents=True)
    shutil.copy(ADAPTER_PATH, adapter)
    return adapter


INVALID_RULE = '[[rules]]\npattern = "invalid-rule"\ndescription = "Unknown mode"\nreason = "r"\nmode = "deny"\n'
PATTERN_FILE_FAULTS = {
    "missing": (None, RULES_NAME),
    "unparsable": ("[[rules]\n", RULES_NAME),
    "invalid rule": (INVALID_RULE, "invalid-rule"),
}


@pytest.mark.parametrize(("rules", "named"), PATTERN_FILE_FAULTS.values(), ids=PATTERN_FILE_FAULTS.keys())
@pytest.mark.parametrize("command", ["ls", "rm -rf build"])
def test_a_pattern_file_fault_reaches_vscode_as_a_refusal_naming_the_fault(tmp_path, rules, named, command) -> None:
    """Validates: ExternalPatternFile faults, through the Copilot adapter.

    The fault asks, and VS Code cannot prompt for a terminal command, so the ask
    degrades to a refusal that names the fault.
    """
    adapter = _adapter_beside_rules(tmp_path, rules)
    result = run_adapter(
        "block-destructive-ops.py", {"tool_name": "run_in_terminal", "tool_input": {"command": command}}, adapter
    )

    assert result.returncode == 2, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert result.stdout == ""
    assert named in result.stderr
    assert "cannot show a confirmation prompt" in result.stderr


class TestEveryInputFieldIsScanned:
    """Validates: TieredSecretDetection scans every field of the call, through the Copilot adapter."""

    def test_a_credential_beside_the_terminal_command_is_refused(self) -> None:
        # Assembled at run time so no secret-shaped literal sits in the file.
        token = "ghp_" + "R7kq2Lm9Xv4Bn8Tw3Yc6Pd1Hs5Jf0Ga2Ke7Q"
        result = run_adapter(
            "block-leaks.py",
            {"tool_name": "run_in_terminal", "tool_input": {"command": "echo done", "explanation": f"uses {token}"}},
        )

        assert result.returncode == 2, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "credential" in result.stderr.lower()
