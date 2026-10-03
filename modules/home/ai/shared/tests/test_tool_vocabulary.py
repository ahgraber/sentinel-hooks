"""The declared tool vocabulary and its consumers."""

import ast
from pathlib import Path

import guarded_paths
from hermetic import load_hook
import hook_response
import pytest
import tomllib

VOCABULARY = Path(__file__).parent.parent / "hooks" / "tool-vocabulary.toml"
HOOKS_DIR = VOCABULARY.parent


def test_vocabulary_declares_each_harness_mapping() -> None:
    """Validates: every configured harness maps its spellings to canonical tool names."""
    with open(VOCABULARY, "rb") as handle:
        vocabulary = tomllib.load(handle)

    assert set(vocabulary) == {"groups", "ask", "mappings", "passthrough", "refused"}
    assert vocabulary["mappings"]["claude"] == {
        "Bash": "Bash",
        "Read": "Read",
        "Write": "Write",
        "Edit": "Edit",
    }
    assert vocabulary["mappings"]["codex"] == {
        "Bash": "Bash",
        "Read": "Read",
        "Write": "Write",
        "Edit": "Edit",
        "apply_patch": "apply_patch",
    }
    assert vocabulary["mappings"]["copilot"] == {
        "Bash": "Bash",
        "runInTerminal": "Bash",
        "run_in_terminal": "Bash",
        "terminal": "Bash",
        "Read": "Read",
        "readFile": "Read",
        "read_file": "Read",
        "Write": "Write",
        "create_file": "Write",
        "createFile": "Write",
        "Edit": "Edit",
        "editFiles": "Edit",
        "replace_string_in_file": "Edit",
        "insert_edit_into_file": "Edit",
        "delete_file": "Edit",
        "rename_file": "Edit",
        "apply_patch": "apply_patch",
        "multi_replace_string_in_file": "Edit",
        "edit_notebook_file": "Edit",
        "create_directory": "Write",
        "send_to_terminal": "Bash",
    }
    assert vocabulary["mappings"]["pi"] == {
        "bash": "Bash",
        "read": "Read",
        "write": "Write",
        "edit": "Edit",
        "grep": "Read",
    }
    assert [entry["tool"] for entry in vocabulary["passthrough"]["pi"]["tools"]] == [
        "find",
        "ls",
        "subagent",
        "intercom",
        "contact_supervisor",
        "mcp__*",
        "tool_search",
        "codemode",
        "subagent_wait",
        "subagent_supervisor",
        "structured_output",
    ]


def test_vocabulary_loader_exposes_groups_mappings_and_ask_support() -> None:
    """Validates: consumers read tool sets and mappings from the declaration."""
    vocabulary = guarded_paths.load_tool_vocabulary(VOCABULARY)

    assert vocabulary.group("mutating") == frozenset({"Bash", "Write", "Edit", "apply_patch"})
    assert vocabulary.group("sensitive-path") == frozenset({"Bash", "Read", "Write", "Edit", "apply_patch"})
    assert vocabulary.group("destructive-ops") == frozenset({"Bash"})
    assert vocabulary.group("shell") == frozenset({"Bash"})
    assert vocabulary.normalize("copilot", "runInTerminal") == "Bash"
    assert vocabulary.normalize("pi", "write") == "Write"
    assert vocabulary.normalize("copilot", "unknownTool") is None
    assert vocabulary.supports_ask("copilot", "Write") is True
    assert vocabulary.supports_ask("copilot", "Bash") is False
    assert vocabulary.is_passthrough("copilot", "mcp_context7_query-docs") is True
    assert vocabulary.is_passthrough("copilot", "edit_files") is False
    assert vocabulary.normalize("copilot", "edit_files") is None
    assert "edit_files" in vocabulary.refused["copilot"]


