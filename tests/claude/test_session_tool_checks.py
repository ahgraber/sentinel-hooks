"""Tests for the tool-availability gate in the session-tool-checks.sh hook."""

import functools
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from conftest import HOOKS_DIR

HOOK_PATH = str(HOOKS_DIR / "session-tool-checks.sh")
_STUBS = tempfile.TemporaryDirectory()


@functools.cache
def _stub_dir(name: str) -> str:
    """A directory holding only a stub executable `name` that does nothing, or nothing when `name` is empty.

    Each stub is written once per module and run once here: macOS checks a new
    executable on its first run, and the check can take several seconds, which
    would count against the hook's time limit.
    """
    directory = Path(_STUBS.name) / (name or "empty")
    directory.mkdir()
    if name:
        stub = directory / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
        subprocess.run([str(stub)], timeout=120, check=True)
    return str(directory)


def run_session_hook(available_tools: list[str], extra_path: str = "") -> subprocess.CompletedProcess:
    """Run the hook with only the named tools resolvable on PATH, as stubs."""
    path = ":".join(_stub_dir(tool) for tool in available_tools or [""])
    if extra_path:
        path = f"{path}:{extra_path}"

    # PATH holds only the stubs, so bash must be invoked by absolute path.
    bash_path = shutil.which("bash")
    env = {
        "PATH": path,
        "HOME": os.environ.get("HOME", "/tmp"),
    }

    return subprocess.run(
        [bash_path, HOOK_PATH],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        check=False,
    )


class TestAllToolsPresent:
    def test_all_tools_present(self):
        result = run_session_hook(["uv", "jq", "perl", "gitleaks"])
        assert result.returncode == 0
        assert result.stderr == ""

    def test_all_required_gitleaks_missing(self):
        """gitleaks is recommended, not required — should warn but exit 0."""
        result = run_session_hook(["uv", "jq", "perl"])
        assert result.returncode == 0
        assert "gitleaks" in result.stderr


class TestMissingRequired:
    def test_missing_uv(self):
        result = run_session_hook(["jq", "perl", "gitleaks"])
        assert result.returncode == 2
        assert "uv" in result.stderr

    def test_missing_jq(self):
        result = run_session_hook(["uv", "perl", "gitleaks"])
        assert result.returncode == 2
        assert "jq" in result.stderr

    def test_missing_perl(self):
        result = run_session_hook(["uv", "jq", "gitleaks"])
        assert result.returncode == 2
        assert "perl" in result.stderr


class TestCheckOrder:
    def test_uv_checked_first(self):
        """With no tools at all, uv should be the first error."""
        result = run_session_hook([])
        assert result.returncode == 2
        assert "uv" in result.stderr

    def test_jq_checked_after_uv(self):
        """With only uv, jq should be next."""
        result = run_session_hook(["uv"])
        assert result.returncode == 2
        assert "jq" in result.stderr

    def test_perl_checked_after_jq(self):
        """With uv and jq, perl should be next."""
        result = run_session_hook(["uv", "jq"])
        assert result.returncode == 2
        assert "perl" in result.stderr
