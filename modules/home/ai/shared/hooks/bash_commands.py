"""Classify a lexed Bash command: what it reads, what it runs, what it destroys.

`shell_words` produces the words; this module reads them. It applies no policy
and judges no path, so a caller supplies the declarations that decide whether a
named path matters.

`read()` classifies in one pass, and `Reading.stopping_syntax()` reports from
that same pass why the command was not recognized. A second pass would let the
two disagree and name a reason the classifier never reached.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

import shell_words
from shell_words import Segment, Word

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DESCRIPTOR = re.compile(r"(?:[0-9]+-?|-)")

# Allow utilities that only read arguments; exclude helper execution and
# write-capable options. `echo` and `printf` are harmless separators.
READ_ONLY_UTILITIES = frozenset(
    {
        "basename", "cat", "cksum", "column", "comm", "cut", "diff", "dirname",
        "du", "echo", "egrep", "fgrep", "file", "find", "fold", "grep", "head",
        "jq", "ls", "md5sum", "nl", "od", "printf", "readlink", "realpath",
        "rev", "rg", "sha1sum", "sha256sum", "shasum", "sort", "stat", "strings",
        "tail", "tr", "wc",
    }
)  # fmt: skip

# Options that make one of the above write or run something, as (short letters,
# whole tokens). A letter is sought anywhere in a cluster, so `-no` catches `-o`.
WRITE_OPTIONS = {
    "find": (
        "",
        ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fls", "-fprint",
         "-fprint0", "-fprintf"),
    ),
    "rg": ("z", ("--pre", "--search-zip", "--hostname-bin")),
    "sort": ("o", ("--output", "--compress-program")),
}  # fmt: skip

# For these commands, the specified option must come first.
REQUIRED_FIRST_OPTION = {"rg": "--no-config"}

INTERPRETERS = frozenset(
    {
        "bash", "deno", "node", "perl", "python", "python3", "ruby", "Rscript",
        "sh", "uv", "uvx", "zsh",
    }
)  # fmt: skip

# These options pass program text to an interpreter.
INLINE_CODE_OPTIONS = frozenset({"-c", "--command", "-e", "--eval", "--exec"})
SHELLS = frozenset({"bash", "sh", "zsh"})
READ_WRAPPERS = frozenset({"time", "timeout", "stdbuf", "setsid"})

# Accept executable files and known script suffixes.
SCRIPT_SUFFIXES = frozenset({".bash", ".cjs", ".js", ".mjs", ".pl", ".py", ".r", ".rb", ".sh", ".ts", ".zsh"})

# A segment holding one of these says less about what it runs than its words do.
OPAQUE_KINDS = frozenset({"unresolvable", "assignment", "redirection target"})

# These programs can destroy a declared tree through its ancestor. `mv` destroys
# all operands; `cp`, `install`, `ln`, and `truncate` replace only the last.
DESTROYS_EVERY_OPERAND = frozenset({"mv", "rm", "rmdir", "shred", "unlink"})
DESTROYS_LAST_OPERAND = frozenset({"cp", "install", "ln", "truncate"})
DESTRUCTIVE = DESTROYS_EVERY_OPERAND | DESTROYS_LAST_OPERAND

# The classifier stops on the program or on the command's shape. Substituting a
# program clears the first; the second stays whatever program runs.
UNKNOWN_PROGRAM = "a command or argument outside the recognized read and run forms"


def accepted_forms() -> str:
    """Describe the commands this module reads, for a refusal that offers an alternative."""
    required_first = "".join(
        f" {utility} requires {option} as its first option."
        for utility, option in sorted(REQUIRED_FIRST_OPTION.items())
    )
    return (
        " Recognized reads use: "
        + ", ".join(sorted(READ_ONLY_UTILITIES))
        + "."
        + required_first
        + " Existing scripts can run directly or as file arguments to: "
        + ", ".join(sorted(INTERPRETERS))
        + ". The classifier rejects redirection, environment assignments, "
        "inline code, variables, command substitutions, and brace expansions. "
        "Globs such as `*.md` are checked against their current matches. "
        "Name paths absolutely, especially after a directory change."
    )


def offers_accepted_forms(syntax: str) -> bool:
    """Whether recognition stopped on the program rather than the command's shape."""
    return syntax == UNKNOWN_PROGRAM


def descriptor_redirect(word: Word) -> bool:
    """Whether a redirection operand duplicates or closes a descriptor instead of naming a file."""
    return (
        word.kind == "redirection target"
        and (word.redirection or "").endswith("&")
        and _DESCRIPTOR.fullmatch(word.value) is not None
    )


