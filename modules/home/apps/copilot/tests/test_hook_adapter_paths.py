from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)
ADAPTER_PATH = (
    REPO_ROOT
    / "modules"
    / "home"
    / "apps"
    / "copilot"
    / "hooks"
    / "copilot-vscode-hook-adapter.py"
)


def load_adapter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("copilot_hook_adapter", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SECURITY_POLICY = REPO_ROOT / "modules/home/apps/copilot/hooks/security-policy.json"
ADAPTER_INVOCATION_RE = re.compile(
    r"copilot-vscode-hook-adapter\.py\s+([A-Za-z0-9._-]+)"
)


def test_adapter_resolves_repository_hook_directories() -> None:
    """The moved adapter must dispatch to hook directories in this worktree."""
    adapter = load_adapter()

    assert adapter.REPO_ROOT == REPO_ROOT
    assert adapter.COPILOT_HOOKS_DIR == REPO_ROOT / "modules/home/apps/copilot/hooks"
    assert adapter.CLAUDE_HOOKS_DIR == REPO_ROOT / "modules/home/apps/claude/hooks"
    assert adapter.COPILOT_HOOKS_DIR.is_dir()
    assert adapter.CLAUDE_HOOKS_DIR.is_dir()


def test_every_dispatch_target_exists() -> None:
    """A SCRIPT_PATHS entry naming a missing file is fail-open.

    The adapter reports 'Unknown hook script' only for names absent from the
    dict; a name that is present but points at a deleted or renamed file fails
    at exec time, per invocation, with the check silently not running.
    """
    adapter = load_adapter()

    missing = {
        name: str(path)
        for name, path in adapter.SCRIPT_PATHS.items()
        if not path.is_file()
    }

    assert not missing, f"SCRIPT_PATHS entries pointing at missing files: {missing}"


def test_policy_only_invokes_known_scripts() -> None:
    """Every script the deployed policy asks for must be in the dispatch table."""
    adapter = load_adapter()
    invoked = set(ADAPTER_INVOCATION_RE.findall(SECURITY_POLICY.read_text()))

    assert invoked, "found no adapter invocations in security-policy.json"

    unknown = invoked - set(adapter.SCRIPT_PATHS)
    assert not unknown, (
        f"security-policy.json invokes scripts the adapter cannot resolve: "
        f"{sorted(unknown)}"
    )


def test_precommit_runs_at_stop_not_per_edit() -> None:
    """Pins the end-of-turn design against a revert to a per-edit PostToolUse run."""
    policy = json.loads(SECURITY_POLICY.read_text())["hooks"]
    events = {
        event
        for event, entries in policy.items()
        for entry in entries
        if "stop-precommit.sh" in entry.get("command", "")
    }

    assert events == {"Stop"}, (
        f"security-policy.json runs stop-precommit.sh on {events or 'no event'}; "
        "it belongs on Stop only"
    )
