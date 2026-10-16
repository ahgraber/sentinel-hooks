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

from hook_response import Instruction
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
    "file": ("zZC", ("--uncompress", "--uncompress-noreport", "--compile")),
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
_SHELL_CODE_CLUSTER = re.compile(r"-[A-Za-z]*c[A-Za-z]*")
READ_WRAPPERS = frozenset({"time", "timeout", "stdbuf", "setsid"})

# Accept executable files and known script suffixes.
SCRIPT_SUFFIXES = frozenset({".bash", ".cjs", ".js", ".mjs", ".pl", ".py", ".r", ".rb", ".sh", ".ts", ".zsh"})

# A segment holding one of these says less about what it runs than its words do.
# A redirection target is not among them: the command text names it, and a
# caller judges it by direction, an input as a read and an output as a write.
OPAQUE_KINDS = frozenset({"unresolvable", "assignment"})

# Privilege wrappers, with the options that take a value.
_PRIVILEGE_WRAPPERS = {"sudo": {"-u", "-g", "-U", "-h", "-p", "-C", "-D", "-r", "-t"}, "doas": {"-u", "-C"}}
_GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
_ACL_FLAG = re.compile(r"^[-+=]a\S*$")
FIND_EXEC_ACTIONS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_FIND_ACTIONS = FIND_EXEC_ACTIONS | {"-delete"}
_FIND_LEADING_OPTIONS = frozenset({"-H", "-L", "-P", "-E", "-X", "-d", "-s", "-x"})
_UNZIP_INSPECTS = frozenset({"-l", "-t", "-v", "-Z", "-z", "-Z1"})

# The classifier stops on the program or on the command's shape. Substituting a
# program clears the first; the second stays whatever program runs.
UNKNOWN_PROGRAM = "a command or argument outside the recognized read and run forms"
# A shape stop the agent can resolve: the same command with each path absolute is judged in full.
RELATIVE_PATH = "a relative path after a directory change or without a known directory"


def read_forms() -> str:
    """Describe the reads this module recognizes, for a refusal that offers one."""
    required_first = "".join(
        f" {utility} requires {option} as its first option."
        for utility, option in sorted(REQUIRED_FIRST_OPTION.items())
    )
    return " Recognized reads use: " + ", ".join(sorted(READ_ONLY_UTILITIES)) + "." + required_first


def accepted_forms() -> str:
    """Describe the commands this module reads or runs, for a refusal that offers an alternative."""
    return (
        read_forms()
        + " Existing scripts can run directly or as file arguments to: "
        + ", ".join(sorted(INTERPRETERS))
        + ". A redirection's target is judged by direction: an input as a read, an output as a write. "
        "The classifier rejects environment assignments, "
        "inline code, variables, command substitutions, and brace expansions. "
        "Globs such as `*.md` are checked against their current matches. "
        "Name paths absolutely, especially after a directory change."
    )


def offers_accepted_forms(syntax: str) -> bool:
    """Whether recognition stopped on the program rather than the command's shape."""
    return syntax == UNKNOWN_PROGRAM


def asks_for_absolute_paths(syntax: str) -> bool:
    """Whether recognition stopped only on relative paths whose directory is unknown."""
    return syntax == RELATIVE_PATH


def refusal_instruction(syntax: str) -> Instruction:
    """Choose the instruction a refusal for `syntax` ends with, per `hook-interface` `BlockAIGuidance`."""
    if offers_accepted_forms(syntax):
        return Instruction.RETRY
    if asks_for_absolute_paths(syntax):
        return Instruction.ABSOLUTE_PATH
    return Instruction.STOP


ABSOLUTE_PATH_HINT = " Name every path absolutely; the restated command is judged in full."


def descriptor_redirect(word: Word) -> bool:
    """Whether a redirection operand duplicates or closes a descriptor instead of naming a file."""
    return (word.redirection or "").endswith("&") and _DESCRIPTOR.fullmatch(word.value) is not None


def redirect_writes(word: Word) -> bool:
    """Whether a redirection opens the file it names for writing, as `>`, `>>`, `&>`, and `<>` do.

    The operator decides, not the word's kind: a target the lexer cannot
    resolve is still opened for writing.
    """
    return ">" in (word.redirection or "") and not descriptor_redirect(word)


# A segment of only these and redirections runs nothing; its redirections are its whole effect.
_NO_OP_PROGRAMS = frozenset({":", "true", "exec"})


