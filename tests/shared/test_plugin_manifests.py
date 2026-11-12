"""Validates the manifests, registrations, and catalogs that make the repository an installable plugin.

Covers `plugin-distribution` `EachHarnessRunsOnlyItsOwnRegistration`,
`HooksRunFromTheInstalledPlugin`, and `OneVersionAcrossManifests`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from hermetic import HOOKS_DIR, REPO_ROOT
import pytest

PLUGIN_DIR = HOOKS_DIR.parent
AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ADAPTER = "harnesses/copilot/copilot-vscode-hook-adapter.py"
# Each registration, and the plugin-root variable its harness sets for hook commands.
REGISTRATIONS = {
    "harnesses/claude/hooks.json": "CLAUDE_PLUGIN_ROOT",
    "harnesses/codex/hooks.json": "PLUGIN_ROOT",
    "com.github.copilot/hooks/hooks.json": "PLUGIN_ROOT",
    "harnesses/pi/hooks.json": "PLUGIN_ROOT",
}
MANIFESTS = ("plugins/sentinel/.claude-plugin/plugin.json", "plugins/sentinel/plugin.json", "package.json")
CATALOGS = (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json", ".github/plugin/marketplace.json")
EXTENSION_MANIFEST = "extensions/pi/package.json"


def commands(registration: Path) -> list[str]:
    """Every command a registration declares, in either the nested or the flat event layout."""

    def walk(node: object) -> list[str]:
        if isinstance(node, dict):
            own = [node["command"]] if isinstance(node.get("command"), str) else []
            return own + [command for value in node.values() for command in walk(value)]
        if isinstance(node, list):
            return [command for item in node for command in walk(item)]
        return []

    return walk(json.loads(registration.read_text()))


def manifest(relative: str) -> dict:
    return json.loads((PLUGIN_DIR / relative).read_text())


class TestEachHarnessRunsOnlyItsOwnRegistration:
    @pytest.mark.parametrize("default", ["hooks/hooks.json", "hooks.json", ".codex-plugin"])
    def test_no_file_another_harness_would_load_by_default(self, default) -> None:
        assert not (PLUGIN_DIR / default).exists()

    def test_the_claude_manifest_names_the_claude_registration(self) -> None:
        assert manifest(".claude-plugin/plugin.json")["hooks"] == "./harnesses/claude/hooks.json"

    def test_the_root_manifest_is_agent_plugins_and_names_the_codex_registration(self) -> None:
        root = manifest("plugin.json")
        assert root["$schema"] == AGENT_PLUGINS_SCHEMA
        assert root["extensions"]["com.openai"]["hooks"] == "./harnesses/codex/hooks.json"

    def test_the_copilot_registration_runs_only_the_adapter(self) -> None:
        declared = commands(PLUGIN_DIR / "com.github.copilot/hooks/hooks.json")
        assert declared
        assert {shlex.split(command)[0] for command in declared} == {f"${{PLUGIN_ROOT}}/{ADAPTER}"}


STUB_SHELL = '#!/bin/sh\nprintf "%s\\n" "$0" >> "$STUB_LOG"\n'
STUB_PYTHON = (
    "#!/usr/bin/env -S uv run --script\n"
    "import os, sys\n"
    "with open(os.environ['STUB_LOG'], 'a') as log:\n"
    "    log.write(os.path.abspath(sys.argv[0]) + '\\n')\n"
)


@pytest.fixture(scope="module")
def stubbed_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the plugin whose hooks, adapter, and dispatcher only record that they ran."""
    copy = tmp_path_factory.mktemp("installed") / "sentinel"
    shutil.copytree(PLUGIN_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    for script in [*copy.glob("hooks/*-*.*"), *copy.glob("harnesses/*/*.py")]:
        if script.suffix in {".sh", ".py"}:
            script.write_text(STUB_SHELL if script.suffix == ".sh" else STUB_PYTHON)
            script.chmod(0o755)
    return copy


@pytest.mark.parametrize("cwd", ["unrelated", "checkout"])
@pytest.mark.parametrize("registration", REGISTRATIONS)
def test_every_command_starts_the_hook_in_the_installed_copy(stubbed_copy, tmp_path, registration, cwd) -> None:
    log = tmp_path / "ran.log"
    workdir = REPO_ROOT if cwd == "checkout" else tmp_path
    env = {key: value for key, value in os.environ.items() if key not in REGISTRATIONS.values()}
    env |= {REGISTRATIONS[registration]: str(stubbed_copy), "STUB_LOG": str(log)}
    declared = commands(PLUGIN_DIR / registration)
    assert declared

    for command in declared:
        subprocess.run(["sh", "-c", command], input="{}", text=True, cwd=workdir, env=env, timeout=60, check=True)

    ran = [Path(line) for line in log.read_text().splitlines()]
    assert len(ran) == len(declared)
    assert all(path.resolve().is_relative_to(stubbed_copy.resolve()) for path in ran), ran


def sentinel_versions(root: Path) -> dict[str, str | None]:
    """The version each manifest and each catalog's Sentinel entry carries."""
    versions = {path: json.loads((root / path).read_text()).get("version") for path in MANIFESTS}
    for path in CATALOGS:
        entries = [entry for entry in json.loads((root / path).read_text())["plugins"] if entry["name"] == "sentinel"]
        versions[path] = entries[0].get("version") if len(entries) == 1 else None
    return versions


def test_every_manifest_and_catalog_carries_one_version() -> None:
    versions = sentinel_versions(REPO_ROOT)
    assert None not in versions.values(), versions
    assert len(set(versions.values())) == 1, versions


def test_one_differing_version_fails(tmp_path) -> None:
    for path in (*MANIFESTS, *CATALOGS):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / path, tmp_path / path)
    package = json.loads((tmp_path / "package.json").read_text())
    package["version"] = "999.0.0"
    (tmp_path / "package.json").write_text(json.dumps(package))

    assert len(set(sentinel_versions(tmp_path).values())) == 2


def test_the_pi_extension_carries_its_own_version(tmp_path) -> None:
    for path in (*MANIFESTS, *CATALOGS, EXTENSION_MANIFEST):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / path, tmp_path / path)
    extension = json.loads((tmp_path / EXTENSION_MANIFEST).read_text())
    assert extension.get("version"), extension
    extension["version"] = "999.0.0"
    (tmp_path / EXTENSION_MANIFEST).write_text(json.dumps(extension))

    assert len(set(sentinel_versions(tmp_path).values())) == 1
