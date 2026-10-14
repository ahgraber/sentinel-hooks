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


@pytest.mark.parametrize("prefix", ["~+", "~-", "~1", "~+1", "~-2"])
def test_a_directory_stack_tilde_is_unresolvable(lexer, shell_world, prefix):
    _, repository = shell_world
    for word in (f"{prefix}/notes", prefix):
        assert lexer.lex(f"cat {word}", str(repository))[0][1].kind == "unresolvable"


def test_assignment_tilde_after_a_colon_expands(lexer, shell_world):
    home, repository = shell_world
    words = lexer.lex("DEST=/tmp:~/notes cat", str(repository))[0]
    assert words[0].value == f"DEST=/tmp:{home}/notes"


def test_assignment_directory_stack_tilde_is_unresolvable(lexer, shell_world):
    _, repository = shell_world
    for command in ("DEST=~+/notes cat", "DEST=/tmp:~-/notes cat"):
        assert lexer.lex(command, str(repository))[0][0].kind == "unresolvable"


def test_an_option_keeps_its_kind_where_an_entry_of_that_name_exists(lexer, shell_world):
    _, repository = shell_world
    (repository / "-n").touch()
    assert lexer.lex("cat -n notes", str(repository))[0][1].kind == "option"


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


def test_a_glob_quoted_only_around_literal_text_is_expanded(lexer, shell_world):
    _, repository = shell_world
    (repository / "a1").touch()

    words = lexer.lex("cat 'a'*", str(repository))[0][1:]

    assert [(word.value, word.kind) for word in words] == [("a1", "path candidate")]


def test_a_quoted_glob_character_keeps_the_word_unresolvable(lexer, shell_world):
    _, repository = shell_world
    assert lexer.lex("cat '*'x*", str(repository))[0][1].kind == "unresolvable"


@pytest.mark.parametrize("text", [chr(0xD800), chr(0xDFFF), "cat $'" + chr(0xD800) + "'"])
def test_lone_surrogate_does_not_raise(lexer, shell_world, text):
    _, repository = shell_world
    result = lexer.lex(text, str(repository))
    assert result is None or isinstance(result, list)


# Each segment's directories, as spellings relative to where the command
# starts: "" is that directory. `None` is a directory change the words do not
# resolve. A segment after a `cd` may run in the starting directory too, since
# the `cd` may fail or be skipped.
START = ("",)
MOVED = ("", "sub")
DIRECTORY_CASES = [
    ("cat a", [START]),
    ("cd sub && cat a", [START, ("sub",)]),
    ("cd sub && cd deeper && cat a", [START, ("sub",), ("sub/deeper",)]),
    ("cd sub; cat a", [START, MOVED]),
    ("cd sub || cat a", [START, START]),
    ("cd /tmp || cd / && cat a", [START, START, ("/", "/tmp")]),
    ("(cd sub); cat a", [START, START]),
    ("(cd sub && cat a); cat b", [START, ("sub",), START]),
    ("cd sub | cat a", [START, START]),
    ("cd sub & cat a", [START, START]),
    ("cd sub 2>/dev/null && cat a", [START, ("sub",)]),
    ("cd . && cat a", [START, START]),
    ("cd '' && cat a", [START, ()]),
    ("pushd sub && cat a", [START, ("sub",)]),
    ("cd -- sub && cat a", [START, ("sub",)]),
    ("command -p cd sub && cat a", [START, ("sub",)]),
    ("builtin cd sub && cat a", [START, ("sub",)]),
    ("! cd sub || cat a", [START, ("sub",)]),
    ("if cd sub; then cat a; fi", [START, MOVED]),
    ("{ cd sub; } && cat a", [START, MOVED]),
    ("command -v cd sub && cat a", [START, START]),
    ("grep cd file && cat a", [START, START]),
    ("env cd sub && cat a", [START, START]),
    ("cd $DIR && cat a", [START, None]),
    ("cd - && cat a", [START, None]),
    ("cd -P sub && cat a", [START, None]),
    ("popd && cat a", [START, None]),
    ("pushd && cat a", [START, None]),
    ("pushd +1 && cat a", [START, None]),
    ("cd $DIR; cd sub && cat a", [START, None, None]),
    ("$(echo cd) sub && cat a", [START, None]),
    ("eval cd sub; cat a", [START, None]),
    ("source env.sh; cat a", [START, None]),
    (". env.sh; cat a", [START, None]),
    ("trap 'cd sub' ERR; cat a", [START, None]),
    ("shopt -s cdable_vars; cat a", [START, None]),
    ("f() { cd sub; }; f; cat a", [START, None, None, None]),
    ("HOME=/x cd && cat a", [START, None]),
    ("cd stays && cat a", [START, ("stays",)]),
    ("cd fails && cat a", [START, ("fails",)]),
    ("cd unknown && cat a", [START, ("unknown",)]),
    ("cd -- -L && cat a", [START, ("-L",)]),
    ("command cd -- -v && cat a", [START, ("-v",)]),
    ("'if' cd sub && cat a", [START, START]),
    ("echo for; cd sub && cat a", [START, START, ("sub",)]),
    ("for i in 1 2; do cd sub; done; cat a", [START, START, None]),
    ("while cd sub; do :; done; cat a", [START, None, None]),
    ("(cd sub && true) > out", [START, ("sub",), START]),
    ("export CDPATH=/x; cd sub && cat a", [START, None, None]),
]


