"""Each registration the plugin ships sends a hook every tool spelling that hook judges.

Validates: RegistrationsRouteTheVocabulary. A registration selects calls by the
harness's own tool names before any hook runs, so a hook can be correct about a
tool it never sees. A hook judges the tools of the vocabulary groups its source
reads; a hook that reads no group, such as a shell script, is not judged here.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import importlib.util
import json
from pathlib import Path
import re
import tomllib

import pytest
from test_capability_coverage import HARNESSES_ROOT, HOOKS_ROOT, REGISTRATIONS, RUN_BY, SCRIPT_NAME_RE, hooks_run

GROUP_READ_RE = re.compile(r'TOOL_VOCABULARY\.group\("([\w-]+)"\)')
VOCABULARY = tomllib.loads((HOOKS_ROOT / "tool-vocabulary.toml").read_text())


def _copilot_scopes() -> Mapping[tuple[str, ...], str]:
    adapter = HARNESSES_ROOT / "copilot" / "copilot-vscode-hook-adapter.py"
    spec = importlib.util.spec_from_file_location("copilot_adapter", adapter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.HOOK_SCOPES


def harness_of(registration: Path) -> str:
    """Name the harness a shipped registration is written for."""
    return "copilot" if "com.github.copilot" in registration.parts else registration.parent.name


def _routes(registration: Path) -> Iterator[tuple[str | None, str]]:
    """Yield each `PreToolUse` command with the matcher that selects its calls, or `None` for every call."""
    for entry in json.loads(registration.read_text())["hooks"].get("PreToolUse", ()):
        for handler in entry.get("hooks", (entry,)):
            yield entry.get("matcher"), handler["command"]


def routing_errors(
    registration: Path,
    harness: str,
    vocabulary: Mapping,
    hooks_root: Path,
    run_by: Mapping[str, tuple[str, ...]],
    scopes: Mapping[tuple[str, ...], str],
) -> list[str]:
    """Return each mapped spelling that does not reach a hook the registration declares and that judges its tool.

    `run_by` names the hooks an adapter or dispatcher runs for every call it
    receives. `scopes` names the tool group an adapter limits a hook to.
    """
    groups = vocabulary["groups"]

    def reaches(matcher: str | None, command: str, spelling: str, tool: str, hook: str) -> bool:
        if matcher is not None and not re.fullmatch(f"(?:{matcher})", spelling):
            return False
        scripts = SCRIPT_NAME_RE.findall(command)
        if hook in scripts:
            scope = scopes.get((hook,))
            return scope is None or tool in groups[scope]
        return any(hook in run_by.get(script, ()) for script in scripts)

    declared = hooks_run(registration, run_by)
    routes = list(_routes(registration))
    errors = []
    for hook in sorted(declared):
        source = hooks_root / hook
        judged = (
            {tool for name in GROUP_READ_RE.findall(source.read_text()) for tool in groups[name]}
            if source.is_file()
            else ()
        )
        for spelling, tool in vocabulary["mappings"][harness].items():
            if tool in judged and not any(
                reaches(matcher, command, spelling, tool, hook) for matcher, command in routes
            ):
                errors.append(f"{registration}: `{spelling}` does not reach {hook}")
    return errors


@pytest.mark.parametrize("registration", REGISTRATIONS, ids=harness_of)
def test_a_shipped_registration_routes_every_mapped_spelling(registration: Path) -> None:
    """Validates: RegistrationRoutesEveryMappedSpelling, RoutingThroughAnAdapter."""
    harness = harness_of(registration)
    scopes = _copilot_scopes() if harness == "copilot" else {}

    errors = routing_errors(registration, harness, VOCABULARY, HOOKS_ROOT, RUN_BY, scopes)

    assert not errors, "\n".join(errors)


FIXTURE_VOCABULARY = {
    "groups": {"file": ["Read", "Write"], "writes": ["Write"]},
    "mappings": {"fixture": {"read": "Read", "write": "Write"}},
}


@pytest.fixture
def judge(tmp_path: Path) -> Path:
    """A hooks directory with one hook that judges the `file` group."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "judge.py").write_text('TOOLS = TOOL_VOCABULARY.group("file")\n')
    return hooks


def registration_of(tmp_path: Path, pre_tool_use: list) -> Path:
    registration = tmp_path / "hooks.json"
    registration.write_text(json.dumps({"hooks": {"PreToolUse": pre_tool_use}}))
    return registration


def test_a_spelling_the_registration_misses_is_named(tmp_path: Path, judge: Path) -> None:
    """Validates: SpellingTheRegistrationMisses. The error names the spelling, the hook, and the registration."""
    handler = {"type": "command", "command": '"${PLUGIN_ROOT}/hooks/judge.py"'}
    registration = registration_of(tmp_path, [{"matcher": "write", "hooks": [handler]}])

    errors = routing_errors(registration, "fixture", FIXTURE_VOCABULARY, judge, {}, {})

    assert errors == [f"{registration}: `read` does not reach judge.py"]


def test_a_dispatcher_s_matcher_is_judged_as_the_registration(tmp_path: Path, judge: Path) -> None:
    """Validates: RoutingThroughAnAdapter. A dispatcher runs its hooks only for the calls its group selects."""
    handler = {"type": "command", "command": '"${PLUGIN_ROOT}/harnesses/fixture/dispatch.py"'}
    registration = registration_of(tmp_path, [{"matcher": "write", "hooks": [handler]}])

    errors = routing_errors(registration, "fixture", FIXTURE_VOCABULARY, judge, {"dispatch.py": ("judge.py",)}, {})

    assert errors == [f"{registration}: `read` does not reach judge.py"]


def test_an_adapter_s_scope_is_judged_as_the_registration(tmp_path: Path, judge: Path) -> None:
    """Validates: RoutingThroughAnAdapter. An adapter that limits a hook to a tool group routes only that group."""
    registration = registration_of(tmp_path, [{"type": "command", "command": "adapter.py judge.py"}])

    errors = routing_errors(registration, "fixture", FIXTURE_VOCABULARY, judge, {}, {("judge.py",): "writes"})

    assert errors == [f"{registration}: `read` does not reach judge.py"]