def test_hook_tool_sets_come_from_the_declaration() -> None:
    """Validates: each Python gate shares the declared canonical tool sets."""
    vocabulary = guarded_paths.TOOL_VOCABULARY

    assert load_hook("block-hook-tampering").MUTATING_TOOLS is vocabulary.group("mutating")
    assert load_hook("block-secrets").SENSITIVE_TOOLS is vocabulary.group("mutating")
    assert load_hook("block-sensitive-paths").SENSITIVE_PATH_TOOLS is vocabulary.group("sensitive-path")
    assert load_hook("block-destructive-ops").DESTRUCTIVE_OPS_TOOLS is vocabulary.group("destructive-ops")


def test_copilot_ask_support_comes_from_the_declaration(monkeypatch) -> None:
    """Validates: Copilot ask support changes with the declared vocabulary."""

    class Vocabulary:
        @staticmethod
        def supports_ask(harness: str, tool_name: str) -> bool:
            return harness == "copilot" and tool_name == "Bash"

    monkeypatch.setattr(hook_response, "TOOL_VOCABULARY", Vocabulary())

    assert hook_response.supports_ask("copilot", "Bash") is True
    assert hook_response.supports_ask("copilot", "Write") is False


def test_added_spelling_reaches_every_consumer(tmp_path, monkeypatch) -> None:
    """Validates: one declaration edit reaches every vocabulary consumer."""
    vocabulary_path = tmp_path / "tool-vocabulary.toml"
    vocabulary_path.write_text(
        """\
[groups]
mutating = ["NovelTool"]
sensitive-path = ["NovelTool"]
destructive-ops = ["NovelTool"]

[ask]
copilot = ["NovelTool"]

[mappings.claude]
NovelTool = "NovelTool"

[mappings.codex]
novel_tool = "NovelTool"

[mappings.copilot]
novelTool = "NovelTool"

[mappings.pi]
novel = "NovelTool"

[passthrough.pi]

[[passthrough.pi.tools]]
tool = "lookup"
reason = "test"

[refused]
"""
    )
    vocabulary = guarded_paths.load_tool_vocabulary(vocabulary_path)
    monkeypatch.setattr(guarded_paths, "TOOL_VOCABULARY", vocabulary)
    monkeypatch.setattr(hook_response, "TOOL_VOCABULARY", vocabulary)

    assert vocabulary.normalize("claude", "NovelTool") == "NovelTool"
    assert vocabulary.normalize("codex", "novel_tool") == "NovelTool"
    assert vocabulary.normalize("copilot", "novelTool") == "NovelTool"
    assert vocabulary.normalize("pi", "novel") == "NovelTool"
    assert "NovelTool" in load_hook("block-hook-tampering").MUTATING_TOOLS
    assert "NovelTool" in load_hook("block-secrets").SENSITIVE_TOOLS
    assert "NovelTool" in load_hook("block-sensitive-paths").SENSITIVE_PATH_TOOLS
    assert "NovelTool" in load_hook("block-destructive-ops").DESTRUCTIVE_OPS_TOOLS
    assert hook_response.supports_ask("copilot", "NovelTool") is True


def _records(table: str, harness: str, *tools: str, reason: str = "test") -> str:
    """Render `[[<table>.<harness>.tools]]` records for a temporary vocabulary."""
    return f"\n[{table}.{harness}]\n" + "".join(
        f'\n[[{table}.{harness}.tools]]\ntool = "{tool}"\nreason = "{reason}"\n' for tool in tools
    )


_PASSTHROUGH_BASE = """\
[groups]
mutating = ["Write"]

[ask]
copilot = ["Write"]

[mappings.copilot]
create_file = "Write"
"""


