"""Tests for the destructive-ops hook engine, using synthetic rules."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

from conftest import run_hook as run_installed_hook
import pytest

HOOKS_DIR = Path(__file__).resolve().parents[2] / "shared" / "hooks"
HOOK_SOURCE = HOOKS_DIR / "block-destructive-ops.py"
RULES_NAME = "block-destructive-ops-patterns.toml"
# The hook reads rules from its own directory, so tests run a copy beside
# synthetic ones; its sibling imports have to travel with the copy.
SIBLING_MODULES = ("hook_response.py", "guarded_paths.py", "guarded-paths.toml", "tool-vocabulary.toml")
RULES = r"""
[[rules]]
pattern = "synthetic-block"
description = "Synthetic block"
reason = "Blocked by the test rule"
mode = "block"

[[rules]]
pattern = "synthetic-ask"
description = "Synthetic ask"
reason = "Confirm the test rule"
mode = "ask"

[[rules]]
pattern = "case-sensitive-source"
description = "Case-insensitive rule"
reason = "Matched without case"
mode = "block"
case_insensitive = true

[[rules]]
pattern = "["
description = "Invalid regular expression"
reason = "This rule must be skipped"
mode = "block"

[[rules]]
pattern = 'synthetic-danger\s+-force'
description = "Synthetic multi-word"
reason = "Blocked by the multi-word test rule"
mode = "block"
"""


def _load_hook_module():
    """Import the hook as a module so its helpers can be tested directly.

    The filename is not a valid identifier, so it cannot be imported by name.
    """
    spec = importlib.util.spec_from_file_location("block_destructive_ops", HOOK_SOURCE)
    module = importlib.util.module_from_spec(spec)
    # Loading by location does not put the hook's directory on the import path
    # the way running it by path does.
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec.loader.exec_module(module)
    return module


normalize = _load_hook_module().normalize


def install_hook(directory: Path) -> Path:
    """Place a runnable copy of the hook in `directory`, siblings included."""
    path = directory / HOOK_SOURCE.name
    shutil.copyfile(HOOK_SOURCE, path)
    for name in SIBLING_MODULES:
        shutil.copyfile(HOOKS_DIR / name, directory / name)
    return path


@pytest.fixture
def hook_path(tmp_path: Path) -> Path:
    path = install_hook(tmp_path)
    (tmp_path / RULES_NAME).write_text(RULES)
    return path


def run_hook(
    hook_path: Path,
    command: str = "",
    *,
    tool_name: str = "Bash",
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = stdin_text
    if payload is None:
        payload = json.dumps(
            {
                "tool_name": tool_name,
                "tool_input": {"command": command},
                # Marks an ask-capable agent, so `ask` rules prompt not block.
                "transcript_path": "/tmp/transcript.jsonl",
            }
        )
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=payload,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def test_non_bash_tools_and_unmatched_commands_are_allowed(hook_path: Path) -> None:
    assert run_hook(hook_path, "synthetic-block", tool_name="Write").returncode == 0
    assert run_hook(hook_path, "safe command").returncode == 0


def test_block_rule_blocks_with_reason_and_contract(hook_path: Path) -> None:
    result = run_hook(hook_path, "run synthetic-block now")

    assert result.returncode == 2
    assert "Blocked by the test rule" in result.stderr
    assert "AI INSTRUCTIONS:" in result.stderr


def test_ask_rule_returns_claude_confirmation(hook_path: Path) -> None:
    result = run_hook(hook_path, "run synthetic-ask now")

    assert result.returncode == 0
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    assert "Confirm the test rule" in output["permissionDecisionReason"]


def test_case_insensitive_rules_match_and_invalid_regexes_are_skipped(
    hook_path: Path,
) -> None:
    assert run_hook(hook_path, "CASE-SENSITIVE-SOURCE").returncode == 2
    assert run_hook(hook_path, "[").returncode == 0


def test_missing_rules_fail_open(tmp_path: Path) -> None:
    assert run_hook(install_hook(tmp_path), "synthetic-block").returncode == 0


def test_malformed_hook_input_fails_closed(hook_path: Path) -> None:
    """Even a parse failure must state why: the agent is told to stop and report,
    and it cannot report a reason it was never given."""
    result = run_hook(hook_path, stdin_text="not json")

    assert result.returncode == 2
    assert "could not parse the hook payload" in result.stderr
    assert "AI INSTRUCTIONS:" in result.stderr


def test_nested_rule_sections_are_loaded(tmp_path: Path) -> None:
    hook_path = install_hook(tmp_path)
    (tmp_path / RULES_NAME).write_text(
        r"""
