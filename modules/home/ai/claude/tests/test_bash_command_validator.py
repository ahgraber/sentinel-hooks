"""Behavioral tests for bash-command-validator.sh."""

from conftest import assert_allowed, assert_blocked, run_hook
import pytest

HOOK = "bash-command-validator.sh"


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


class TestToolScope:
    def test_non_bash_tool_is_allowed(self):
        result = run_hook(HOOK, "Read", {"command": "python script.py"})

        assert_allowed(result)

    def test_missing_command_is_allowed(self):
        result = run_hook(HOOK, "Bash", {})

        assert_allowed(result)

    def test_empty_command_is_allowed(self):
        assert_allowed(bash(""))

    def test_safe_command_is_allowed(self):
        assert_allowed(bash("echo hello world"))

    def test_malformed_json_returns_error(self):
        result = run_hook(HOOK, stdin_text="not json")

        assert result.exit_code == 1
        assert "invalid json" in result.stderr.lower()


class TestZshCommandHazards:
    @pytest.mark.parametrize(
        ("command", "message"),
        [
            pytest.param(
                "cat <<EOF\nhello\nEOF",
                "heredoc",
                id="heredoc",
            ),
            pytest.param(
                'echo "value!=expected"',
                "double-quoted string",
                id="double-quoted-bang",
            ),
            pytest.param(
                "echo !history",
                "unquoted '!word'",
                id="unquoted-bang",
            ),
            pytest.param(
                "nix build .#host",
                "quote the flake reference",
                id="unquoted-flake-reference",
            ),
            pytest.param(
                "git show abc123^",
                "after a git commit",
                id="unquoted-git-parent",
            ),
            pytest.param(
                "rg --glob=*.py pattern",
                "quote the value",
                id="unquoted-flag-glob",
            ),
            pytest.param(
                "ls /nix/store/*",
                "do not glob /nix/store",
                id="nix-store-glob",
            ),
        ],
    )
    def test_hazard_is_blocked(self, command, message):
        assert_blocked(bash(command), message)

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("cat <<<hello", id="here-string"),
            pytest.param("echo 'value!=expected'", id="single-quoted-bang"),
            pytest.param("[[ value != expected ]]", id="comparison-bang"),
            pytest.param("nix build '.#host'", id="quoted-flake-reference"),
            pytest.param("git show abc123~1", id="git-parent-with-tilde"),
            pytest.param("rg --glob='*.py' pattern", id="quoted-flag-glob"),
            pytest.param(
                "ls /nix/store/aaaaaaaa-package",
                id="explicit-nix-store-path",
            ),
        ],
    )
    def test_safe_alternative_is_allowed(self, command):
        assert_allowed(bash(command))


class TestRipgrepFlags:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("rg -rn pattern", id="recursive-line-number-flags"),
            pytest.param("rg -lr pattern", id="list-recursive-flags"),
            pytest.param("rg -r pattern", id="replace-short-flag"),
            pytest.param(
                "rg -r=replacement pattern",
                id="replace-short-flag-with-value",
            ),
        ],
    )
    def test_recursive_flag_is_blocked(self, command):
        assert_blocked(bash(command), "recursive by default")

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("rg -n pattern", id="line-numbers"),
            pytest.param("rg -l pattern", id="list-files"),
            pytest.param("rg pattern | head", id="pipeline"),
        ],
    )
    def test_supported_flags_are_allowed(self, command):
        assert_allowed(bash(command))


class TestPythonRedirect:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("python script.py", id="python"),
            pytest.param("python3 script.py", id="python3"),
            pytest.param("ENV=value python3.12 script.py", id="environment-prefix"),
            pytest.param("/usr/bin/python3 script.py", id="absolute-path"),
            pytest.param("echo ready && python script.py", id="after-separator"),
        ],
    )
    def test_direct_python_is_blocked(self, command):
        assert_blocked(bash(command), "uv run")

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("uv run python script.py", id="uv-run-python"),
            pytest.param("echo python script.py", id="python-as-argument"),
            pytest.param('rg -n "python|ruby" notes.md', id="search-pattern"),
            pytest.param("cat docs/python-notes.md", id="filename"),
        ],
    )
    def test_non_direct_python_is_allowed(self, command):
        assert_allowed(bash(command))

    def test_a_name_after_a_pipe_is_still_an_invocation(self):
        assert_blocked(bash("cat input.txt | python -"), "uv run")


class TestPipRedirect:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("pip install package", id="pip-install"),
            pytest.param("pip uninstall package", id="pip-uninstall"),
            pytest.param("pip download package", id="pip-download"),
            pytest.param("pip3 install package", id="pip3-install"),
            pytest.param("pip3 uninstall package", id="pip3-uninstall"),
            pytest.param("pip3 download package", id="pip3-download"),
        ],
    )
    def test_package_mutation_is_blocked(self, command):
        assert_blocked(bash(command), "uv add")

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("pip list", id="pip-list"),
            pytest.param("pip3 show package", id="pip3-show"),
            pytest.param("uv add package", id="uv-add"),
            pytest.param("uv run --with package script.py", id="uv-run-with"),
            pytest.param('rg -n "pip install" notes.md', id="search-pattern"),
            pytest.param("cat docs/pip-install-guide.md", id="filename"),
        ],
    )
    def test_supported_package_commands_are_allowed(self, command):
        assert_allowed(bash(command))


