"""Generated shell spellings shared by lexer and hook properties."""

import shlex

from hypothesis import strategies as st

GUARDED = "~/.claude/skills/sdd-sync/references/sdd-spec-formats.md"
GUARDED_DIR = "~/.claude/skills/sdd-sync"
ORDINARY = "notes.md"

# Ways a shell word can be spelled. Each takes the text a generator wants in the
# command and returns the text to write, which the shell turns back into that
# word — or into two.
# Forms the classifier resolves to the same word the shell does. Every quoting
# form belongs here, ANSI-C quoting included, because the classifier decodes it.
STABLE_FORMS = [
    lambda w: w,
    lambda w: f"'{w}'",
    lambda w: f'"{w}"',
    lambda w: "{" + w + "}",
    lambda w: "$'" + w + "'",
]

ATTACHED_FORMS = [
    lambda w: "-o" + shlex.quote(w),
    lambda w: "of=" + w,
    lambda w: "VAR=" + w,
    lambda w: "-c" + shlex.quote(w),
    lambda w: "-e" + shlex.quote(w),
]

# Forms that produce words from text the classifier cannot read: a brace
# expansion states the words directly, and a parameter expansion names a value
# the hook's own environment does not hold. Neither may be judged, so neither
# may be allowed.
UNRESOLVED_FORMS = [
    lambda w: "{" + w + ",second-word}",
    lambda w: "${HYPOTHESIS_UNSET:-" + w + "}",
    lambda w: "{" + w + ",--output=/tmp/out}",
    lambda w: "$HYPOTHESIS_UNSET" + w,
]

OPTIONS = ["-n", "-r", "--output=/tmp/out", "-o", "-delete", "--exec", "-i", "-l"]
PROGRAMS = ["cat", "head", "sort", "find", "grep", "rm", "tee", "cp"]
SEPARATORS = [" && ", " ; ", " | ", " || "]

ORDINARY_DIR = "notes"

# A filename the shell passes as an operand and the program reads as an option.
# `--` and `-` mean something to the program besides a file, and both are legal
# names, so a classifier reading operand position alone gets them wrong.
OPTION_NAMED_FILES = ["-n", "--output=/tmp/out", "-o", "--", "-"]

# Last components that reach a boundary the three fixed paths cannot.
# The two non-ASCII names are written as escapes because a spellchecker rewrites
# the characters themselves back to ASCII, which is the whole of what they test.
BOUNDARY_COMPONENTS = [
    "\ufb01le.md",  # the "fi" ligature, which normalizes onto ASCII under NFKC
    "\uff53kill.md",  # a fullwidth letter where an ASCII one is expected
    "x" * 300,  # longer than a filesystem allows one component to be
    "SKILL.md",  # differs from a real name only in case
    "a b.md",  # a space, which the shell splits on unless it is quoted
    "a\nb.md",  # a newline, which separates commands unless it is quoted
    "..",
    ".",
]


def paths() -> st.SearchStrategy[str]:
    """A path a command can name.

    The three anchors are drawn most often: a command naming nothing guarded
    reaches no gate, so it exercises little of what these properties are about.
    The rest reach the spellings a fixed set cannot — a name that is itself an
    option, a name differing from a declared one only in case, and a component
    whose bytes the filesystem will not accept as written.
    """
    anchors = st.sampled_from([GUARDED, GUARDED_DIR, ORDINARY])
    cased = st.sampled_from(
        [
            GUARDED_DIR.replace(".claude", ".Claude"),
            GUARDED.replace("sdd-sync", "SDD-SYNC"),
        ]
    )
    beneath = st.builds(
        lambda base, component: f"{base}/{component}",
        st.sampled_from([GUARDED_DIR, ORDINARY_DIR]),
        st.sampled_from(BOUNDARY_COMPONENTS),
    )
    return st.one_of(anchors, anchors, st.sampled_from(OPTION_NAMED_FILES), cased, beneath)


@st.composite
def words(draw: st.DrawFn, forms: list) -> str:
    """One shell word: a path or an option, spelled in one of `forms`."""
    payload = draw(st.one_of(paths(), st.sampled_from(OPTIONS)))
    return draw(st.sampled_from(forms))(payload)


@st.composite
def segments(draw: st.DrawFn, forms: list) -> str:
    program = draw(st.sampled_from(PROGRAMS))
    arguments = draw(st.lists(words(forms), min_size=1))
    return " ".join([program, *arguments])


@st.composite
def commands(draw: st.DrawFn, forms: list = STABLE_FORMS) -> str:
    parts = draw(st.lists(segments(forms), min_size=1, max_size=3))
    joins = [draw(st.sampled_from(SEPARATORS)) for _ in parts[1:]]
    command = parts[0]
    for join, part in zip(joins, parts[1:], strict=True):
        command += join + part
    return command


def attached_operand_commands(path: str) -> st.SearchStrategy[str]:
    """Spell the same target as an option, named operand, assignment, or program."""
    operand = shlex.quote(path)
    python_program = shlex.quote(f"open({path!r}, 'w')")
    shell_program = shlex.quote("rm " + operand)
    ruby_program = shlex.quote(f"File.delete({path!r})")
    perl_program = shlex.quote(f"unlink({path!r})")
    return st.sampled_from(
        [
            f"dd if=/tmp/source of={operand}",
            f"cp /tmp/source -t{operand}",
            f"tar -C{operand}",
            f"curl -o{operand} https://example.invalid",
            f'VAR={operand}; rm "$VAR"',
            f"python3 -c{python_program}",
            f"ruby -e{ruby_program}",
            f"perl -e{perl_program}",
            f"env sh -c {shell_program}",
            f"nice -n 5 sh -c {shell_program}",
            f"printf '%s' {shell_program} | sh",
        ]
    )


