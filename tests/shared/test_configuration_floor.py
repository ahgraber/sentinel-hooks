"""The session-start check reports the settings that defeat Sentinel's hooks, and no other setting.

Validates: SettingsThatDefeatTheHooksAreReported. Each case writes one harness's
settings into a temporary home and project, and reads the report the check gives.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

from configuration_floor import CODEX_HOOK_MARKER, FLOOR_PATH, check_floor, floor_findings
from conftest import HOOKS_DIR, REPO_ROOT
import pytest

VSCODE_USER = "Library/Application Support/Code/User/settings.json"


@pytest.fixture
def world(tmp_path):
    """A home, a project, and a root for managed files, each empty."""
    for name in ("home", "project", "root"):
        (tmp_path / name).mkdir()
    return tmp_path


def write(world: Path, relative: str, text: str) -> Path:
    path = world / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def report(world: Path, environment: dict[str, str] | None = None) -> list[str]:
    return floor_findings(world / "home", world / "project", environment or {}, root=world / "root")


HOOKS_OFF = {
    "claude": ("home/.claude/settings.json", '{"disableAllHooks": true}', "Claude Code", "disableAllHooks"),
    "copilot": (
        "home/.copilot/settings.json",
        '{"disableAllHooks": true, "defaultPermissionMode": "manual"}',
        "Copilot CLI",
        "disableAllHooks",
    ),
    "codex": ("home/.codex/config.toml", "[features]\nhooks = false\n", "Codex", "features.hooks"),
    "codex-plugins": ("home/.codex/config.toml", "[features]\nplugins = false\n", "Codex", "features.plugins"),
    "vscode": (
        f"home/{VSCODE_USER}",
        '{\n  // hooks are off\n  "chat.useHooks": false,\n}\n',
        "VS Code",
        "chat.useHooks",
    ),
    "vscode-workspace": (
        "project/team.code-workspace",
        '{"folders": [], "settings": {"chat.plugins.enabled": false}}',
        "VS Code",
        "chat.plugins.enabled",
    ),
}


@pytest.mark.parametrize(("relative", "text", "harness", "setting"), HOOKS_OFF.values(), ids=HOOKS_OFF.keys())
def test_hooks_switched_off_are_reported(world, relative, text, harness, setting) -> None:
    """Validates: HooksSwitchedOff. The report names the harness, the file, and the setting."""
    path = write(world, relative, text)

    (finding,) = report(world)

    assert finding.startswith(f"{harness}: `{setting}` is ")
    assert str(path) in finding


SENTINEL_OFF = {
    "claude": ("home/.claude/settings.json", '{"enabledPlugins": {"sentinel@sentinel-hooks": false}}', "Claude Code"),
    "copilot-project": (
        "project/.github/copilot/settings.local.json",
        '{"enabledPlugins": {"sentinel@sentinel-hooks": false}}',
        "Copilot CLI",
    ),
    "vscode": (
        f"home/{VSCODE_USER}",
        '{"chat.plugins.enabledPlugins": {"sentinel@sentinel-hooks": false}}',
        "VS Code",
    ),
    "codex": ("home/.codex/config.toml", '[plugins."sentinel@sentinel-hooks"]\nenabled = false\n', "Codex"),
    "codex-default": ("home/.codex/config.toml", "[plugins._default]\nenabled = false\n", "Codex"),
    "pi-excluded": (
        "home/.pi/agent/settings.json",
        '{"packages": [{"source": "git:github.com/ahgraber/sentinel-hooks", "extensions": ["-extensions/pi/index.ts"]}]}',
        "Pi",
    ),
    "pi-none": (
        "home/.pi/agent/settings.json",
        '{"packages": [{"source": "git:github.com/ahgraber/sentinel-hooks", "extensions": []}]}',
        "Pi",
    ),
}


@pytest.mark.parametrize(("relative", "text", "harness"), SENTINEL_OFF.values(), ids=SENTINEL_OFF.keys())
def test_sentinel_switched_off_is_reported(world, relative, text, harness) -> None:
    """Validates: SentinelSwitchedOffInSettings, by Sentinel's own entry or by a default for every plugin."""
    path = write(world, relative, text)

    (finding,) = report(world)

    assert finding.startswith(f"{harness}: ")
    assert str(path) in finding


