"""Readings the lexer gets wrong today, one named gap per test.

Each test states what bash reads and is a strict expected failure: when a
gap closes, its test passes, the run fails, and the mark comes out. Until
then the lexer gives no reading for the multi-line forms here, so the hooks
judge their whole text; the one-line misreadings are live.
"""

from __future__ import annotations

import pytest
import shell_words


def _reading(command: str, cwd: str) -> list[tuple[str, list[tuple[str, str]]]] | None:
    """Return each segment's separator and its words' values and kinds, or `None`."""
    segments = shell_words.lex(command, cwd)
    if segments is None:
        return None
    return [(segment.separator, [(word.value, word.kind) for word in segment]) for segment in segments]


def _gap(name: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=f"known gap {name}")


@_gap("LineContinuation")
@pytest.mark.parametrize(
    ("multi_line", "one_line"),
    [
        ("cat a \\\n  b", "cat a b"),
        ("cat a\\\nb", "cat ab"),
        ("cd /tmp &\\\n& cat x", "cd /tmp && cat x"),
    ],
)
def test_a_continuation_joins_the_lines(tmp_path, multi_line, one_line):
    assert _reading(multi_line, str(tmp_path)) == _reading(one_line, str(tmp_path)) is not None


@_gap("CompoundCommandAcrossLines")
@pytest.mark.parametrize(
    ("multi_line", "one_line"),
    [
        ("if true; then\ncat a\nfi", "if true; then cat a; fi"),
        ("for x in a; do\ncat a\ndone", "for x in a; do cat a; done"),
        ("{\ncat a\n}", "{ cat a; }"),
    ],
)
def test_a_compound_command_across_lines_reads_as_on_one_line(tmp_path, multi_line, one_line):
    assert _reading(multi_line, str(tmp_path)) == _reading(one_line, str(tmp_path)) is not None


@_gap("ParenthesisAcrossLines")
@pytest.mark.parametrize(("multi_line", "one_line"), [("(cat a)\nhead b", "(cat a); head b")])
def test_a_subshell_in_a_multi_line_command_reads_as_on_one_line(tmp_path, multi_line, one_line):
    assert _reading(multi_line, str(tmp_path)) == _reading(one_line, str(tmp_path)) is not None


@_gap("HereDocumentOrCaseInsideSubstitution")
@pytest.mark.parametrize(
    "command",
    [
        "echo $(cat <<'EOF'\n'\nEOF\n); echo HIDDEN; #')",
        "echo $(case x in x) cat a;; esac); echo HIDDEN",
    ],
)
def test_a_substitution_ends_at_its_own_close(tmp_path, command):
    reading = _reading(command, str(tmp_path))

    assert reading is not None
    assert ["echo", "HIDDEN"] in [[value for value, _ in words] for _, words in reading]


@_gap("HereDocumentDelimiterWithDollar")
@pytest.mark.parametrize("delimiter", ["$X", "$(echo EOF)", "${HOME}"])
def test_a_here_document_delimiter_is_taken_literally(tmp_path, delimiter):
    reading = _reading(f"cat <<{delimiter}\nbody\n{delimiter}\necho HIDDEN", str(tmp_path))

    assert reading is not None
    assert ("body\n", "here-document") in reading[0][1]
    assert [value for value, _ in reading[-1][1]] == ["echo", "HIDDEN"]


@_gap("HereDocumentBodyEscapes")
@pytest.mark.parametrize(
    ("body", "delivered"),
    [
        ("\\$X\n", "$X\n"),
        ("\\`x\\`\n", "`x`\n"),
        ("a\\\\\n", "a\\\n"),
        ("a\\\nb\n", "ab\n"),
    ],
)
def test_an_unquoted_body_delivers_what_bash_delivers(tmp_path, body, delivered):
    reading = _reading(f"cat <<EOF\n{body}EOF", str(tmp_path))

    assert reading is not None
    assert (delivered, "here-document") in reading[0][1]
