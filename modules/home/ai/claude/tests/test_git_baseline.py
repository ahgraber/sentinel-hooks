"""Tests for git-baseline.sh HEAD drift detection hook."""

import json
import os
from pathlib import Path
import subprocess

from conftest import HookResult
import pytest

HOOK_PATH = Path(__file__).parents[2] / "shared" / "hooks" / "git-baseline.sh"


def _create_git_repo(path: Path) -> Path:
    """Initialize a git repo with one commit at the given path."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "testuser@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "commit.gpgsign", "false"],
        check=True,
        capture_output=True,
    )
    (path / "file.txt").write_text("init")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return path


def _get_head(repo: Path) -> str:
    """Return the current HEAD SHA of a git repo."""
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _get_branch(repo: Path) -> str:
    """Return the abbreviated HEAD ref (branch name) of a git repo."""
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_commit(repo: Path) -> str:
    """Append a commit to the repo and return the new HEAD SHA."""
    counter_file = repo / ".counter"
    count = int(counter_file.read_text()) + 1 if counter_file.exists() else 1
    counter_file.write_text(str(count))
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", f"change {count}"],
        check=True,
        capture_output=True,
    )
    return _get_head(repo)


def run_baseline(
    stage: str,
    *,
    session_id: str = "test-session-1",
    cwd: Path | None = None,
    tool_name: str | None = None,
    stdin_text: str | None = None,
) -> HookResult:
    """Run git-baseline.sh with the given stage and JSON payload."""
    if stdin_text is None:
        payload: dict = {"session_id": session_id}
        if cwd is not None:
            payload["cwd"] = str(cwd)
        if tool_name is not None:
            payload["tool_name"] = tool_name
        stdin_text = json.dumps(payload)

    env = os.environ.copy()
    env.pop("GIT_DIR", None)

    result = subprocess.run(
        ["bash", str(HOOK_PATH), stage],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )
    return HookResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with one commit."""
    return _create_git_repo(tmp_path / "repo")


class TestSessionIdSafety:
    """Baseline filenames are derived from the session ID and scoped to one GIT_DIR."""

    def test_alphanumeric_id_unchanged_in_filename(self, git_repo: Path) -> None:
        """Alphanumeric session ID is used as-is in the baseline filename."""
        session_id = "abc123-XYZ"
        run_baseline("init", session_id=session_id, cwd=git_repo)
        assert (git_repo / ".git" / f"agent-baseline-{session_id}").exists()

    def test_special_chars_replaced_with_dashes(self, git_repo: Path) -> None:
        """Session ID with special characters has those characters replaced by dashes."""
        run_baseline("init", session_id="abc/def.ghi@jkl", cwd=git_repo)
        assert (git_repo / ".git" / "agent-baseline-abc-def-ghi-jkl").exists()

    def test_two_session_ids_produce_distinct_filenames(self, git_repo: Path) -> None:
        """Two distinct session IDs produce two distinct baseline files under the same GIT_DIR."""
        run_baseline("init", session_id="session-alpha", cwd=git_repo)
        run_baseline("init", session_id="session-beta", cwd=git_repo)
        assert (git_repo / ".git" / "agent-baseline-session-alpha").exists()
        assert (git_repo / ".git" / "agent-baseline-session-beta").exists()

    def test_two_worktrees_produce_distinct_paths(self, tmp_path: Path) -> None:
        """Two distinct GIT_DIR values produce baseline paths within their respective directories."""
        repo_a = _create_git_repo(tmp_path / "repo_a")
        repo_b = _create_git_repo(tmp_path / "repo_b")
        session_id = "shared-session"
        run_baseline("init", session_id=session_id, cwd=repo_a)
        run_baseline("init", session_id=session_id, cwd=repo_b)
        baseline_a = repo_a / ".git" / f"agent-baseline-{session_id}"
        baseline_b = repo_b / ".git" / f"agent-baseline-{session_id}"
        assert baseline_a.exists()
        assert baseline_b.exists()
        assert baseline_a.resolve() != baseline_b.resolve()


