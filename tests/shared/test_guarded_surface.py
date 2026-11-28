"""Exercise the real declarations in a temporary home and repository."""

import io
import json
from pathlib import Path

from guarded_paths import GuardedLocations, PathPolicy, load_manifest
from hermetic import build_world, install_policy, load_hook
import pytest

MANIFEST = load_manifest()


@pytest.mark.parametrize("agent", [".claude", ".codex", ".copilot"])
def test_deployed_hook_cannot_be_carved_out(surface, agent):
    home, repo, _ = surface
    hook = home / agent / "hooks/local.py"
    hook.parent.mkdir(parents=True)
    hook.touch()
    data = {**MANIFEST, "write-through": {"paths": [f"~/{agent}/hooks/"]}}
    policy = PathPolicy(
        data,
        home=str(home),
        manifest_path=repo / "plugins/sentinel/hooks/guarded-paths.toml",
    )
    assert policy.verdict(str(hook), "write") == "guarded"
    assert any("does not apply" in finding for finding in policy.findings)


@pytest.fixture
def surface(tmp_path, monkeypatch):
    """The real declarations, judged in a temporary home and repository.

    The manifest sits at its path in the repository's plugin directory.
    """
    home, repo, manifest_path = build_world(tmp_path, monkeypatch, "plugins/sentinel/hooks")
    policy = PathPolicy(MANIFEST, home=str(home), manifest_path=manifest_path)
    hook = load_hook("block-hook-tampering")
    install_policy(monkeypatch, hook, policy)
    return home, repo, hook


def representative(declaration, home, repo):
    path = declaration.replace("~/", str(home) + "/", 1)
    path = path.replace("<repo>/", str(repo) + "/", 1).replace("<project>/", str(repo) + "/", 1)
    path = path.replace("*", "example")
    return path + "example.txt" if path.endswith("/") else path


