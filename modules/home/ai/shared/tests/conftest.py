"""Make the shared hook modules and `conformance` importable under every runner.

pytest adds a test file's directory to `sys.path` only under some import modes,
and the `nix flake check` sandbox runs under one of the others.
"""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent
HOOKS_DIR = TESTS_DIR.parent / "hooks"

for directory in (HOOKS_DIR, TESTS_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
