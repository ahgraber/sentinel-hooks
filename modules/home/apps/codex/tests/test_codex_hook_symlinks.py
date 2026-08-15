"""Tests for which Codex hooks are shared vs. Codex-specific."""

from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"
CLAUDE_HOOKS_DIR = Path(__file__).resolve().parents[2] / "claude" / "hooks"

SHARED_HOOKS = [
    "bash-command-validator.sh",
    "block-dangerous-bash.sh",
    "block-destructive-ops-patterns.toml",
    "block-hook-tampering.py",
    "git-baseline.sh",
    "stop-precommit.sh",
    "reload-skills-catalog.py",
    "session-tool-checks.sh",
    "instructions",  # dir symlink: shares all session-instruction fragments
    "session-instructions.sh",
]

CODEX_SPECIFIC_HOOKS = [
    "block-destructive-ops.py",
    "block-secrets.py",
    "block-sensitive-paths.py",
    "codex-block-hook-tampering.py",
]


def test_shared_hooks_are_symlinked():
    for name in SHARED_HOOKS:
        path = HOOKS_DIR / name
        assert path.is_symlink(), f"Expected {name} to be a symlink"
        assert path.exists(), f"Expected {name} to resolve to an existing Claude hook"
        assert path.resolve() == (CLAUDE_HOOKS_DIR / name).resolve(), (
            f"Expected {name} to point at the Claude hook implementation"
        )


def test_codex_specific_hooks_remain_real_files():
    for name in CODEX_SPECIFIC_HOOKS:
        path = HOOKS_DIR / name
        assert path.exists(), f"Missing expected Codex hook {name}"
        assert not path.is_symlink(), (
            f"Expected {name} to remain a Codex-specific implementation"
        )


def test_every_hook_is_classified():
    """The two lists above must account for the whole directory.

    Without this, a hook added as a real file — rather than as a symlink to the
    Claude implementation — is invisible to both tests above, which only assert
    over names they already know.
    """
    present = {
        entry.name
        for entry in HOOKS_DIR.iterdir()
        if not entry.name.startswith(".") and entry.name != "__pycache__"
    }
    unclassified = present - set(SHARED_HOOKS) - set(CODEX_SPECIFIC_HOOKS)

    assert not unclassified, (
        f"Unclassified hooks in {HOOKS_DIR.name}/: {sorted(unclassified)}. "
        "Add each to SHARED_HOOKS (symlink to the Claude implementation) or to "
        "CODEX_SPECIFIC_HOOKS (deliberate Codex-only implementation)."
    )
