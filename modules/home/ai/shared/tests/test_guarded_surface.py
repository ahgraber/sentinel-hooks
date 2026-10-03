"""Exercise the real declarations in a temporary home and repository."""

import io
import json
from pathlib import Path

from guarded_paths import PathPolicy, load_manifest
from hermetic import build_world, install_policy, load_hook
import pytest

MANIFEST = load_manifest()
REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "flake.nix").is_file())


def test_per_user_editor_settings_source_is_guarded(surface):
    _, repo, hook = surface
    source = repo / "users/example/home-manager/vscode/settings.json"
    assert hook.protected_class(str(source)) == "guarded"


@pytest.mark.parametrize("agent", ["claude", "codex", "copilot"])
def test_end_of_turn_hook_source_reaches_each_agent_gate(tmp_path, monkeypatch, capsys, agent):
    home = tmp_path / "home"
    home.mkdir()
    source = REPO_ROOT / "modules/home/ai/claude/hooks/clean-cc-writes.sh"
    assert source.is_file()

    policy = PathPolicy(
        MANIFEST,
        home=str(home),
        repo_root=str(REPO_ROOT),
        manifest_path=REPO_ROOT / "modules/home/ai/shared/hooks/guarded-paths.toml",
    )
    hook = load_hook("block-hook-tampering")
    install_policy(monkeypatch, hook, policy)
    monkeypatch.setenv("AI_HOOK_AGENT", agent)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(source)},
        "cwd": str(REPO_ROOT),
    }
    if agent == "claude":
        payload["transcript_path"] = "/tmp/transcript.jsonl"
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))

    with pytest.raises(SystemExit) as stopped:
        hook.main()

    captured = capsys.readouterr()
    if agent in {"claude", "copilot"}:
        assert stopped.value.code == 0
        assert json.loads(captured.out)["hookSpecificOutput"]["permissionDecision"] == "ask"
    else:
        assert stopped.value.code == 2
        assert "clean-cc-writes" in captured.err


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
        repo_root=str(repo),
        manifest_path=repo / "modules/home/ai/shared/hooks/guarded-paths.toml",
    )
    assert policy.verdict(str(hook), "write") == "guarded"
    assert any("does not apply" in finding for finding in policy.findings)


@pytest.fixture
def surface(tmp_path, monkeypatch):
    """The real declarations, judged in a temporary home and repository.

    The manifest sits at its repository path, so a declared repository source
    is told apart from the enforcement set the loader walks beside it.
    """
    home, repo, manifest_path = build_world(tmp_path, monkeypatch, "modules/home/ai/shared/hooks")
    policy = PathPolicy(MANIFEST, home=str(home), repo_root=str(repo), manifest_path=manifest_path)
    hook = load_hook("block-hook-tampering")
    install_policy(monkeypatch, hook, policy)
    return home, repo, hook


def representative(declaration, home, repo):
    path = declaration.replace("~/", str(home) + "/", 1).replace("<repo>/", str(repo) + "/", 1)
    path = path.replace("*", "example")
    return path + "example.txt" if path.endswith("/") else path


@pytest.mark.parametrize(
    ("class_name", "declaration"),
    [
        (name, path)
        for name in ("guarded", "block", "exec-through", "write-through")
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
    source = worktree / "modules/home/ai/shared/hooks/example.py"
    source.parent.mkdir(parents=True)
    assert hook.protected_class(str(source)) == "guarded"
    assert hook.protected_class(str(worktree / "modules/home/ai/shared/default.nix")) is None


@pytest.mark.parametrize("root", MANIFEST["exec-through"]["paths"])
def test_skill_runs_directly_and_through_link(surface, root):
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


def test_renderer_is_readable(surface):
    _, repo, _ = surface
    sensitive = load_hook("block-sensitive-paths")
    assert not sensitive.should_block(str(repo / "scripts/mcp-secrets.sh"))


def test_exception_does_not_travel_along_a_link(surface, tmp_path):
    """The exception covers the spelling it names; a link named for secrets is judged by its own name."""
    _, repo, _ = surface
    renderer = repo / "scripts/mcp-secrets.sh"
    renderer.parent.mkdir(parents=True, exist_ok=True)
    renderer.touch()
    (tmp_path / "deploy-secrets.sh").symlink_to(renderer)
    (tmp_path / "plainname.sh").symlink_to(renderer)
    sensitive = load_hook("block-sensitive-paths")
    assert sensitive.should_block(str(tmp_path / "deploy-secrets.sh"))
    assert not sensitive.should_block(str(tmp_path / "plainname.sh"))


def test_exception_covers_the_declared_file_alone(tmp_path):
    """A file outside any checkout that shares the declared name and tail is not excused."""
    elsewhere = tmp_path / "unrelated/scripts/mcp-secrets.sh"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.touch()
    assert load_hook("block-sensitive-paths").should_block(str(elsewhere))