class TestBaselineCapture:
    """The init stage records HEAD in a git repo and does nothing outside one."""

    def test_init_writes_head_sha_in_git_repo(self, git_repo: Path) -> None:
        """init stage writes the current HEAD SHA to the baseline file."""
        head = _get_head(git_repo)
        run_baseline("init", session_id="cap-test", cwd=git_repo)
        baseline = git_repo / ".git" / "agent-baseline-cap-test"
        assert baseline.exists()
        assert baseline.read_text() == head

    def test_init_exits_silently_in_non_git_directory(self, tmp_path: Path) -> None:
        """init stage exits 0 with no file written when the directory is not a git repo."""
        non_git = tmp_path / "not-a-repo"
        non_git.mkdir()
        result = run_baseline("init", session_id="no-git", cwd=non_git)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert list(tmp_path.rglob("agent-baseline-*")) == []


class TestDriftWarning:
    """The check stage is silent unless HEAD has moved off the session baseline."""

    def test_check_silent_when_head_matches_baseline(self, git_repo: Path) -> None:
        """check stage exits 0 with no output when HEAD matches the session baseline."""
        run_baseline("init", session_id="drift-none", cwd=git_repo)
        result = run_baseline("check", session_id="drift-none", cwd=git_repo)
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_check_emits_context_when_head_has_moved(self, git_repo: Path) -> None:
        """check stage outputs JSON additionalContext with old SHA, new SHA, and branch when HEAD drifted."""
        run_baseline("init", session_id="drift-detect", cwd=git_repo)
        baseline_sha = _get_head(git_repo)
        new_sha = _make_commit(git_repo)
        branch = _get_branch(git_repo)

        result = run_baseline("check", session_id="drift-detect", cwd=git_repo)

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        ctx = data["hookSpecificOutput"]["additionalContext"]
        assert baseline_sha[:8] in ctx
        assert new_sha[:8] in ctx
        assert branch in ctx


class TestDriftWarningPersistence:
    """The warning repeats until an update advances the baseline; check never does."""

    def test_warning_repeats_and_baseline_unchanged_between_checks(self, git_repo: Path) -> None:
        """check warns on every qualifying call and does not advance the baseline."""
        run_baseline("init", session_id="persist", cwd=git_repo)
        _make_commit(git_repo)
        baseline_file = git_repo / ".git" / "agent-baseline-persist"
        stored = baseline_file.read_text()

        result1 = run_baseline("check", session_id="persist", cwd=git_repo)
        assert result1.stdout != "", "First check should warn"
        assert baseline_file.read_text() == stored, "check must not advance baseline"

        result2 = run_baseline("check", session_id="persist", cwd=git_repo)
        assert result2.stdout != "", "Second check should also warn"

    def test_warning_clears_after_bash_advances_baseline(self, git_repo: Path) -> None:
        """check is silent after update (Bash PostToolUse) advances the baseline to current HEAD."""
        run_baseline("init", session_id="clear-test", cwd=git_repo)
        _make_commit(git_repo)

        warn = run_baseline("check", session_id="clear-test", cwd=git_repo)
        assert warn.stdout != "", "check should warn before update"

        run_baseline("update", session_id="clear-test", cwd=git_repo, tool_name="Bash")

        silent = run_baseline("check", session_id="clear-test", cwd=git_repo)
        assert silent.exit_code == 0
        assert silent.stdout == ""


class TestBaselineAdvancement:
    """The update stage moves the baseline to current HEAD."""

    def test_update_overwrites_baseline_with_current_head(self, git_repo: Path) -> None:
        """update stage overwrites the baseline file with the current HEAD SHA."""
        run_baseline("init", session_id="adv-test", cwd=git_repo)
        new_sha = _make_commit(git_repo)
        run_baseline("update", session_id="adv-test", cwd=git_repo, tool_name="Bash")
        baseline = git_repo / ".git" / "agent-baseline-adv-test"
        assert baseline.read_text() == new_sha


class TestFailSilent:
    """A missing baseline or unusable input exits 0 silently, never as an error."""

    def test_check_silent_when_no_baseline_exists(self, git_repo: Path) -> None:
        """check exits 0 with no output when no baseline file exists for the session."""
        result = run_baseline("check", session_id="no-baseline", cwd=git_repo)
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_all_stages_silent_on_invalid_json_stdin(self) -> None:
        """All stages exit 0 with no output when stdin is not valid JSON."""
        for stage in ("init", "check", "update"):
            result = run_baseline(stage, stdin_text="not-valid-json{{{")
            assert result.exit_code == 0, f"Stage {stage!r}: expected exit 0, got {result.exit_code}"
            assert result.stdout == "", f"Stage {stage!r}: expected no stdout, got {result.stdout!r}"