def word_paths(word: Word, cwd: str | None) -> list[str]:
    """Paths named by a word, retaining unresolved text for fragment checks."""
    if descriptor_redirect(word):
        return []
    if word.kind == "unresolvable":
        return list(word.paths)
    value = word.value
    candidates = []
    if word.kind in {"path candidate", "redirection target", "pattern"} or (
        word.kind == "command" and any(char in value for char in "/\\~")
    ):
        candidates.append(value)
    if "=" in value and (word.kind in {"option", "assignment"} or shell_words.is_assignment(value)):
        candidates.append(os.path.expanduser(value.split("=", 1)[1]))
    if word.kind == "option" and not value.startswith("--") and len(value) > 2:
        candidates.append(os.path.expanduser(value[2:]))
    return [
        os.path.join(cwd, candidate) if not os.path.isabs(candidate) and cwd is not None else candidate
        for candidate in candidates
    ]


def invocation(segment: list[Word], *, read_only: bool = False) -> list[Word]:
    """Find the program after assignments and supported execution wrappers."""
    words = [word for word in segment if word.kind != "assignment"]
    wrappers = READ_WRAPPERS if read_only else READ_WRAPPERS | {"env", "nice", "command", "exec", "nohup", "builtin"}
    while words and os.path.basename(words[0].value) in wrappers:
        if read_only and ("/" in words[0].value or "\\" in words[0].value):
            return []
        wrapper = os.path.basename(words.pop(0).value)
        operands = {
            "env": {"-u", "--unset", "-C", "--chdir", "-a", "--argv0"},
            "nice": {"-n", "--adjustment"},
            "exec": {"-a"},
            "timeout": {"-s", "--signal", "-k", "--kill-after"},
            "stdbuf": {"-i", "--input", "-o", "--output", "-e", "--error"},
            "time": {"-f", "--format", "-o", "--output"},
        }.get(wrapper, set())
        while words:
            value = words[0].value
            if value == "--":
                words.pop(0)
                break
            if value.startswith("-"):
                if read_only and wrapper == "time" and value not in {"-p", "--portability"}:
                    return []
                words.pop(0)
                if value in operands and words:
                    words.pop(0)
            elif wrapper == "env" and shell_words.is_assignment(value):
                words.pop(0)
            else:
                break
        if wrapper == "timeout" and words:
            words.pop(0)
    return words


def program_text(segment: list[Word]) -> list[str]:
    """Extract text the segment runs now, or installs for the shell to run later."""
    words = invocation(segment)
    if not words:
        return []
    name = os.path.basename(words[0].value)
    if name == "trap":
        arguments = words[1:]
        # `trap -p` lists handlers and `trap -` resets them; neither installs a body.
        if not arguments or arguments[0].value.startswith("-"):
            return []
        return [" ".join(word.value for word in arguments)]
    if name == "eval":
        return [" ".join(word.value for word in words[1:])]
    if name == "git":
        programs = []
        for index, word in enumerate(words[1:], 1):
            if words[index - 1].value != "-c":
                continue
            key, _, value = word.value.partition("=")
            if key in {"core.pager", "core.editor", "sequence.editor", "diff.external"}:
                programs.append(value)
            elif key.startswith("alias.") and value.startswith("!"):
                programs.append(value[1:])
        return programs
    if name not in INTERPRETERS:
        return []
    programs = []
    for index, word in enumerate(words[1:], 1):
        option, separator, value = word.value.partition("=")
        if option in INLINE_CODE_OPTIONS:
            if separator:
                programs.append(value)
            elif index + 1 < len(words):
                programs.append(words[index + 1].value)
        elif not word.value.startswith("--") and word.value[:2] in {"-c", "-e"}:
            programs.append(word.value[2:])
    return programs


def defines_function(segment: Segment) -> bool:
    """Return whether this segment binds a command name to a body."""
    # `name()` lexes as a lone name terminated by `(`; `function name` keeps the keyword.
    words = [word for word in segment if word.kind != "assignment"]
    if not words:
        return False
    if segment.separator == "(" and len(words) == 1 and _NAME.match(words[0].value):
        return True
    return words[0].value == "function"


def _reads_stdin_program(segment: list[Word]) -> bool:
    """Whether a shell segment takes its program text from standard input."""
    words = invocation(segment)
    if not words or os.path.basename(words[0].value) not in SHELLS:
        return False
    args = words[1:]
    return any(word.value in {"-s", "--stdin", "-"} for word in args) or not any(
        word.kind not in {"option", "redirection target"} for word in args
    )


def _builder(segment: Segment, *, pipe_fed: bool) -> bool:
    """Whether the segment builds or runs text this reading cannot see."""
    if defines_function(segment):
        return True
    words = invocation(segment)
    if not words:
        return pipe_fed
    name = os.path.basename(words[0].value)
    if pipe_fed and (words[0].value != name or name not in READ_ONLY_UTILITIES):
        return True
    if name in {"xargs", "eval"} or program_text(segment):
        return True
    return _reads_stdin_program(segment)


