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


@pytest.mark.parametrize(
    "command",
    [
        "cat '\x00'",
        "cat '",
        "cat a\nhead 'b",
        'cat a\nhead "b',
        "cat a\r\nhead b",
        "cat a\nhead '\x00'",
        "cat a\ncat <<< x",
        "cat a\n;; b",
        "cat a >\nb",
        "cat a\\",
        "[[ -n x; ]]",
        "[[ -n x",
    ],
)
def test_unreadable_command_returns_no_partial_reading(lexer, shell_world, command):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert segments is None


@pytest.mark.parametrize(
    ("command", "hidden"),
    [
        ("echo \"${X:-'\"'}\"; echo HIDDEN #'", ["echo", "HIDDEN"]),
        ("echo \"$(echo '\"')\"; echo HIDDEN #'", ["echo", "HIDDEN"]),
        ("echo \"`echo '\"'`\"; echo HIDDEN #'", ["echo", "HIDDEN"]),
        ("echo \"${X:-'\"'}\"\necho HIDDEN #'", ["echo", "HIDDEN"]),
        ("echo `echo a; echo b`; echo HIDDEN", ["echo", "HIDDEN"]),
        ("echo ${X:-$(# } \"'\"'\n)} ; echo HIDDEN #'", ["echo", "HIDDEN"]),
        ("echo $(#'\n); echo HIDDEN; #')", ["echo", "HIDDEN"]),
        ("cat $(#'\n); rm x; #')", ["rm", "x"]),
        ('cat "`echo"`"; rm x; " #\n" #"', ["rm", "x"]),
        ("echo $((1<<2)); echo HIDDEN", ["echo", "HIDDEN"]),
        ("echo $(cat <<'EOF'\n'\nEOF\n); echo HIDDEN; #')", ["echo", "HIDDEN"]),
        ('echo "$(cat <<\'EOF\'\nit\'s "q" )\nEOF\n)"; echo HIDDEN', ["echo", "HIDDEN"]),
        ("echo $(cat <<E1 <<-E2\n)\nE1\n\t)\n\tE2\n); echo HIDDEN", ["echo", "HIDDEN"]),
        ("echo $(echo $'\\'') ; echo HIDDEN ; echo ')'", ["echo", "HIDDEN"]),
        # A `case` pattern's `)` does not close the substitution, nor does one in a quote or a comment.
        ("echo $(case x in x) cat a;; esac); echo HIDDEN", ["echo", "HIDDEN"]),
        ('echo $(case x in x) echo ")";; esac); echo HIDDEN', ["echo", "HIDDEN"]),
        ("echo $(case x in (a|b) :;; esac # )\n); echo HIDDEN", ["echo", "HIDDEN"]),
    ],
)
def test_a_substitution_ends_where_bash_ends_it(lexer, shell_world, command, hidden):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert hidden in [[word.value for word in segment] for segment in segments]
    assert len(segments[0]) == 2


def reading(lexer, command, cwd):
    """Return what a hook judges in a command: each segment's words, separator, and directories."""
    segments = lexer.lex(command, cwd)
    assert segments is not None
    return [
        ([(word.value, word.kind, word.redirection) for word in segment], segment.separator, segment.directories)
        for segment in segments
    ]