def only_redirects(segment: list[Word]) -> bool:
    """Return whether a segment does nothing but redirect, as `> file`, `: > file`, and `exec 3> file` do."""
    words = [word for word in segment if word.kind != "redirection target"]
    return not words or (len(words) == 1 and words[0].kind == "command" and words[0].value in _NO_OP_PROGRAMS)


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
    words = invoked(segment)
    if not words:
        return []
    name = os.path.basename(words[0].value)
    if name == "su":
        return _su_code(words)
    if name == "trap":
        arguments = words[1:]
        # `--` ends the options, so the body follows it.
        if arguments and arguments[0].value == "--":
            arguments = arguments[1:]
            if not arguments or arguments[0].value == "-":
                return []
        # `trap -p` lists handlers and `trap -` resets them; neither installs a body.
        elif not arguments or arguments[0].value.startswith("-"):
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
    return _inline_code(name, words)


def _inline_code(name: str, words: list[Word]) -> list[str]:
    """Extract the code an interpreter's options pass it inline."""
    programs = []
    for index, word in enumerate(words[1:], 1):
        following = words[index + 1].value if index + 1 < len(words) else None
        option, separator, value = word.value.partition("=")
        if option in INLINE_CODE_OPTIONS:
            code = value if separator else following
        elif name in SHELLS and _SHELL_CODE_CLUSTER.fullmatch(word.value):
            # `bash -lc '<code>'`: the code is the next word, not the rest of the cluster.
            code = following
        elif not word.value.startswith("--") and word.value[:2] in {"-c", "-e"}:
            code = word.value[2:]
        else:
            code = None
        if code is not None:
            programs.append(code)
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


def _su_code(words: list[Word]) -> list[str]:
    """Return the text `su -c` or `su --command` passes to the target user's shell."""
    for index, word in enumerate(words[1:], 1):
        if word.value.startswith("--command="):
            return [word.value.partition("=")[2]]
        if word.value in {"-c", "--command"} and index + 1 < len(words):
            return [words[index + 1].value]
    return []


def _privileged_shell(segment: list[Word]) -> bool:
    """Whether `sudo -s`, `sudo -i`, or `doas -s` starts a shell with no command, which reads its standard input."""
    values = {word.value for word in segment}
    wrapped = any(os.path.basename(value) in _PRIVILEGE_WRAPPERS for value in values)
    return wrapped and bool(values & {"-s", "--shell", "-i", "--login"})


def reads_stdin_program(segment: list[Word]) -> bool:
    """Whether a shell segment takes its program text from standard input."""
    words = invoked(segment)
    if not words:
        return _privileged_shell(segment)
    if os.path.basename(words[0].value) == "su":
        return not _su_code(words)
    if os.path.basename(words[0].value) not in SHELLS:
        return False
    args = words[1:]
    return any(word.value in {"-s", "--stdin", "-"} for word in args) or not any(
        word.kind not in {"option", "redirection target"} for word in args
    )


def _builder(segment: Segment, *, pipe_fed: bool) -> bool:
    """Whether the segment builds or runs text this reading cannot see."""
    if defines_function(segment):
        return True
    words = invoked(segment)
    if not words:
        return pipe_fed
    name = os.path.basename(words[0].value)
    if pipe_fed and (words[0].value != name or name not in READ_ONLY_UTILITIES):
        return True
    if name in {"xargs", "eval"} or program_text(segment):
        return True
    return reads_stdin_program(segment)


def read_only(segment: list[Word]) -> bool:
    """Return whether one pipeline segment runs a utility that only reads its arguments.

    Redirections are left to the caller, which judges each target by direction.
    """
    words = [word for word in segment if word.kind != "redirection target"]
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
        # GNU utilities accept any unambiguous prefix of a long option.
        stem = arg.value.split("=", 1)[0]
        if len(stem) > 2 and stem.startswith("--") and any(token.startswith(stem) for token in whole):
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


def _operands(args: list[Word]) -> list[str]:
    return [arg.value for arg in args if arg.kind != "option"]


def _option_value(args: list[Word], *names: str) -> str | None:
    """Return the value given to the first of `names`, written separately or after `=`."""
    for index, arg in enumerate(args):
        for name in names:
            if arg.value == name and index + 1 < len(args):
                return args[index + 1].value
            if name.startswith("--") and arg.value.startswith(name + "="):
                return arg.value.split("=", 1)[1]
    return None


def _destination(args: list[Word]) -> list[str]:
    """Return the destination of `cp`, `install`, or `ln`: the `-t` value, or the last operand."""
    target = _option_value(args, "--target-directory")
    if target:
        return [target]
    for index, arg in enumerate(args):
        value = arg.value
        if value.startswith("-") and not value.startswith("--") and "t" in value[1:]:
            # `t` takes the rest of its cluster, or the next word when it ends the cluster.
            rest = value[value.index("t", 1) + 1 :]
            if rest:
                return [rest]
            if index + 1 < len(args):
                return [args[index + 1].value]
    return _operands(args)[-1:]


