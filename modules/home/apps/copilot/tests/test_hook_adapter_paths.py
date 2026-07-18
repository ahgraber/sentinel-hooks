from __future__ import annotations

import importlib.util
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


def test_adapter_resolves_repository_hook_directories() -> None:
    """The moved adapter must dispatch to hook directories in this worktree."""
    adapter = load_adapter()

    assert adapter.REPO_ROOT == REPO_ROOT
    assert adapter.COPILOT_HOOKS_DIR == REPO_ROOT / "modules/home/apps/copilot/hooks"
    assert adapter.CLAUDE_HOOKS_DIR == REPO_ROOT / "modules/home/apps/claude/hooks"
    assert adapter.COPILOT_HOOKS_DIR.is_dir()
    assert adapter.CLAUDE_HOOKS_DIR.is_dir()
