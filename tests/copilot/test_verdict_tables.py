"""Copilot's adapter judged against the shared verdict tables.

Each table input goes to the adapter as VS Code sends it, under the adapter's own
tool names, and the table's hook must reach the declared outcome through it.
"""

from __future__ import annotations

import itertools
import os
from pathlib import Path
import sys

from conftest import ADAPTER_PATH, REPO_ROOT
import pytest

SHARED_TESTS = REPO_ROOT / "tests" / "shared"
sys.path.insert(0, str(SHARED_TESTS))

from verdict_conformance import Case, conformance, decode, directly, load_cases, run, workdir  # noqa: E402

VSCODE_TOOLS = {"Write": "create_file", "Read": "read_file", "Bash": "run_in_terminal"}


def vscode_payload(case: Case, cwd: Path) -> dict:
    """The payload VS Code sends for `case`: its own tool name, and an absolute `filePath`."""
    if case.tool == "Bash":
        tool_input = {"command": case.target}
    else:
        tool_input = {"filePath": str(cwd / os.path.expanduser(case.target))}
        if case.tool == "Write":
            tool_input["content"] = "x"
    return {
        "hookEventName": "PreToolUse",
        "cwd": str(cwd),
        "tool_name": VSCODE_TOOLS[case.tool],
        "tool_input": tool_input,
    }


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """Fresh working directories under a scratch home."""
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return (tmp_path / str(n) for n in itertools.count())


def test_the_adapter_reaches_every_table_outcome_as_a_direct_invocation_does(scratch) -> None:
    """Validates: SharedTableAgrees and AdapterDiverges on Copilot."""
    cases = load_cases()

    def adapter(case: Case) -> str:
        cwd = workdir(case, next(scratch))
        result = run(["python3", str(ADAPTER_PATH), case.hook], vscode_payload(case, cwd), cwd, "copilot")
        return decode(result.returncode, result.stdout)

    def direct(case: Case) -> str:
        return directly(case, workdir(case, next(scratch)), "copilot")

    assert conformance(cases, {"copilot adapter": adapter, "direct": direct}) == []