@pytest.mark.parametrize(
    ("multi_line", "one_line"),
    [
        ("cat a\nhead b", "cat a; head b"),
        ("cd sub\ncat a", "cd sub; cat a"),
        ("cat a\n\nhead b\n", "cat a; head b"),
        ("\ncat a", "cat a"),
        ("cat a;\nhead b", "cat a; head b"),
        ("cat a &\nhead b", "cat a & head b"),
        ("cat a |\nhead", "cat a | head"),
        ("cd sub &&\ncat a", "cd sub && cat a"),
        ("cd sub ||\ncat a", "cd sub || cat a"),
        ("A=1 cat a\nhead b", "A=1 cat a; head b"),
        # A reserved word passed as an argument is a word; the newline after it ends the command.
        ("echo then\ncat a", "echo then; cat a"),
        ("echo if then\nrm a", "echo if then; rm a"),
        ("cat a\necho done", "cat a; echo done"),
        ("cat a > then\nhead b", "cat a > then; head b"),
        ("echo 'if'\ncat a", "echo 'if'; cat a"),
        # A substitution is one unresolvable word, wherever its command sits.
        ("x=$(cat a)\nhead b", "x=$(cat a); head b"),
        ("cat `echo a`\nhead b", "cat `echo a`; head b"),
        # A line continuation joins its lines before bash reads words, operators, or comments.
        ("cat a \\\n  b", "cat a b"),
        ("cat a\\\nb", "cat ab"),
        ("cat \\\n~/x", "cat ~/x"),
        ('cat "a\\\nb"', 'cat "ab"'),
        ("cd sub &\\\n& cat a", "cd sub && cat a"),
        ("cat a\\\n#x", "cat a#x"),
        # After a reserved word that leads a command, a newline ends an empty command.
        ("if true; then\ncat a\nfi", "if true; then cat a; fi"),
        ("if true\nthen\n  cat a\nelse\n  head b\nfi", "if true; then cat a; else head b; fi"),
        ("while true; do\ncat a\ndone", "while true; do cat a; done"),
        ("for i in 1 2\ndo\ncat a\ndone", "for i in 1 2; do cat a; done"),
        ("for i #c\n\tin 1 2; do\ncat a\ndone", "for i in 1 2; do cat a; done"),
        ("{\ncat a\n}", "{ cat a; }"),
        ("!\ncat a", "cat a"),
        ("cat a\n! head b", "cat a; ! head b"),
        ("time cat a\nhead b", "time cat a; head b"),
        # A subshell or an arithmetic command across lines; `<<` in `((…))` is a shift.
        ("(cat a)\nhead b", "(cat a); head b"),
        ("(\ncat a\n)", "(cat a;)"),
        ("((x<<2))\ncat a", "((x<<2)); cat a"),
        # A `case`, a function definition, and a coprocess across lines.
        ("case x in\nx) cat a;;\nesac", "case x in x) cat a;; esac"),
        ("case x\nin\n  x | y)\n    cat a\n    ;;\nesac", "case x in x|y) cat a;; esac"),
        ("function f {\ncat a\n}", "function f { cat a; }"),
        ("coproc cat a\nhead b", "coproc cat a; head b"),
        ("A\\\n=1 rm a", "A=1 rm a"),
        ("i\\\nf true; then cat a; fi", "if true; then cat a; fi"),
        ("cat <<E\\\nOF\nbody\nEOF", "cat <<EOF\nbody\nEOF"),
        ('cat "$(echo a)"\nhead b', 'cat "$(echo a)"; head b'),
        ('cat "${A}/a"\nhead b', 'cat "${A}/a"; head b'),
        ("cat ${X:-$(echo a)}\nhead b", "cat ${X:-$(echo a)}; head b"),
    ],
)
def test_a_multi_line_command_reads_as_its_one_line_form(lexer, shell_world, multi_line, one_line):
    _, repository = shell_world
    (repository / "sub").mkdir()

    assert reading(lexer, multi_line, str(repository)) == reading(lexer, one_line, str(repository))


@pytest.mark.parametrize(
    "command",
    [
        # A process substitution.
        "cat <(head\nb)",
    ],
)
def test_a_multi_line_form_the_lexer_does_not_yet_read_has_no_reading(lexer, shell_world, command):
    _, repository = shell_world

    assert lexer.lex(command, str(repository)) is None


@pytest.mark.parametrize(
    ("command", "value"),
    [
        ("cat 'a\nb'", "a\nb"),
        ('cat "a\nb"', "a\nb"),
        ("cat 'a\\\nb'", "a\\\nb"),
        ("cat $'a\nb'", "a\nb"),
    ],
)
def test_a_quoted_newline_is_part_of_the_word(lexer, shell_world, command, value):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [[word.value for word in segment] for segment in segments] == [["cat", value]]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat a # head b", [["cat", "a"]]),
        ("# rm b\ncat a", [["cat", "a"]]),
        ("cat a\n# rm b\nhead c", [["cat", "a"], ["head", "c"]]),
        ("cat a # rm b\nhead c", [["cat", "a"], ["head", "c"]]),
        ("cat a # rm b \\\nhead c", [["cat", "a"], ["head", "c"]]),
        ("cat a # if (`$(\nhead c", [["cat", "a"], ["head", "c"]]),
        ("cat a#b", [["cat", "a#b"]]),
        ("cat '#b'", [["cat", "#b"]]),
        ('cat "#b"', [["cat", "#b"]]),
        ("cat \\#b", [["cat", "#b"]]),
        ("cat $#", [["cat", "$#"]]),
        ("cat ${#x}", [["cat", "${#x}"]]),
    ],
)
def test_a_comment_runs_to_the_end_of_its_line(lexer, shell_world, command, expected):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [[word.value for word in segment] for segment in segments] == expected


