"""Make the shared hook modules and `verdict_conformance` importable under every runner,
and supply the fixtures more than one module builds a case on.

pytest adds a test file's directory to `sys.path` only under some import modes,
and the `nix flake check` sandbox runs under one of the others.

A fixture here is discovered by name, so a module that needs one states it as a
parameter rather than importing it from another test module.
"""

from pathlib import Path
import sys

TESTS_DIR = Path(__file__).parent
HOOKS_DIR = TESTS_DIR.parent / "hooks"

for directory in (HOOKS_DIR, TESTS_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from guarded_paths import PathPolicy  # noqa: E402
from hermetic import build_world, install_policy, load_hook  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A temporary world with a substituted policy bound into the tamper hook.

    The tree and the five classes below are what the class-outcome and
    attached-operand cases judge against.
    """
    home, repo, manifest = build_world(tmp_path, monkeypatch)
    (home / "skills").mkdir()
    (home / "skills/task.py").touch()
    (home / "base").mkdir()
    (home / "base/task.py").touch()
    (home / "memory").mkdir()
    (home / "memory/link").symlink_to(home / "base/file")
    policy = PathPolicy(
        {
            "guarded": {"paths": ["~/base/", "~/other-agent/"]},
            "block": {"paths": ["~/base/private"]},
            "exec-through": {"paths": ["~/skills/"]},
            "write-through": {"paths": ["~/base/notes/*.md", "~/memory/"]},
            "exceptions": [],
        },
        home=str(home),
        repo_root=str(repo),
        manifest_path=manifest,
    )
    hook = load_hook("block-hook-tampering")
    install_policy(monkeypatch, hook, policy)
    return home, repo, hook
