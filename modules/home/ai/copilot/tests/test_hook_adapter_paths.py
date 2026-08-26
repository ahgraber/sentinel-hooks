from __future__ import annotations

import importlib.util
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
    / "ai"
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


SECURITY_POLICY = REPO_ROOT / "modules/home/ai/copilot/hooks/security-policy.json"
ADAPTER_INVOCATION_RE = re.compile(
    r"copilot-vscode-hook-adapter\.py\s+([A-Za-z0-9._-]+)"
)


def test_configured_dispatch_targets_exist() -> None:
    """Each configured adapter invocation must resolve to a repository script."""
    adapter = load_adapter()
    invoked = set(ADAPTER_INVOCATION_RE.findall(SECURITY_POLICY.read_text()))

    assert invoked, "found no adapter invocations in security-policy.json"

    unknown = invoked - set(adapter.SCRIPT_PATHS)
    assert not unknown, (
        "security-policy.json invokes scripts the adapter cannot resolve: "
        f"{sorted(unknown)}"
    )
    missing = {
        name: str(adapter.SCRIPT_PATHS[name])
        for name in invoked
        if not adapter.SCRIPT_PATHS[name].is_file()
    }
    assert not missing, f"configured adapter targets do not exist: {missing}"
