#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run the shared Python PreToolUse hooks for Pi, in one process over one payload.

Pi's hook runner passes Pi's own tool names and input. The dispatcher maps them
onto the declared tool vocabulary, runs each hook as its own `__main__`, and
answers the runner the way a single hook does: exit 2 with the reasons on stderr
to refuse, the ask JSON on stdout to ask, exit 1 with notices on stderr to warn,
or exit 0 to allow.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys

SHARED_HOOKS_DIR = Path(__file__).resolve().parents[2] / "shared" / "hooks"
if str(SHARED_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HOOKS_DIR))

# The order `copilot/hooks/security-policy.json` registers them in. Every hook runs,
# so the order decides only the order of the reasons, not the verdict.
PYTHON_HOOKS = (
    "block-sensitive-paths.py",
    "block-hook-tampering.py",
    "block-destructive-ops.py",
    "block-leaks.py",
)

_RANK = {"allow": 0, "warn": 0, "ask": 1, "block": 2}


class HookCrashError(Exception):
    """A hook ended in an error it did not handle."""


def run_hook(path: Path, payload: str) -> tuple[int, str, str]:
    """Run the hook at `path` as `__main__` with `payload` on stdin; return status, stdout, stderr.

    Raise `HookCrashError` when the hook ends in an error it did not handle: run alone,
    it would exit 1, which the runner lets through, so the caller must refuse instead.
    """
    stdout, stderr = io.StringIO(), io.StringIO()
    saved_stdin = sys.stdin
    sys.stdin = io.StringIO(payload)
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(path), run_name="__main__")
            except SystemExit as exit_:
                code = exit_.code
                if code is None:
                    return 0, stdout.getvalue(), stderr.getvalue()
                if isinstance(code, int):
                    return code, stdout.getvalue(), stderr.getvalue()
                raise HookCrashError(f"exited with {code!r}") from None
            except Exception as error:
                raise HookCrashError(f"raised {type(error).__name__}: {error}") from error
    finally:
        sys.stdin = saved_stdin
    return 0, stdout.getvalue(), stderr.getvalue()


def decode(status: int, stdout: str, stderr: str) -> tuple[str, str]:
    """Return the decision and message a hook's outcome encodes for Pi.

    `Ask` and `Allow` share status 0, so the decision is read from stdout.
    Status 1 is the warning Pi can show.
    """
    if status == 2:
        return "block", stderr.strip()
    if status == 1:
        return "warn", stderr.strip()
    if status == 0 and stdout.strip():
        try:
            output = json.loads(stdout).get("hookSpecificOutput", {})
        except (json.JSONDecodeError, AttributeError):
            output = {}
        if output.get("permissionDecision") == "ask":
            return "ask", str(output.get("permissionDecisionReason", "")).strip()
    if status == 0:
        return "allow", ""
    detail = stderr.strip()
    raise HookCrashError(f"exited with status {status}" + (f": {detail}" if detail else ""))


def normalize(payload: dict) -> dict | None:
    """Map Pi's tool name and input onto the declared vocabulary.

    Return `None` for a tool the declaration lists as passthrough. Raise
    `LookupError` for a tool it neither maps nor passes through.
    """
    from guarded_paths import TOOL_VOCABULARY

    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        raise LookupError(tool_name)
    mapped = TOOL_VOCABULARY.normalize("pi", tool_name)
    if mapped is None:
        if TOOL_VOCABULARY.is_passthrough("pi", tool_name):
            return None
        raise LookupError(tool_name)

    tool_input = dict(payload.get("tool_input") or {})
    path = tool_input.get("path")
    if mapped in TOOL_VOCABULARY.group("file") and isinstance(path, str) and path:
        # Pi resolves a relative `path` against the session's working directory.
        cwd = payload.get("cwd") or os.getcwd()
        tool_input["file_path"] = str(Path(cwd, os.path.expanduser(path)))
    return {**payload, "tool_name": mapped, "tool_input": tool_input}


def dispatch(payload: dict, hooks_dir: Path = SHARED_HOOKS_DIR, hooks: tuple[str, ...] = PYTHON_HOOKS) -> dict:
    """Run every hook over `payload` and combine their decisions, most restrictive first."""
    from hook_response import STOP_INSTRUCTIONS

    serialized = json.dumps(payload)
    decision = "allow"
    reasons: dict[str, list[str]] = {"ask": [], "block": []}
    notices: list[str] = []
    for name in hooks:
        try:
            verdict, message = decode(*run_hook(hooks_dir / name, serialized))
        except HookCrashError as crash:
            verdict = "block"
            message = f"Blocked: {name} {crash}, so the call is refused.\n{STOP_INSTRUCTIONS}"
        if verdict in ("allow", "warn"):
            if message:
                notices.append(message)
            continue
        reasons[verdict].append(message)
        if _RANK[verdict] > _RANK[decision]:
            decision = verdict

    return {"decision": decision, "reasons": reasons.get(decision, []), "notices": notices}


def answer(verdict: dict) -> int:
    """Write `verdict` in the hook contract and return the exit status."""
    if verdict["decision"] == "block":
        sys.stderr.write("\n\n".join(verdict["reasons"]) + "\n")
        return 2
    if verdict["decision"] == "ask":
        reply = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "\n\n".join(verdict["reasons"]),
            }
        }
        sys.stdout.write(json.dumps(reply))
        return 0
    if verdict["notices"]:
        sys.stderr.write("\n\n".join(verdict["notices"]) + "\n")
        return 1
    return 0


def refuse(message: str) -> int:
    """Refuse the call with the stop form, even when the instruction text cannot load."""
    try:
        from hook_response import STOP_INSTRUCTIONS
    except Exception:  # noqa: BLE001
        STOP_INSTRUCTIONS = ""  # noqa: N806
    sys.stderr.write(f"{message}\n{STOP_INSTRUCTIONS}\n")
    return 2


def main() -> int:
    """Read the runner's payload from stdin and answer it in the hook contract.

    Any error here ends in exit 2: the runner lets exit 1 through, and a call the
    hooks could not judge must not run.
    """
    # The hooks infer the agent from their invocation path, which running them in
    # this process bypasses.
    os.environ["AI_HOOK_AGENT"] = "pi"
    try:
        payload = json.loads(sys.stdin.read())
        try:
            normalized = normalize(payload)
        except LookupError as unmapped:
            return refuse(
                f"Blocked: Pi tool {unmapped.args[0]!r} has no declared mapping to the shared security hooks."
            )
        if normalized is None:
            return 0
        return answer(dispatch(normalized))
    except Exception as error:  # noqa: BLE001
        return refuse(
            f"Blocked: the Pi hook dispatcher failed ({type(error).__name__}: {error}), so the call is refused."
        )


if __name__ == "__main__":
    raise SystemExit(main())
