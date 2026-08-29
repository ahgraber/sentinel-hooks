"""Tests for the tool-availability gate in the session-tool-checks.sh hook."""

import os
import shutil
import subprocess

HOOK_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    os.pardir,
    "shared",
    "hooks",
    "session-tool-checks.sh",
)


def _make_stub_bin(bin_dir: str, name: str) -> None:
    """Create a stub executable that does nothing."""
    stub = os.path.join(bin_dir, name)
    with open(stub, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(stub, 0o755)


def run_session_hook(
    available_tools: list[str], extra_path: str = ""
) -> subprocess.CompletedProcess:
    """Run the hook with only the named tools resolvable on PATH, as stubs."""
    import tempfile

    with tempfile.TemporaryDirectory() as bin_dir:
        for tool in available_tools:
            _make_stub_bin(bin_dir, tool)

        path = bin_dir
        if extra_path:
            path = f"{bin_dir}:{extra_path}"

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
