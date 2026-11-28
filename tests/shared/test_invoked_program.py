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
        ("tcsh -c 'ls -la'", "ls -la"),
    ],
)
def test_shell_option_clusters_with_c_run_the_next_word(command, code):
    assert bash_commands.program_text(_segment(command)) == [code]


@pytest.mark.parametrize(
    "command",
    [
        "bash -c -- 'ls -la'",
        "bash -c - 'ls -la'",
        "bash -c -x 'ls -la'",
        "bash -c +x 'ls -la'",
        "bash -lc -x 'ls -la'",
        "bash --norc -c 'ls -la'",
    ],
)
def test_a_shell_runs_the_first_word_after_its_options(command):
    """A shell reads options after `-c` too; the code is the first word that is not one."""
    assert bash_commands.program_text(_segment(command)) == ["ls -la"]


@pytest.mark.parametrize(
    ("command", "code"),
    [
        ("bash -c -o errexit 'ls -la'", ["errexit", "ls -la"]),
        ("sh -c +o errexit -e 'ls -la'", ["errexit", "ls -la"]),
        ("bash -c -O extglob 'ls -la'", ["extglob", "ls -la"]),
        ("zsh -c -O 'ls -la' x", ["ls -la", "x"]),
        ("bash -oc errexit 'ls -la'", ["errexit", "ls -la"]),
    ],
)
def test_an_option_name_after_c_is_read_as_code_too(command, code):
    """`bash -O` takes a name and `zsh -O` runs the next word, so both words are read."""
    assert bash_commands.program_text(_segment(command)) == code


def test_an_interpreter_with_a_capital_in_its_name_passes_program_text():
    assert bash_commands.program_text(_segment("Rscript -e 'x <- 1'")) == ["x <- 1"]


def test_a_word_after_c_that_is_not_an_option_string_is_the_code():
    """A shell rejects `+++ x` as an option; reading it as code asks instead of hiding it."""
    assert bash_commands.program_text(_segment("bash -c '+++ ~/x'")) == ["+++ ~/x"]


@pytest.mark.parametrize("shell", ["dash", "ksh", "mksh", "yash", "fish", "/usr/bin/dash"])
def test_other_shells_run_inline_code(shell):
    assert bash_commands.program_text(_segment(f"{shell} -c 'ls -la'")) == ["ls -la"]


@pytest.mark.parametrize(("command", "code"), [("python -c -x", "-x"), ("node -e --", "--"), ("perl -e -l", "-l")])
def test_an_interpreter_runs_the_word_after_its_code_option(command, code):
    """`python -c`, `node -e`, and `perl -e` take the next word as code even when it starts with `-`."""
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


@pytest.mark.parametrize(
    ("value", "bodies"),
    [
        ("$(ls -la)", ["ls -la"]),
        ("x=`ls -la`", ["ls -la"]),
        ("a $(ls) b $(pwd)", ["ls", "pwd"]),
        ("$(echo $(ls))", ["echo $(ls)"]),
        ("${x:-$(ls)}", ["ls"]),
        ("$(( $(ls) + 1 ))", ["ls"]),
        ("$((1 + 2))", []),
        ("$HOME", []),
        ("\\$(ls)", []),
    ],
)
def test_command_substitutions_name_the_text_each_one_runs(value, bodies):
    assert shell_words.command_substitutions(value) == bodies


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
