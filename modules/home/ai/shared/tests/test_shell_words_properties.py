"""Compare the shared lexer with Bash and exercise arbitrary input."""

import shlex

from hypothesis import HealthCheck, assume, example, given, settings, strategies as st
import pytest
from shell_strategies import ATTACHED_FORMS, UNRESOLVED_FORMS, commands as structured_commands
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


@given(command=st.one_of(commands(), structured_commands(), structured_commands(ATTACHED_FORMS)))
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
def test_bash_runs_only_the_words_the_lexer_handed(probe, command):
    segments = lex(command, str(probe.work))
    assume(segments is not None)
    assume(all(word.kind != "unresolvable" for segment in segments for word in segment))
    expected = [tuple(word.value for word in segment) for segment in segments]

    observed = [invocation.words for invocation in probe.run(command)]

    assume(observed)
    assert all(invocation in expected for invocation in observed), (
        command,
        expected,
        observed,
    )


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