@pytest.mark.parametrize(("command", "expected"), DIRECTORY_CASES)
def test_each_segment_carries_the_directories_it_may_run_in(lexer, shell_world, command, expected):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [segment.directories for segment in segments] == expected


def test_an_inherited_cdpath_leaves_a_bare_relative_cd_unknown(lexer, shell_world, monkeypatch):
    _, repository = shell_world
    monkeypatch.setenv("CDPATH", "/elsewhere")

    segments = lexer.lex("cd sub && cat a; cd ./sub && cat b", str(repository))

    assert [segment.directories for segment in segments] == [START, None, None, None]


def test_cd_without_an_operand_enters_home(lexer, shell_world):
    home, repository = shell_world

    segments = lexer.lex("cd && cat a", str(repository))

    assert segments[1].directories == (str(home),)


@pytest.mark.parametrize("command", ["HOME=/x; cat ~/a", "export HOME=/x; cat $HOME/a", "HOME=/x; DEST=~/a cat"])
def test_a_home_assignment_leaves_later_home_spellings_unresolvable(lexer, shell_world, command):
    _, repository = shell_world

    words = lexer.lex(command, str(repository))[-1]

    assert "unresolvable" in [word.kind for word in words]


@pytest.mark.parametrize("command", ["cd ~/.config && cat secrets.env", "cd ~/.config; cat secrets.env"])
def test_relative_word_after_cd_carries_its_path_in_each_directory(lexer, shell_world, command):
    home, repository = shell_world

    word = lexer.lex(command, str(repository))[1][1]

    assert word.kind == "unresolvable"
    assert str(home / ".config/secrets.env") in word.paths


@pytest.mark.parametrize("command", ["cd /absent; cat sub/notes", "cd ..; cat ../sub/notes"])
def test_a_relative_path_is_not_cut_at_a_slash_into_a_root_path(lexer, shell_world, command):
    _, repository = shell_world

    word = lexer.lex(command, str(repository))[1][1]

    assert not {"/notes", "/sub/notes"} & set(word.paths)


def test_relative_word_after_a_cd_that_may_fail_carries_both_paths(lexer, shell_world):
    _, repository = shell_world

    word = lexer.lex("cd /absent; cat secrets.env", str(repository))[1][1]

    assert {str(repository / "secrets.env"), "/absent/secrets.env"} <= set(word.paths)


