"""The protected class of a path is structural, read from the declarations.

The class decides the gate's outcome: a credential write is refused on every
agent, everything else protected is put to the user.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from guarded_paths import load_manifest
from hermetic import HOOKS_DIR, REPO_ROOT
import pytest


def load_hook():
    """Import the hook by location; its filename is not a valid identifier."""
    spec = importlib.util.spec_from_file_location("block_hook_tampering", HOOKS_DIR / "block-hook-tampering.py")
    module = importlib.util.module_from_spec(spec)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec.loader.exec_module(module)
    return module


HOOK = load_hook()


def _declared_path(declaration: str) -> str:
    """A concrete path a declaration matches, for feeding to the classifier."""
    return declaration.replace("<repo>/", f"{REPO_ROOT}/").replace("*", "testuser")


def test_credential_and_enforcement_paths_report_distinct_classes() -> None:
    assert HOOK.protected_class("~/.codex/auth.json") == HOOK.CREDENTIAL
    assert HOOK.protected_class(f"{REPO_ROOT}/modules/home/ai/shared/hooks/guarded_paths.py") == HOOK.GATED


@pytest.mark.parametrize("declaration", sorted(HOOK.POLICY.classes["block"].declarations))
def test_every_credential_declaration_reports_the_credential_class(
    declaration: str,
) -> None:
    assert HOOK.protected_class(_declared_path(declaration)) == HOOK.CREDENTIAL


@pytest.mark.parametrize("declaration", sorted(load_manifest()["guarded"]["paths"]))
def test_every_other_declared_path_reports_the_gated_class(declaration: str) -> None:
    path = _declared_path(declaration)
    assert HOOK.protected_class(path) == HOOK.GATED


@pytest.mark.parametrize("declaration", sorted(load_manifest()["enforcement-floor"]["paths"]))
def test_every_floor_declaration_reports_the_gated_class(declaration: str, tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _declared_path(declaration).replace("<project>/", f"{project}/")
    assert HOOK.protected_class(path, cwd=str(project)) == HOOK.GATED


def test_an_unprotected_path_reports_no_class(tmp_path: Path) -> None:
    assert HOOK.protected_class(str(tmp_path / "notes.txt")) is None