[[synthetic.rules]]
pattern = "nested-rule"
description = "Nested rule"
reason = "Loaded from a nested section"
mode = "block"
"""
    )

    assert run_hook(hook_path, "nested-rule").returncode == 2


def test_block_wins_over_earlier_ask_rule(hook_path: Path) -> None:
    """A block rule must win even when an ask rule matches earlier in the file.

    'synthetic-ask' (ask, rule index 1) and 'case-sensitive-source' (block, rule
    index 2) both match. First-match-wins would downgrade the block to a prompt;
    the two-pass engine blocks.
    """
    result = run_hook(hook_path, "synthetic-ask and case-sensitive-source together")

    assert result.returncode == 2
    assert "Matched without case" in result.stderr
    assert "permissionDecision" not in result.stdout


class TestNormalize:
    """Unit tests for the spelling normalizer that runs before rule matching."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            pytest.param("r'm' -rf /", "rm -rf /", id="single-quote-splice"),
            pytest.param('r"m" -rf /', "rm -rf /", id="double-quote-splice"),
            pytest.param('c""at .env', "cat .env", id="empty-double-pair"),
            pytest.param("c''at .env", "cat .env", id="empty-single-pair"),
            pytest.param("'rm' -rf /", "rm -rf /", id="standalone-quoted-word"),
            pytest.param("rm \\\n -rf /", "rm  -rf /", id="continuation-between-words"),
            pytest.param("r\\\nm -rf /", "rm -rf /", id="continuation-within-word"),
            pytest.param("pre'fix suffix'", "prefix suffix", id="adjacent-span-splices"),
        ],
    )
    def test_obfuscated_spelling_is_rewritten(self, command, expected):
        assert normalize(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("echo hello", id="nothing-to-rewrite"),
            pytest.param("grep 'rm -rf /' file", id="quoted-search-argument"),
            pytest.param("git log --grep 'the rm -rf bug'", id="quoted-multiword-flag"),
            pytest.param("cat 'my file.txt'", id="quoted-path-with-space"),
            pytest.param("cat 'unbalanced", id="unbalanced-quote"),
        ],
    )
    def test_argument_quoting_is_preserved(self, command):
        """A quoted span standing alone as an argument keeps its quotes.

        Stripping them would turn a command that searches for a string into one
        that reads as if it runs it.
        """
        assert normalize(command) == command


class TestNormalizedRuleMatching:
    """Rules fire on obfuscated spellings, via the synthetic rule set."""

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param('synthetic-b""lock', id="empty-double-pair"),
            pytest.param("synthetic-b''lock", id="empty-single-pair"),
            pytest.param("synthetic-b'l'ock", id="single-quote-splice"),
            pytest.param('synthetic-b"l"ock', id="double-quote-splice"),
            pytest.param("'synthetic-block'", id="standalone-quoted-word"),
            pytest.param("synthetic-\\\nblock", id="line-continuation"),
            pytest.param("run synthetic-b'l'ock now", id="spliced-within-command"),
        ],
    )
    def test_obfuscated_command_still_blocks(self, hook_path: Path, command):
        result = run_hook(hook_path, command)

        assert result.returncode == 2, f"stdout: {result.stdout}"
        assert "Blocked by the test rule" in result.stderr

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("echo 'synthetic block'", id="hyphen-absent-in-quotes"),
            pytest.param("git log --grep 'synthetic'", id="quoted-search-argument"),
            pytest.param('echo "safe command"', id="quoted-safe-command"),
        ],
    )
    def test_ordinary_quoted_command_is_untouched(self, hook_path: Path, command):
        assert run_hook(hook_path, command).returncode == 0

    def test_multiword_rule_is_not_assembled_across_arguments(self, hook_path: Path) -> None:
        """Unquoting must not weld separate arguments into a rule match.

        `synthetic-danger\\s+-force` matches only when the two words are
        adjacent; quoting them apart must stay apart.
        """
        assert run_hook(hook_path, "echo 'synthetic-danger' x '-force'").returncode == 0


def _verdict(command: str) -> str:
    """Run the installed hook, with the real rule catalogue, and label the outcome."""
    result = run_installed_hook("block-destructive-ops.py", "Bash", {"command": command})
    if result.exit_code == 2:
        return "block"
    if "permissionDecision" in result.stdout:
        return "ask"
    return "allow"


NORMALIZATION_PAIRS = [
    pytest.param("rm -rf /tmp/scratch", "r'm' -rf /tmp/scratch", id="rm-quote-splice"),
    pytest.param("rm -rf ~/data", "rm \\\n-rf ~/data", id="rm-line-continuation"),
    pytest.param("git push --force", 'git push --f"o"rce', id="force-push-splice"),
    pytest.param("git reset --hard", "git re's'et --hard", id="reset-hard-splice"),
    pytest.param("chmod -R 777 /etc", "ch''mod -R 777 /etc", id="chmod-empty-pair"),
    pytest.param("git clean -fd", "'git' clean -fd", id="clean-standalone-quote"),
    pytest.param(
        "git -c core.pager=sh log",
        "git -c core.pa'g'er=sh log",
        id="config-injection-splice",
    ),
]


class TestCatalogueNormalizationParity:
    """The deployed catalogue must treat both spellings of a command alike.

    Asserting the two verdicts agree — rather than asserting a specific verdict —
    keeps these tests independent of the rules themselves. A pattern can be
    retuned, retitled, or moved between block and ask without touching this file.
    """

    @pytest.mark.parametrize(("plain", "obfuscated"), NORMALIZATION_PAIRS)
    def test_spellings_agree(self, plain: str, obfuscated: str) -> None:
        expected = _verdict(plain)
        actual = _verdict(obfuscated)

        assert actual == expected, f"Spelling changed the verdict: {plain!r} -> {expected}, {obfuscated!r} -> {actual}"

    def test_parity_table_is_not_vacuous(self) -> None:
        """At least one pair must reach a rule, or parity proves nothing.

        Without this, emptying the catalogue would leave every pair agreeing on
        'allow' and the suite above would still pass.
        """
        verdicts = [_verdict(param.values[0]) for param in NORMALIZATION_PAIRS]

        assert any(v != "allow" for v in verdicts), f"No pair in NORMALIZATION_PAIRS matches any rule: {verdicts}"
