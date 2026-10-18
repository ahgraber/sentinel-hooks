"""Hold the lexer to bash over the shell inputs of mvdan/sh's parser tests.

`corpus/extract_mvdan_sh.py` builds `corpus/mvdan-sh-inputs.json` and keeps only
inputs bash accepts. Bash, not mvdan/sh, decides each expectation here: the
programs bash starts for an input, recorded with `ShellProbe`.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest
from shell_words import lex
from shellprobe import ShellProbe

CORPUS = json.loads((Path(__file__).parent / "corpus" / "mvdan-sh-inputs.json").read_text())
INPUTS = [text for group in CORPUS["groups"] for text in group["inputs"]]

# Groups whose spellings the lexer reads unlike each other, by the group's first
# input, each under the gap it shows; a strict expected failure each.
KNOWN_GAPS = {
    "for i\ndo foo\ndone": "OneLineCompoundCommand",
    "for (( i = 0 ; i < 10 ; i++ ))\ndo echo $i\ndone": "OneLineCompoundCommand",
    "select i in; do foo; done": "OneLineCompoundCommand",
    "[[\n!\n-a $a\n]]": "ConditionalExpression",
    "[[ -S a && -L b ]]": "ConditionalExpression",
    "let a=(1 + 2) b=3+4": "ArrayAssignment",
    "b[ i ]+=2": "ArrayAssignment",
    'a[ $"x y" ]=b': "ArrayAssignment",
    'a=( [ "x y" ]=b)': "ArrayAssignment",
}


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    return ShellProbe(tmp_path_factory.mktemp("probe"), set(), record_missing=True)


def _program_words(segment) -> list:
    """The words bash passes to the segment's program: not its assignments, redirections, or input."""
    return [
        word
        for word in segment
        if word.redirection is None and word.kind not in {"assignment", "redirection target", "here-document"}
    ]


def test_the_corpus_is_loaded():
    """Guards the corpus itself: an empty one would make every check below vacuous."""
    assert len(INPUTS) > 500
    assert sum("\n" in text for text in INPUTS) > 100


def test_every_program_bash_runs_for_a_corpus_input_is_in_the_reading(probe):
    """A program bash starts is a word of the reading, or inside an unresolvable one.

    A launcher such as `time` or `eval` hands its program on as a word; the
    classifier, not the lexer, reads what a launcher runs.
    """
    hidden = []
    for text in INPUTS:
        segments = lex(text, str(probe.work))
        if segments is None:
            continue
        program_words = [_program_words(segment) for segment in segments]
        # A program named by an expansion could be any program; the hooks gate it as unknown.
        if any(words and words[0].kind == "unresolvable" for words in program_words):
            continue
        visible = {word.value for words in program_words for word in words}
        opaque = " ".join(word.value for segment in segments for word in segment if word.kind == "unresolvable")
        hidden.extend(
            (text, invocation.words)
            for invocation in probe.run(text, timeout=2)
            if invocation.program not in visible and not re.search(rf"\b{re.escape(invocation.program)}\b", opaque)
        )
    assert not hidden, hidden


def test_bash_passes_a_corpus_program_the_words_the_lexer_handed(probe):
    """Every program bash starts receives the tail of a segment's words: all of them, or a launcher's operand."""
    differing = []
    for text in INPUTS:
        segments = lex(text, str(probe.work))
        if segments is None or any(word.kind == "unresolvable" for segment in segments for word in segment):
            continue
        expected = [tuple(word.value for word in _program_words(segment)) for segment in segments]
        differing.extend(
            (text, invocation.words)
            for invocation in probe.run(text, timeout=2)
            if not any(words[len(words) - len(invocation.words) :] == invocation.words for words in expected)
        )
    assert not differing, differing


def _shape(text: str) -> list | None:
    """What a reading says bash runs: each program's words, its assignments, and its redirections in any order.

    Unresolvable text keeps its spelling, which differs between spellings of one program.
    """
    segments = lex(text, "/tmp")
    if segments is None:
        return None

    def value(word):
        return (word.kind, None if word.kind == "unresolvable" else word.value)

    return [
        [
            [value(word) for word in _program_words(segment)],
            [value(word) for word in segment if word.kind == "assignment"],
            sorted(
                ((*value(word), word.redirection or "") for word in segment if word.redirection is not None),
                key=json.dumps,
            ),
        ]
        for segment in segments
    ]


def _group_param(group: dict):
    gap = KNOWN_GAPS.get(group["inputs"][0])
    marks = [pytest.mark.xfail(strict=True, reason=f"known gap {gap}")] if gap else []
    return pytest.param(group["inputs"], marks=marks, id=group["inputs"][0][:40])


@pytest.mark.parametrize(
    "inputs",
    [_group_param(group) for group in CORPUS["groups"] if group["one_program"] and len(group["inputs"]) > 1],
)
def test_inputs_bash_runs_as_one_program_read_alike(inputs):
    shapes = {text: shape for text in inputs if (shape := _shape(text)) is not None}
    assert len({json.dumps(shape) for shape in shapes.values()}) <= 1, shapes
