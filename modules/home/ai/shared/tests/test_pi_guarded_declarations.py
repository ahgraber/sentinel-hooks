"""pi's port must guard the same surface as the hook it mirrors.

Both sides read `guarded-paths.toml` at invocation, so the checks here are
structural: neither carries a mirrored literal, both name the one manifest, and
`guarded-path-cases.json` supplies the behavioural coverage for both languages.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
EXTENSION = (
    Path(__file__).parents[2] / "pi" / "security" / "security-extension-index.ts"
)
CASES = json.loads((Path(__file__).parent / "guarded-path-cases.json").read_text())[
    "cases"
]

SOURCE = EXTENSION.read_text()


def test_extension_reads_the_manifest_rather_than_a_mirrored_literal() -> None:
    assert "guarded-paths.toml" in SOURCE, (
        f"{EXTENSION.name} no longer names the manifest it is supposed to read"
    )
    for name in (
        "GUARDED_FILES",
        "CREDENTIAL_FILES",
        "INSTRUCTION_LAYERS",
        "LOCATION_ONLY",
    ):
        assert not re.search(rf"const {name}\s*(?::[^=]+)?=\s*\[", SOURCE), (
            f"{name} is declared as a literal array again in {EXTENSION.name}; "
            "it should be built from the manifest instead"
        )


def test_hook_and_extension_agree_on_the_manifest_filename() -> None:
    hook_source = (HOOKS_DIR / "block-hook-tampering.py").read_text()
    assert "guarded-paths.toml" in hook_source


def test_instruction_layer_carve_out_has_behavioural_coverage() -> None:
    """Both language suites assert this table, so a case here covers both sides."""
    instruction_cases = [c for c in CASES if "instructions" in c["path"]]
    assert any(not c["blocked"] for c in instruction_cases), (
        "no case shows the instruction-markdown carve-out actually allowing a write"
    )
    assert any(c["blocked"] for c in instruction_cases), (
        "no case shows the carve-out's narrowness (nested, non-markdown, or a link)"
    )


def test_location_only_class_has_behavioural_coverage() -> None:
    """A location-only declaration contributes no text fragment, so only a path
    resolving inside the guarded root can cover it."""
    home_wide_cases = [
        c
        for c in CASES
        if "whole" in c["why"] or "not only the" in c["why"] or "shares" in c["why"]
    ]
    assert any(c["blocked"] for c in home_wide_cases), (
        "no case shows a location-only root guarding a path it names no file for"
    )
    assert any(not c["blocked"] for c in home_wide_cases), (
        "no case shows a sibling outside the location-only root staying allowed"
    )