def _after_mode(args: list[Word]) -> list[str]:
    """Operands after the mode, owner, or flags; every operand after `--reference` or an ACL flag."""
    values = [arg.value for arg in args]
    if any(value.startswith("--reference") or _ACL_FLAG.match(value) for value in values):
        return _operands(args)
    return _operands(args)[1:]


def _find_roots(args: list[Word], implicit: str | None) -> list[str]:
    """Return the starting points of a `find` that deletes or runs a program."""
    if not any(arg.value in _FIND_ACTIONS for arg in args):
        return []
    roots = []
    for arg in args:
        if not roots and arg.value in _FIND_LEADING_OPTIONS:
            continue
        if arg.value.startswith(("-", "(", "!")):
            break
        roots.append(arg.value)
    return roots or ([implicit] if implicit else [])


def _tar_extracts(args: list[Word]) -> bool:
    for index, arg in enumerate(args):
        value = arg.value
        if value in {"--extract", "--get"}:
            return True
        if value.startswith("-") and not value.startswith("--") and "x" in value[1:]:
            return True
        if index == 0 and not value.startswith("-") and "x" in value:
            return True
    return False


def _tar_target(args: list[Word], implicit: str | None) -> list[str]:
    """Where an extracting `tar` writes."""
    if not _tar_extracts(args):
        return []
    directory = _option_value(args, "-C", "--directory") or implicit
    return [directory] if directory else []


def _unzip_target(args: list[Word], implicit: str | None) -> list[str]:
    """Where `unzip` writes, unless it only lists or tests."""
    if any(arg.value in _UNZIP_INSPECTS for arg in args):
        return []
    directory = _option_value(args, "-d") or implicit
    return [directory] if directory else []


def _git_targets(args: list[Word], cwd_known: bool) -> list[str]:
    """Paths a git command reverts, removes, or detaches."""
    base = _option_value(args, "-C")
    index = 0
    while index < len(args) and args[index].value.startswith("-"):
        index += 2 if args[index].value in _GIT_VALUE_OPTIONS else 1
    if index >= len(args):
        return []
    subcommand, rest = args[index].value, args[index + 1 :]
    if subcommand == "stash":
        if not rest or rest[0].value not in {"push", "save"}:
            return []
        rest = rest[1:]
    elif subcommand == "worktree":
        if not rest or rest[0].value != "remove":
            return []
        rest = rest[1:]
    elif subcommand not in {"checkout", "restore", "rm", "clean"}:
        return []
    values = [arg.value for arg in rest]
    if "--" in values:
        targets = values[values.index("--") + 1 :]
    elif cwd_known:
        # A revision name resolves beneath the working directory and encloses nothing.
        targets = _operands(rest)
    else:
        targets = []
    return [os.path.join(base, target) if base and not os.path.isabs(target) else target for target in targets]


def _strip_privilege(words: list[Word]) -> list[Word]:
    while words and os.path.basename(words[0].value) in _PRIVILEGE_WRAPPERS:
        value_options = _PRIVILEGE_WRAPPERS[os.path.basename(words.pop(0).value)]
        while words and words[0].value.startswith("-"):
            if words.pop(0).value in value_options and words:
                words.pop(0)
    return words


def invoked(segment: list[Word]) -> list[Word]:
    """Return the program and its arguments, past privilege and execution wrappers in any order and nesting."""
    words = list(segment)
    while True:
        words = _strip_privilege([word for word in words if word.kind != "assignment"])
        # `command -v` and `command -V` name a program without running it.
        if shell_words.command_position(words) is None:
            return []
        unwrapped = invocation(words)
        if unwrapped == words:
            return unwrapped
        words = unwrapped


# Options that take a separate value, for the programs that launch a command from their arguments.
# GNU `-e`, `-i`, and `-l` take only an attached value, so they are absent.
_XARGS_VALUE_OPTIONS = frozenset(
    {
        "-a", "--arg-file", "-d", "--delimiter", "-E", "--eof", "-I", "--replace", "-J", "-L",
        "--max-lines", "-n", "--max-args", "-P", "--max-procs", "-R", "-S", "-s", "--max-chars",
        "--process-slot-var",
    }
)  # fmt: skip
_WATCH_VALUE_OPTIONS = frozenset({"-n", "--interval"})


def _after_options(words: list[Word], value_options: frozenset[str]) -> list[Word]:
    """Return the words from the first operand on, skipping options and the values listed options take."""
    index = 0
    while index < len(words) and words[index].value.startswith("-") and words[index].value != "-":
        if words[index].value == "--":
            return words[index + 1 :]
        index += 1 + (words[index].value in value_options)
    return words[index:]


