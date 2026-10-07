"""Grants permit content changes without permitting changes to enforcement."""

import io
import json

from guarded_paths import PathPolicy
from hermetic import build_world, install_policy, load_hook, policy
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
        "~/.pi/agent/shared-hooks/hook-dispatch.py",
        "~/.pi/agent/extensions/hooks/extension.ts",
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
    [".claude/settings.local.json", ".codex/config.toml", ".vscode/settings.json"],
)
def test_project_permission_settings_are_floor_without_git(policy_world, relative):
    home, _, _ = policy_world
    project = home / "project"
    rules = policy(policy_world, write=[str(project) + "/"])
    assert rules.verdict(str(project / relative), "write", cwd=str(project)) == "guarded"
    assert rules.verdict(str(project / "notes"), "write") == "write-through"


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
    home, repo, manifest = policy_world
    launch = home / "custom-agent/hooks/guard.py"
    launch.parent.mkdir(parents=True)
    launch.touch()
    data = {name: {"paths": []} for name in ("guarded", "block", "exec-through", "write-through")}
    data["write-through"]["paths"] = [str(launch.parent) + "/"]
    data["exceptions"] = []
    rules = PathPolicy(
        data,
        home=str(home),
        repo_root=str(repo),
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
