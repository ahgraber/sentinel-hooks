"""The program a lexed segment runs, past wrappers, and the inline code it runs."""

import bash_commands
import pytest
import shell_words


def _segment(command: str) -> shell_words.Segment:
    segments = shell_words.lex(command, None)
    assert segments is not None
    assert len(segments) == 1
    return segments[0]


def _invoked(command: str) -> list[str]:
    return [word.value for word in bash_commands.invoked(_segment(command))]


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "sudo ls -la",
        "env A=1 ls -la",
        "env sudo ls -la",
        "sudo env A=1 nice -n 5 ls -la",
        "A=1 sudo -u root ls -la",
    ],
)
def test_wrappers_are_removed_in_any_order(command):
    assert _invoked(command) == ["ls", "-la"]


@pytest.mark.parametrize("command", ["command -v ls", "command -V ls", "sudo command -v ls"])
def test_a_program_lookup_runs_no_program(command):
    assert _invoked(command) == []


def test_command_without_lookup_runs_the_program():
    assert _invoked("command ls -la") == ["ls", "-la"]


@pytest.mark.parametrize(
    ("command", "code"),
    [
        ("bash -c 'ls -la'", "ls -la"),
        ("bash -lc 'ls -la'", "ls -la"),
        ("zsh -ic 'ls -la'", "ls -la"),
        ("sh -ec 'ls -la'", "ls -la"),
    ],
)
def test_shell_option_clusters_with_c_run_the_next_word(command, code):
    assert bash_commands.program_text(_segment(command)) == [code]


def test_shell_option_cluster_without_c_runs_no_inline_code():
    assert bash_commands.program_text(_segment("bash -l script.sh")) == []