@pytest.mark.parametrize(
    ("command", "name"),
    [
        ("X=1 if cat file", "if"),
        ("> out if cat file", "if"),
        ("X=1 [[ -n x ]]", "[["),
        ("> out [[ -n x ]]", "[["),
        ("X=1 if cat file\nhead b", "if"),
        ("X=1 time cat file\nhead b", "time"),
    ],
)
def test_a_reserved_word_after_an_assignment_or_a_redirection_is_a_command_name(lexer, shell_world, command, name):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [word.value for word in segments[0] if word.kind == "command"] == [name]


@pytest.mark.parametrize(
    "command", ["((cat)); echo HIDDEN", "((cat<<2)); echo HIDDEN", "((x = (1 + 2))) && echo HIDDEN"]
)
def test_an_arithmetic_command_runs_no_program(lexer, shell_world, command):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [word.kind for word in segments[0]] == ["unresolvable"]
    assert [word.value for word in segments[-1]] == ["echo", "HIDDEN"]


@pytest.mark.parametrize("command", ["((cat) ); echo x", "(( $(rm x) )); echo x", "((`rm x`)); echo x", "((x)"])
def test_an_arithmetic_command_bash_may_read_otherwise_is_unresolvable(lexer, shell_world, command):
    _, repository = shell_world

    assert lexer.lex(command, str(repository)) is None


@pytest.mark.parametrize(
    "command",
    [
        "[[ -S a && -L b ]] && echo HIDDEN",
        "[[ ( -n x )]]; echo HIDDEN",
        "[[ x =~ (a|b) ]] || echo HIDDEN",
        "[[ x < y ]]; echo HIDDEN",
        '[[ "]]" ]]; echo HIDDEN',
        "[[ $(echo ]]) ]]; echo HIDDEN",
        "! [[ -n x ]] || echo HIDDEN",
        "[[ -n x\n]] && echo HIDDEN",
        "[[ # ]]\n-n x ]]; echo HIDDEN",
        "[[ -n x \\\n]] && echo HIDDEN",
    ],
)
def test_a_conditional_expression_runs_no_program(lexer, shell_world, command):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [word.kind for word in segments[0]] == ["unresolvable"]
    assert [word.value for word in segments[-1]] == ["echo", "HIDDEN"]


