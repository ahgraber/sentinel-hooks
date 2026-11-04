"""Grants permit content changes without permitting changes to enforcement."""

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys

import guarded_paths
from guarded_paths import ManifestError, PathPolicy
from hermetic import HOOKS_DIR, REPO_ROOT, build_world, install_policy, load_hook, policy
import pytest


@pytest.fixture
def policy_world(tmp_path, monkeypatch):
    return build_world(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    "target",
    [
        "~/.claude/settings.json",
        "~/.claude/settings.local.json",
        "~/.claude/hooks/local.py",
        "~/.codex/config.toml",
        "~/.codex/hooks.json",
        "~/.codex/work.config.toml",
        "~/.codex/rules/default.rules",
        "~/.copilot/hooks/security-policy.json",
        "~/.pi/agent/settings.json",
        "~/.pi/agent/hooks.json",
        "~/.pi/agent/extensions/hooks/extension.ts",
        "~/.agents/hooks/session.json",
        "~/.vscode/agent-plugins/example/hooks/hooks.json",
        "~/.config/Code/User/settings.json",
        "~/Library/Application Support/Code/User/settings.json",
    ],
)
@pytest.mark.parametrize(("operation", "grant"), [("write", "write"), ("run", "run")])
def test_exact_grant_cannot_override_floor(policy_world, target, operation, grant):
    rules = policy(policy_world, **{grant: [target]})
    assert rules.verdict(target, operation) == "guarded"
    assert rules.verdict(target, "read") == "undeclared"


def test_broad_grant_preserves_content_but_not_enforcement(policy_world):
    rules = policy(policy_world, write=["~/.claude/"])
    assert not rules.findings
    assert rules.verdict("~/.claude/hooks/local.py", "write") == "guarded"
    assert rules.verdict("~/.claude/notes", "write") == "write-through"
    assert rules.verdict("~/.claude/hooks/instructions/style.md", "write") == "write-through"
    assert any("does not apply" in finding and "hooks/local.py" in finding for finding in rules.findings)


@pytest.mark.parametrize("target", ["~/.copilot/settings.json", "~/.copilot/config.json"])
def test_copilot_plugin_switches_hold_against_a_broad_grant(policy_world, target):
    """Validates: CopilotSettingsDisableTheHooks."""
    rules = policy(policy_world, write=["~/.copilot/"])
    assert rules.verdict(target, "write") == "guarded"
    assert rules.verdict("~/.copilot/notes", "write") == "write-through"


def test_grant_inside_the_floor_is_reported(policy_world):
    rules = policy(policy_world, write=["~/.claude/hooks/"])
    assert rules.verdict("~/.claude/hooks/local.py", "write") == "guarded"
    assert any("does not apply" in finding and ".claude/hooks" in finding for finding in rules.findings)
    assert all("ignored" not in finding for finding in rules.findings)


def test_block_still_outranks_floor(policy_world):
    target = "~/.claude/settings.json"
    rules = policy(policy_world, block=[target], write=[target])
    assert all(rules.verdict(target, operation) == "block" for operation in ("read", "write", "run"))


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/settings.local.json",
        ".codex/config.toml",
        ".vscode/settings.json",
        ".github/hooks/policy.json",
        ".github/copilot/settings.json",
        ".github/copilot/settings.local.json",
    ],
)
def test_project_permission_settings_are_floor_without_git(policy_world, relative):
    """Validates: ProjectCopilotSettingsAreWritten, among the other project settings files."""
    home, _, _ = policy_world
    project = home / "project"
    rules = policy(policy_world, write=[str(project) + "/"])
    assert rules.verdict(str(project / relative), "write", cwd=str(project)) == "guarded"
    assert rules.verdict(str(project / "notes"), "write") == "write-through"


def test_a_floor_declaration_holds_against_a_grant(policy_world):
    home, _, _ = policy_world
    target = str(home / "custom/hooks/guard.py")
    declared = policy(policy_world, write=["~/custom/"], floor=["~/custom/hooks/"])
    undeclared = policy(policy_world, write=["~/custom/"], floor=[])
    assert declared.verdict(target, "write") == "guarded"
    assert declared.verdict(target, "run") == "guarded"
    assert undeclared.verdict(target, "write") == "write-through"


def test_instruction_text_in_a_floor_directory_is_guarded(policy_world):
    target = "~/custom/hooks/instructions/style.md"
    assert policy(policy_world, floor=["~/custom/hooks/"]).verdict(target, "write") == "guarded"
    granted = policy(policy_world, write=["~/custom/"], floor=["~/custom/hooks/"])
    assert granted.verdict(target, "write") == "write-through"


