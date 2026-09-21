"""pi's port must guard the same surface as the hook it mirrors.

Both sides read `guarded-paths.toml` at invocation, so the checks here are
structural: neither carries a mirrored literal, both name the one manifest, and
`guarded-path-cases.json` supplies the behavioral coverage for both languages.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
EXTENSION = Path(__file__).parents[2] / "pi" / "security" / "index.ts"
CASES = json.loads((Path(__file__).parent / "guarded-path-cases.json").read_text())["cases"]

SOURCE = EXTENSION.read_text()


def test_extension_reads_the_manifest_rather_than_a_mirrored_literal() -> None:
    assert "guarded-paths.toml" in SOURCE, f"{EXTENSION.name} no longer names the manifest it is supposed to read"
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


def test_write_through_has_explicit_pi_divergence():
    memory = [case for case in CASES if "/projects/" in case["path"]]
    assert memory
    assert all(not case["blocked"] and case["pi_blocked"] for case in memory)


def test_instruction_markdown_is_guarded():
    instructions = [case for case in CASES if "/instructions/" in case["path"]]
    assert instructions
    assert all(case["blocked"] for case in instructions)