def launched_arguments(words: list[Word]) -> list[list[Word]]:
    """Return the argument lists a launcher (`xargs`, `find` actions) executes directly."""
    name = os.path.basename(words[0].value) if words else ""
    if name == "xargs":
        return [_after_options(words[1:], _XARGS_VALUE_OPTIONS)]
    if name != "find":
        return []
    commands, current = [], None
    for word in words[1:]:
        if current is None:
            current = [] if word.value in FIND_EXEC_ACTIONS else None
        elif word.value in {";", "+"}:
            commands.append(current)
            current = None
        else:
            current.append(word)
    return commands


def watch_script(words: list[Word]) -> list[str]:
    """Return the text `watch` runs: its arguments joined for `sh -c`, which loses their quoting."""
    if not words or os.path.basename(words[0].value) != "watch":
        return []
    return [" ".join(word.value for word in _after_options(words[1:], _WATCH_VALUE_OPTIONS))]


def destroyed_operands(segment: list[Word], *, cwd_known: bool = True, directory: str | None = "") -> list[str]:
    """Return the operands `segment` removes, renames, replaces, or changes the permissions of.

    `directory` is where earlier `cd`s left the shell: `""` for none, `None` if unknown.
    """
    words = _strip_privilege([word for word in segment if word.kind != "redirection target"])
    base = directory
    if words and os.path.basename(words[0].value) == "env":
        chdir = _option_value(words[1:], "-C", "--chdir")
        if chdir is not None:
            base = os.path.join(base or "", chdir) if base is not None else None
    words = invocation(words)
    if not words:
        return []
    name, args = os.path.basename(words[0].value), words[1:]
    extract = _OPERAND_EXTRACTORS.get(name)
    if extract is None:
        return []
    targets = extract(args, cwd_known, "." if base is not None else None)
    return [os.path.join(base, target) if base and not os.path.isabs(target) else target for target in targets]


# Programs that can take a tree away, mapped to the operands they act on.
# A program missing here passes on an ancestor.
_OPERAND_EXTRACTORS = {
    **dict.fromkeys(
        ("mv", "rm", "rmdir", "shred", "unlink", "trash", "xattr", "setfacl"), lambda a, _c, _i: _operands(a)
    ),
    **dict.fromkeys(("cp", "install", "ln"), lambda a, _c, _i: _destination(a)),
    **dict.fromkeys(("truncate", "ditto", "rsync"), lambda a, _c, _i: _operands(a)[-1:]),
    **dict.fromkeys(("chmod", "chown", "chgrp", "chflags"), lambda a, _c, _i: _after_mode(a)),
    "find": lambda a, _c, implicit: _find_roots(a, implicit),
    **dict.fromkeys(("tar", "bsdtar", "gtar"), lambda a, _c, implicit: _tar_target(a, implicit)),
    "unzip": lambda a, _c, implicit: _unzip_target(a, implicit),
    "git": lambda a, cwd_known, _i: _git_targets(a, cwd_known),
}
DESTRUCTIVE = frozenset(_OPERAND_EXTRACTORS)


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
    # False after a `cd` the words do not resolve.
    anchored: bool = True


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
        if "assignment" in kinds:
            return "an environment assignment"
        unresolved = [word.value for segment in self.segments for word in segment.words if word.kind == "unresolvable"]
        if unresolved and not any(char in value for value in unresolved for char in "$`{*?["):
            return RELATIVE_PATH
        if unresolved:
            return "an unresolved substitution, variable, glob, or brace expansion"
        return UNKNOWN_PROGRAM


def _piped_programs(segments: list[SegmentReading]) -> tuple[str, ...]:
    """Text emitted by echo or printf into a shell's standard input."""
    programs = []
    for index, segment in enumerate(segments):
        if segment.programs or not reads_stdin_program(segment.words):
            continue
        source = index - 1
        while source >= 0 and segments[source].words.separator == "|":
            producer = invoked(segments[source].words)
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
        directories = (None,) if words.directories is None else words.directories
        destroyed = (
            target
            for directory in directories
            for target in destroyed_operands(words, cwd_known=cwd is not None, directory=directory)
        )
        segments.append(
            SegmentReading(
                words=words,
                defines_function=defines_function(words),
                programs=tuple(program_text(words)),
                builder=_builder(words, pipe_fed=index > 0 and lexed[index - 1].separator == "|"),
                read_only=read_only(words),
                run_targets=tuple(run_targets(words)),
                destroyed=tuple(dict.fromkeys(destroyed)),
                anchored=words.directories is not None,
            )
        )
    return Reading(command, tuple(segments), _piped_programs(segments), None)
