from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import re
from typing import Literal

import pytest

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".specs").is_dir())
SPECS_ROOT = REPO_ROOT / ".specs" / "specs"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "sentinel"
HOOKS_ROOT = PLUGIN_ROOT / "hooks"
HARNESSES_ROOT = PLUGIN_ROOT / "harnesses"
EXTENSIONS_ROOT = REPO_ROOT / "extensions"
TESTS_ROOT = REPO_ROOT / "tests" / "shared"
REGISTRATIONS = (
    *sorted(HARNESSES_ROOT.glob("*/hooks.json")),
    PLUGIN_ROOT / "com.github.copilot" / "hooks" / "hooks.json",
)

CapabilityKind = Literal["enforcement", "mechanism", "posture", "conformance", "harness"]
CAPABILITY_KINDS = frozenset({"enforcement", "mechanism", "posture", "conformance", "harness"})
HOOK_DATA_FILES = frozenset(
    {
        "block-destructive-ops-patterns.toml",
        "guarded-paths.toml",
        "tool-vocabulary.toml",
    }
)
TOOLING: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Capability:
    kind: CapabilityKind
    artifacts: tuple[str, ...]


CAPABILITIES: Mapping[str, Capability] = {
    "agent-configuration-floor": Capability("enforcement", ("session-policy-checks.py",)),
    "bash-command-validator": Capability("enforcement", ("bash-command-validator.sh",)),
    "cross-agent-capability-parity": Capability("conformance", ("test_capability_coverage.py",)),
    "dangerous-bash-blocking": Capability("enforcement", ("block-dangerous-bash.sh",)),
    "destructive-ops-blocking": Capability("enforcement", ("block-destructive-ops.py",)),
    "git-baseline-drift": Capability("enforcement", ("git-baseline.sh",)),
    "guarded-path-declarations": Capability("mechanism", ("guarded_paths.py",)),
    "guarded-surface": Capability("posture", ("guarded-paths.toml",)),
    "hook-events": Capability("harness", ("pi/extension.ts", "pi/index.ts")),
    "hook-execution": Capability(
        "harness",
        ("pi/runner.ts", "pi/decode.ts", "pi/combine.ts"),
    ),
    "hook-interface": Capability("mechanism", ("hook_response.py",)),
    "hook-registration": Capability("harness", ("pi/registration.ts", "pi/matcher.ts")),
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
    extensions_root: Path,
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
        if not capability.artifacts:
            errors.append(f"{name} has no package artifacts")
            continue
        root = {"conformance": tests_root, "harness": extensions_root}.get(capability.kind, hooks_root)
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


def _pi_dispatched_hooks() -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location("hook_dispatch", HARNESSES_ROOT / "pi" / "hook-dispatch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PYTHON_HOOKS


# Hooks that a registered adapter or launcher runs without the registration naming
# them. Both adapters refuse a tool the vocabulary does not map, so each carries
# unlisted-tool refusal in place of the hook.
RUN_BY: Mapping[str, tuple[str, ...]] = {
    "copilot-vscode-hook-adapter.py": ("refuse-unlisted-tools.py",),
    "hook-dispatch.py": (*_pi_dispatched_hooks(), "refuse-unlisted-tools.py"),
    "session-tool-checks.sh": ("session-policy-checks.py",),
}
SCRIPT_NAME_RE = re.compile(r"[\w.-]+\.(?:py|sh)\b")


def _commands(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                yield value
            else:
                yield from _commands(value)
    elif isinstance(node, list):
        for item in node:
            yield from _commands(item)


def hooks_run(registration: Path, run_by: Mapping[str, tuple[str, ...]]) -> set[str]:
    """Return the scripts a registration runs, directly or through an adapter or launcher."""
    run = {
        name for command in _commands(json.loads(registration.read_text())) for name in SCRIPT_NAME_RE.findall(command)
    }
    pending = list(run)
    while pending:
        for hook in run_by.get(pending.pop(), ()):
            if hook not in run:
                run.add(hook)
                pending.append(hook)
    return run


def registration_coverage_errors(
    registrations: Iterable[Path],
    capabilities: Mapping[str, Capability],
    run_by: Mapping[str, tuple[str, ...]],
) -> list[str]:
    """Return each registration that does not run every hook of the enforcement kind."""
    enforcement = {
        artifact
        for capability in capabilities.values()
        if capability.kind == "enforcement"
        for artifact in capability.artifacts
        if artifact not in HOOK_DATA_FILES
    }
    return [
        f"{registration} does not run enforcement hooks: {sorted(missing)}"
        for registration in registrations
        if (missing := enforcement - hooks_run(registration, run_by))
    ]


def assert_package_coverage(
    specs_root: Path,
    hooks_root: Path,
    tests_root: Path,
    extensions_root: Path,
    capabilities: Mapping[str, Capability],
) -> None:
    errors = package_coverage_errors(specs_root, hooks_root, tests_root, extensions_root, capabilities)
    assert not errors, "\n".join(errors)


def assert_hook_coverage(
    hooks_root: Path,
    capabilities: Mapping[str, Capability],
    tooling: frozenset[str],
) -> None:
    errors = hook_coverage_errors(hooks_root, capabilities, tooling)
    assert not errors, "\n".join(errors)


def test_every_capability_has_a_kind_and_existing_package_artifact() -> None:
    assert_package_coverage(SPECS_ROOT, HOOKS_ROOT, TESTS_ROOT, EXTENSIONS_ROOT, CAPABILITIES)


def test_every_hook_is_claimed_by_a_capability_or_tooling_record() -> None:
    assert_hook_coverage(HOOKS_ROOT, CAPABILITIES, TOOLING)


def test_every_registration_runs_every_enforcement_hook() -> None:
    errors = registration_coverage_errors(REGISTRATIONS, CAPABILITIES, RUN_BY)
    assert not errors, "\n".join(errors)


def test_registration_missing_an_enforcement_hook_fails_coverage(tmp_path: Path) -> None:
    registration = tmp_path / "hooks.json"
    command = {"type": "command", "command": '"${PLUGIN_ROOT}/hooks/block-kept.py"'}
    registration.write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [command]}]}}))
    capabilities = {
        "kept": Capability("enforcement", ("block-kept.py",)),
        "dropped": Capability("enforcement", ("block-dropped.sh",)),
    }

    errors = registration_coverage_errors([registration], capabilities, {})

    assert errors == [f"{registration} does not run enforcement hooks: ['block-dropped.sh']"]


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

    errors = package_coverage_errors(specs, hooks, tests, tmp_path / "harnesses", capabilities)

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
        assert_package_coverage(specs, hooks, tests, tmp_path / "harnesses", {})


def test_hook_without_a_capability_or_tooling_record_fails_coverage(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    hooks = tmp_path / "hooks"
    tests = tmp_path / "tests"
    specs.mkdir()
    hooks.mkdir()
    tests.mkdir()
    (specs / "configuration-capability").mkdir()
    (hooks / "unclaimed-hook.py").touch()
    (hooks / "claimed.py").touch()
    capabilities = {"configuration-capability": Capability("mechanism", ("claimed.py",))}
    assert_package_coverage(specs, hooks, tests, tmp_path / "harnesses", capabilities)

    with pytest.raises(AssertionError, match=r"unclaimed-hook\.py"):
        assert_hook_coverage(hooks, capabilities, frozenset())
