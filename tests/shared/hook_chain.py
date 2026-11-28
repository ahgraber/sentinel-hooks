"""Run the shared Python PreToolUse hooks over one payload, once per agent, and report each verdict.

Each call starts one process with `HOME` set to the home the caller built.
`guarded_paths` reads `HOME` when it is first imported, so running the hooks in
the test process would expand `~` against the real home.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".specs").is_dir())
HOOKS_DIR = REPO_ROOT / "plugins" / "sentinel" / "hooks"
HOOKS = (
    "block-sensitive-paths.py",
    "block-hook-tampering.py",
    "block-destructive-ops.py",
    "block-leaks.py",
)
RANK = {"allow": 0, "ask": 1, "block": 2}


def verdicts(payload: dict, agents: list[str], home: Path, cwd: Path) -> dict[str, str]:
    """Return the most restrictive verdict the hooks reach for each agent."""
    env = {**os.environ, "HOME": str(home)}
    env.pop("AI_HOOK_AGENT", None)
    result = subprocess.run(
        [sys.executable, __file__],
        input=json.dumps({"payload": {**payload, "cwd": str(cwd)}, "agents": agents}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def _decide(name: str, payload: str) -> str:
    stdout, stderr = io.StringIO(), io.StringIO()
    sys.stdin = io.StringIO(payload)
    code = 0
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            runpy.run_path(str(HOOKS_DIR / name), run_name="__main__")
        except SystemExit as exit_:
            code = exit_.code or 0
    # Every hook catches its own errors, so an error that escapes, or an exit no
    # agent decodes, is a defect in the hook and fails the caller's test.
    if code not in (0, 1, 2):
        raise RuntimeError(f"{name} exited {code!r}: {stderr.getvalue()}")
    if code == 2:
        return "block"
    if code == 0 and '"permissionDecision": "ask"' in stdout.getvalue():
        return "ask"
    return "allow"


def _main() -> None:
    request = json.load(sys.stdin)
    results = {}
    for agent in request["agents"]:
        payload = dict(request["payload"])
        # Claude is named by its payload; the others by the variable their adapters set.
        if agent == "claude":
            payload["transcript_path"] = "/dev/null"
            os.environ.pop("AI_HOOK_AGENT", None)
        else:
            os.environ["AI_HOOK_AGENT"] = agent
        serialized = json.dumps(payload)
        results[agent] = max((_decide(name, serialized) for name in HOOKS), key=RANK.__getitem__)
    sys.stdout = sys.__stdout__
    print(json.dumps(results))


if __name__ == "__main__":
    sys.path.insert(0, str(HOOKS_DIR))
    _main()