def test_a_floor_directory_is_followed_to_its_sources(policy_world):
    home, repo, _ = policy_world
    hooks = home / "custom/hooks"
    hooks.mkdir(parents=True)
    source = repo / "custom-source.py"
    source.touch()
    (hooks / "guard.py").symlink_to(source)
    rules = policy(policy_world, write=[str(repo) + "/"], floor=["~/custom/hooks/"])
    assert rules.verdict(str(source), "write") == "guarded"


def test_project_anchor_covers_the_working_directory_and_above(policy_world):
    home, _, _ = policy_world
    project = home / "project"
    nested = project / "src/module"
    rules = policy(policy_world, write=[str(project) + "/"], floor=["<project>/.tool/settings.json"])
    for root in (project, nested):
        assert rules.verdict(str(root / ".tool/settings.json"), "write", cwd=str(nested)) == "guarded"
    assert rules.verdict(str(project / "notes"), "write", cwd=str(nested)) == "write-through"


@pytest.mark.parametrize("class_name", ["guarded", "block", "run", "write"])
def test_project_anchor_outside_the_floor_does_not_load(policy_world, class_name):
    with pytest.raises(ManifestError, match="<project>/"):
        policy(policy_world, **{class_name: ["<project>/.tool/settings.json"]})


def test_an_empty_floor_keeps_the_manifest_and_the_running_hooks(policy_world):
    _, repo, manifest = policy_world
    rules = policy(policy_world, write=[str(repo) + "/"], floor=[])
    assert rules.verdict(str(manifest), "write") == "guarded"
    assert rules.verdict(str(Path(guarded_paths.__file__).resolve()), "write") == "guarded"


def test_unrelated_hooks_directory_is_not_enforcement(policy_world):
    home, _, _ = policy_world
    hooks = home / "ordinary/hooks"
    hooks.mkdir(parents=True)
    (hooks / "task.py").touch()
    rules = policy(policy_world, write=[str(hooks) + "/"])
    assert rules.verdict(str(hooks / "task.py"), "write") == "write-through"
    assert rules.findings == []


def test_floor_follows_deployed_hook_to_source(policy_world):
    home, repo, _ = policy_world
    hooks = home / ".claude/hooks"
    hooks.mkdir(parents=True)
    source = repo / "custom.py"
    source.touch()
    (hooks / "local.py").symlink_to(source)
    rules = policy(policy_world, write=[str(repo) + "/"])
    assert rules.verdict(str(source), "write") == "guarded"


def test_launch_directory_supplies_enforcement(policy_world):
    home, _, manifest = policy_world
    launch = home / "custom-agent/hooks/guard.py"
    launch.parent.mkdir(parents=True)
    launch.touch()
    data = {name: {"paths": []} for name in ("guarded", "enforcement-floor", "block", "exec-through", "write-through")}
    data["write-through"]["paths"] = [str(launch.parent) + "/"]
    data["exceptions"] = []
    rules = PathPolicy(
        data,
        home=str(home),
        manifest_path=manifest,
        invocation_path=str(launch),
    )
    assert rules.verdict(str(launch), "write") == "guarded"


def test_project_setting_source_is_floor_through_its_link(policy_world):
    home, repo, _ = policy_world
    project = home / "project"
    (project / ".claude").mkdir(parents=True)
    source = repo / "project-permissions.json"
    source.touch()
    (project / ".claude/settings.local.json").symlink_to(source)
    rules = policy(policy_world, write=[str(repo) + "/"])
    assert rules.verdict(str(source), "write", cwd=str(project)) == "guarded"
    assert any(str(source) in finding for finding in rules.findings)


def test_a_declaration_does_not_extend_the_floor(policy_world):
    home, repo, _ = policy_world
    hooks = home / ".claude/custom/hooks"
    hooks.mkdir(parents=True)
    source = repo / "custom-agent-hook.py"
    source.touch()
    (hooks / "local.py").symlink_to(source)
    rules = policy(policy_world, guarded=["~/.claude/custom/hooks/"], write=[str(source)])
    assert rules.verdict(str(source), "write") == "write-through"
    assert not rules.findings


def test_instruction_named_ancestor_does_not_exempt_permission_rules(policy_world):
    home, _, _ = policy_world
    project = home / "instructions/project"
    target = project / ".codex/rules/permission.md"
    rules = policy(policy_world, write=[str(project) + "/"])
    assert rules.verdict(str(target), "write", cwd=str(project)) == "guarded"