def test_passthrough_tools_match_by_name_or_pattern(tmp_path) -> None:
    """Validates: a declared passthrough tool is known, and a pattern admits every name it matches."""
    path = tmp_path / "tool-vocabulary.toml"
    path.write_text(_PASSTHROUGH_BASE + _records("passthrough", "copilot", "list_dir", "mcp_*") + "\n[refused]\n")
    vocabulary = guarded_paths.load_tool_vocabulary(path)

    assert vocabulary.is_passthrough("copilot", "list_dir") is True
    assert vocabulary.is_passthrough("copilot", "mcp_context7_query-docs") is True
    assert vocabulary.is_passthrough("copilot", "MCP_context7_query-docs") is False
    assert vocabulary.is_passthrough("copilot", "futureTool") is False
    assert vocabulary.is_passthrough("pi", "list_dir") is False


@pytest.mark.parametrize(
    ("tables", "message"),
    [
        (_records("passthrough", "copilot", "create_file"), "covers mapped spellings: create_file"),
        (_records("passthrough", "copilot", "create_*"), "covers mapped spellings: create_file"),
        (_records("passthrough", "codex", "shell"), "names a harness with no mapping"),
        (_records("refused", "copilot", "create_file"), "covers mapped spellings: create_file"),
        (
            _records("passthrough", "copilot", "mcp_*") + _records("refused", "copilot", "mcp_server_tool"),
            "names passthrough tools: mcp_server_tool",
        ),
        (_records("passthrough", "copilot", "list_dir", reason=" "), "nonempty `tool` and `reason`"),
    ],
)
def test_a_contradictory_or_unexplained_entry_is_refused(tmp_path, tables, message) -> None:
    """Validates: a spelling sits in one table at most, and every record states its reason."""
    path = tmp_path / "tool-vocabulary.toml"
    passthrough = "" if "[passthrough." in tables else "\n[passthrough]\n"
    refused = "" if "[refused." in tables else "\n[refused]\n"
    path.write_text(_PASSTHROUGH_BASE + passthrough + refused + tables)

    with pytest.raises(guarded_paths.ToolVocabularyError, match=message):
        guarded_paths.load_tool_vocabulary(path)


def _private_tool_vocabulary(path: Path, canonical_tools: frozenset[str]) -> list[str]:
    """Return module-level collections that copy two or more canonical tool names."""
    tree = ast.parse(path.read_text(), filename=str(path))
    findings = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
            value = statement.value
        else:
            continue
        if value is None or not isinstance(value, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
            continue
        strings = {
            node.value for node in ast.walk(value) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        if len(strings & canonical_tools) < 2:
            continue
        findings.extend(target.id for target in targets if isinstance(target, ast.Name))
    return findings


def test_shared_hooks_hold_no_private_tool_vocabulary() -> None:
    """Validates: shared hook modules and adapters derive tool sets from the declaration."""
    canonical_tools = frozenset(
        canonical for mapping in guarded_paths.TOOL_VOCABULARY.mappings.values() for canonical in mapping.values()
    )
    consumers = (
        HOOKS_DIR / "block-hook-tampering.py",
        HOOKS_DIR / "block-secrets.py",
        HOOKS_DIR / "block-sensitive-paths.py",
        HOOKS_DIR / "block-destructive-ops.py",
        HOOKS_DIR / "hook_response.py",
        HOOKS_DIR.parents[1] / "copilot" / "hooks" / "copilot-vscode-hook-adapter.py",
        HOOKS_DIR.parents[1] / "pi" / "security" / "hook-dispatch.py",
    )

    findings = {path.name: names for path in consumers if (names := _private_tool_vocabulary(path, canonical_tools))}

    assert findings == {}


def test_private_tool_vocabulary_is_reported(tmp_path) -> None:
    """Validates: the conformance check fails on a private tool-name collection."""
    implementation = tmp_path / "implementation.py"
    implementation.write_text('PRIVATE_TOOLS = {"Bash", "Write"}\n')

    findings = _private_tool_vocabulary(
        implementation,
        frozenset({"Bash", "Read", "Write", "Edit", "apply_patch"}),
    )

    assert findings == ["PRIVATE_TOOLS"]
