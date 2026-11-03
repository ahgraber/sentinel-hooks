"""Every verdict-reaching surface is judged against the shared verdict tables.

The direct hooks are judged here; Copilot's adapter in `copilot/tests/`, and Pi's
dispatcher and hook runner in `tests/pi/`. The cases with stand-in surfaces show the
rule fails in each way `VerdictSurfacesAgree` names, so a passing suite is evidence
the check can fail.
"""

from __future__ import annotations

from dataclasses import replace
import itertools

import pytest
from verdict_conformance import (
    HOOKS_DIR,
    Case,
    claude_payload,
    conformance,
    decode,
    directly,
    load_cases,
    run,
    workdir,
)

CASES = load_cases()


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """Fresh working directories under a scratch home."""
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return (tmp_path / str(n) for n in itertools.count())


@pytest.fixture(scope="module")
def shared(tmp_path_factory):
    """The direct outcome of every case under Claude's encoding, the reference the stand-in surfaces vary."""
    root = tmp_path_factory.mktemp("shared")
    (root / "home").mkdir()
    directories = (root / str(n) for n in itertools.count())
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HOME", str(root / "home"))
        outcomes = {_input(case): directly(case, workdir(case, next(directories)), "claude") for case in CASES}
    return lambda case: outcomes[_input(case)]


def _input(case: Case) -> tuple:
    """What a surface judges: the case without the outcome the table declares for it."""
    return (case.hook, case.tool, case.target, case.exists)


def test_both_tables_are_loaded() -> None:
    """Guards the tables themselves: an empty one would make every conformance case vacuous."""
    assert {case.hook for case in CASES} == {"block-hook-tampering.py", "block-sensitive-paths.py"}
    assert {case.tool for case in CASES} == {"Write", "Read", "Bash"}
    assert any(case.blocked for case in CASES)
    assert any(not case.blocked for case in CASES)


def test_the_direct_hooks_reach_every_table_outcome_under_claude(shared) -> None:
    """Validates: SharedTableAgrees for the agents that run the hooks natively."""
    assert conformance(CASES, {"claude": shared}) == []


def test_the_direct_hooks_reach_every_table_outcome_under_codex(scratch) -> None:
    """Validates: SharedTableAgrees under Codex's encoding, which has no prompt to degrade to."""
    assert conformance(CASES, {"codex": lambda case: directly(case, workdir(case, next(scratch)), "codex")}) == []


def test_a_reimplementation_that_diverges_fails(shared) -> None:
    """Validates: ReimplementationDiverges."""
    diverging = CASES[0]

    def reimplementation(case: Case) -> str:
        outcome = shared(case)
        if case != diverging:
            return outcome
        return "allow" if outcome != "allow" else "block"

    failures = conformance(CASES, {"shared": shared, "reimplementation": reimplementation})
    assert len(failures) == 1
    assert failures[0].startswith(f"reimplementation reaches allow on {diverging.label}")


def test_an_adapter_whose_payload_misses_the_gate_fails(shared, scratch) -> None:
    """Validates: AdapterDiverges — the adapter holds no policy, and its payload alone decides the gate."""

    def adapter(case: Case) -> str:
        cwd = workdir(case, next(scratch))
        payload = claude_payload(case, cwd)
        # Forwarding the harness's own name reaches no gate, which is the fall-through the adapters refuse.
        payload["tool_name"] = "create_file"
        result = run(["python3", str(HOOKS_DIR / case.hook)], payload, cwd, "copilot")
        return decode(result.returncode, result.stdout)

    failures = conformance(CASES, {"shared": shared, "adapter": adapter})
    assert failures
    assert all(failure.startswith("adapter reaches allow") for failure in failures)


def test_an_input_a_surface_does_not_judge_fails(shared) -> None:
    """A table entry no surface covers is a failure, not a pass."""
    skipped = CASES[-1]
    assert conformance(CASES, {"partial": lambda case: None if case == skipped else shared(case)}) == [
        f"partial does not judge {skipped.label}"
    ]


def test_a_contract_amended_on_one_surface_only_fails(shared) -> None:
    """Validates: CapabilityAmendedInOnePlace — the amended table is judged against every surface."""
    amended = next(case for case in CASES if case.blocked)
    table = [replace(case, blocked=False) if case == amended else case for case in CASES]

    def updated(case: Case) -> str:
        return "allow" if _input(case) == _input(amended) else shared(case)

    failures = conformance(table, {"updated": updated, "shared": shared})
    assert len(failures) == 1
    assert failures[0].startswith("shared reaches")