def test_validator_does_not_recommend_a_grant_over_the_floor(policy_world):
    home, _, _ = policy_world
    (home / "memory").mkdir()
    (home / "memory/link").symlink_to(home / ".claude/settings.json")
    rules = policy(policy_world, write=["~/memory/"])
    findings = rules.validate()
    assert findings
    assert all("declare the target explicitly to permit it" not in item for item in findings)


@pytest.mark.parametrize("agent", ["claude", "codex", "copilot"])
@pytest.mark.parametrize(
    "target",
    [
        "~/.claude/settings.json",
        "~/.codex/config.toml",
        "~/.copilot/hooks/security-policy.json",
        "~/.pi/agent/settings.json",
    ],
)
def test_home_grant_keeps_each_harness_settings_gated(policy_world, monkeypatch, capsys, agent, target):
    _, repo, _ = policy_world
    rules = policy(policy_world, write=["~/"])
    hook = load_hook("block-hook-tampering")
    install_policy(monkeypatch, hook, rules)
    monkeypatch.setenv("AI_HOOK_AGENT", agent)
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": target},
                    "cwd": str(repo),
                }
            )
        ),
    )
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    output = capsys.readouterr()
    if agent == "codex":
        assert stopped.value.code == 2
    else:
        assert stopped.value.code == 0
        assert json.loads(output.out)["hookSpecificOutput"]["permissionDecision"] == "ask"


PLUGINS = "~/.claude/plugins/"
INSTALLED = "~/.claude/plugins/cache/market/sentinel/0.1.0"
PLUGIN_SKILLS = "~/.claude/plugins/cache/*/*/*/skills/"


def installed_plugin(world) -> Path:
    """An installed plugin directory under a plugin install location in `world`'s home."""
    home = world[0]
    plugin = home / INSTALLED.removeprefix("~/")
    (plugin / "hooks").mkdir(parents=True)
    (plugin / "hooks" / "block-leaks.py").touch()
    (plugin / "skills" / "review" / "scripts").mkdir(parents=True)
    (plugin / "skills" / "review" / "scripts" / "check.py").touch()
    return plugin


def install_location_policy(world, **declarations):
    return policy(world, floor=[PLUGINS], plugins=[PLUGINS], **declarations)


