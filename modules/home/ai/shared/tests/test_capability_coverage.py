from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

PACKAGE_ROOT = Path(__file__).parent.parent
SPECS_ROOT = PACKAGE_ROOT / ".specs" / "specs"
HOOKS_ROOT = PACKAGE_ROOT / "hooks"
TESTS_ROOT = PACKAGE_ROOT / "tests"

CapabilityKind = Literal["enforcement", "mechanism", "posture", "configuration", "conformance"]
CAPABILITY_KINDS = frozenset({"enforcement", "mechanism", "posture", "configuration", "conformance"})
HOOK_DATA_FILES = frozenset(
    {
        "block-destructive-ops-patterns.toml",
        "guarded-paths.toml",
        "tool-vocabulary.toml",
    }
)
TOOLING = frozenset({"reload-skills-catalog.py", "session-instructions.sh"})


@dataclass(frozen=True)
class Capability:
    kind: CapabilityKind
    artifacts: tuple[str, ...]


CAPABILITIES: Mapping[str, Capability] = {
    "agent-configuration-floor": Capability("configuration", ()),
    "bash-command-validator": Capability("enforcement", ("bash-command-validator.sh",)),
    "cross-agent-capability-parity": Capability("conformance", ("test_capability_coverage.py",)),
    "dangerous-bash-blocking": Capability("enforcement", ("block-dangerous-bash.sh",)),
    "destructive-ops-blocking": Capability("enforcement", ("block-destructive-ops.py",)),
    "end-of-turn-precommit": Capability("enforcement", ("stop-precommit.sh",)),
    "git-baseline-drift": Capability("enforcement", ("git-baseline.sh",)),
    "guarded-path-declarations": Capability("mechanism", ("guarded_paths.py",)),
    "guarded-surface": Capability("posture", ("guarded-paths.toml",)),
    "hook-interface": Capability("mechanism", ("hook_response.py",)),
    "hook-tampering-blocking": Capability("enforcement", ("block-hook-tampering.py",)),
    "path-matching": Capability("mechanism", ("guarded_paths.py",)),
    "secret-access-blocking": Capability("enforcement", ("block-leaks.py",)),
    "sensitive-path-blocking": Capability("enforcement", ("block-sensitive-paths.py",)),
    "session-tool-checks": Capability(
        "enforcement",
        ("session-tool-checks.sh", "session-policy-checks.py"),
    ),
    "shell-lexing": Capability("mechanism", ("shell_words.py",)),
    "unlisted-tool-refusal": Capability("enforcement", ("refuse-unlisted-tools.py",)),
}


def package_coverage_errors(
    specs_root: Path,
    hooks_root: Path,
    tests_root: Path,
    capabilities: Mapping[str, Capability],
) -> list[str]:
    """Return missing capability records and package artifacts."""
    errors: list[str] = []
    declared = {entry.name for entry in specs_root.iterdir() if entry.is_dir()}
    if missing := declared - set(capabilities):
        errors.append(f"capabilities have no recorded kind: {sorted(missing)}")

    for name, capability in capabilities.items():
        if capability.kind not in CAPABILITY_KINDS:
            errors.append(f"{name} has unknown kind: {capability.kind}")
            continue
        if capability.kind == "configuration":
            if capability.artifacts:
                errors.append(f"configuration capability {name} names artifacts")
            continue
        if not capability.artifacts:
            errors.append(f"{name} has no package artifacts")
            continue
        root = tests_root if capability.kind == "conformance" else hooks_root
        errors.extend(
            f"{name} artifact does not exist: {artifact}"
            for artifact in capability.artifacts
            if not (root / artifact).is_file()
        )

    return errors


def hook_coverage_errors(
    hooks_root: Path,
    capabilities: Mapping[str, Capability],
    tooling: frozenset[str],
) -> list[str]:
    """Return executable hook files that no capability or tooling entry claims."""
    claimed = {
        artifact
        for capability in capabilities.values()
        if capability.kind != "conformance"
        for artifact in capability.artifacts
    }
    hooks = {
        entry.name
        for entry in hooks_root.iterdir()
        if entry.is_file() and "-" in entry.name and entry.name not in HOOK_DATA_FILES
    }
    unclaimed = hooks - claimed - tooling
    return [f"hooks have no capability or tooling record: {sorted(unclaimed)}"] if unclaimed else []


def assert_package_coverage(
    specs_root: Path,
    hooks_root: Path,
    tests_root: Path,
    capabilities: Mapping[str, Capability],
) -> None:
    errors = package_coverage_errors(specs_root, hooks_root, tests_root, capabilities)
    assert not errors, "\n".join(errors)


def assert_hook_coverage(
    hooks_root: Path,
    capabilities: Mapping[str, Capability],
    tooling: frozenset[str],
) -> None:
    errors = hook_coverage_errors(hooks_root, capabilities, tooling)
    assert not errors, "\n".join(errors)


def test_every_capability_has_a_kind_and_existing_package_artifact() -> None:
    assert_package_coverage(SPECS_ROOT, HOOKS_ROOT, TESTS_ROOT, CAPABILITIES)


def test_every_hook_is_claimed_by_a_capability_or_tooling_record() -> None:
    assert_hook_coverage(HOOKS_ROOT, CAPABILITIES, TOOLING)


def test_every_artifact_named_by_a_capability_is_checked(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    hooks = tmp_path / "hooks"
    tests = tmp_path / "tests"
    specs.mkdir()
    hooks.mkdir()
    tests.mkdir()
    (specs / "example").mkdir()
    (hooks / "exists.py").touch()
    capabilities = {"example": Capability("mechanism", ("exists.py", "missing.py"))}

    errors = package_coverage_errors(specs, hooks, tests, capabilities)

    assert errors == ["example artifact does not exist: missing.py"]


def test_capability_without_a_record_fails_coverage(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    hooks = tmp_path / "hooks"
    tests = tmp_path / "tests"
    specs.mkdir()
    hooks.mkdir()
    tests.mkdir()
    (specs / "unrecorded-capability").mkdir()

    with pytest.raises(AssertionError, match="unrecorded-capability"):
        assert_package_coverage(specs, hooks, tests, {})


def test_hook_without_a_capability_or_tooling_record_fails_coverage(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    hooks = tmp_path / "hooks"
    tests = tmp_path / "tests"
    specs.mkdir()
    hooks.mkdir()
    tests.mkdir()
    (specs / "configuration-capability").mkdir()
    (hooks / "unclaimed-hook.py").touch()
    capabilities = {"configuration-capability": Capability("configuration", ())}
    assert_package_coverage(specs, hooks, tests, capabilities)

    with pytest.raises(AssertionError, match=r"unclaimed-hook\.py"):
        assert_hook_coverage(hooks, capabilities, frozenset())