def test_a_conditional_expression_keeps_its_written_paths(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("[[ -f /etc/secret && -r ~/notes ]]", str(repository))

    assert {"/etc/secret", "~/notes"} <= set(segments[0][0].paths)


@pytest.mark.parametrize(("command", "name"), [("[[-n x ]]", "[[-n"), ("echo [[ -n x ]]", "echo")])
def test_double_brackets_outside_command_position_are_a_word(lexer, shell_world, command, name):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [word.value for word in segments[0] if word.kind == "command"] == [name]


@pytest.mark.parametrize(
    "command",
    [
        "a+=1 rm x",
        "a[0]=1 rm x",
        "a[ i ]+=1 rm x",
        "a[x[1]]=1 rm x",
        "a=(1 2) rm x",
        "a=(\n1\n2) rm x",
        "X=1 a=( $(echo) ) rm x",
    ],
)
def test_an_array_or_append_assignment_leaves_the_program_in_command_position(lexer, shell_world, command):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert len(segments) == 1
    assert [word.value for word in segments[0] if word.kind == "command"] == ["rm"]


@pytest.mark.parametrize(
    ("command", "words"),
    [
        ("declare a=(1 2) b; echo x", ["declare", "a=(1 2)", "b"]),
        ("let a=(1 + 2) b=3; echo x", ["let", "a=(1 + 2)", "b=3"]),
        ("X=1 export a=(1)> out; echo x", ["X=1", "export", "a=(1)", "out"]),
    ],
)
def test_an_assignment_builtin_takes_an_array_value_as_one_word(lexer, shell_world, command, words):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [word.value for word in segments[0]] == words
    assert [word.value for word in segments[1]] == ["echo", "x"]


def test_an_array_value_keeps_its_written_paths(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("a=( /etc/secret [k]=~/notes ) cat", str(repository))

    assert segments[0][0].kind == "unresolvable"
    assert {"/etc/secret", "~/notes"} <= set(segments[0][0].paths)


def test_a_subscript_that_closes_before_its_word_ends_names_the_program(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("a[x]]=1 rm x", str(repository))

    assert [word.kind for word in segments[0]] == ["unresolvable", "plain word", "plain word"]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat 'a\\\nb'", [["cat", "a\\\nb"]]),
        ("cat $'a\\\nb'", [["cat", "a\\\nb"]]),
        ("cat a # c \\\nhead b", [["cat", "a"], ["head", "b"]]),
        ("cat a\\\\\nhead b", [["cat", "a\\"], ["head", "b"]]),
    ],
)
def test_a_backslash_newline_bash_keeps_is_not_a_continuation(lexer, shell_world, command, expected):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [[word.value for word in segment] for segment in segments] == expected


def test_a_continuation_inside_unresolvable_text_keeps_the_joined_path(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("cat $(cat /etc/sec\\\nret)", str(repository))

    assert "/etc/secret" in segments[0][1].paths


@pytest.mark.parametrize("command", ["if cat file; then :; fi", "! cat file", "{ cat file; }"])
def test_a_reserved_word_first_in_a_command_is_not_its_program(lexer, shell_world, command):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [word.value for word in segments[0] if word.kind == "command"] == ["cat"]


@pytest.mark.parametrize("character", ["\v", "\f", "\xa0", "\u2003", "\x1c", "\x85"])
@pytest.mark.parametrize("after", ["", "\nhead c"])
def test_only_space_and_tab_separate_words(lexer, shell_world, character, after):
    _, repository = shell_world

    segments = lexer.lex(f"cat a{character}#; rm b{after}", str(repository))

    expected = [["cat", f"a{character}#"], ["rm", "b"]] + ([["head", "c"]] if after else [])
    assert [[word.value for word in segment] for segment in segments] == expected


@pytest.mark.parametrize(
    ("command", "operator"),
    [("foo {fd}<f", "{fd}<"), ("foo {fds[3]}<f", "{fds[3]}<"), ("cat {x}>f", "{x}>"), ("cat 2>f", "2>")],
)
def test_a_named_descriptor_is_part_of_its_redirection(lexer, shell_world, command, operator):
    _, repository = shell_world

    (segment,) = lexer.lex(command, str(repository))

    assert [(word.value, word.redirection) for word in segment[1:]] == [("f", operator)]


def test_a_here_document_kind_is_declared(lexer):
    assert "here-document" in lexer.Kind.__args__


@pytest.mark.parametrize(
    ("command", "body"),
    [
        ("cat <<'EOF'\nrm a; cat b\n# c\nEOF", "rm a; cat b\n# c\n"),
        ('cat <<"EOF"\n$HOME `x`\nEOF', "$HOME `x`\n"),
        ("cat <<E\\OF\n$x\nEOF", "$x\n"),
        ("cat <<EOF\nplain text\nEOF", "plain text\n"),
        ("cat <<EOF\nEOF", ""),
        ("cat <<EOF\na\\\\b\nEOF", "a\\b\n"),
        ("cat <<'EOF'\na\nEOF\n", "a\n"),
        ("cat <<'EOF'\na\nEOF \nEOF", "a\nEOF \n"),
        ("cat <<'EOF'\na\n EOF\nEOF", "a\n EOF\n"),
        ("cat <<-'EOF'\n\t\ta\n  b\n\tEOF", "a\n  b\n"),
        ("cat <<'EOF'\n\ta\n\tEOF\nEOF", "\ta\n\tEOF\n"),
        # A delimiter is taken after quote removal alone; any quoting keeps the body literal.
        ("cat <<$X\na\n$X", "a\n"),
        ("cat <<${HOME}\na\n${HOME}", "a\n"),
        ('cat <<a"b"c\n$x\nabc', "$x\n"),
        ("cat <<$'E'\n$x\nE", "$x\n"),
        # An unquoted body loses only the backslashes before `$`, a backquote, or a backslash.
        ('cat <<EOF\na \\$x \\`y\\` \\\\ \\" \\z\nEOF', 'a $x `y` \\ \\" \\z\n'),
        ("cat <<-EOF\n\ta\\\n\tb\nEOF", "a\tb\n"),
    ],
)
def test_a_here_document_body_is_one_word(lexer, shell_world, command, body):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [[word.kind for word in segment] for segment in segments] == [["command", "here-document"]]
    assert segments[0][1].redirection in {"<<", "<<-"}
    assert segments[0][1].value == body


@pytest.mark.parametrize("command", ["cat <<EOF\n$X /guarded/file\nEOF", "cat <<EOF\n`x` /guarded/file\nEOF"])
def test_an_unquoted_body_with_an_expansion_is_unresolvable(lexer, shell_world, command):
    _, repository = shell_world

    word = lexer.lex(command, str(repository))[0][-1]

    assert (word.kind, word.redirection) == ("unresolvable", "<<")
    assert "/guarded/file" in word.paths


@pytest.mark.parametrize(
    ("command", "header", "body"),
    [
        ('for f in a b; do cat "$f"; done', ["for", "a", "b"], ["cat", "$f"]),
        ("for i do foo; done", ["for"], ["foo"]),
        ("for i in; do foo; done", ["for"], ["foo"]),
        ("select i; do foo; done", ["select"], ["foo"]),
        ("for ((i=0;i<3;i++)) do echo x; done", ["for", "((i=0;i<3;i++))"], ["echo", "x"]),
        ("for f in rm a; do echo; done", ["for", "rm", "a"], ["echo"]),
    ],
)
def test_a_loop_header_is_a_segment_that_runs_no_program(lexer, shell_world, command, header, body):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [word.value for word in segments[0]] == header
    assert segments[0].loop_header
    assert "command" not in [word.kind for word in segments[0]]
    assert [word.value for word in segments[1]] == body
    assert not segments[1].loop_header


@pytest.mark.parametrize(
    "command", ["for f in a > x; do :; done", "for f in a | cat; do :; done", "for a b; do :; done"]
)
def test_a_loop_header_bash_refuses_has_no_reading(lexer, shell_world, command):
    _, repository = shell_world

    assert lexer.lex(command, str(repository)) is None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            "case $(x) in a) cat a;; b|c) rm b;& *) echo;;& d) head d;; esac; echo HIDDEN",
            [["case", "$(x)"], ["cat", "a"], ["rm", "b"], ["echo"], ["head", "d"], ["echo", "HIDDEN"]],
        ),
        ("case x in $(rm p)) cat a;; esac", [["case", "$(rm p)"], ["cat", "a"]]),
        ("case x in (a) cat a;; esac", [["cat", "a"]]),
        ("case x in a) cat a; esac", [["cat", "a"]]),
        ("case x in a) echo esac;; esac", [["echo", "esac"]]),
        ("case x in a) case y in b) cat b;; esac;; esac", [["cat", "b"]]),
        ("case x in a) (cat a);; esac | head", [["cat", "a"], ["head"]]),
        ("coproc cat a", [["cat", "a"]]),
        ("coproc NAME { cat a; }", [["cat", "a"]]),
        ("coproc NAME [[\t-n x ]]", [["[[\t-n x ]]"]]),
        ("coproc NAME ((x))", [["((x))"]]),
        ("coproc NAME cat a", [["NAME", "cat", "a"]]),
        ("function f { cat a; }", [["function", "f"], ["cat", "a"]]),
    ],
)
def test_case_coproc_and_function_read_as_bash_reads_them(lexer, shell_world, command, expected):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [[word.value for word in segment] for segment in segments] == expected