class TestInstallLocationsDeclareTheirLinks:
    """Validates: the floor inside a plugin install location covers every link, every hop, and every path under a linked directory."""

    def test_a_new_file_behind_a_link_below_the_top_level_is_floor(self, policy_world, tmp_path):
        """Validates: NewFileBehindALinkInAnInstallLocation."""
        outside = tmp_path / "outside" / "vendor"
        outside.mkdir(parents=True)
        (installed_plugin(policy_world) / "hooks" / "vendor").symlink_to(outside)
        rules = install_location_policy(policy_world)

        assert rules.verdict(str(outside / "created-later.py"), "write") == "guarded"

    def test_a_file_link_below_the_top_level_puts_its_target_in_the_floor(self, policy_world, tmp_path):
        target = tmp_path / "outside" / "hook.py"
        target.parent.mkdir(parents=True)
        target.touch()
        (installed_plugin(policy_world) / "hooks" / "linked.py").symlink_to(target)
        rules = install_location_policy(policy_world)

        assert rules.verdict(str(target), "write") == "guarded"

    def test_a_hidden_top_level_link_puts_its_target_in_the_floor(self, policy_world, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (installed_plugin(policy_world) / ".hidden").symlink_to(outside)
        rules = install_location_policy(policy_world)

        assert rules.verdict(str(outside / "hooks.json"), "write") == "guarded"

    def test_the_middle_hop_of_a_link_to_a_link_is_floor(self, policy_world, tmp_path):
        target = tmp_path / "far" / "hook.py"
        target.parent.mkdir()
        target.touch()
        middle = tmp_path / "near" / "hook.py"
        middle.parent.mkdir()
        middle.symlink_to(target)
        (installed_plugin(policy_world) / "hooks" / "linked.py").symlink_to(middle)
        rules = install_location_policy(policy_world)

        assert rules.verdict(str(middle), "write") == "guarded"
        assert rules.verdict(str(target), "write") == "guarded"

    def test_an_unlinked_path_outside_the_location_is_not_floor(self, policy_world, tmp_path):
        installed_plugin(policy_world)
        rules = install_location_policy(policy_world)

        assert rules.verdict(str(tmp_path / "elsewhere.py"), "write") == "undeclared"


class TestRunningPluginDirectory:
    def test_a_registration_beside_the_running_hooks_is_floor(self, policy_world):
        """Validates: RunningCopyLoadedInPlace, with the checkout's own plugin directory."""
        plugin = HOOKS_DIR.parent
        assert (plugin / ".claude-plugin" / "plugin.json").is_file()
        rules = policy(policy_world, write=[str(REPO_ROOT) + "/"])

        assert rules.verdict(str(plugin / "harnesses" / "claude" / "hooks.json"), "write") == "guarded"
        assert rules.verdict(str(REPO_ROOT / "tests" / "shared" / "notes.md"), "write") == "write-through"

    def test_a_hooks_directory_whose_parent_holds_no_manifest_adds_nothing(self, policy_world, tmp_path, monkeypatch):
        copy = tmp_path / "loose"
        shutil.copytree(HOOKS_DIR, copy / "hooks", ignore=shutil.ignore_patterns("__pycache__"))
        (copy / "registration.json").touch()
        spec = importlib.util.spec_from_file_location("loose_guarded_paths", copy / "hooks" / "guarded_paths.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        home, _, manifest = policy_world
        data = {
            name: {"paths": []} for name in ("guarded", "enforcement-floor", "block", "exec-through", "write-through")
        }
        data["write-through"]["paths"] = [str(copy) + "/"]
        data["exceptions"] = []
        rules = module.PathPolicy(data, home=str(home), manifest_path=manifest)

        assert rules.verdict(str(copy / "registration.json"), "write") == "write-through"
        assert rules.verdict(str(copy / "hooks" / "block-leaks.py"), "write") == "guarded"


class TestPluginInstallLocationGrants:
    def test_a_grant_over_an_install_location_does_not_reach_an_installed_hook(self, policy_world):
        """Validates: CarveOutOverAnInstalledCopy."""
        installed_plugin(policy_world)
        rules = install_location_policy(policy_world, write=[PLUGINS])
        hook = f"{INSTALLED}/hooks/block-leaks.py"

        assert rules.verdict(hook, "write") == "guarded"
        assert any("does not apply" in finding and "block-leaks.py" in finding for finding in rules.findings)

    def test_a_plugin_skill_script_runs_inside_the_floor(self, policy_world):
        """Validates: PluginSkillScriptRunsInsideTheFloor."""
        installed_plugin(policy_world)
        rules = install_location_policy(policy_world, run=[PLUGIN_SKILLS])

        assert rules.verdict(f"{INSTALLED}/skills/review/scripts/check.py", "run") == "exec-through"

    def test_a_write_to_a_plugin_skill_script_asks(self, policy_world):
        """Validates: PluginSkillScriptWriteInsideTheFloor."""
        installed_plugin(policy_world)
        rules = install_location_policy(policy_world, run=[PLUGIN_SKILLS], write=[PLUGIN_SKILLS])

        assert rules.verdict(f"{INSTALLED}/skills/review/scripts/check.py", "write") == "guarded"

    def test_session_start_reports_nothing_for_plugin_skill_directories(self, policy_world):
        installed_plugin(policy_world)
        rules = install_location_policy(policy_world, run=[PLUGIN_SKILLS])

        assert rules.validate() == []

    def test_an_exec_through_over_a_non_skill_directory_has_no_effect_inside_the_floor(self, policy_world):
        installed_plugin(policy_world)
        rules = install_location_policy(policy_world, run=["~/.claude/plugins/cache/*/*/*/hooks/"])

        assert rules.verdict(f"{INSTALLED}/hooks/block-leaks.py", "run") == "guarded"


class TestPluginInstallLocationRecords:
    def test_a_floor_record_marks_a_plugin_install_location(self, tmp_path):
        manifest = tmp_path / "guarded-paths.toml"
        manifest.write_text(
            '[[enforcement-floor.paths]]\npath = "~/.claude/plugins/"\nreason = "plugins"\nplugins = true\n'
            '[[enforcement-floor.paths]]\npath = "~/.claude/hooks/"\nreason = "hooks"\n'
        )

        floor = guarded_paths.load_manifest(manifest)["enforcement-floor"]

        assert floor == {"paths": ["~/.claude/plugins/", "~/.claude/hooks/"], "plugins": ["~/.claude/plugins/"]}

    def test_a_plugins_value_other_than_true_is_a_manifest_failure(self, tmp_path):
        manifest = tmp_path / "guarded-paths.toml"
        manifest.write_text(
            '[[enforcement-floor.paths]]\npath = "~/.claude/plugins/"\nreason = "plugins"\nplugins = "yes"\n'
        )

        with pytest.raises(ManifestError, match="plugins"):
            guarded_paths.load_manifest(manifest)

    def test_a_plugin_install_location_outside_the_floor_is_a_manifest_failure(self, policy_world):
        with pytest.raises(ManifestError, match="plugin install location"):
            policy(policy_world, floor=[], plugins=[PLUGINS])


def sentinel_checkout(root: Path) -> Path:
    """A checkout whose catalog names its one plugin by relative path."""
    checkout = root / "checkout"
    plugin = checkout / "plugins" / "sentinel"
    for relative in (".claude-plugin/plugin.json", "hooks/block-leaks.py", "skills/review/scripts/check.py"):
        (plugin / relative).parent.mkdir(parents=True, exist_ok=True)
        (plugin / relative).touch()
    (checkout / "tests").mkdir()
    (checkout / "tests" / "test_hooks.py").touch()
    (checkout / ".claude-plugin").mkdir()
    (checkout / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "local", "plugins": [{"name": "sentinel", "source": "./plugins/sentinel"}]})
    )
    return checkout


