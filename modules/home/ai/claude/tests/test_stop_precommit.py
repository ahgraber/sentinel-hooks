"""Tests for stop-precommit.sh, the end-of-turn pre-commit hook."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import HookResult

HOOK_PATH = Path(__file__).parents[2] / "shared" / "hooks" / "stop-precommit.sh"

RUNNER = (
    "prek"
    if shutil.which("prek")
    else "pre-commit"
    if shutil.which("pre-commit")
    else None
)

requires_runner = pytest.mark.skipif(
    RUNNER is None, reason="neither prek nor pre-commit is on PATH"
)

# A hook that always passes, so a clean run stays silent.
PASSING_CONFIG = """repos:
  - repo: local
    hooks:
      - id: noop
        name: noop
        language: system
        entry: "true"
"""


# A hook scoped to one filename, so tests can prove which paths reach the runner.
def _rejecting_config(filename: str) -> str:
    return f"""repos:
  - repo: local
    hooks:
      - id: reject-target
        name: reject-target
        language: system
        entry: "false"
        files: ^{filename}$
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_git_repo(path: Path, config: str | None = None) -> Path:
    """Initialize a git repo with one commit, optionally with a pre-commit config."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    for key, value in (
        ("user.email", "testuser@example.com"),
        ("user.name", "Test User"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(
            ["git", "-C", str(path), "config", key, value],
            check=True,
            capture_output=True,
        )
    if config is not None:
        (path / ".pre-commit-config.yaml").write_text(config)
    (path / "tracked.txt").write_text("init\n")
    subprocess.run(
        ["git", "-C", str(path), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return path


def _run_hook(
    cwd: Path, *, stop_hook_active: bool = False, run_cwd: Path | None = None
) -> HookResult:
    """Run the Stop hook with a payload rooted at the given directory.

    run_cwd sets the process working directory, which the hook falls back to when
    the payload's cwd does not resolve.
    """
    payload = {
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        "cwd": str(cwd),
    }
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        cwd=str(run_cwd) if run_cwd else None,
    )
    return HookResult(
        exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr
    )


def _assert_silent(result: HookResult) -> None:
    assert result.exit_code == 0, (
        f"Expected exit 0, got {result.exit_code}.\nstderr: {result.stderr}"
    )
    assert result.stderr.strip() == "", f"Expected no stderr, got: {result.stderr}"


# ---------------------------------------------------------------------------
# Early returns
# ---------------------------------------------------------------------------


class TestEarlyReturns:
    def test_loop_guard_skips_run(self, tmp_path):
        """stop_hook_active caps the agent at one blocking round."""
        repo = _create_git_repo(tmp_path / "repo", _rejecting_config("tracked.txt"))
        (repo / "tracked.txt").write_text("changed\n")

        _assert_silent(_run_hook(repo, stop_hook_active=True))

    def test_non_git_directory_is_a_no_op(self, tmp_path):
        _assert_silent(_run_hook(tmp_path))

    def test_unresolvable_payload_cwd_falls_back_to_the_process_directory(
        self, tmp_path
    ):
        """A missing cwd must not crash the hook or escape to an unrelated repo."""
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()

        _assert_silent(_run_hook(tmp_path / "does-not-exist", run_cwd=elsewhere))

    def test_repo_without_precommit_config_is_a_no_op(self, tmp_path):
        repo = _create_git_repo(tmp_path / "repo")
        (repo / "tracked.txt").write_text("changed\n")

        _assert_silent(_run_hook(repo))

    def test_repo_without_changes_is_a_no_op(self, tmp_path):
        repo = _create_git_repo(tmp_path / "repo", _rejecting_config("tracked.txt"))

        _assert_silent(_run_hook(repo))


# ---------------------------------------------------------------------------
# Which files reach the runner
# ---------------------------------------------------------------------------


@requires_runner
class TestChangedFileSet:
    def test_passing_run_stays_silent(self, tmp_path):
        repo = _create_git_repo(tmp_path / "repo", PASSING_CONFIG)
        (repo / "tracked.txt").write_text("changed\n")
        (repo / "untracked.txt").write_text("new\n")

        _assert_silent(_run_hook(repo))

    def test_modified_tracked_file_reaches_the_runner(self, tmp_path):
        repo = _create_git_repo(tmp_path / "repo", _rejecting_config("tracked.txt"))
        (repo / "tracked.txt").write_text("changed\n")

        result = _run_hook(repo)

        assert result.exit_code == 2
        assert "reject-target" in result.stderr

    def test_untracked_file_reaches_the_runner(self, tmp_path):
        """git ls-files --others feeds the runner, not just the tracked diff."""
        repo = _create_git_repo(tmp_path / "repo", _rejecting_config("untracked.txt"))
        (repo / "untracked.txt").write_text("new\n")

        result = _run_hook(repo)

        assert result.exit_code == 2
        assert "reject-target" in result.stderr

    def test_staged_file_reaches_the_runner(self, tmp_path):
        """diff against HEAD covers staged changes, not just the work tree."""
        repo = _create_git_repo(tmp_path / "repo", _rejecting_config("staged.txt"))
        (repo / "staged.txt").write_text("staged\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "staged.txt"],
            check=True,
            capture_output=True,
        )

        result = _run_hook(repo)

        assert result.exit_code == 2
        assert "reject-target" in result.stderr

    def test_ignored_file_is_excluded(self, tmp_path):
        """--exclude-standard keeps gitignored files out of the set."""
        repo = _create_git_repo(tmp_path / "repo", _rejecting_config("ignored.txt"))
        (repo / ".gitignore").write_text("ignored.txt\n")
        (repo / "ignored.txt").write_text("noise\n")

        result = _run_hook(repo)

        assert result.exit_code == 0, (
            f"An ignored file reached the runner.\nstderr: {result.stderr}"
        )

    def test_deleted_file_is_excluded(self, tmp_path):
        """--diff-filter=d drops deletions, which the runner cannot open."""
        repo = _create_git_repo(tmp_path / "repo", PASSING_CONFIG)
        (repo / "tracked.txt").unlink()

        result = _run_hook(repo)

        assert result.exit_code == 0, (
            f"A deleted path reached the runner.\nstderr: {result.stderr}"
        )

    def test_repo_without_head_uses_the_staged_diff(self, tmp_path):
        """A repo with no commits still resolves a file set."""
        repo = tmp_path / "fresh"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        (repo / ".pre-commit-config.yaml").write_text(_rejecting_config("staged.txt"))
        (repo / "staged.txt").write_text("staged\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "staged.txt"],
            check=True,
            capture_output=True,
        )

        result = _run_hook(repo)

        assert result.exit_code == 2
        assert "reject-target" in result.stderr


# ---------------------------------------------------------------------------
# Failure reporting
# ---------------------------------------------------------------------------


@requires_runner
class TestFailureContract:
    def test_failure_blocks_the_stop_and_explains_itself(self, tmp_path):
        repo = _create_git_repo(tmp_path / "repo", _rejecting_config("tracked.txt"))
        (repo / "tracked.txt").write_text("changed\n")

        result = _run_hook(repo)

        assert result.exit_code == 2, "A failing run must block the stop"
        assert "reject-target" in result.stderr, "Runner output must reach the agent"
        assert "re-read those files" in result.stderr, (
            "The agent must be told its in-context copies may be stale"
        )