STAYS_ON = {
    "another-plugin-off": ("home/.claude/settings.json", '{"enabledPlugins": {"other@market": false}}'),
    "sentinel-on": ("home/.claude/settings.json", '{"enabledPlugins": {"sentinel@sentinel-hooks": true}}'),
    "codex-own-entry-outranks-the-default": (
        "home/.codex/config.toml",
        '[plugins._default]\nenabled = false\n[plugins."sentinel@sentinel-hooks"]\nenabled = true\n',
    ),
    "pi-unfiltered": ("home/.pi/agent/settings.json", '{"packages": ["git:github.com/ahgraber/sentinel-hooks"]}'),
    "pi-another-package-filtered": (
        "home/.pi/agent/settings.json",
        '{"packages": [{"source": "npm:pi-subagents", "extensions": []}]}',
    ),
    "vscode-workspace-cannot-set-an-application-setting": (
        "project/.vscode/settings.json",
        '{"chat.plugins.enabledPlugins": {"sentinel@sentinel-hooks": false}}',
    ),
}


@pytest.mark.parametrize(("relative", "text"), STAYS_ON.values(), ids=STAYS_ON.keys())
def test_settings_that_leave_sentinel_on_are_not_reported(world, relative, text) -> None:
    write(world, relative, text)

    assert report(world) == []


def test_a_pi_package_at_a_local_path_is_named_by_its_package_file(world) -> None:
    """Validates: SentinelSwitchedOffInSettings. `pi config` wrote this form for a package installed from a directory."""
    write(world, "home/src/package.json", '{"name": "sentinel-hooks"}')
    path = write(
        world,
        "home/.pi/agent/settings.json",
        '{"packages": [{"source": "../../src", "extensions": ["-extensions/pi/index.ts"]}]}',
    )

    (finding,) = report(world)

    assert finding.startswith("Pi: `packages.extensions`")
    assert str(path) in finding


def codex_hooks(world: Path, command: str) -> Path:
    hooks = {
        "hooks": {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "other"}, {"type": "command", "command": command}]}
            ]
        }
    }
    return write(world, "home/.codex/hooks.json", json.dumps(hooks))


def test_one_sentinel_hook_switched_off_is_reported(world) -> None:
    """Validates: OneSentinelHookSwitchedOff. The report names the harness, the file, and the hook."""
    hooks = codex_hooks(world, f"sh -c 'echo \"{CODEX_HOOK_MARKER}\"' /plugins/sentinel/hooks/block-leaks.py")
    config = write(world, "home/.codex/config.toml", f'[hooks.state."{hooks}:pre_tool_use:0:1"]\nenabled = false\n')

    (finding,) = report(world)

    assert finding.startswith("Codex: `hooks.state.")
    assert "block-leaks.py" in finding
    assert str(config) in finding


def test_another_hook_switched_off_is_not_reported(world) -> None:
    hooks = codex_hooks(world, f"sh -c 'echo \"{CODEX_HOOK_MARKER}\"' /plugins/sentinel/hooks/block-leaks.py")
    write(world, "home/.codex/config.toml", f'[hooks.state."{hooks}:pre_tool_use:0:0"]\nenabled = false\n')

    assert report(world) == []


