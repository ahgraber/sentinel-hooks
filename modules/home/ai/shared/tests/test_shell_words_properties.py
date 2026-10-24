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
    pipeline_commands,
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


def _handed(segment) -> tuple[str, ...]:
    """The words a segment hands its program, as the probe records them: no redirection or here-document."""
    return tuple(word.value for word in segment if not word.redirection and word.kind != "here-document")


def _standard_input(segment) -> str:
    """The body bash delivers on standard input: the last here-document on descriptor 0, or none."""
    bodies = [
        word.value
        for word in segment
        if word.kind == "here-document" and (word.redirection or "").lstrip("0").startswith("<<")
    ]
    return bodies[-1] if bodies else ""


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
        pipeline_commands(),
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
# Bash hands a program no redirection target.
@example(command="cat a 2>/dev/null | head b >/dev/null")
# Of several bodies on standard input, bash delivers the last.
@example(command="cat <<'A' <<'B'\none\nA\ntwo\nB")
@example(command=r"cat $'\e' $'\cA' $'\c?' $'\101' $'\x41'")
@example(command=r"cat $'\u0041' $'\U00000041' $'\xc3\xa9' $'\xff' $'a\0discarded'")
@example(command="cat a\nhead \\\n  b # c \\\nsort")
@example(command="cat <<EOF | head\na\\\\b\nEOF\nsort")
def test_bash_runs_only_the_words_the_lexer_handed(probe, command):
    segments = lex(command, str(probe.work))
    assume(segments is not None)
    assume(all(word.kind != "unresolvable" for segment in segments for word in segment))
    # A here-document is the program's standard input, not one of its words; a
    # piped program's input is what the stage before it printed.
    expected = [
        (
            _handed(segment),
            None if segment.piped_in else _standard_input(segment),
        )
        for segment in segments
    ]

    observed = [(invocation.words, invocation.stdin) for invocation in probe.run(command)]

    assume(observed)
    assert all(
        any(words == invocation[0] and stdin in {None, invocation[1]} for words, stdin in expected)
        for invocation in observed
    ), (
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


@given(command=pipeline_commands())
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@example(command="{\ncat <<'EOF'\nrm a\nEOF\n} | sort notes.md")
@example(command="cat a | {\nhead b\nsort c\n}")
@example(command="coproc {\ncat a\n} </dev/null\nwait")
@example(command="for i in 1; do\ncat a\ndone 2>&1 | head b")
def test_the_reading_pipes_what_bash_pipes(probe, command):
    """A program bash runs with its output or input on a pipe is a command whose reading says so.

    The reading may mark more than bash pipes, never less. A here-document
    or an input redirection also reaches a program through a pipe, so only
    output is compared where the command holds one.
    """
    segments = lex(command, str(probe.work))
    assume(segments is not None)
    checked = subprocess.run([probe.bash, "-n"], input=command, text=True, capture_output=True, check=False)
    assume(checked.returncode == 0)
    compare_input = "<" not in command
    invocations = probe.run(command)
    # A run past the probe's timeout records nothing, which would pass unchecked.
    assume(invocations)

    for invocation in invocations:
        matches = [segment for segment in segments if _handed(segment) == invocation.words]
        if not matches:
            continue
        if invocation.pipes_out:
            assert any(segment.pipes_out for segment in matches), (command, invocation)
        if invocation.piped_in and compare_input:
            assert any(segment.piped_in for segment in matches), (command, invocation)


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
    reader = _handed(segments[0])
    bodies = [word.value for word in segments[0] if word.kind == "here-document"]
    assume(bodies)

    # A later program in the command may take the same words, so the reader is one of the matches.
    received = [invocation.stdin for invocation in probe.run(command) if invocation.words == reader]

    assert bodies[0] in received, (command, bodies, received)
    if body is not None:
        assert bodies == [body]


@pytest.mark.parametrize(
    ("command", "delivered"),
    [
        ("cat <<'A' <<'B'\none\nA\ntwo\nB", "two\n"),
        ("cat <<'A' 0<<'B'\none\nA\ntwo\nB", "two\n"),
        ("cat 0<<'A' <<'B' <<'C'\none\nA\ntwo\nB\nthree\nC", "three\n"),
    ],
)
def test_bash_delivers_the_last_of_several_bodies_on_one_descriptor(probe, command, delivered):
    """Every body is a word of the reading; the last on standard input is the one the program reads."""
    segments = lex(command, str(probe.work))
    bodies = [word.value for word in segments[0] if word.kind == "here-document"]

    [invocation] = probe.run(command)

    assert invocation.stdin == delivered == bodies[-1]


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