@pytest.mark.parametrize(
    ("spelling", "beneath"),
    [
        ("$HOME/x", "x"),
        ('"$HOME"/x', "x"),
        ("${HOME}/x", "x"),
        ('"${HOME}"/x', "x"),
        ('"$HOME/x"', "x"),
        ("$HOME", ""),
    ],
)
def test_leading_home_variable_resolves_like_a_tilde(lexer, shell_world, spelling, beneath):
    home, repository = shell_world

    word = lexer.lex(f"cat {spelling}", str(repository))[0][1]

    assert (word.value, word.kind) == (str(home / beneath) if beneath else str(home), "path candidate")


def test_leading_home_variable_takes_part_in_pathname_expansion(lexer, shell_world):
    home, repository = shell_world
    (home / ".config").mkdir()
    (home / ".config/secrets.env").touch()

    words = lexer.lex('cat "$HOME"/.config/*', str(repository))[0][1:]

    assert [word.value for word in words] == [str(home / ".config/secrets.env")]


@pytest.mark.parametrize("spelling", ["$HOMEDIR/x", "x$HOME", "'$HOME'/x", "$HOME_X"])
def test_other_home_spellings_do_not_resolve(lexer, shell_world, spelling):
    home, repository = shell_world

    word = lexer.lex(f"cat {spelling}", str(repository))[0][1]

    assert not word.value.startswith(str(home))


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("{ cat a; }", [["cat", "a"]]),
        ("if true; then head b; fi", [["true"], ["head", "b"]]),
        ("! cat a", [["cat", "a"]]),
        ("while true; do cat a; done", [["true"], ["cat", "a"]]),
        ("if ! cat a; then :; else head b; fi > out", [["cat", "a"], [":"], ["head", "b"], ["out"]]),
    ],
)
def test_a_reserved_word_leaves_the_program_in_command_position(lexer, shell_world, command, expected):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [[word.value for word in segment] for segment in segments] == expected
    assert all(segment[0].kind in {"command", "redirection target"} for segment in segments)


def test_a_quoted_reserved_word_is_the_program(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("'if' a", str(repository))

    assert [[(word.value, word.kind) for word in segment] for segment in segments] == [
        [("if", "command"), ("a", "plain word")]
    ]


@pytest.mark.parametrize("operator", ["&>", "&>>"])
def test_both_streams_redirect_within_the_segment(lexer, shell_world, operator):
    _, repository = shell_world

    segments = lexer.lex(f"cat a {operator} out", str(repository))

    assert [[(word.value, word.kind, word.redirection) for word in segment] for segment in segments] == [
        [("cat", "command", None), ("a", "plain word", None), ("out", "redirection target", operator)]
    ]


def test_a_directory_change_with_both_streams_redirected_carries_its_directory(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("cd sub &>/dev/null && cat a", str(repository))

    assert [segment.directories for segment in segments] == [("",), ("sub",)]


@pytest.mark.parametrize(
    ("spelling", "literal"), [('~"/x"', "~/x"), ("'~'/x", "~/x"), ("\\~/x", "~/x"), ('~"root"/x', "~root/x")]
)
def test_a_tilde_with_a_quoted_prefix_stays_as_written(lexer, shell_world, spelling, literal):
    _, repository = shell_world

    word = lexer.lex(f"cat {spelling}", str(repository))[0][1]

    assert word.value == literal


def test_a_tilde_before_a_quoted_path_expands(lexer, shell_world):
    home, repository = shell_world

    word = lexer.lex('cat ~/"x"', str(repository))[0][1]

    assert word.value == f"{home}/x"


@pytest.mark.parametrize("pattern", ["[^x]b", "[[:alpha:]]b", "[[=a=]]b", "[[.a.]]b"])
def test_a_bracket_expression_glob_reads_differently_is_unresolvable(lexer, shell_world, pattern):
    _, repository = shell_world
    (repository / "ab").touch()

    word = lexer.lex(f"cat {pattern}", str(repository))[0][1]

    assert word.kind == "unresolvable"