@pytest.mark.parametrize("command", ["case x", "case x in a) cat a", "case x of a) cat a;; esac", "function"])
def test_a_case_or_function_bash_refuses_has_no_reading(lexer, shell_world, command):
    _, repository = shell_world

    assert lexer.lex(command, str(repository)) is None


@pytest.mark.parametrize("operator", ["|&", "&&", "||", "&>", "&>>", ">>", ";;", "&\\\n&"])
def test_an_operator_at_the_end_of_the_text_ends_the_scan(lexer, shell_world, operator):
    _, repository = shell_world

    segments = lexer.lex(f"cat a {operator}", str(repository))

    assert segments is None or segments[0][0].value == "cat"


@pytest.mark.parametrize(
    "command",
    [
        "echo $(case x in " + "a) :;; " * 200 + "esac)",
        "echo $(case x in a) $(case y in " + "b) :;; " * 20 + "esac);; esac)",
    ],
)
def test_a_case_substitution_with_more_closes_than_the_budget_has_no_reading(lexer, shell_world, command):
    _, repository = shell_world

    assert lexer.lex(command, str(repository)) is None


def test_a_continuation_joins_a_body_line_before_the_delimiter_is_matched(lexer, shell_world):
    _, repository = shell_world

    segments = lexer.lex("cat <<EOF\nE\\\nOF\nrm a\nEOF", str(repository))

    assert [[word.value for word in segment] for segment in segments] == [["cat", ""], ["rm", "a"], ["EOF"]]