def test_the_marker_is_the_one_the_codex_installer_writes() -> None:
    installer = REPO_ROOT / "plugins/sentinel/harnesses/codex/install-hooks.py"
    spec = importlib.util.spec_from_file_location("install_hooks", installer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.MISSING_HOOK_NOTICE == CODEX_HOOK_MARKER


def test_a_switch_off_in_a_codex_profile_is_reported_with_its_file(world) -> None:
    """A profile applies only when the user selects it, so each profile file is judged."""
    write(world, "home/.codex/config.toml", "[features]\nhooks = true\n")
    profile = write(world, "home/.codex/quiet.config.toml", "[features]\nhooks = false\n")

    (finding,) = report(world)

    assert str(profile) in finding


def test_an_ask_answered_by_a_model_is_reported(world) -> None:
    """Validates: AskAnsweredByAModel."""
    path = write(world, "home/.copilot/settings.json", '{"defaultPermissionMode": "assisted"}')

    (finding,) = report(world)

    assert finding.startswith('Copilot CLI: `defaultPermissionMode` is "assisted"')
    assert str(path) in finding


def test_an_unset_setting_with_an_unsafe_default_is_reported_as_unset(world) -> None:
    """Validates: UnsetSettingWithAnUnsafeDefault. Copilot CLI can start in assisted mode with the mode unset."""
    write(world, "home/.copilot/settings.json", "{}")

    (finding,) = report(world)

    assert finding.startswith("Copilot CLI: `defaultPermissionMode` is unset")


def test_an_unset_setting_is_not_reported_for_a_harness_with_no_home(world) -> None:
    assert report(world) == []


def test_a_managed_mode_takes_the_place_of_the_unset_one(world) -> None:
    write(world, "home/.copilot/settings.json", "{}")
    write(
        world,
        "root/Library/Application Support/GitHubCopilot/managed-settings.json",
        '{"permissions": {"defaultMode": "manual"}}',
    )

    assert report(world) == []


SAFE = {
    "unset-with-a-safe-default": ("home/.claude/settings.json", "{}"),
    "claude-bypass-mode": ("home/.claude/settings.json", '{"permissions": {"defaultMode": "bypassPermissions"}}'),
    "claude-auto-mode": ("home/.claude/settings.json", '{"permissions": {"defaultMode": "auto"}}'),
    "copilot-allow-all": ("home/.copilot/settings.json", '{"defaultPermissionMode": "allow-all"}'),
    "copilot-autopilot": (
        "home/.copilot/settings.json",
        '{"defaultPermissionMode": "manual", "defaultMode": "autopilot"}',
    ),
    "codex-full-access": ("home/.codex/config.toml", 'sandbox_mode = "danger-full-access"\n'),
}


@pytest.mark.parametrize(("relative", "text"), SAFE.values(), ids=SAFE.keys())
def test_a_setting_that_keeps_the_hooks_and_the_ask_is_not_reported(world, relative, text) -> None:
    """Validates: UnsetSettingWithASafeDefault, ModeThatKeepsTheAsk."""
    write(world, relative, text)

    assert report(world) == []


def test_a_higher_file_outranks_a_lower_one(world) -> None:
    """The settings are judged as the harness merges them: a project's local file outranks the user's."""
    write(world, "home/.claude/settings.json", '{"disableAllHooks": true}')
    write(world, "project/.claude/settings.local.json", '{"disableAllHooks": false}')

    assert report(world) == []


def test_a_managed_file_outranks_the_user_file(world) -> None:
    write(world, "home/.claude/settings.json", '{"disableAllHooks": false}')
    managed = write(
        world, "root/Library/Application Support/ClaudeCode/managed-settings.json", '{"disableAllHooks": true}'
    )

    (finding,) = report(world)

    assert str(managed) in finding


def test_a_home_moved_by_its_variable_is_read(world) -> None:
    path = write(world, "elsewhere/settings.json", '{"disableAllHooks": true}')

    (finding,) = report(world, {"CLAUDE_CONFIG_DIR": str(world / "elsewhere")})

    assert str(path) in finding


def test_a_settings_file_that_does_not_parse_is_reported_and_nothing_is_written(world) -> None:
    """Validates: SettingsFileCannotBeRead."""
    broken = write(world, "home/.claude/settings.json", '{"disableAllHooks": ')
    write(world, "home/.codex/config.toml", "[features]\nhooks = false\n")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in world.rglob("*") if path.is_file()}

    findings = report(world)

    assert any(str(broken) in finding and "unchecked" in finding for finding in findings)
    assert any(finding.startswith("Codex: `features.hooks`") for finding in findings)
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in world.rglob("*") if path.is_file()
    } == before


def test_every_value_records_its_evidence_version_and_date() -> None:
    """A value is listed only with a probe, source, or documentation, and the build and date it was read from."""
    floor = tomllib.loads(FLOOR_PATH.read_text())

    for harness in floor["harnesses"].values():
        assert harness["version"]
        for value in harness["values"]:
            assert value["evidence"] in {"probe", "source", "documentation"}, value["key"]
            assert value["source"], value["key"]
            assert isinstance(value["checked"], datetime.date), value["key"]


