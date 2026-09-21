"""Shell words retain their role, quoting, and unresolved path evidence."""

import importlib

from hermetic import build_home
import pytest


@pytest.fixture
def lexer():
    return importlib.import_module("shell_words")


@pytest.fixture
def shell_world(tmp_path, monkeypatch):
    """The lexer reads no manifest, and a case here globs the repository."""
    return build_home(tmp_path, monkeypatch)


KIND_CASES = {
    "command": [("cat", [("cat", "command")])],
    "plain word": [
        ("cat notes", [("cat", "command"), ("notes", "plain word")]),
        ("cat '{a,b}'", [("cat", "command"), ("{a,b}", "plain word")]),
        ("cat '*.md'", [("cat", "command"), ("*.md", "plain word")]),
        ("cat 'a b'", [("cat", "command"), ("a b", "plain word")]),
        ("cat $'a\\tb'", [("cat", "command"), ("a\tb", "plain word")]),
        ('cat "|"', [("cat", "command"), ("|", "plain word")]),
    ],
    "option": [("cat -n", [("cat", "command"), ("-n", "option")])],
    "assignment": [("MODE=1 cat", [("MODE=1", "assignment"), ("cat", "command")])],
    "redirection target": [
        ("cat>notes", [("cat", "command"), ("notes", "redirection target")]),
        ("cat < notes", [("cat", "command"), ("notes", "redirection target")]),
    ],
    "pattern": [("cat *.absent", [("cat", "command"), ("*.absent", "pattern")])],
    "path candidate": [("cat dir/absent", [("cat", "command"), ("dir/absent", "path candidate")])],
    "unresolvable": [
        ("cat $VALUE", [("cat", "command"), ("$VALUE", "unresolvable")]),
        ("cat {a,b}", [("cat", "command"), ("{a,b}", "unresolvable")]),
    ],
}


@pytest.mark.parametrize("kind", KIND_CASES)
def test_word_kinds_follow_shell_syntax(lexer, shell_world, kind):
    _, repository = shell_world
    for command, expected in KIND_CASES[kind]:
        segments = lexer.lex(command, str(repository))
        assert segments is not None
        assert [[(word.value, word.kind) for word in segment] for segment in segments] == [expected]


@pytest.mark.parametrize("exists", [False, True])
def test_bare_word_is_a_path_only_when_an_entry_exists(lexer, shell_world, exists):
    _, repository = shell_world
    if exists:
        (repository / "notes").touch()

    segments = lexer.lex("cat notes", str(repository))

    assert segments[0][1].kind == ("path candidate" if exists else "plain word")


def test_glob_uses_the_supplied_directory(lexer, shell_world):
    _, repository = shell_world
    (repository / "a.md").touch()
    (repository / "b.md").touch()

    segments = lexer.lex("cat *.md", str(repository))

    assert [(word.value, word.kind) for word in segments[0][1:]] == [
        ("a.md", "path candidate"),
        ("b.md", "path candidate"),
    ]


@pytest.mark.parametrize("spelling", ["~/notes", "'~/notes'"])
def test_tilde_expands_only_when_unquoted(lexer, shell_world, spelling):
    home, repository = shell_world

    segments = lexer.lex(f"cat {spelling}", str(repository))

    assert segments[0][1].value == (str(home / "notes") if spelling == "~/notes" else "~/notes")


@pytest.mark.parametrize("command", ["DEST=~/notes cat", "cat DEST=~/notes"])
def test_assignment_tilde_expansion(lexer, shell_world, command):
    home, repository = shell_world
    words = lexer.lex(command, str(repository))[0]
    assert f"DEST={home}/notes" in [word.value for word in words]


def test_quoted_assignment_tilde_is_literal(lexer, shell_world):
    _, repository = shell_world
    words = lexer.lex("DEST='~/notes' cat", str(repository))[0]
    assert words[0].value == "DEST=~/notes"


@pytest.mark.parametrize("separator", ["|", ";", "&&", "||", "&"])
def test_control_operator_splits_segments(lexer, shell_world, separator):
    _, repository = shell_world

    segments = lexer.lex(f"cat a {separator} head b", str(repository))

    assert [[word.value for word in segment] for segment in segments] == [
        ["cat", "a"],
        ["head", "b"],
    ]


@pytest.mark.parametrize("command", ["cat a\nhead b", "cat 'a\nb'", "cat a\\\nb", "cat '\x00'", "cat '"])
def test_unreadable_command_returns_no_partial_reading(lexer, shell_world, command):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert segments is None


@pytest.mark.parametrize("spelling", ["${VALUE:-/guarded/file}", "{a,/guarded/file}", "$(cat /guarded/file)"])
def test_unresolvable_word_retains_embedded_paths(lexer, shell_world, spelling):
    _, repository = shell_world

    segments = lexer.lex(f"cat {spelling}", str(repository))

    word = segments[0][1]
    assert word.kind == "unresolvable"
    assert "/guarded/file" in word.paths


def test_input_redirection_keeps_its_direction(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("read name 0<notes", str(repository))

    assert segments[0][-1].kind == "redirection target"
    assert segments[0][-1].redirection == "0<"


def test_relative_path_after_cd_is_unresolvable(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("cd elsewhere && cat ./file", str(repository))

    assert segments[1][1].kind == "unresolvable"


def test_bare_word_after_unknown_cd_is_unresolvable(lexer, shell_world):
    _, repository = shell_world
    segments = lexer.lex("cd $DIR && cat settings.json", str(repository))
    assert segments[1][1].kind == "unresolvable"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (r"\e", "\x1b"),
        (r"\cA", "\x01"),
        (r"\c?", "\x7f"),
        (r"\101", "A"),
        (r"\x41", "A"),
        (r"\u0041", "A"),
        (r"\U00000041", "A"),
        (r"\xc3\xa9", "é"),
        (r"\xff", "\udcff"),
        (r"a\0discarded", "a"),
    ],
)
def test_ansi_c_escapes_match_bash_characters(lexer, shell_world, body, expected):
    _, repository = shell_world

    segments = lexer.lex(f"cat $'{body}'", str(repository))

    assert segments[0][1].value == expected


def test_glob_in_command_position_has_only_one_command_word(lexer, shell_world):
    _, repository = shell_world
    (repository / "a").touch()
    (repository / "b").touch()

    segments = lexer.lex("*", str(repository))

    assert [(word.value, word.kind) for word in segments[0]] == [
        ("a", "command"),
        ("b", "path candidate"),
    ]


@pytest.mark.parametrize(
    ("command", "expected"),
    [("'MODE=1' cat", "command"), ("MODE='1' cat", "assignment")],
)
def test_quoted_assignment_name_is_a_command(lexer, shell_world, command, expected):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert segments[0][0].kind == expected


def test_subshell_boundaries_split_segments(lexer, shell_world):
    _, repository = shell_world
    segments = lexer.lex("(cat a); (head b)", str(repository))
    assert [[word.value for word in segment] for segment in segments] == [
        ["cat", "a"],
        ["head", "b"],
    ]


def test_partly_quoted_glob_is_refused(lexer, shell_world):
    _, repository = shell_world
    assert lexer.lex("cat 'a'*", str(repository))[0][1].kind == "unresolvable"


@pytest.mark.parametrize("text", [chr(0xD800), chr(0xDFFF), "cat $'" + chr(0xD800) + "'"])
def test_lone_surrogate_does_not_raise(lexer, shell_world, text):
    _, repository = shell_world
    result = lexer.lex(text, str(repository))
    assert result is None or isinstance(result, list)
