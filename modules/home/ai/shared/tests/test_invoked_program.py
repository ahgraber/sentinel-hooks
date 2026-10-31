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


@pytest.mark.parametrize("command", ["command -v ls", "command -V ls", "sudo command -v ls", "builtin command -v ls"])
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


@pytest.mark.parametrize(
    ("command", "code"),
    [
        ("sudo bash -c 'ls -la'", ["ls -la"]),
        ("su -c 'ls -la'", ["ls -la"]),
        ("su root --command 'ls -la'", ["ls -la"]),
        ("su --command='ls -la'", ["ls -la"]),
        ("su root", []),
    ],
)
def test_inline_code_is_read_through_privilege_wrappers(command, code):
    assert bash_commands.program_text(_segment(command)) == code


@pytest.mark.parametrize(
    ("command", "reads"),
    [
        ("sudo -s", True),
        ("sudo -u root -i", True),
        ("doas -s", True),
        ("su root", True),
        ("sudo bash", True),
        ("su -c 'ls'", False),
        ("sudo ls", False),
        ("command -v sudo", False),
    ],
)
def test_a_privileged_shell_with_no_command_reads_standard_input(command, reads):
    assert bash_commands.reads_stdin_program(_segment(command)) is reads


def test_shell_option_cluster_without_c_runs_no_inline_code():
    assert bash_commands.program_text(_segment("bash -l script.sh")) == []


def _launched(command: str) -> list[list[str]]:
    words = bash_commands.invoked(_segment(command))
    return [[word.value for word in arguments] for arguments in bash_commands.launched_arguments(words)]


@pytest.mark.parametrize(
    ("command", "launched"),
    [
        ("xargs ls -la", [["ls", "-la"]]),
        ("xargs -n 1 -P 4 ls -la", [["ls", "-la"]]),
        ("xargs -0 -- ls", [["ls"]]),
        ("find . -name x -exec ls {} \\;", [["ls", "{}"]]),
        ("find . -exec ls {} + -execdir cat {} \\;", [["ls", "{}"], ["cat", "{}"]]),
        ("find . -name x -delete", []),
        ("ls -la", []),
    ],
)
def test_launchers_name_the_argument_lists_they_run(command, launched):
    assert _launched(command) == launched


@pytest.mark.parametrize(
    ("command", "script"),
    [
        ("watch ls -la", ["ls -la"]),
        ("watch -n 5 'ls -la'", ["ls -la"]),
        ("watch -d ls", ["ls"]),
        ("ls -la", []),
    ],
)
def test_watch_runs_its_joined_arguments(command, script):
    assert bash_commands.watch_script(bash_commands.invoked(_segment(command))) == script