class TestPytestRedirect:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("pytest tests", id="pytest"),
            pytest.param("py.test tests", id="py-test"),
        ],
    )
    def test_direct_test_runner_is_blocked(self, command):
        assert_blocked(bash(command), "uv run pytest")

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("uv run pytest tests", id="uv-run-pytest"),
            pytest.param("uv run py.test tests", id="uv-run-py-test"),
        ],
    )
    def test_uv_test_runner_is_allowed(self, command):
        assert_allowed(bash(command))

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param(
                'rg -n -A20 -B5 "pytest|testpaths|addopts|pythonpath" pyproject.toml',
                id="search-pattern",
            ),
            pytest.param("cat docs/pytest-notes.md", id="filename"),
            pytest.param("echo 'run pytest through uv'", id="prose-argument"),
            pytest.param("grep -n pytest tests/conftest.py", id="grep-argument"),
            pytest.param('rg -n "a|pytest" notes.md', id="quoted-alternation"),
            pytest.param(
                r'grep -rn "hypothesis\|pytest" pyproject.toml',
                id="quoted-basic-regex-alternation",
            ),
        ],
    )
    def test_the_name_outside_command_position_is_allowed(self, command):
        assert_allowed(bash(command))

    def test_a_name_after_a_separator_is_still_an_invocation(self):
        assert_blocked(bash("echo ready && pytest tests"), "uv run pytest")


class TestPreCommitRedirect:
    def test_pre_commit_run_is_blocked(self):
        assert_blocked(bash("pre-commit run --all-files"), "prek run")

    def test_pre_commit_run_after_a_separator_is_blocked(self):
        assert_blocked(bash("cd /repo && pre-commit run"), "prek run")

    def test_prek_run_is_allowed(self):
        assert_allowed(bash("prek run --all-files"))

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param('rg -n "pre-commit run" README.md', id="search-pattern"),
            pytest.param("cat docs/pre-commit-run.md", id="filename"),
        ],
    )
    def test_the_name_outside_command_position_is_allowed(self, command):
        assert_allowed(bash(command))


class TestGitCommitRedirect:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("git commit -m 'unsigned'", id="direct"),
            pytest.param(
                "git -c user.name=Agent commit -m 'unsigned'",
                id="global-config",
            ),
            pytest.param(
                "git -C /repo commit -m 'unsigned'",
                id="working-directory",
            ),
            pytest.param(
                "git --git-dir=/repo/.git commit -m 'unsigned'",
                id="git-directory",
            ),
            pytest.param(
                "git --work-tree=/repo commit -m 'unsigned'",
                id="work-tree",
            ),
            pytest.param(
                "git --config-env=user.name=GIT_AUTHOR_NAME commit -m 'unsigned'",
                id="config-environment",
            ),
            pytest.param(
                "GIT_CONFIG_COUNT=0 git commit -m 'unsigned'",
                id="environment-assignment",
            ),
            pytest.param(
                "echo ready && git commit --amend",
                id="after-separator",
            ),
            pytest.param(
                "command git --no-pager commit --amend",
                id="command-wrapper",
            ),
        ],
    )
    def test_direct_commit_subcommand_is_blocked(self, command):
        assert_blocked(bash(command), "agent-commit")

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param(
                "git agent-commit -m 'signed'",
                id="agent-commit",
            ),
            pytest.param(
                "git -c commit.gpgsign=true status",
                id="commit-config-key",
            ),
            pytest.param(
                "git --work-tree=commit status",
                id="commit-as-option-value",
            ),
            pytest.param(
                "git --git-dir=/repo/.git status",
                id="non-commit-long-option",
            ),
            pytest.param(
                "rg -n 'git commit' .",
                id="commit-as-search-argument",
            ),
            pytest.param(
                "echo 'git commit is prohibited'",
                id="commit-as-echo-argument",
            ),
        ],
    )
    def test_commit_text_outside_subcommand_is_allowed(self, command):
        assert_allowed(bash(command))


class TestGitWorkingDirectoryRedirect:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("git -C /repo status", id="direct"),
            pytest.param("git -C /repo --no-pager diff", id="before-pager-option"),
            pytest.param("git --no-pager -C /repo log --oneline", id="after-option"),
            pytest.param("command git -C /repo rev-parse HEAD", id="command-wrapper"),
            pytest.param("cd /tmp && git -C /repo ls-files", id="after-separator"),
        ],
    )
    def test_working_directory_option_is_blocked(self, command):
        assert_blocked(bash(command), "cd <path>")

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("git status --short", id="plain-subcommand"),
            pytest.param("git --no-pager diff -- path", id="plain-with-pager-option"),
            pytest.param("git branch -c old new", id="lowercase-copy-option"),
            pytest.param("rg -n 'git -C' shlib/", id="option-as-search-argument"),
            pytest.param(
                "rg -n 'commit|git -C' shlib/",
                id="option-in-quoted-alternation",
            ),
            pytest.param("scripts/gist-publish.sh", id="script-using-the-option"),
        ],
    )
    def test_plain_form_and_quoted_text_are_allowed(self, command):
        assert_allowed(bash(command))


class TestIssueReporting:
    def test_all_matching_issues_are_reported(self):
        result = bash("rg -rn pattern; python script.py")

        assert_blocked(result)
        assert "recursive by default" in result.stderr
        assert "uv run" in result.stderr