@pytest.mark.parametrize(
    "command",
    [
        "cat <<$(echo E)\na\nE",
        "cat <<EOF\na",
        "cat <<'EOF'\na\nEOF ",
        "cat <<EOF",
        "cat << ;\na",
        "cat <<EOF <<END\na\nEOF",
        # Under an unquoted delimiter a line continuation joins the next line, delimiter included.
        "cat <<EOF\na\\\nEOF",
        # A here-document inside a substitution whose body never starts.
        "echo $(cat <<EOF)\nx\nEOF\necho HIDDEN",
    ],
)
def test_an_unreadable_here_document_makes_the_command_unresolvable(lexer, shell_world, command):
    _, repository = shell_world

    assert lexer.lex(command, str(repository)) is None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat <<'EOF' | tr a b\nx\nEOF", [["cat", "x\n"], ["tr", "a", "b"]]),
        ("cat <<'EOF'; head c\nx\nEOF", [["cat", "x\n"], ["head", "c"]]),
        ("cat <<'EOF' |\nx\nEOF\ntr a b", [["cat", "x\n"], ["tr", "a", "b"]]),
        ("cat <<'EOF'\nx\nEOF\nhead c", [["cat", "x\n"], ["head", "c"]]),
        ("cat <<'A' <<'B'\none\nA\ntwo\nB", [["cat", "one\n", "two\n"]]),
        ("cat <<'A'; cat <<'B'\none\nA\ntwo\nB", [["cat", "one\n"], ["cat", "two\n"]]),
        ("cat 0<<'EOF'\nx\nEOF", [["cat", "x\n"]]),
        ("cat <<'EOF' # c\nx\nEOF", [["cat", "x\n"]]),
    ],
)
def test_here_document_bodies_follow_their_operators_line(lexer, shell_world, command, expected):
    _, repository = shell_world

    segments = lexer.lex(command, str(repository))

    assert [[word.value for word in segment] for segment in segments] == expected
    bodies = [word for segment in segments for word in segment if word.redirection and "<<" in word.redirection]
    assert all(word.kind == "here-document" for word in bodies)


def test_a_here_string_is_read_as_on_one_line(lexer, shell_world):
    _, repository = shell_world

    assert lexer.lex("cat <<< x", str(repository)) is None


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
    ("cd sub && [[ -n x ]] && cat a", [START, ("sub",), ("sub",)]),
    ("cd sub && ((1)) && cat a", [START, ("sub",), ("sub",)]),
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


@pytest.mark.parametrize(
    "command",
    [
        "HOME=/x; cat ~/a",
        "export HOME=/x; cat $HOME/a",
        "HOME=/x; DEST=~/a cat",
        "HOME+=/x; cat ~/a",
        "HOME[0]=/x; cat ~/a",
    ],
)
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