# How a list operator may be written across lines: bash reads on past a newline
# after `|`, `&&`, `||`, and `&`, and a newline ends a command as `;` does.
LINE_JOINS = {
    ";": [" ; ", "\n", " ;\n", "\n\n"],
    "&": [" & ", " &\n"],
    "&&": [" && ", " &&\n"],
    "||": [" || ", " ||\n"],
    "|": [" | ", " |\n"],
}


@st.composite
def line_pairs(draw: st.DrawFn, forms: list = STABLE_FORMS) -> tuple[str, str]:
    """Plain commands on one line, and the same commands with newlines bash reads as whitespace or `;`.

    The multi-line form may break a line after a list operator or with a line
    continuation between words, and carry comments, some ending in a
    backslash, which continues nothing.
    """
    comments = st.sampled_from(["rm notes.md", "cat " + GUARDED, "trailing \\"])
    one_line: list[str] = []
    multi_line: list[str] = []
    if draw(st.booleans()):
        multi_line.append(f"# {draw(comments)}\n")
    for index in range(draw(st.integers(min_value=1, max_value=3))):
        if index:
            operator = draw(st.sampled_from(sorted(LINE_JOINS)))
            one_line.append(f" {operator} ")
            join = draw(st.sampled_from(LINE_JOINS[operator]))
            # A comment runs to the newline, so it goes only where a line ends.
            if join.endswith("\n") and draw(st.booleans()):
                join = f"{join[:-1]} # {draw(comments)}\n"
            multi_line.append(join)
        program = draw(st.sampled_from(PROGRAMS))
        arguments = draw(st.lists(words(forms), min_size=1, max_size=3))
        # A reserved word passed as an argument stays a word.
        if draw(st.booleans()):
            arguments.append(draw(st.sampled_from(["then", "done", "if", "!", "{"])))
        one_line.append(" ".join([program, *arguments]))
        multi_line.append(draw(st.sampled_from([" ", " \\\n", " \\\n  "])).join([program, *arguments]))
    if draw(st.booleans()):
        multi_line.append(f" # {draw(comments)}")
    return "".join(one_line), "".join(multi_line)


# Forms the lexer does not read, each written where it would change the
# reading if the lexer took it for plain text; a command holding one has no
# reading.
NOT_YET_READ = [
    lambda c: f"cat <({c})",
]


@st.composite
def not_yet_read_commands(draw: st.DrawFn) -> str:
    """A multi-line command holding one form the lexer does not yet read, applied to its first command."""
    lead = draw(segments(STABLE_FORMS))
    _, rest = draw(line_pairs())
    return draw(st.sampled_from(NOT_YET_READ))(lead) + "\n" + rest


# Body lines for here-documents: shell syntax a body holds as text, and the
# tabs `<<-` strips.
BODY_LINES = st.text(alphabet="ab ;|#&\t'\"\\$`./", max_size=12)


@st.composite
def here_document_commands(draw: st.DrawFn) -> tuple[str, str | None]:
    """A command whose first program reads a here-document, with the body bash delivers.

    The body is `None` under an unquoted delimiter, where bash rewrites
    backslashes and the lexer's reading decides what the program receives.
    """
    program = draw(st.sampled_from(PROGRAMS))
    arguments = draw(st.lists(words(STABLE_FORMS), max_size=2))
    dash = draw(st.booleans())
    delimiter = draw(st.sampled_from(["EOF", "'EOF'", '"EOF"', "E\\OF"]))
    after = draw(st.sampled_from(["", " | head", "; head notes.md", " # comment"]))
    lines = draw(st.lists(BODY_LINES.filter(lambda line: line.lstrip("\t") != "EOF"), max_size=4))
    closing = ("\t" if dash and draw(st.booleans()) else "") + "EOF"
    following = draw(st.sampled_from(["", "\nhead notes.md", "\n# done"]))
    operator = "<<-" if dash else "<<"
    command = (
        " ".join([program, *arguments, operator + delimiter])
        + after
        + "\n"
        + "".join(line + "\n" for line in lines)
        + closing
        + following
    )
    body = "".join((line.lstrip("\t") if dash else line) + "\n" for line in lines)
    return command, body if delimiter != "EOF" else None


# Substitutions written so that a scan which misses their grammar ends them early
# or late: quotes, comments, and closing characters inside, and nesting.
SUBSTITUTIONS = [
    "$({inner})",
    "`{inner}`",
    '"$({inner})"',
    '"`{inner}`"',
    "${{X:-$({inner})}}",
    '"${{X:-$({inner})}}"',
    '"${{X:-\'"\'}}"',
    "$(# ' \" ) }}\n{inner})",
    "$( ({inner}) )",
    "$((1 << 2))",
]
# Inner text holding the characters a scan could take for the substitution's end.
INNER_TEXT = st.text(alphabet="ab ;#)}'\"", max_size=6)


@st.composite
def substitution_commands(draw: st.DrawFn) -> str:
    """Plain commands, on one line or several, with a substitution among the first command's words."""
    one_line, multi_line = draw(line_pairs())
    command = draw(st.sampled_from([one_line, multi_line]))
    inner = f"{draw(st.sampled_from(PROGRAMS))} {shlex.quote(draw(INNER_TEXT))}"
    substitution = draw(st.sampled_from(SUBSTITUTIONS)).format(inner=inner)
    head, _, rest = command.partition(" ")
    return f"{head} {substitution} {rest}"
