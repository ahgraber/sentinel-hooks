"""The hook that refuses a tool the vocabulary does not list, for harnesses with no adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from hermetic import HOOKS_DIR
import pytest

HOOK_NAME = "refuse-unlisted-tools.py"
STOP_MARKER = "Do NOT attempt to find alternative commands"


def run_hook(
    tool_name: str, agent: str, hooks_dir: Path = HOOKS_DIR, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the hook as `agent` would: Claude Code by its transcript path, others by declaration."""
    payload: dict = {"tool_name": tool_name, "tool_input": {}, "cwd": "/tmp"}
    env = {**os.environ}
    env.pop("AI_HOOK_AGENT", None)
    if agent == "claude":
        payload["transcript_path"] = "/tmp/transcript.jsonl"
    elif agent != "unknown":
        env["AI_HOOK_AGENT"] = agent
    return subprocess.run(
        ["python3", str(hooks_dir / HOOK_NAME)],
        input=json.dumps(payload) if stdin is None else stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env=env,
    )


def assert_proceeds(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def assert_refused(result: subprocess.CompletedProcess[str], *fragments: str) -> None:
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert STOP_MARKER in result.stderr
    for fragment in fragments:
        assert fragment in result.stderr


@pytest.fixture
def hooks_copy(tmp_path: Path) -> Path:
    """A copy of the hooks directory whose vocabulary a case can break."""
    copy = tmp_path / "hooks"
    shutil.copytree(HOOKS_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    return copy


class TestListedToolsProceed:
    @pytest.mark.parametrize(("agent", "tool"), [("claude", "Bash"), ("claude", "Edit"), ("codex", "apply_patch")])
    def test_a_mapped_tool_proceeds(self, agent: str, tool: str) -> None:
        assert_proceeds(run_hook(tool, agent))

    @pytest.mark.parametrize(("agent", "tool"), [("claude", "Glob"), ("claude", "Agent"), ("codex", "update_plan")])
    def test_a_passthrough_tool_proceeds(self, agent: str, tool: str) -> None:
        assert_proceeds(run_hook(tool, agent))

    @pytest.mark.parametrize("agent", ["claude", "codex"])
    def test_a_tool_matched_by_a_passthrough_pattern_proceeds(self, agent: str) -> None:
        assert_proceeds(run_hook("mcp__server__any_tool", agent))


class TestUnlistedToolsAreRefused:
    @pytest.mark.parametrize(("agent", "tool"), [("claude", "Monitor"), ("codex", "future_tool")])
    def test_an_unlisted_tool_is_refused_naming_the_tool_and_the_file(self, agent: str, tool: str) -> None:
        assert_refused(run_hook(tool, agent), f"'{tool}'", "tool-vocabulary.toml")

    def test_a_spelling_of_another_harness_is_refused(self) -> None:
        """Each harness is judged against its own table: Codex's shell spelling is not Claude's."""
        assert_refused(run_hook("apply_patch", "claude"), "'apply_patch'")

    def test_an_unidentified_harness_is_refused(self) -> None:
        assert_refused(run_hook("Bash", "unknown"), "'Bash'")

    def test_a_mapping_to_another_name_is_refused(self, hooks_copy: Path) -> None:
        """The hooks judge the name Claude sends, so a converted name would be judged by none."""
        vocabulary = hooks_copy / "tool-vocabulary.toml"
        text = vocabulary.read_text().replace("[mappings.claude]\n", '[mappings.claude]\nNovelTool = "Bash"\n')
        vocabulary.write_text(text)
        assert_refused(run_hook("NovelTool", "claude", hooks_copy), "'NovelTool' is mapped to 'Bash'", "no adapter")


class TestUnreadableVocabularyRefusesEveryCall:
    @pytest.mark.parametrize("tool", ["Read", "Glob", "Bash"])
    def test_a_missing_vocabulary_refuses_even_a_read(self, hooks_copy: Path, tool: str) -> None:
        (hooks_copy / "tool-vocabulary.toml").unlink()
        assert_refused(run_hook(tool, "claude", hooks_copy), "tool-vocabulary.toml", "repair the file by hand")

    def test_an_unparsable_vocabulary_names_the_error(self, hooks_copy: Path) -> None:
        (hooks_copy / "tool-vocabulary.toml").write_text("[groups\n")
        result = run_hook("Read", "codex", hooks_copy)
        assert_refused(result, "tool-vocabulary.toml")
        assert "Expected" in result.stderr or "Invalid" in result.stderr or "line 1" in result.stderr

    def test_an_invalid_vocabulary_names_the_error(self, hooks_copy: Path) -> None:
        (hooks_copy / "tool-vocabulary.toml").write_text("[groups]\n")
        assert_refused(
            run_hook("Read", "claude", hooks_copy), "expected groups, ask, mappings, passthrough, and refused"
        )


def test_an_unparsable_payload_warns_and_proceeds() -> None:
    """A payload that names no tool takes the read-only direction.

    The unparsed payload does not name the agent either, so the warning takes the
    exit code for an unidentified agent, which proceeds.
    """
    result = run_hook("", "claude", stdin="{not json")
    assert result.returncode == 0
    assert "could not parse" in result.stderr


def test_the_instruction_text_loads_without_the_vocabulary(hooks_copy: Path) -> None:
    """The refusal needs the stop instruction even when the vocabulary is the failure."""
    (hooks_copy / "tool-vocabulary.toml").unlink()
    probe = "import hook_response; print(hook_response.TOOL_VOCABULARY is None, 'AI INSTRUCTIONS' in hook_response.STOP_INSTRUCTIONS)"
    result = subprocess.run(
        ["python3", "-c", probe], cwd=hooks_copy, capture_output=True, text=True, check=False, timeout=10
    )
    assert result.stdout.split() == ["True", "True"], result.stderr
