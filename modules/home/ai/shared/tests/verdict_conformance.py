"""The rule every verdict-reaching surface is judged by over the shared verdict tables.

Each table declares one hook's verdict: `guarded-path-cases.json` is
`block-hook-tampering.py`'s, and `sensitive-path-cases.json` is
`block-sensitive-paths.py`'s. A surface is a function from a table input to that
hook's outcome through the surface, `allow`, `ask`, or `block`, or `None` for an input
it does not judge. An outcome other than `allow` satisfies `blocked`, because a
surface that cannot show a prompt refuses where one that can asks.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess

TESTS_DIR = Path(__file__).parent
HOOKS_DIR = TESTS_DIR.parent / "hooks"
# The table inputs name repository paths relative to the checkout root.
REPO_ROOT = next(parent for parent in TESTS_DIR.resolve().parents if (parent / "flake.nix").is_file())


@dataclass(frozen=True)
class Case:
    """One table input: a file tool over a path, or a command run where `exists` names files."""

    hook: str
    tool: str
    target: str
    blocked: bool
    exists: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        suffix = f" with {', '.join(self.exists)}" if self.exists else ""
        return f"{self.hook}: {self.tool} {self.target}{suffix}"


Surface = Callable[[Case], "str | None"]


def load_cases() -> list[Case]:
    """Every input in both verdict tables, under the hook and tool each is judged by."""
    guarded = json.loads((TESTS_DIR / "guarded-path-cases.json").read_text())
    sensitive = json.loads((TESTS_DIR / "sensitive-path-cases.json").read_text())
    tampering, zero_access = "block-hook-tampering.py", "block-sensitive-paths.py"
    return [
        *(Case(tampering, "Write", case["path"], case["blocked"]) for case in guarded["cases"]),
        *(Case(zero_access, "Read", case["path"], case["blocked"]) for case in sensitive["cases"]),
        *(
            Case(zero_access, "Bash", case["command"], case["blocked"], tuple(case["exists"]))
            for case in sensitive["bash_cases"]
        ),
    ]


def conformance(cases: list[Case], surfaces: Mapping[str, Surface]) -> list[str]:
    """Return every way `surfaces` fail the tables: an input one does not judge, or an outcome the table rejects."""
    failures = []
    for case in cases:
        for name, surface in surfaces.items():
            outcome = surface(case)
            if outcome is None:
                failures.append(f"{name} does not judge {case.label}")
            elif (outcome != "allow") is not case.blocked:
                failures.append(f"{name} reaches {outcome} on {case.label}, but the table has blocked={case.blocked}")
    return failures


def workdir(case: Case, scratch: Path) -> Path:
    """The directory `case` is judged from: the checkout for a path, `scratch` holding `exists` for a command."""
    if case.tool != "Bash":
        return REPO_ROOT
    scratch.mkdir(parents=True, exist_ok=True)
    for name in case.exists:
        (scratch / name).touch()
    return scratch


def decode(status: int, stdout: str) -> str:
    """Read one hook's decision from its exit status and reply."""
    if status == 2:
        return "block"
    if status == 0 and stdout.strip():
        decision = json.loads(stdout).get("hookSpecificOutput", {}).get("permissionDecision")
        if decision == "deny":
            return "block"
        if decision == "ask":
            return "ask"
    return "allow"


def claude_payload(case: Case, cwd: Path) -> dict:
    """The payload Claude Code sends for `case`, with `~` and relative paths resolved as it resolves them."""
    if case.tool == "Bash":
        tool_input = {"command": case.target}
    else:
        tool_input = {"file_path": str(cwd / os.path.expanduser(case.target))}
        if case.tool == "Write":
            tool_input["content"] = "x"
    return {"hook_event_name": "PreToolUse", "cwd": str(cwd), "tool_name": case.tool, "tool_input": tool_input}


def run(command: list[str], payload: dict, cwd: Path, agent: str) -> subprocess.CompletedProcess[str]:
    """Run `command` on `payload` from `cwd`, declaring `agent` as the adapters do."""
    return subprocess.run(
        command,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env={**os.environ, "AI_HOOK_AGENT": agent},
    )


def directly(case: Case, cwd: Path, agent: str) -> str:
    """The table's hook, run alone on Claude Code's payload for `case`."""
    result = run(["python3", str(HOOKS_DIR / case.hook)], claude_payload(case, cwd), cwd, agent)
    return decode(result.returncode, result.stdout)
