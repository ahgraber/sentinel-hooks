"""Compare the shared lexer with Bash and exercise arbitrary input."""

from collections import Counter
import re
import shlex
import subprocess

from hypothesis import HealthCheck, assume, example, given, settings, strategies as st
import pytest
from shell_strategies import (
    ATTACHED_FORMS,
    PROGRAMS,
    UNRESOLVED_FORMS,
    commands as structured_commands,
    here_document_commands,
    line_pairs,
    run_once_commands,
    substitution_commands,
    unread_commands,
)
from shell_words import lex
from shellprobe import ShellProbe


@pytest.fixture
def probe(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return ShellProbe(tmp_path / "probe", {"cat", "head", "sort", "find", "grep", "rm", "tee", "cp"})


@st.composite
def commands(draw):
    program = draw(st.sampled_from(["cat", "head", "sort"]))
    values = draw(st.lists(st.text(alphabet="abcXYZ09 ./~_-*?[];|&{}é", max_size=25), max_size=6))
    arguments = [shlex.quote(value) for value in values]
    return " ".join([program, *arguments])


def _reading(command, cwd):
    """Return each segment's words with their kinds and redirections, separator, and directories."""
    segments = lex(command, cwd)
    if segments is None:
        return None
    return [
        ([(word.value, word.kind, word.redirection) for word in segment], segment.separator, segment.directories)
        for segment in segments
    ]


@given(pair=line_pairs())
@settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(pair=("cat a && head b", "cat a &&\nhead b"))
@example(pair=("echo if then ; cat a", "# rm a \\\necho if then\ncat a"))
def test_a_multi_line_command_lexes_as_its_one_line_form(tmp_path, pair):
    one_line, multi_line = pair

    assert _reading(multi_line, str(tmp_path)) == _reading(one_line, str(tmp_path)), pair


@given(command=unread_commands())
@settings(max_examples=250, deadline=None)
def test_a_form_the_lexer_does_not_read_has_no_reading(command):
    assert lex(command, "/tmp") is None, command


@given(
    command=st.one_of(
        commands(),
        structured_commands(),
        structured_commands(ATTACHED_FORMS),
        line_pairs().map(lambda pair: pair[1]),
        here_document_commands().map(lambda case: case[0]),
    )
)
@settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(command="cat ~/file")
@example(command="cat of=~/file")
@example(command="cat VAR=~/file")
@example(command="cat '*.md'")
@example(command="cat a | head b")
@example(command=r"cat $'\e' $'\cA' $'\c?' $'\101' $'\x41'")
@example(command=r"cat $'\u0041' $'\U00000041' $'\xc3\xa9' $'\xff' $'a\0discarded'")
@example(command="cat a\nhead \\\n  b # c \\\nsort")
@example(command="cat <<EOF | head\na\\\\b\nEOF\nsort")
def test_bash_runs_only_the_words_the_lexer_handed(probe, command):
    segments = lex(command, str(probe.work))
    assume(segments is not None)
    assume(all(word.kind != "unresolvable" for segment in segments for word in segment))
    # A here-document is the program's standard input, not one of its words.
    expected = [
        (
            tuple(word.value for word in segment if word.kind != "here-document"),
            "".join(word.value for word in segment if word.kind == "here-document"),
        )
        for segment in segments
    ]

    observed = [(invocation.words, invocation.stdin) for invocation in probe.run(command)]

    assume(observed)
    assert all(invocation in expected for invocation in observed), (
        command,
        expected,
        observed,
    )


@given(command=substitution_commands())
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(command="cat \"${X:-'\"'}\" ; head a #'")
@example(command="cat $(# ' \" ) }\nrm 'a)') ; head b")
@example(command="cat `head a; rm b` ; sort c")
def test_every_program_bash_runs_is_in_the_reading(probe, command):
    """A substitution is one unresolvable word: bash may run programs inside it, but none outside the reading."""
    segments = lex(command, str(probe.work))
    assume(segments is not None)
    commands = [word.value for segment in segments for word in segment if word.kind == "command"]
    opaque = " ".join(word.value for segment in segments for word in segment if word.kind == "unresolvable")

    hidden = [
        invocation.words
        for invocation in probe.run(command)
        if invocation.program not in commands and not re.search(rf"\b{invocation.program}\b", opaque)
    ]

    assert not hidden, (command, commands, opaque, hidden)


def _programs_the_reading_runs(segments) -> Counter | None:
    """Count the recorded programs a reading runs, following `&&` and `||` on each pipeline's status.

    A recorded program, `true`, `:`, `break`, and a segment that runs no
    program succeed; any other program is not found and fails. `None` where
    `&&` or `||` follows a program an unresolvable word names, whose status
    the reading cannot know.
    """
    programs: Counter = Counter()
    previous, runs, status = ";", True, 0
    for segment in segments:
        if previous not in {"|", "|&"}:
            if previous in {"&&", "||"} and status is None:
                return None
            runs = previous not in {"&&", "||"} or (previous == "&&") == (status == 0)
        names = [word.value for word in segment if word.kind == "command"]
        if runs:
            programs.update(name for name in names if name in PROGRAMS)
            if segment.separator not in {"|", "|&"}:
                leading = next((word for word in segment if word.kind != "assignment"), None)
                if leading is not None and leading.kind == "unresolvable":
                    status = None
                else:
                    status = 0 if not names or names[0] in {*PROGRAMS, "true", ":", "break"} else 127
        previous = segment.separator
    return programs


@given(command=run_once_commands())
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@example(command="cat a $(inner ')') ; head b")
@example(command="if true; then\ncat a || head b | sort c\nfi")
@example(command="cat notes/a\nb.md && cat notes/c")
@example(command="cat {notes/a\nb.md} && cat notes/c")
def test_bash_runs_exactly_the_programs_the_reading_names(probe, command):
    """Each program bash runs outside a substitution is a command of the reading, and the reading names no other.

    A substitution read past its `)` would take a later program into its text, which this catches.
    """
    segments = lex(command, str(probe.work))
    assume(segments is not None)
    # A background job may end after the probe stops recording.
    assume(all(segment.separator != "&" for segment in segments))
    checked = subprocess.run([probe.bash, "-n"], input=command, text=True, capture_output=True, check=False)
    assume(checked.returncode == 0)

    expected = _programs_the_reading_runs(segments)
    assume(expected is not None)
    ran = Counter(invocation.program for invocation in probe.run(command) if invocation.program in PROGRAMS)

    assert ran == expected, command


@given(case=here_document_commands())
@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(case=("cat <<-'EOF'\n\ta\n  b\n\tEOF", "a\n  b\n"))
@example(case=("cat <<'EOF'\nEOF \nEOF", "EOF \n"))
def test_a_here_document_word_holds_the_body_bash_delivers(probe, case):
    command, body = case
    segments = lex(command, str(probe.work))
    assume(segments is not None)
    reader = tuple(word.value for word in segments[0] if word.kind != "here-document")
    bodies = [word.value for word in segments[0] if word.kind == "here-document"]
    assume(bodies)

    # A later program in the command may take the same words, so the reader is one of the matches.
    received = [invocation.stdin for invocation in probe.run(command) if invocation.words == reader]

    assert bodies[0] in received, (command, bodies, received)
    if body is not None:
        assert bodies == [body]


@given(command=st.text())
@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(command="~\x00")
@example(command="cat $'\\cß'")
@example(command="cat " + "x" * 300)
def test_arbitrary_text_returns_words_or_an_unresolvable_report(tmp_path, command):
    segments = lex(command, str(tmp_path))

    assert segments is None or isinstance(segments, list)


@given(command=st.text(alphabet=st.characters(codec="utf-8"), min_size=1))
@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_arbitrary_unicode_returns_words_or_an_unresolvable_report(tmp_path, command):
    segments = lex(command, str(tmp_path))

    assert segments is None or isinstance(segments, list)


@given(command=structured_commands(UNRESOLVED_FORMS))
@settings(max_examples=250, deadline=None)
def test_expansions_remain_unresolved(command):
    segments = lex(command, "/tmp")

    assert segments is None or any(word.kind == "unresolvable" for segment in segments for word in segment)


@given(value=st.text(alphabet=st.characters(blacklist_characters="\x00\n\r", blacklist_categories=("Cs",))))
@settings(max_examples=250, deadline=None)
def test_shell_quoting_preserves_a_single_word(value):
    segments = lex("cat " + shlex.quote(value), "/tmp")

    assert segments is not None
    assert [word.value for word in segments[0]] == ["cat", value]