def run_check(world: Path, agent: str) -> subprocess.CompletedProcess:
    """Run the session check as a harness does, with a home and a working directory under `world`."""
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "session-policy-checks.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(world / "project")}),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(world / "home"),
            "AI_HOOK_AGENT": agent,
            "CLAUDE_CODE_SHELL": "/bin/bash",
        },
    )


@pytest.mark.parametrize("agent", ["claude", "codex", "pi"])
def test_an_agent_that_shows_a_system_message_receives_the_report_in_one(world, agent) -> None:
    """Claude Code, Codex, and Pi show the user a session hook's `systemMessage`, and not its standard error on exit 0."""
    write(world, "home/.codex/config.toml", "[features]\nhooks = false\n")

    result = run_check(world, agent)

    assert result.returncode == 0
    assert "Codex: `features.hooks` is false" in json.loads(result.stdout)["systemMessage"]


def test_copilot_receives_the_report_as_context_for_the_model_to_pass_on(world) -> None:
    """VS Code shows the user none of a session hook's output, and gives the model its `additionalContext`."""
    write(world, "home/.codex/config.toml", "[features]\nhooks = false\n")

    result = run_check(world, "copilot")

    reply = json.loads(result.stdout)["hookSpecificOutput"]
    assert result.returncode == 0
    assert reply["hookEventName"] == "SessionStart"
    assert "Tell the user each warning" in reply["additionalContext"]
    assert "Codex: `features.hooks` is false" in reply["additionalContext"]


def test_an_undeclared_agent_receives_the_report_on_standard_error(world) -> None:
    write(world, "home/.codex/config.toml", "[features]\nhooks = false\n")

    result = run_check(world, "something-else")

    assert result.returncode == 0
    assert result.stdout == ""
    assert "Warning: Codex: `features.hooks` is false" in result.stderr


def mutated(change) -> dict:
    """Return the shipped floor data with one change applied."""
    floor = tomllib.loads(FLOOR_PATH.read_text())
    change(floor["harnesses"])
    return floor


def test_the_shipped_floor_passes_its_check() -> None:
    check_floor(mutated(lambda harnesses: None))


FLOOR_DEFECTS = {
    "a-mistyped-file-scope": (lambda h: h["claude"]["files"][0].update(scope="usr"), "unknown scope `usr`"),
    "a-mistyped-value-scope": (lambda h: h["claude"]["values"][0].update(scopes=["usr"]), "unknown scopes `usr`"),
    "a-setting-with-no-values": (lambda h: h["claude"]["values"][0].pop("is"), "has no `is` list"),
    "a-field-of-another-kind": (lambda h: h["claude"]["values"][0].update(field="enabled"), "unknown field `field`"),
    "an-unknown-kind": (lambda h: h["claude"]["values"][0].update(kind="plugin"), "unknown kind `plugin`"),
    "a-value-with-no-effect": (lambda h: h["claude"]["values"][0].pop("effect"), "has no `effect`"),
    "a-stand-in-with-no-unset": (lambda h: h["copilot"]["values"][2].pop("unset"), "`unset-unless` without `unset`"),
    "unknown-evidence": (lambda h: h["claude"]["values"][0].update(evidence="guess"), "unknown evidence `guess`"),
    "an-unknown-format": (lambda h: h["claude"].update(format="yaml"), "unknown format `yaml`"),
    "a-mistyped-field": (
        lambda h: h["claude"]["values"][0].update(checked="2026-11-10"),
        "field `checked` is not date",
    ),
}


@pytest.mark.parametrize(("change", "problem"), FLOOR_DEFECTS.values(), ids=FLOOR_DEFECTS.keys())
def test_a_floor_with_a_defect_is_rejected_by_name(change, problem) -> None:
    """A defect is reported when the file loads, and not only where the defective setting is present."""
    with pytest.raises(ValueError, match=re.escape(problem)):
        check_floor(mutated(change))