@pytest.mark.parametrize(
    ("class_name", "declaration"),
    [
        (name, path)
        for name in ("guarded", "enforcement-floor", "block", "exec-through", "write-through")
        for path in MANIFEST[name]["paths"]
    ],
)
@pytest.mark.parametrize("tool", ["Read", "Write"])
def test_each_declaration_through_hook(surface, monkeypatch, capsys, class_name, declaration, tool):
    home, repo, hook = surface
    path = representative(declaration, home, repo)
    payload = {
        "tool_name": tool,
        "tool_input": {"file_path": path},
        "cwd": str(repo),
        "transcript_path": "/tmp/transcript.jsonl",
    }
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    captured = capsys.readouterr()
    if class_name == "block":
        assert stopped.value.code == 2
    elif tool == "Read" or class_name == "write-through":
        assert stopped.value.code == 0
        assert captured.out == ""
    else:
        assert stopped.value.code == 0
        assert json.loads(captured.out)["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_source_in_another_worktree(surface, tmp_path):
    _, _, hook = surface
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /unused")
    source = worktree / ".codex/rules/example.rules"
    source.parent.mkdir(parents=True)
    assert hook.protected_class(str(source)) == "guarded"
    assert hook.protected_class(str(worktree / ".codex/notes.md")) is None


@pytest.mark.parametrize("root", MANIFEST["exec-through"]["paths"])
def test_skill_runs_directly_and_through_link(surface, root):
    """Validates: SkillScriptRun and SkillContentWrite, for each skills root and each plugin layout's skill directories."""
    home, repo, hook = surface
    script = Path(representative(root, home, repo)).with_suffix(".py")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.touch()
    alias = home / "alias.py"
    alias.symlink_to(script)
    for path in (script, alias):
        assert hook.command_protected_class(f"python {path}", str(repo)) is None
        assert hook.protected_class(str(path)) == "guarded"


def test_real_manifest_has_no_findings_in_the_declared_world(surface):
    _, _, hook = surface
    assert hook.POLICY.validate() == []


# Sentinel's plugin directory as each harness installs it.
INSTALLED_COPIES = {
    "claude": "~/.claude/plugins/cache/sentinel-hooks/sentinel/0.1.0/",
    "codex": "~/.codex/plugins/cache/sentinel-hooks/sentinel/0.1.0/",
    "copilot": "~/.copilot/installed-plugins/sentinel-hooks/sentinel/",
    "vscode": "~/.vscode/agent-plugins/github.com/ahgraber/sentinel-hooks/plugins/sentinel/",
    "pi-git": "~/.pi/agent/git/github.com/ahgraber/sentinel-hooks/plugins/sentinel/",
    "pi-npm": "~/.pi/agent/npm/node_modules/sentinel-hooks/plugins/sentinel/",
}
OTHER_PLUGIN = "~/.codex/plugins/cache/market/other/1.0.0/"


def installed(home, copy: str, relative: str) -> Path:
    """Create `relative` in an installed plugin directory under `home`."""
    path = home / copy.removeprefix("~/") / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def claude_call(hook, monkeypatch, capsys, repo, tool: str, tool_input: dict) -> tuple[int, str]:
    """Run the hook on one Claude Code tool call; return its exit code and output."""
    payload = {
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": str(repo),
        "transcript_path": "/tmp/transcript.jsonl",
    }
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    return stopped.value.code, capsys.readouterr().out


def asks(result: tuple[int, str]) -> bool:
    code, out = result
    return code == 0 and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "ask"


class TestInstalledEnforcement:
    """The real declarations over plugins installed in a temporary home, judged in a Claude Code session."""

    @pytest.mark.parametrize("harness", sorted(INSTALLED_COPIES))
    def test_a_write_to_each_harnesses_installed_copy_asks(self, surface, monkeypatch, capsys, harness):
        """Validates: AnotherHarnessesCopyIsWritten."""
        home, repo, hook = surface
        target = installed(home, INSTALLED_COPIES[harness], "hooks/block-leaks.py")
        assert asks(claude_call(hook, monkeypatch, capsys, repo, "Write", {"file_path": str(target), "content": "x"}))

    def test_a_write_to_another_plugins_file_asks(self, surface, monkeypatch, capsys):
        """Validates: AnotherPluginsFileIsWritten."""
        home, repo, hook = surface
        target = installed(home, OTHER_PLUGIN, "scripts/tool.py")
        assert asks(claude_call(hook, monkeypatch, capsys, repo, "Write", {"file_path": str(target), "content": "x"}))

    def test_a_plugin_skill_script_runs(self, surface, monkeypatch, capsys):
        """Validates: PluginSkillScriptRuns."""
        home, repo, hook = surface
        script = installed(home, OTHER_PLUGIN, "skills/review/scripts/check.py")
        assert claude_call(hook, monkeypatch, capsys, repo, "Bash", {"command": f"python {script}"}) == (0, "")

    @pytest.mark.parametrize("harness", sorted(INSTALLED_COPIES))
    def test_a_read_of_an_installed_copy_proceeds(self, surface, monkeypatch, capsys, harness):
        """Validates: InstalledCopyIsRead."""
        home, repo, hook = surface
        target = installed(home, INSTALLED_COPIES[harness], "hooks/block-leaks.py")
        assert claude_call(hook, monkeypatch, capsys, repo, "Read", {"file_path": str(target)}) == (0, "")


RENDERER = "<repo>/scripts/render-secrets.sh"


@pytest.fixture
def sensitive(monkeypatch):
    """The sensitive-path hook with one name-heuristic exception declared for `RENDERER`."""
    hook = load_hook("block-sensitive-paths")
    monkeypatch.setattr(hook, "NAME_HEURISTIC_EXCEPTIONS", GuardedLocations([RENDERER]))
    return hook


@pytest.fixture
def renderer(tmp_path):
    """The excepted file, in a checkout."""
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    path = tmp_path / "repo" / RENDERER.removeprefix("<repo>/")
    path.parent.mkdir()
    path.touch()
    return path


def test_declared_exception_is_readable(sensitive, renderer):
    assert not sensitive.should_block(str(renderer))


def test_exception_does_not_travel_along_a_link(sensitive, renderer, tmp_path):
    """The exception covers the spelling it names; a link named for secrets is judged by its own name."""
    (tmp_path / "deploy-secrets.sh").symlink_to(renderer)
    (tmp_path / "plainname.sh").symlink_to(renderer)
    assert sensitive.should_block(str(tmp_path / "deploy-secrets.sh"))
    assert not sensitive.should_block(str(tmp_path / "plainname.sh"))


def test_exception_covers_the_declared_file_alone(sensitive, tmp_path):
    """A file outside any checkout that shares the declared name and tail is not excused."""
    elsewhere = tmp_path / "unrelated/scripts/render-secrets.sh"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.touch()
    assert sensitive.should_block(str(elsewhere))
