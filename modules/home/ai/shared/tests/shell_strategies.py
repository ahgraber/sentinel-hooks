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
