"""Session checks report manifest failures and shell assumptions."""

import json
import os
import shutil
import subprocess

from hermetic import HOOKS_DIR, dump_manifest, manifest_floor
import pytest


@pytest.fixture
def session(tmp_path):
    hooks = tmp_path / "hooks"
    shutil.copytree(HOOKS_DIR, hooks)
    home = tmp_path / "home"
    home.mkdir()
    data = {
        "guarded": {"paths": ["~/guarded/"]},
        "enforcement-floor": {"paths": manifest_floor()},
        "block": {"paths": []},
        "exec-through": {"paths": []},
        "write-through": {"paths": []},
        "exceptions": [],
    }
    return hooks, home, data


def run_session(session, agent="claude", pin=None, defect=None):
    hooks, home, data = session
    manifest = hooks / "guarded-paths.toml"
    manifest.write_text(dump_manifest(data) if data["exceptions"] else "exceptions = []\n" + dump_manifest(data))
    if defect == "absent":
        manifest.unlink()
    elif defect == "unparsable":
        manifest.write_text("invalid [toml")
    elif defect == "missing-table":
        manifest.write_text("exceptions = []")
    env = {**os.environ, "HOME": str(home), "AI_HOOK_AGENT": agent}
    env.pop("CLAUDE_CODE_SHELL", None)
    if pin is not None:
        env["CLAUDE_CODE_SHELL"] = pin
    return subprocess.run(
        ["bash", str(hooks / "session-tool-checks.sh")],
        input=json.dumps({"hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=env,
    )


@pytest.mark.parametrize("pin", [None, "/bin/zsh", "/absent/bash"])
def test_bad_shell_pin_warns(session, pin):
    result = run_session(session, pin=pin)

    assert result.returncode == 0
    assert "CLAUDE_CODE_SHELL" in result.stderr
    assert "Set it to a bash" in result.stderr
    assert "/bin/bash" not in result.stderr


@pytest.mark.parametrize("agent", ["codex", "copilot"])
def test_other_agents_do_not_check_claude_shell(session, agent):
    result = run_session(session, agent=agent)

    assert result.returncode == 0
    assert "CLAUDE_CODE_SHELL" not in result.stderr


def test_valid_manifest_and_pin_are_silent(session):
    result = run_session(session, pin="/bin/bash")

    assert result.returncode == 0
    # Optional-tool warnings depend on the host; only the policy checks are judged.
    for marker in ("CLAUDE_CODE_SHELL", "guarded-paths.toml", "grant", "Error"):
        assert marker not in result.stderr


@pytest.mark.parametrize("defect", ["absent", "unparsable", "missing-table"])
def test_unloadable_manifest_reports_error(session, defect):
    result = run_session(session, pin="/bin/bash", defect=defect)

    assert result.returncode == 2
    assert "guarded-paths.toml" in result.stderr
    assert "mutating calls" in result.stderr.lower()


def test_enforcement_carve_out_warns(session):
    hooks, _, data = session
    data["write-through"]["paths"] = [str(hooks) + "/"]

    result = run_session(session, pin="/bin/bash")

    assert result.returncode == 0
    assert "write-through grant" in result.stderr
    assert "does not apply to enforcement floor path" in result.stderr


def test_link_into_stricter_target_warns(session):
    _, home, data = session
    (home / "memory").mkdir()
    (home / "memory/link").symlink_to(home / "guarded/file")
    data["write-through"]["paths"] = ["~/memory/"]

    result = run_session(session, pin="/bin/bash")

    assert result.returncode == 0
    assert "guarded/file" in result.stderr


def test_a_shell_warning_is_still_reported_when_the_manifest_cannot_be_loaded(session):
    result = run_session(session, pin="/bin/zsh", defect="unparsable")

    assert result.returncode == 2
    assert "CLAUDE_CODE_SHELL is /bin/zsh" in result.stderr
    assert "guarded-paths.toml could not be loaded" in result.stderr


def test_a_floor_file_with_a_defect_is_reported_and_the_session_proceeds(session):
    hooks, _, _ = session
    (hooks / "configuration-floor.toml").write_text('plugin = "sentinel"\n')

    result = run_session(session, pin="/bin/bash")

    assert result.returncode == 0
    assert "configuration-floor.toml could not be read: the floor has no `package`" in result.stderr