def write_record(home: Path, harness: str, checkout: Path) -> None:
    """Record `checkout` as loaded in place in `harness`'s user-level record."""
    directory = {"source": {"source": "directory", "path": str(checkout)}}
    records = {
        "claude": (
            ".claude/plugins/known_marketplaces.json",
            json.dumps({"local": {**directory, "installLocation": str(checkout)}}),
        ),
        "copilot": (".copilot/settings.json", json.dumps({"extraKnownMarketplaces": {"local": directory}})),
        # Relative to the settings file's directory, as Pi resolves it.
        "pi": (
            ".pi/agent/settings.json",
            json.dumps({"packages": [os.path.relpath(checkout, home / ".pi" / "agent")]}),
        ),
        # The plugin directory itself, with the comments and trailing commas VS Code accepts.
        "vscode": (
            ".config/Code/User/settings.json",
            '{\n  // local plugins\n  "chat.pluginLocations": {\n    "%s": true, /* sentinel */\n  },\n}\n'
            % (checkout / "plugins" / "sentinel"),
        ),
    }
    relative, text = records[harness]
    (home / relative).parent.mkdir(parents=True, exist_ok=True)
    (home / relative).write_text(text)


class TestInPlaceCopies:
    """Validates: InstalledEnforcementIsInTheFloor, for a copy a harness's records name as loaded in place."""

    @pytest.mark.parametrize("harness", ["claude", "copilot", "pi", "vscode"])
    def test_a_recorded_in_place_copy_is_floor(self, policy_world, tmp_path, harness):
        """Validates: AnotherHarnessesInPlaceCopyIsWritten."""
        home = policy_world[0]
        checkout = sentinel_checkout(tmp_path)
        write_record(home, harness, checkout)
        rules = policy(policy_world)

        assert rules.verdict(str(checkout / "plugins/sentinel/hooks/block-leaks.py"), "write") == "guarded"

    @pytest.mark.parametrize("harness", ["claude", "copilot", "pi", "vscode"])
    def test_the_rest_of_the_checkout_is_not_floor(self, policy_world, tmp_path, harness):
        """Validates: CheckoutOutsideThePluginDirectory."""
        home = policy_world[0]
        checkout = sentinel_checkout(tmp_path)
        write_record(home, harness, checkout)
        rules = policy(policy_world)

        assert rules.verdict(str(checkout / "tests/test_hooks.py"), "write") == "undeclared"

    def test_an_in_place_skill_script_runs_and_its_write_asks(self, policy_world, tmp_path):
        home = policy_world[0]
        checkout = sentinel_checkout(tmp_path)
        write_record(home, "claude", checkout)
        rules = policy(policy_world)
        script = str(checkout / "plugins/sentinel/skills/review/scripts/check.py")

        assert rules.verdict(script, "run") == "exec-through"
        assert rules.verdict(script, "write") == "guarded"

    @pytest.mark.parametrize("record", ["", "{not json"], ids=["missing", "unparsable"])
    def test_a_missing_or_unparsable_record_adds_nothing(self, policy_world, tmp_path, record):
        home = policy_world[0]
        checkout = sentinel_checkout(tmp_path)
        if record:
            (home / ".copilot").mkdir(parents=True, exist_ok=True)
            (home / ".copilot" / "settings.json").write_text(record)
        rules = policy(policy_world)

        assert rules.verdict(str(checkout / "plugins/sentinel/hooks/block-leaks.py"), "write") == "undeclared"

    def test_a_location_with_no_manifest_or_catalog_is_covered_whole(self, policy_world, tmp_path):
        home = policy_world[0]
        location = tmp_path / "loose"
        (location / "hooks").mkdir(parents=True)
        write_record(home, "copilot", location)
        rules = policy(policy_world)

        assert rules.verdict(str(location / "hooks" / "run.py"), "write") == "guarded"