def read_only(segment: list[Word]) -> bool:
    """Return whether one pipeline segment runs a utility that only reads its arguments."""
    words = [word for word in segment if not descriptor_redirect(word)]
    # `invocation` only drops leading words, so one check covers what it returns.
    if any(word.kind in OPAQUE_KINDS for word in words):
        return False
    words = invocation(words, read_only=True)
    if not words:
        return False
    name, *args = words
    # A path-qualified name picks which binary runs.
    if "/" in name.value or "\\" in name.value:
        return False
    if name.value not in READ_ONLY_UTILITIES:
        return False
    required = REQUIRED_FIRST_OPTION.get(name.value)
    if required is not None and (not args or args[0].value != required):
        return False
    letters, whole = WRITE_OPTIONS.get(name.value, ("", ()))
    for arg in args:
        if arg.kind != "option":
            continue
        if arg.value in whole or any(arg.value.startswith(f"{token}=") for token in whole):
            return False
        if letters and not arg.value.startswith("--") and any(letter in arg.value[1:] for letter in letters):
            return False
    return True


def run_targets(segment: list[Word]) -> list[str]:
    """Programs `segment` would run: a path as the command, or an interpreter's operands."""
    words = [word for word in segment if not descriptor_redirect(word)]
    if not words:
        return []
    name, *args = words
    targets = [name.value] if "/" in name.value or name.value.startswith("~") else []
    if name.value in INTERPRETERS:
        targets.extend(word.value for word in args if word.kind == "path candidate")
    return targets


def destroyed_operands(segment: list[Word]) -> list[str]:
    """Return the operands `segment` removes, renames, or replaces."""
    # A leading assignment or redirection leaves the command word later in the
    # segment; a path-qualified name picks which binary runs.
    if not segment or segment[0].kind != "command":
        return []
    name, *args = segment
    if "/" in name.value or "\\" in name.value:
        return []
    operands = [arg.value for arg in args if arg.kind != "option"]
    if name.value in DESTROYS_EVERY_OPERAND:
        return operands
    if name.value in DESTROYS_LAST_OPERAND:
        return operands[-1:]
    return []


@dataclass(frozen=True)
class SegmentReading:
    """One pipeline segment, with what its words say it does."""

    words: Segment
    defines_function: bool
    programs: tuple[str, ...]
    builder: bool
    read_only: bool
    run_targets: tuple[str, ...]
    destroyed: tuple[str, ...]


@dataclass(frozen=True)
class Reading:
    """What a Bash command runs.

    `segments` is empty and `unlexable` names the syntax where the lexer has no
    reading for the command at all.
    """

    command: str
    segments: tuple[SegmentReading, ...]
    piped_programs: tuple[str, ...]
    unlexable: str | None

    @property
    def has_builder(self) -> bool:
        """Whether any segment builds or runs text this reading cannot see."""
        return any(segment.builder for segment in self.segments)

    def stopping_syntax(self) -> str:
        """Name what kept this command from being read as a read or a run."""
        if self.unlexable is not None:
            return self.unlexable
        if any(segment.defines_function for segment in self.segments):
            return "a function definition, which rebinds a command name"
        if any(segment.programs for segment in self.segments):
            return "program text to an interpreter, eval, or trap"
        if self.has_builder:
            return "a command builder or a shell reading standard input"
        kinds = {word.kind for segment in self.segments for word in segment.words}
        if "redirection target" in kinds:
            return "a redirection"
        if "assignment" in kinds:
            return "an environment assignment"
        if "unresolvable" in kinds:
            return (
                "an unresolved substitution, variable, brace expansion, or relative path "
                "without a known directory (including after a directory change)"
            )
        return UNKNOWN_PROGRAM


def _piped_programs(segments: list[SegmentReading]) -> tuple[str, ...]:
    """Text emitted by echo or printf into a shell's standard input."""
    programs = []
    for index, segment in enumerate(segments):
        if segment.programs or not _reads_stdin_program(segment.words):
            continue
        source = index - 1
        while source >= 0 and segments[source].words.separator == "|":
            producer = invocation(segments[source].words)
            if producer and os.path.basename(producer[0].value) in {"echo", "printf"}:
                programs.append(" ".join(word.value for word in producer[1:]))
            source -= 1
    return tuple(programs)


def read(command: str, cwd: str | None = None) -> Reading:
    """Read what `command` runs, in the one pass that also names why recognition stopped."""
    lexed = shell_words.lex(command, cwd)
    if lexed is None:
        # Lexing first keeps every hook on one reading; the lexer refuses any newline.
        newline = "\n" in command or "\r" in command
        return Reading(command, (), (), "a newline" if newline else "unresolvable shell syntax")
    segments = []
    for index, words in enumerate(lexed):
        segments.append(
            SegmentReading(
                words=words,
                defines_function=defines_function(words),
                programs=tuple(program_text(words)),
                builder=_builder(words, pipe_fed=index > 0 and lexed[index - 1].separator == "|"),
                read_only=read_only(words),
                run_targets=tuple(run_targets(words)),
                destroyed=tuple(destroyed_operands(words)),
            )
        )
    return Reading(command, tuple(segments), _piped_programs(segments), None)
