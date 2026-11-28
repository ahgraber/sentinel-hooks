"""Placeholder dotenv files are readable by declaration, and writes to them stay refused."""

from __future__ import annotations

import io
import json

from guarded_paths import MANIFEST_PATH, ManifestError, PathPolicy, load_manifest
from hermetic import load_hook
import pytest

SURFACE = "sensitive-path-dotenv-placeholder"


def _with_exception(pattern: str) -> dict:
    manifest = load_manifest(MANIFEST_PATH)
    manifest["exceptions"].append({"surface": SURFACE, "pattern": pattern, "reason": "a test placeholder"})
    return manifest


@pytest.mark.parametrize(
    "pattern",
    [
        "apps/.env.example",
        "~/.env.example",
        "<repo>/.env.example",
        ".env.*",
        ".env.ex?mple",
        "[.]env.example",
        "a\\.env",
        ".env",
        ".ENV",
        "README.md",
        ".env.example\n",
        ".env.{a,b}",
        ".env.$HOME",
    ],
)
def test_a_placeholder_exception_must_be_a_file_name(pattern):
    with pytest.raises(ManifestError, match="file name"):
        PathPolicy(_with_exception(pattern))


def test_a_bare_placeholder_name_validates():
    PathPolicy(_with_exception(".env.placeholder"))


def test_the_shipped_manifest_declares_exactly_the_placeholder_names():
    names = {e["pattern"] for e in load_manifest(MANIFEST_PATH)["exceptions"] if e["surface"] == SURFACE}
    assert names == {".env.example", ".env.op", ".env.sample", ".env.template"}


def _decision(hook, monkeypatch, capsys, tool: str, path: str, cwd: str) -> int:
    payload = {"tool_name": tool, "tool_input": {"file_path": path}, "cwd": cwd}
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    capsys.readouterr()
    return stopped.value.code


def test_a_placeholder_is_readable_through_the_read_tool(tmp_path, monkeypatch, capsys):
    hook = load_hook("block-sensitive-paths")
    assert _decision(hook, monkeypatch, capsys, "Read", "apps/web/.env.example", str(tmp_path)) == 0


@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_a_placeholder_write_is_refused(tool, tmp_path, monkeypatch, capsys):
    hook = load_hook("block-sensitive-paths")
    assert _decision(hook, monkeypatch, capsys, tool, "apps/web/.env.example", str(tmp_path)) == 2


def test_a_placeholder_linking_to_a_dotenv_file_is_refused(tmp_path):
    (tmp_path / ".env").touch()
    (tmp_path / ".env.example").symlink_to(tmp_path / ".env")
    hook = load_hook("block-sensitive-paths")
    assert hook.should_block(str(tmp_path / ".env.example"), reading=True)


def test_a_placeholder_inside_a_credential_directory_is_refused(tmp_path):
    hook = load_hook("block-sensitive-paths")
    assert hook.should_block(str(tmp_path / ".ssh/.env.example"), reading=True)


def test_a_placeholder_linking_to_a_dotenv_file_is_refused_in_bash(tmp_path):
    (tmp_path / ".env").touch()
    (tmp_path / "linked").mkdir()
    (tmp_path / "linked/.env.example").symlink_to(tmp_path / ".env")
    hook = load_hook("block-sensitive-paths")
    assert hook.bash_blocked_target("cat linked/.env.example", str(tmp_path))


def _bash_refusal_text(hook, monkeypatch, capsys, command: str, cwd: str) -> str:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    assert stopped.value.code == 2
    return capsys.readouterr().err


def test_a_placeholder_read_refused_for_its_form_names_the_reads_that_proceed(tmp_path, monkeypatch, capsys):
    hook = load_hook("block-sensitive-paths")
    err = _bash_refusal_text(hook, monkeypatch, capsys, "sed -n 1p .env.example", str(tmp_path))
    assert "placeholder dotenv file" in err
    assert "writing to it is refused" in err
    assert "Recognized reads use: " in err
    assert "Reading this path is allowed with the commands listed above." in err
    assert "Do NOT attempt" not in err
    assert "Existing scripts can run" not in err


@pytest.mark.parametrize(
    "command",
    [
        "echo x > .env.example",
        "cat .env.local",
        "sed -n 1p .env.local",
        "sed -n 1p .env.example .env.local",
        "sed -n 1p .env.example; cat .env.local",
    ],
)
def test_a_refusal_the_policy_makes_keeps_the_stop_form(command, tmp_path, monkeypatch, capsys):
    hook = load_hook("block-sensitive-paths")
    err = _bash_refusal_text(hook, monkeypatch, capsys, command, str(tmp_path))
    assert "Do NOT attempt" in err
    assert "Recognized reads use" not in err


def test_a_placeholder_linking_to_a_dotenv_file_keeps_the_stop_form(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env").touch()
    (tmp_path / ".env.example").symlink_to(tmp_path / ".env")
    hook = load_hook("block-sensitive-paths")
    err = _bash_refusal_text(hook, monkeypatch, capsys, "sed -n 1p .env.example", str(tmp_path))
    assert "Do NOT attempt" in err
