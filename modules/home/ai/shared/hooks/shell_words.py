"""Read Bash command text for path-judging hooks without running it.

An unquoted newline ends a command as `;` does, except after `;`, `&`, `|`,
`|&`, `&&`, or `||`, where bash reads on; after a reserved word such as `then`
it ends an empty command, which adds no segment. A quoted newline is part of
its word. A here-document body is one word, read on the descriptor its
operator names, standard input by default; a here-document whose body never
ends refuses the whole command. A
line continuation joins its lines, as bash joins them outside single quotes
and comments. A carriage return or a null byte refuses the whole command.
A substitution, `$(…)`, `${…}`, or a backquote, ends where bash ends it, quotes,
nesting, and `case` patterns included, and a here-document body inside one is
input. `((…))` and `[[ … ]]` in command position are each one word that runs
no program, and an array subscript or value, as in `a[ i ]=1` or `a=(1 2)`, is
part of its word. The header of a `for` or `select` loop is a segment of its
own that runs no program; so is a `case` subject or pattern where it expands,
and a function's name, after `function` or before `(`. `((…))`, `[[ … ]]`, array subscripts
and values, expanding `case` words, substitutions, and brace expansions keep
their written paths but are unresolvable, except a leading `$HOME`, which
expands as a leading `~` does.
Each segment carries the directories it may run in; a relative path after a
directory change is unresolvable and carries its spelling in each of them.
Each segment also records whether its output or input is a pipe, including
through a piped compound command around it or as a coprocess. A closing word
with no opener refuses the whole command. `text_paths` takes the path
spellings from text the lexer refuses, for a hook that judges it by text.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import glob
from itertools import pairwise
import os
import re
from typing import Literal, NamedTuple

Kind = Literal[
    "command",
    "option",
    "assignment",
    "redirection target",
    "here-document",
    "pattern",
    "path candidate",
    "plain word",
    "unresolvable",
]


@dataclass(frozen=True)
class Word:
    """A resolved word or an unresolved spelling with embedded path evidence."""

    value: str
    kind: Kind
    paths: tuple[str, ...] = ()
    redirection: str | None = None
    # Part of the word was quoted or escaped, so it is never a reserved word.
    quoted: bool = False


class Segment(list[Word]):
    """Words passed to one command, with the control operator after it.

    `directories` holds every directory the command may run in, spelled
    relative to where the whole command starts (`""` is that directory), or is
    `None` after a directory change the words do not resolve.

    A `loop_header` segment runs no program: it is the header of a `for` or
    `select` loop, its first word the reserved word and the rest the values
    the loop variable takes, which reach the body through that variable, or
    the one unresolvable word of a `for ((…))` header.

    `pipes_out` holds whether the command's output goes to another program, and
    `piped_in` whether its input comes from one, directly or through a piped
    compound command around it. A coprocess's output always goes to a pipe.
    """

    def __init__(
        self,
        words: list[Word],
        separator: str,
        directories: tuple[str, ...] | None = ("",),
        *,
        loop_header: bool = False,
        pipes_out: bool = False,
        piped_in: bool = False,
    ) -> None:
        super().__init__(words)
        self.separator = separator
        self.directories = directories
        self.loop_header = loop_header
        self.pipes_out = pipes_out
        self.piped_in = piped_in


@dataclass(frozen=True)
class _Token:
    value: str
    active: str = ""
    quoted: bool = False
    operator: bool = False
    tilde: bool = False
    raw: str = ""
    # The word starts with `$HOME` or `${HOME}`, already replaced by its value.
    home: bool = False
    # A glob character sits inside quotes or after a backslash, where it is literal.
    literal_glob: bool = False
    # The body of a here-document, which stands where its delimiter was written.
    here_document: bool = False


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# `~+`, `~-`, and `~N` name entries of the shell's directory stack, which the hook does not track.
_STACK_TILDE = re.compile(r"~(?:[+-]\d*|\d+)(?:/|$)")
# A descriptor before a redirection: a number, or `{name}`, in which bash stores the one it opens.
_DESCRIPTOR_NAME = re.compile(r"[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?\}")
_REDIRECTION = re.compile(rf"&>>|&>|(?:{_DESCRIPTOR_NAME.pattern})?(?:>>|<<-|<<|<>|>&|<&|>\||>|<)")
# A path inside an unresolvable word starts where a word or an operator ends, as in
# `${X:-/etc/file}`; a `/` after a name character or a `.` continues a relative path.
_PATH = re.compile(r"(?<![\w.])[~/][^{}$(),`\"'\s]*")
_BREAKS = {";", "|", "||", "&", "&&", "(", ")"}
# Operators of more than one character; each longer one extends one listed, as `&>>` extends `&>`.
_LONG_OPERATORS = {"&&", "||", "&>", "&>>", ">>", "<<", "<>", ">&", "<&", ">|", "|&", ";;", ";&", ";;&"}
# Operators after which bash reads on past a newline for the rest of the list.
_CONTINUED = {";", "&", "|", "|&", "||", "&&"}
# `$HOME` and `${HOME}` at the start of a word; `$HOMEDIR` names another variable.
_HOME_REFERENCE = re.compile(r"\$(?:\{HOME\}|HOME(?![A-Za-z0-9_]))")
# A value the shell would split or glob cannot stand in as one literal word.
_UNSPLIT = re.compile(r"[*?\[\s$]")
# Bracket syntax bash matches and Python's glob does not: `^` negation and `[:`, `[=`, `[.` classes.
_BRACKET_SYNTAX = re.compile(r"\[(?:\^|\[[:=.])")


def _ansi_c(body: str) -> str:
    """Decode Bash ANSI-C escapes, including byte escapes and null termination."""
    simple = {
        "a": 7,
        "b": 8,
        "e": 27,
        "E": 27,
        "f": 12,
        "n": 10,
        "r": 13,
        "t": 9,
        "v": 11,
        "\\": 92,
        "'": 39,
        '"': 34,
    }
    result = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\" or index + 1 == len(body):
            result.extend(char.encode("utf-8", "surrogateescape"))
            index += 1
            continue
        char = body[index + 1]
        index += 2
        if char in simple:
            result.append(simple[char])
        elif char == "c" and index < len(body):
            control = body[index]
            if not control.isascii():
                raise ValueError("non-ASCII control escape")
            result.append(127 if control == "?" else ord(control.upper()) & 31)
            index += 1
        elif char in "01234567xuU":
            octal = char in "01234567"
            start = index - 1 if octal else index
            limit = 3 if octal else {"x": 2, "u": 4, "U": 8}[char]
            digits = "01234567" if octal else "0123456789abcdefABCDEF"
            end = start
            while end < min(len(body), start + limit) and body[end] in digits:
                end += 1
            if end == start:
                result.extend(("\\" + char).encode())
                continue
            number = int(body[start:end], 8 if octal else 16)
            if octal or char == "x":
                result.append(number & 255)
            else:
                result.extend(chr(number).encode("utf-8"))
            index = end
        else:
            result.extend(("\\" + char).encode("utf-8", "surrogateescape"))
        if 0 in result:
            break
    return bytes(result).split(b"\0", 1)[0].decode("utf-8", "surrogateescape")


# A line that ends in a line continuation: an odd number of backslashes before its end.
_CONTINUED_LINE = re.compile(r"(?<!\\)(?:\\\\)*\\$")
# A `$` or a backquote no backslash escapes, which bash expands in an unquoted here-document body.
_UNESCAPED_EXPANSION = re.compile(r"(?<!\\)(?:\\\\)*[$`]")
# Deeper nesting than this leaves the command with no reading rather than recursing further.
_MAX_NESTING = 32
# How many `)` one command may try as the close of a substitution holding a `case`.
# Each try reads the text before it again, nested substitutions included, so the work
# grows with the square of the text and with each level of nesting; past this many the
# command has no reading.
_CASE_CLOSE_TRIES = 128


class _Budget:
    """The `)` tries left to the command `lex` is reading."""

    case_closes = _CASE_CLOSE_TRIES


def _opens_substitution(command: str, index: int) -> bool:
    """Return whether `$(…)`, `${…}`, or a backquote opens at `index`."""
    return command[index] == "`" or command.startswith(("$(", "${"), index)


def _double_quote_end(command: str, start: int, depth: int) -> int | None:
    """Return the index after the double-quoted text that opens at `start`.

    `None` where it never closes or an expansion inside it has no end.
    """
    index = start + 1
    while index < len(command):
        char = command[index]
        if char == "\\":
            index += 2
        elif char == '"':
            return index + 1
        elif _opens_substitution(command, index):
            end = _expansion_end(command, index, depth + 1)
            if end is None:
                return None
            index = end
        else:
            index += 1
    return None


def _expansion_end(command: str, start: int, depth: int = 0) -> int | None:
    """Return the index after the `$(…)`, `$((…))`, `${…}`, or backquote that opens at `start`.

    The contents are not read, only their boundary, which follows bash: quotes
    and nested expansions inside are matched, a comment inside `$(…)` runs to
    its newline, a here-document body inside it is skipped, and a backquote
    ends at the first unescaped backquote. `None` where the text ends first,
    nesting runs deeper than `_MAX_NESTING`, a here-document body inside
    never ends, or the boundary depends on grammar the scan does not follow:
    a quote inside `$((…))`, or `$((` that closes as two nested subshells.
    """
    if depth > _MAX_NESTING:
        return None
    if command[start] == "`":
        return _escaped_end(command, start + 1, "`")
    if command.startswith("$((", start):
        return _group_end(command, start + 3, "(", ")", depth, arithmetic=True)
    if command.startswith("${", start):
        return _group_end(command, start + 2, "{", "}", depth)
    return _group_end(command, start + 2, "(", ")", depth, commands=True)


def _case_commands_end(command: str, start: int) -> int | None:
    """Return the index after the `)` that closes the commands from `start`, which hold a `case`.

    Bash closes them at the first `)` before which they read as complete
    commands: a `)` that ends a `case` pattern leaves the `case` open, and one
    inside a quote leaves the quote open. A `)` inside a comment is not one,
    since a word after it is part of the comment. `None` where no `)` closes
    them, or where the command has used its `_CASE_CLOSE_TRIES`.
    """
    index = start
    while _Budget.case_closes > 0:
        _Budget.case_closes -= 1
        index = command.find(")", index)
        if index < 0:
            return None
        commands = command[start:index]
        reading = _lex(commands, None)
        probe = _lex(commands + " :", None)
        if reading is not None and probe is not None and sum(map(len, probe)) > sum(map(len, reading)):
            return index + 1
        index += 1
    return None


def _escaped_end(command: str, index: int, close: str) -> int | None:
    """Return the index after the first `close` from `index` that no backslash escapes, or `None`."""
    while index < len(command):
        if command[index] == "\\":
            index += 2
        elif command[index] == close:
            return index + 1
        else:
            index += 1
    return None


def _unit_end(command: str, index: int, depth: int) -> int | None:
    """Return the index after the escape, quote, or expansion that opens at `index`.

    `index` itself where none opens there, and `None` where one never closes.
    """
    char = command[index]
    if char == "\\":
        return index + 2
    if command.startswith("$'", index):
        # An ANSI-C quote ends at the first `'` no backslash escapes, so `$'\''` is one quote.
        return _escaped_end(command, index + 2, "'")
    if char == "'":
        end = command.find("'", index + 1)
        return None if end < 0 else end + 1
    if char == '"':
        return _double_quote_end(command, index, depth)
    if _opens_substitution(command, index):
        return _expansion_end(command, index, depth + 1)
    return index


def _group_end(  # noqa: C901
    command: str,
    index: int,
    opening: str,
    closing: str,
    depth: int = 0,
    *,
    arithmetic: bool = False,
    commands: bool = False,
) -> int | None:
    """Return the index after the `closing` that matches an `opening` just before `index`.

    Quotes and nested expansions inside are matched. With `commands`, the text
    is shell commands, where a comment runs to its newline and a here-document
    body is skipped; commands holding a `case` end where `_case_commands_end` finds.
    With `arithmetic`, the group closes with `))`. `None` where the text ends
    first, nesting runs too deep, a here-document operator has no delimiter
    word, a here-document body never starts or ends, or the boundary depends
    on grammar the scan does not follow: a quote in `arithmetic`, or a `)`
    that closes an `arithmetic` group alone.
    """
    start = index
    level = 0
    word_start = True
    # Each here-document on the current line: its delimiter word, and whether `<<-` strips tabs.
    pending: list[tuple[str, bool]] = []
    while index < len(command):
        char = command[index]
        if arithmetic and (char in "'\"" or command.startswith("$'", index)):
            return None
        end = _unit_end(command, index, depth)
        if end is None:
            return None
        if end > index:
            # Bash removes a line continuation before it reads words, so one leaves a word start as it was.
            index, word_start = end, word_start and command.startswith("\\\n", index)
            continue
        if commands:
            if char == "#" and word_start:
                newline = command.find("\n", index)
                if newline < 0:
                    return None
                index = newline
                continue
            if command.startswith("<<<", index):
                index, word_start = index + 3, False
                continue
            if command.startswith("<<", index):
                strip = command.startswith("<<-", index)
                word = _delimiter_word(command, index + (3 if strip else 2))
                if word is None:
                    return None
                pending.append((command[word[0] : word[1]], strip))
                index, word_start = word[1], False
                continue
            # The bodies of the line's here-documents follow its newline, and are input, not commands.
            if char == "\n" and pending:
                index += 1
                for raw, strip in pending:
                    body = _here_document(command, index, raw, strip)
                    if body is None:
                        return None
                    index = body[1]
                pending.clear()
                word_start = True
                continue
            if word_start and re.match(r"case\b", command[index:]):
                return _case_commands_end(command, start)
        if char == opening:
            level += 1
        elif char == closing:
            if level:
                level -= 1
            elif not arithmetic:
                return None if pending else index + 1
            elif command.startswith("))", index):
                return index + 2
            else:
                return None
        word_start = char in " \t\n;&|()"
        index += 1
    return None


def _home_at(command: str, index: int) -> tuple[str, int] | None:
    """Return the home directory and the end of a `$HOME` reference starting at `index`."""
    reference = _HOME_REFERENCE.match(command, index)
    home = os.path.expanduser("~")
    if reference is None or _UNSPLIT.search(home):
        return None
    return home, reference.end()


def _newline_ends_command(words: list[_Token]) -> bool:
    """Return whether an unquoted newline after `words` ends a command, as `;` does.

    After an operator that continues the list, bash reads on, so the newline is whitespace.
    """
    return bool(words) and not (words[-1].operator and words[-1].value in _CONTINUED)


def _arithmetic_end(command: str, index: int) -> int | None:
    """Return the index after the `))` that closes the arithmetic command at `index`.

    `None` where the text ends first, holds a quote, an escape, or a
    substitution, or where a `)` closes the outer parenthesis alone, since
    `((a) )` is two nested subshells to bash.
    """
    depth = 0
    for position in range(index + 2, len(command)):
        char = command[position]
        if char in "'\"\\`" or command.startswith("$(", position):
            return None
        if char == "(":
            depth += 1
        elif char == ")":
            if depth:
                depth -= 1
            elif command.startswith("))", position):
                return position + 2
            else:
                return None
    return None


def _at_command_position(words: list[_Token]) -> bool:
    """Return whether a word after `words` stands in command position, where bash reads a reserved word.

    That is the first word, or the first after a control operator or after a
    reserved word that leads a command, such as `!`, `if`, `do`, or `coproc`,
    or after the name a `coproc` gives the compound command that follows it.
    """
    position = True
    after_coproc = False
    for word in words:
        if word.operator:
            position, after_coproc = not _REDIRECTION.fullmatch(word.value), False
            continue
        named = after_coproc and not word.quoted and _NAME.fullmatch(word.value) is not None
        after_coproc = position and _reserved(word, {"coproc"})
        position = (position and _reserved(word, _COMMAND_LEADERS)) or named
    return position


def _conditional_end(command: str, index: int) -> int | None:
    """Return the index after the `]]` that closes the conditional expression `[[` at `index`.

    `]]` closes it only as a word of its own; quotes, escapes, expansions, and
    comments inside are skipped. `None` where the text ends first, an
    expansion inside never closes, or at an unquoted `;`, which bash refuses
    inside it.
    """
    position = index + 2
    word_start = True
    while position < len(command):
        char = command[position]
        if (
            word_start
            and command.startswith("]]", position)
            and command[position + 2 : position + 3] in _AFTER_CONDITIONAL
        ):
            return position + 2
        if char == ";":
            return None
        if char == "#" and word_start:
            newline = command.find("\n", position)
            if newline < 0:
                return None
            position = newline
            continue
        if command.startswith("\\\n", position):
            position += 2
            continue
        end = _unit_end(command, position, 0)
        if end is None:
            return None
        word_start = end == position and char in " \t\n()"
        position = max(end, position + 1)
    return None


def _assignment_end(text: str) -> int | None:
    """Return the index after the `=` of the assignment `text` starts with: `NAME=`, `NAME+=`, or `NAME[…]=`.

    `None` where `text` starts with no assignment. A subscript ends at the
    `]` that matches its `[`, as bash reads it.
    """
    name = _NAME.match(text)
    if name is None:
        return None
    index = name.end()
    if text.startswith("[", index):
        end = _group_end(text, index + 1, "[", "]")
        if end is None:
            return None
        index = end
    for operator in ("=", "+="):
        if text.startswith(operator, index):
            return index + len(operator)
    return None


class _AssignmentPlace:
    """Where the next word stands for bash's array syntax, read once per word as words are added.

    `"command"` before the command word, after leading reserved words and
    assignments, where bash reads `NAME[…]` to its closing `]` and
    `NAME=(…)` as one word. `"operand"` after an assignment builtin such as
    `declare`, where bash reads `NAME=(…)` alone. `None` anywhere else. A
    redirection and its target leave the place as it was.
    """

    def __init__(self) -> None:
        self.place: Literal["command", "operand"] | None = "command"
        self.target = False
        self.read = 0

    def after(self, words: list[_Token]) -> Literal["command", "operand"] | None:
        """Return the place of a word after `words`, which extend the words read before."""
        for word in words[self.read :]:
            if word.operator:
                self.target = bool(_REDIRECTION.fullmatch(word.value))
                if not self.target:
                    self.place = "command"
            elif self.target:
                self.target = False
            elif self.place == "command" and (
                _reserved(word, _COMMAND_LEADERS) or _assignment_end(word.raw) is not None
            ):
                continue
            elif self.place == "command" and _reserved(word, _ASSIGNMENT_BUILTINS):
                self.place = "operand"
            elif self.place != "operand":
                self.place = None
        self.read = len(words)
        return self.place


def _delimiter(raw: str) -> tuple[str, bool] | None:
    """Return the here-document delimiter bash takes from the word `raw`, and whether any of it is quoted.

    Bash removes quotes and expands nothing, so `<<$X` ends at a line reading
    `$X`, and an expansion keeps its text as written, quotes inside included.
    `None` where a quote or an expansion in it never closes, for an expansion
    inside double quotes, or for a locale string, `$"…"`.
    """
    text: list[str] = []
    quoted = False
    index = 0
    while index < len(raw):
        char = raw[index]
        end = _unit_end(raw, index, 0)
        if end is None or raw.startswith('$"', index):
            return None
        if char == "\\":
            text.append(raw[index + 1 : end])
        elif raw.startswith("$'", index):
            text.append(_ansi_c(raw[index + 2 : end - 1]))
        elif char == "'":
            text.append(raw[index + 1 : end - 1])
        elif char == '"':
            body = raw[index + 1 : end - 1]
            if any(_opens_substitution(body, position) for position in range(len(body))):
                return None
            text.append(re.sub(r'\\([$`"\\])', r"\1", body))
        else:
            text.append(raw[index:end] if end > index else char)
            index = max(end, index + 1)
            continue
        quoted = True
        index = end
    return "".join(text), quoted


def _line_at(command: str, index: int) -> tuple[str, int, bool]:
    """Return the line that starts at `index`, the index after it, and whether a newline ends it."""
    end = command.find("\n", index)
    if end < 0:
        return command[index:], len(command), False
    return command[index:end], end + 1, True


def _here_document(command: str, index: int, raw: str, strip: bool) -> tuple[_Token, int] | None:
    """Read the body of the here-document whose delimiter word is `raw` from `index`.

    Return its token and the index after the delimiter line. Under an unquoted
    delimiter a line continuation joins the lines before the delimiter is
    matched, so a line `EO` continued by `F` ends a body at `EOF`, and `<<-`
    strips leading tabs after the join. A quoted body keeps every backslash;
    an unquoted body that does not expand keeps all but those before `$`, a
    backquote, or a backslash; one that expands keeps its text as written.
    `None` where the delimiter has no reading or the text ends first.
    """
    delimiter = _delimiter(raw)
    if delimiter is None:
        return None
    text, quoted = delimiter
    lines = []
    while index < len(command):
        line, index, ended = _line_at(command, index)
        while not quoted and ended and _CONTINUED_LINE.search(line) and index < len(command):
            more, index, ended = _line_at(command, index)
            line = line[:-1] + more
        if strip:
            line = line.lstrip("\t")
        if line == text:
            break
        if not ended:
            return None
        lines.append(line + "\n")
    else:
        return None
    body = "".join(lines)
    if quoted:
        return _Token(body, "", True, raw=body, here_document=True), index
    if _UNESCAPED_EXPANSION.search(body):
        return _Token(body, "$", raw=body, here_document=True), index
    return _Token(re.sub(r"\\([$`\\])", r"\1", body), raw=body, here_document=True), index


def _delimiter_word(command: str, index: int) -> tuple[int, int] | None:
    """Return where the delimiter word after a here-document operator ending at `index` starts and ends.

    `None` where no word follows or a quote or an expansion in it never closes.
    """
    while command[index : index + 1] in {" ", "\t"}:
        index += 1
    start = index
    while index < len(command) and command[index] not in " \t\n;&|()<>":
        end = _unit_end(command, index, 0)
        if end is None:
            return None
        index = max(end, index + 1)
    return (start, index) if index > start else None


def _split_words(command: str) -> list[_Token] | None:  # noqa: C901
    words: list[_Token] = []
    place = _AssignmentPlace()
    value: list[str] = []
    active: set[str] = set()
    quoted = started = tilde = home_reference = literal_glob = False
    index = 0
    word_start = 0
    # A here-document operator waits for its delimiter word; each delimiter
    # read waits, by its place in `words`, for the body after the line ends.
    awaiting_delimiter: str | None = None
    awaiting_body: list[tuple[int, bool]] = []

    def literal(text: str) -> None:
        """Append quoted or escaped text, noting a glob character it holds."""
        nonlocal literal_glob
        literal_glob |= any(char in "*?[" for char in text)
        value.append(text)

    def substitution() -> bool:
        """Append the substitution that opens at `index` as written; `False` where it has no end."""
        nonlocal index
        end = _expansion_end(command, index)
        if end is None:
            return False
        value.append(command[index:end])
        active.add("`" if command[index] == "`" else "$")
        index = end
        return True

    def whole_word(end: int | None) -> bool:
        """Append the text from `index` to `end` as one unresolvable word.

        `False` where it has no end, or spans a newline before a here-document body it would hide.
        """
        nonlocal index
        if end is None or (awaiting_body and "\n" in command[index:end]):
            return False
        text = command[index:end]
        words.append(_Token(text, "$", raw=text))
        index = end
        return True

    def flush() -> None:
        nonlocal value, active, quoted, started, tilde, home_reference, literal_glob, awaiting_delimiter
        raw = command[word_start:index]
        # bash expands `~` only when nothing before the first unquoted `/` is quoted or expanded.
        if tilde and any(char in raw.split("/", 1)[0] for char in "'\"\\$`"):
            tilde = False
        if started:
            words.append(
                _Token(
                    "".join(value),
                    "".join(sorted(active)),
                    quoted,
                    False,
                    tilde,
                    raw,
                    home_reference,
                    literal_glob,
                )
            )
            if awaiting_delimiter is not None:
                awaiting_body.append((len(words) - 1, awaiting_delimiter.endswith("-")))
                awaiting_delimiter = None
        value, active = [], set()
        quoted = started = tilde = home_reference = literal_glob = False

    while index < len(command):
        char = command[index]
        # A line continuation joins the lines before bash reads operators, words, or comments.
        if command.startswith("\\\n", index):
            command = command[:index] + command[index + 2 :]
            continue
        if char == "\n":
            flush()
            if awaiting_delimiter is not None:
                return None
            index += 1
            # The bodies of the line's here-documents start on the next line, in order.
            for position, strip in awaiting_body:
                body = _here_document(command, index, words[position].raw, strip)
                if body is None:
                    return None
                words[position], index = body
            awaiting_body.clear()
            if _newline_ends_command(words):
                words.append(_Token(";", operator=True))
            continue
        # Bash separates words on space and tab alone; a vertical tab, a form feed, or a
        # Unicode space is a character of the word, so a `#` after one starts no comment.
        if char in " \t":
            flush()
            index += 1
            continue
        # `((…))` is an arithmetic command: bash runs no program, and `<<` in it is a shift.
        # It stays one unresolvable word, since it may assign variables later words read.
        if not started and command.startswith("((", index) and awaiting_delimiter is None:
            if not whole_word(_arithmetic_end(command, index)):
                return None
            continue
        # `[[ … ]]` is a conditional expression: bash runs no program, and `&&`, `<`, and `(`
        # inside it are its operators. It stays one unresolvable word, as `((…))` does.
        if (
            not started
            and command.startswith("[[", index)
            and command[index + 2 : index + 3] in {" ", "\t", "\n"}
            and _at_command_position(words)
        ):
            if not whole_word(_conditional_end(command, index)):
                return None
            continue
        # Bash reads an array subscript to its `]` and an array value to its `)` as part of the
        # word, so `a[ i ]=1` and `a=(1 2)` are one word each. A subscript is an expression and
        # a value a list of words, so the word is unresolvable.
        if char in "([" and started and not quoted:
            raw = command[word_start:index]
            subscript = char == "[" and _NAME.fullmatch(raw) and place.after(words) == "command"
            array = char == "(" and _assignment_end(raw) == len(raw) and place.after(words) is not None
            if subscript or array:
                end = _group_end(command, index + 1, char, "]" if subscript else ")", commands=bool(array))
                if end is None or (awaiting_body and "\n" in command[index:end]):
                    return None
                value.append(command[index:end])
                active.add("$")
                index = end
                continue
        if char in "();<>|&":
            descriptor = ""
            if char in "<>" and not quoted and started and _DESCRIPTOR_NAME.fullmatch(command[word_start:index]):
                descriptor = command[word_start:index]
                value, active = [], set()
                started = False
            flush()
            end = index + 1
            while True:
                # A line continuation inside an operator is removed as well, so `&\⏎&` is `&&`.
                while command.startswith("\\\n", end):
                    command = command[:end] + command[end + 2 :]
                if end == len(command) or command[index : end + 1] not in _LONG_OPERATORS:
                    break
                end += 1
            operator = descriptor + command[index:end]
            if operator.endswith("<<") and command[end : end + 1] != "<":
                if command[end : end + 1] == "-":
                    operator += "-"
                    end += 1
                awaiting_delimiter = operator
            words.append(_Token(operator, operator=True))
            index = end
            continue
        if char == "#" and not started:
            # A comment runs to the end of its line; the newline still ends the command.
            newline = command.find("\n", index)
            index = len(command) if newline < 0 else newline
            continue
        if not started:
            word_start = index
            tilde = char == "~"
        started = True
        if char == "\\":
            if index + 1 == len(command):
                return None
            literal(command[index + 1])
            quoted = True
            index += 2
            continue
        home = None if value else _home_at(command, index)
        if home is not None:
            value.append(home[0])
            home_reference = True
            index = home[1]
            continue
        if _opens_substitution(command, index):
            if not substitution():
                return None
            continue
        if char == "'" or command.startswith("$'", index):
            end = _unit_end(command, index, 0)
            if end is None:
                return None
            body = command[index + (2 if char == "$" else 1) : end - 1]
            literal(_ansi_c(body) if char == "$" else body)
            quoted = True
            index = end
            continue
        if char == '"':
            index += 1
            home = None if value else _home_at(command, index)
            if home is not None:
                value.append(home[0])
                home_reference = True
                index = home[1]
            while index < len(command) and command[index] != '"':
                char = command[index]
                if char == "\\" and index + 1 < len(command) and command[index + 1] in '$`"\\\n':
                    if command[index + 1] == "\n":
                        command = command[:index] + command[index + 2 :]
                        continue
                    literal(command[index + 1])
                    index += 2
                    continue
                # An expansion inside double quotes ends where bash finds its close: a `"`
                # inside it, as in `"${X:-'"'}"`, does not end the quoted word.
                if _opens_substitution(command, index):
                    if not substitution():
                        return None
                    continue
                if char == "$":
                    active.add(char)
                literal(char)
                index += 1
            if index == len(command):
                return None
            quoted = True
            index += 1
            continue
        if char in "$*?[{},":
            active.add(char)
        value.append(char)
        index += 1
    flush()
    if awaiting_delimiter is not None or awaiting_body:
        return None
    return words


def is_assignment(value: str) -> bool:
    """Return whether a word has the shape `NAME=`, `NAME+=`, or `NAME[…]=`, wherever it stands.

    The `assignment` kind marks only the leading words the shell assigns; a
    later word of the same shape is an operand such as `dd of=`.
    """
    return _assignment_end(value) is not None


def unresolved_paths(value: str) -> tuple[str, ...]:
    """Keep possible path spellings from text the lexer cannot resolve."""
    # A line continuation inside the text may split a path that bash reads joined.
    joined = value.replace("\\\n", "")
    pieces = [value, joined, *re.split(r"[{},()\s\"']", joined), *_PATH.findall(joined)]
    return tuple(dict.fromkeys(piece for piece in pieces if piece))


_TEXT_BREAKS = frozenset(" \t\n;&|()<>=`")


def text_paths(command: str, cwd: str | None) -> tuple[str, ...]:
    """Spellings of the paths in text the lexer cannot read, for a hook that judges it by text.

    Quotes group words, a quote left open ends at its line, and a backslash
    escapes the next character, so a path that holds a space stays one
    spelling. A relative spelling is also joined to `cwd` and to each `cd` or
    `pushd` target the text names, since the text may change directory first.
    """
    words: list[str] = []
    current: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        escaped = char == "\\" and index + 1 < len(command) and quote != "'"
        if escaped:
            index += 1
            if command[index] != "\n":
                current.append(command[index])
        elif quote and char != "\n":
            if char == quote:
                quote = ""
            else:
                current.append(char)
        elif char in "'\"":
            quote = char
        elif char in _TEXT_BREAKS:
            if current:
                words.append("".join(current))
            current, quote = [], ""
        else:
            current.append(char)
        index += 1
    if current:
        words.append("".join(current))
    roots = [cwd] if cwd else []
    for previous, word in pairwise(words):
        if previous in {"cd", "pushd"} and not word.startswith("-"):
            target = os.path.expanduser(word)
            roots.append(os.path.join(cwd, target) if cwd and not os.path.isabs(target) else target)
    spellings = []
    for word in words:
        spellings.append(word)
        if not os.path.isabs(os.path.expanduser(word)):
            spellings.extend(os.path.join(root, word) for root in roots)
    return tuple(dict.fromkeys(spellings))


def _resolve(token: _Token, roots: list[str | None], *, home_known: bool = True) -> list[str] | None:
    if _holds_expansion(token):
        return None
    active = set(token.active)
    if (token.tilde or token.home) and not home_known:
        return None
    if ("{" in active) != ("}" in active):
        return None
    if "{" in active and ("," in active or ".." in token.value):
        return None
    if token.tilde and _STACK_TILDE.match(token.value):
        return None
    value = os.path.expanduser(token.value) if token.tilde else token.value
    if _assignment_end(token.raw) is not None:
        name, _, operand = value.partition("=")
        pieces, raw_pieces = operand.split(":"), token.raw.partition("=")[2].split(":")
        if any(piece.startswith("~") for piece in raw_pieces):
            # Bash expands a tilde after `=` and after each `:` in an assignment.
            if not home_known or len(pieces) != len(raw_pieces):
                return None
            if any(_STACK_TILDE.match(piece) for piece in raw_pieces):
                return None
            pieces = [
                os.path.expanduser(p) if r.startswith("~") else p for p, r in zip(pieces, raw_pieces, strict=True)
            ]
            value = name + "=" + ":".join(pieces)
    if not active & set("*?["):
        return [value]
    # Python's glob reads `[^...]` and POSIX bracket classes differently from bash.
    if "[" in active and _BRACKET_SYNTAX.search(value):
        return None
    if token.literal_glob or (not os.path.isabs(value) and None in roots):
        return None
    matches = {match for root in roots for match in glob.glob(value, root_dir=root)}
    return sorted(matches) or [value]


# Reserved words bash reads only in command position, and `time`, which leads a command.
_RESERVED = {"!", "{", "}", "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "time"}
# Reserved words that are not the program they precede. `time` stays a word,
# because readers treat it as a wrapper that takes options.
_KEYWORDS = _RESERVED - {"time"}
# Reserved words after which the next word stands in command position.
_COMMAND_LEADERS = (_RESERVED - {"}", "fi", "done"}) | {"coproc"}
# Builtins whose operands bash reads as assignments, so `declare a=(1 2)` assigns an array.
_ASSIGNMENT_BUILTINS = {"alias", "declare", "eval", "export", "let", "local", "readonly", "typeset"}
# What may follow the `]]` that closes a conditional expression.
_AFTER_CONDITIONAL = {"", " ", "\t", "\n", ";", "&", "|", ")", "<", ">"}
# Builtins that run text or change the shell in ways these words do not show, and
# `function`, whose body any later call may run.
_OPAQUE = {"eval", "source", ".", "trap", "shopt", "function"}
# Assignments that change where `cd` goes or what `~` and `$HOME` mean.
_DIRECTORY_VARIABLES = re.compile(r"^(?:HOME|CDPATH)(?:[+=[]|$)")
# Reserved words that open a loop, whose body may run any number of times.
_LOOPS = {"while", "until", "for", "select"}
# Operators that end a `case` body.
_CASE_ENDS = {";;", ";&", ";;&"}
# What follows `coproc NAME` when NAME names the coprocess: a compound command.
_COMPOUND_OPENERS = _LOOPS | {"{", "(", "if", "case"}
# Reserved words that open a loop header: a variable, then `in` and its values.
_LIST_LOOPS = {"for", "select"}
# The openers the reserved-word branch of the lexer opens a compound for (the
# others open where their syntax is read), and the openers each closing word closes.
_KEYWORD_OPENERS = _COMPOUND_OPENERS - _LIST_LOOPS - {"case", "("}
_CLOSERS = {"}": {"{"}, ")": {"(", "()"}, "fi": {"if"}, "done": _LOOPS, "esac": {"case"}}


class _Compound(NamedTuple):
    """A compound command open around the word being read."""

    opener: str
    # The index of its first segment.
    start: int
    # A pipe feeds it, or a compound around it.
    fed: bool
    # It runs as a coprocess, or a compound around it does.
    coprocess: bool


# What a segment does to the directory, where it names no path: distinct objects,
# so no directory name can be mistaken for one.
_UNKNOWN = object()
_STAYS = object()
_FAILS = object()


def _holds_expansion(token: _Token) -> bool:
    """Return whether `token` holds a parameter expansion or a substitution."""
    return bool(set(token.active) & {"$", "`"})


def _reserved(word: Word | _Token, names: set[str] = _RESERVED) -> bool:
    """Return whether `word` is one of the reserved `names`; quoting makes it an ordinary word."""
    return not word.quoted and word.value in names


def _expands(value: str) -> bool:
    """Return whether an unresolvable word's text holds an expansion, not only a relative path."""
    return any(char in value for char in "$`{*?[")


def _is_conditional_or_arithmetic(word: Word | _Token) -> bool:
    """Return whether `word` is a whole `((…))` or `[[ … ]]` command, which runs no program.

    No other unquoted word starts with `((`, or with `[[` and a blank.
    """
    return not word.quoted and (word.value.startswith("((") or word.value[:3] in {"[[ ", "[[\t", "[[\n"})


def command_position(words: list[Word]) -> list[Word] | None:
    """Return the words from the command word on; `None` where `command -v` only looks one up."""
    index = 0
    while index < len(words) and (words[index].kind == "assignment" or _reserved(words[index])):
        index += 1
        if words[index - 1].value == "time" and index < len(words) and words[index].value == "-p":
            index += 1
    rest = words[index:]
    while rest and rest[0].value in {"builtin", "command"}:
        wrapper, rest = rest[0].value, rest[1:]
        options = []
        while rest and rest[0].value.startswith("-") and rest[0].value != "-":
            option, rest = rest[0].value, rest[1:]
            if option == "--":
                break
            options.append(option)
        if wrapper == "command" and any(set(option) & {"v", "V"} for option in options):
            return None
    return rest


def _directory_effect(words: list[Word]) -> tuple[str, list[Word]] | object | None:
    """Return the `cd`, `pushd`, or `popd` a segment runs with its operands, `_UNKNOWN`, or `None`."""
    if any(_DIRECTORY_VARIABLES.match(word.value) for word in words):
        return _UNKNOWN
    rest = command_position(words)
    if not rest or _is_conditional_or_arithmetic(rest[0]):
        return None
    if (rest[0].kind == "unresolvable" and _expands(rest[0].value)) or rest[0].value in _OPAQUE:
        return _UNKNOWN
    if rest[0].value not in {"cd", "pushd", "popd"}:
        return None
    return rest[0].value, [word for word in rest[1:] if word.kind != "redirection target"]


def _target(words: list[Word]) -> str | object:
    """Return where a segment's `cd` or `pushd` goes: a path, `_STAYS`, `_FAILS`, or `_UNKNOWN`."""
    effect = _directory_effect(words)
    if effect is None:
        return _STAYS
    if effect is _UNKNOWN:
        return _UNKNOWN
    name, operands = effect
    while operands and operands[0].value.startswith("-") and operands[0].value != "-":
        option, operands = operands[0].value, operands[1:]
        if option == "--":
            break
        if "P" in option:
            # `-P` resolves links before `..`, which these spellings do not.
            return _UNKNOWN
    if name == "popd" or len(operands) > 1:
        return _UNKNOWN
    if not operands:
        return _UNKNOWN if name == "pushd" else os.path.expanduser("~")
    target = operands[0].value
    if target == "":
        # bash refuses a null directory.
        return _FAILS
    # `-` names the previous directory and a `pushd` `+N` or `-N` a stack position;
    # an expansion names a value these words do not hold. Any other operand
    # starting with `-` follows `--` and names a directory.
    if target == "-" or (name == "pushd" and re.fullmatch(r"[+-]\d+", target)) or _expands(target):
        return _UNKNOWN
    if os.environ.get("CDPATH") and not target.startswith(("/", "./", "../")) and target not in {".", ".."}:
        return _UNKNOWN
    return target


def _leading_reserved(words: list[Word]) -> set[str]:
    """Return the reserved and loop words before a segment's command word."""
    leading = set()
    for word in words:
        if word.kind == "assignment":
            continue
        if not _reserved(word, _RESERVED | _LOOPS):
            break
        leading.add(word.value)
    return leading


def _negated(words: list[Word]) -> bool:
    """Return whether a leading `!` inverts the segment's status."""
    bangs = 0
    for word in words:
        if _reserved(word, {"!"}):
            bangs += 1
        elif word.kind != "assignment" and not _reserved(word):
            break
    return bangs % 2 == 1


def _joined(cwd: str | None, *parts: str) -> str | None:
    """Join `parts` onto `cwd`; `None` where the result is relative to an unknown directory.

    A `..` stays as written: after a link, the file it reaches is found by
    resolving the link first, which collapsing `link/..` would skip.
    """
    path = os.path.join(cwd or "", *parts)
    return path if os.path.isabs(path) else None


# The status of the last segment that ran: `&&` runs the next segment unless it
# failed, and `||` unless it succeeded. A command other than `cd` may do either.
_OK, _FAIL, _EITHER = "ok", "fail", "either"
_State = tuple[str, str]


class _Directories:
    """Where each segment of one command may run, following its `cd`s as bash does.

    Each state is a directory the shell may be in and the status of the
    segment that left it there. A list operator runs the next segment from the
    states it selects and carries the others past it, so a `cd` that fails or
    is skipped leaves its starting directory among the states.
    """

    def __init__(self, cwd: str | None) -> None:
        self.cwd = cwd
        self.home_known = True
        # `None` once a directory change the words do not resolve may have run.
        self.states: frozenset[_State] | None = frozenset({("", _OK)})
        self.run: frozenset[str] | None = frozenset({""})
        self.skipped: frozenset[_State] = frozenset()
        self.piped = False
        # How many loops the segment being read sits inside.
        self.loops = 0
        self.enclosing: list[tuple[frozenset[str] | None, frozenset[_State]]] = []

    @property
    def moved(self) -> bool:
        """Whether a directory change may have moved the segment being read."""
        return self.run != {""}

    def spelled(self) -> tuple[str, ...] | None:
        """Return the directories the segment being read may run in, for `Segment.directories`."""
        return None if self.run is None else tuple(sorted(self.run))

    def roots(self) -> list[str | None]:
        """Return the directories a pattern in the segment being read expands against."""
        if not self.moved:
            return [self.cwd]
        if self.run is None:
            return [None]
        return [_joined(self.cwd, directory) for directory in sorted(self.run)]

    def evidence(self, value: str) -> tuple[str, ...]:
        """Return the paths an unresolvable `value` may name.

        Each relative path, the value and each fragment written inside it, is
        also spelled in every directory a moved segment may run in.
        """
        written = unresolved_paths(value)
        if not self.moved or self.run is None:
            return written
        joined = (
            _joined(self.cwd, directory, path)
            for path in written
            if not os.path.isabs(path) and not path.startswith("~")
            for directory in sorted(self.run)
        )
        return tuple(dict.fromkeys([*written, *(path for path in joined if path)]))

    def _outcomes(self, segment: list[Word], operator: str) -> frozenset[_State] | None:
        """Return the states running `segment` leaves, before the states it skipped."""
        if self.run is None:
            return None
        # A pipeline element and a background job run in a subshell, so a `cd` there does not last.
        target = _STAYS if self.piped or operator in {"|", "&"} else _target(segment)
        # A `cd` inside a loop may run any number of times.
        if target is _UNKNOWN or (self.loops and target is not _STAYS):
            return None
        if target is _STAYS:
            status = _OK if operator == "&" else _EITHER
            return frozenset((directory, status) for directory in self.run)
        swap = {_OK: _FAIL, _FAIL: _OK} if _negated(segment) else {_OK: _OK, _FAIL: _FAIL}
        outcomes = {(directory, swap[_FAIL]) for directory in self.run}
        if target is not _FAILS:
            entered = (os.path.normpath(os.path.join(directory, target)) for directory in self.run)
            outcomes |= {("" if directory == "." else directory, swap[_OK]) for directory in entered}
        return frozenset(outcomes)

    def _select(self, operator: str) -> None:
        """Split the states into those the next segment runs from and those it skips."""
        if self.states is None:
            self.run, self.skipped = None, frozenset()
            return
        if operator not in {"&&", "||"}:
            self.run, self.skipped = frozenset(directory for directory, _ in self.states), frozenset()
            return
        # `&&` skips the next segment after a failure, and `||` after a success.
        skips = _FAIL if operator == "&&" else _OK
        self.run = frozenset(directory for directory, status in self.states if status != skips)
        self.skipped = frozenset(state for state in self.states if state[1] != ({_FAIL: _OK, _OK: _FAIL}[skips]))

    def follow(self, segment: list[Word], operator: str) -> None:
        """Move past `segment` and the control `operator` after it."""
        if any(_DIRECTORY_VARIABLES.match(word.value) for word in segment):
            self.home_known = False
        if segment:
            leading = _leading_reserved(segment)
            self.loops += bool(leading & _LOOPS)
            # A segment before `(` defines a function; calling it later may run any `cd` in its body.
            outcomes = None if operator == "(" else self._outcomes(segment, operator)
            self.states = None if outcomes is None or self.states is None else outcomes | self.skipped
            self.piped = operator == "|"
            self.loops -= bool(self.loops) and "done" in leading
        if operator == "(":
            if self.states is None:
                self.run = None
            self.enclosing.append((self.run, self.skipped))
            # The subshell's first segment runs from every selected directory.
            self.states = None if self.run is None else frozenset((directory, _EITHER) for directory in self.run)
            self.skipped = frozenset()
            return
        if operator == ")" and self.enclosing:
            # A `cd` inside a subshell does not outlast it, and a redirection after
            # the subshell opens its target where the subshell started.
            entry, skipped = self.enclosing.pop()
            self.states = None if entry is None else frozenset((directory, _EITHER) for directory in entry) | skipped
            self.run = entry
            return
        self._select(operator if operator in {"&&", "||"} else ";")


def _lex(command: str, cwd: str | None) -> list[Segment] | None:  # noqa: C901
    if any(char in command for char in ("\r", "\x00")):
        return None
    tokens = _split_words(command)
    if tokens is None:
        return None
    segments: list[Segment] = []
    segment: list[Word] = []
    # Reserved words before the command word; directory tracking reads them, consumers do not.
    keywords: list[Word] = []
    redirect: str | None = None
    has_command = False
    # Where a `for` or `select` header stands: before its variable, after it, or in the
    # values after `in`; `None` outside a header.
    header: Literal["variable", "after", "values"] | None = None
    directories = _Directories(cwd)
    # Each compound command open around the word being read, innermost last. A `(`
    # after a function's name does not open a compound, and is kept as `()` so
    # its `)` does not close one.
    compounds: list[_Compound] = []
    # The first segment of the compound just closed, which a `|` after it pipes out.
    closed_start: int | None = None
    # A `|` before the next command or compound feeds it; `coproc` sends its output to a pipe.
    fed = False
    coprocess = False
    mismatched = False

    def around() -> _Compound | None:
        return compounds[-1] if compounds else None

    def open_compound(opener: str) -> None:
        nonlocal fed, coprocess
        outer = around()
        compounds.append(
            _Compound(
                opener,
                len(segments),
                fed or (outer is not None and outer.fed),
                coprocess or (outer is not None and outer.coprocess),
            )
        )
        fed = coprocess = False

    def close_compound(closer: str) -> None:
        """Close the innermost compound `closer` ends, or mark the text unreadable when it ends none."""
        nonlocal closed_start, mismatched
        if not compounds or compounds[-1].opener not in _CLOSERS[closer]:
            mismatched = True
            return
        closing = compounds.pop()
        if closing.opener != "()":
            closed_start = closing.start

    def unresolvable(token: _Token) -> Word:
        """Return `token` as an unresolvable word that keeps the paths written in it."""
        return Word(token.value, "unresolvable", directories.evidence(token.value), redirect, token.quoted)

    def open_segment(word: Word) -> None:
        """Start a segment with `word`, after which no word is its command."""
        nonlocal has_command
        segment.append(word)
        has_command = True

    def end_segment(separator: str) -> None:
        nonlocal segment, keywords, has_command, header, closed_start, fed, coprocess
        # A lone name before `(` is the name a function definition binds, which does not run a program.
        defines = separator == "(" and len(segment) == 1 and segment[0].kind == "command"
        if defines and _NAME.fullmatch(segment[0].value):
            segment = [replace(segment[0], kind="plain word")]
        # A pipe after a compound command carries the output of every command inside it.
        if closed_start is not None and separator == "|":
            for inner in segments[closed_start:]:
                inner.pipes_out = True
        closed_start = None
        if segment:
            outer = around()
            segments.append(
                Segment(
                    segment,
                    separator,
                    directories.spelled(),
                    loop_header=header is not None,
                    pipes_out=separator == "|" or coprocess or (outer is not None and outer.coprocess),
                    piped_in=fed or (outer is not None and outer.fed),
                )
            )
            fed = coprocess = False
        directories.follow(keywords + segment, separator)
        segment, keywords = [], []
        has_command = False
        header = None
        if separator == "|":
            fed = True
        elif separator == "(":
            open_compound("()" if defines else "(")
        elif separator == ")":
            close_compound(")")

    # Each `case` open around the word being read, innermost last: before its subject,
    # before `in`, in a pattern list, or in a body.
    cases: list[Literal["subject", "in", "patterns", "body"]] = []
    # A `function` keyword waits for its name, which ends its segment.
    function_name = False
    stream = [*tokens, _Token(";", operator=True)]
    skip = -1
    for at, token in enumerate(stream):
        if at == skip:
            continue
        if token.operator and cases and cases[-1] != "body":
            # Bash reads newlines around a `case` subject, `in`, and its patterns.
            if token.value == ";" or (cases[-1] == "patterns" and token.value in {"(", "|"}):
                continue
            if cases[-1] != "patterns" or token.value != ")":
                return None
            if segment:
                end_segment(";")
            cases[-1] = "body"
            continue
        if token.operator:
            if redirect or function_name or (header is not None and token.value != ";"):
                return None
            # Bash reads newlines between a loop variable and `in` or `do`; `;` is one of them.
            if header == "after":
                continue
            if _REDIRECTION.fullmatch(token.value):
                redirect = token.value
                continue
            if cases and token.value in _CASE_ENDS:
                end_segment(";")
                cases[-1] = "patterns"
                continue
            if token.value not in _BREAKS:
                return None
            end_segment(token.value)
            continue
        if cases and cases[-1] == "subject":
            cases[-1] = "in"
            if _holds_expansion(token):
                segment.append(unresolvable(token))
            continue
        if cases and cases[-1] == "in":
            if token.quoted or token.value != "in":
                return None
            # A subject that does not expand runs nothing, so it leaves no segment.
            if len(segment) > 1:
                end_segment(";")
            else:
                segment, has_command = [], False
            cases[-1] = "patterns"
            continue
        if (
            cases
            and cases[-1] in {"patterns", "body"}
            and not segment
            and redirect is None
            and _reserved(token, {"esac"})
        ):
            cases.pop()
            keywords.append(Word("esac", "plain word"))
            close_compound("esac")
            continue
        if cases and cases[-1] == "patterns":
            # A pattern is matched against the subject and names no file; one that expands may run a substitution.
            if _holds_expansion(token):
                if not segment:
                    open_segment(Word("case", "plain word"))
                segment.append(unresolvable(token))
            continue
        if function_name:
            segment.append(Word(token.value, "plain word", (), None, token.quoted))
            function_name = False
            end_segment(";")
            continue
        if not segment and redirect is None and not token.quoted:
            if token.value == "case":
                open_compound("case")
                open_segment(Word("case", "plain word"))
                cases.append("subject")
                continue
            if token.value == "function":
                open_segment(Word("function", "plain word"))
                function_name = True
                continue
            if token.value == "coproc":
                keywords.append(Word("coproc", "plain word"))
                coprocess = True
                # `coproc NAME` names the coprocess only before a compound command.
                name, following = stream[at + 1], stream[at + 2] if at + 2 < len(stream) else None
                if (
                    following is not None
                    and not name.operator
                    and _NAME.fullmatch(name.value)
                    and not name.quoted
                    and (
                        (following.value in _COMPOUND_OPENERS and (following.operator or not following.quoted))
                        or _is_conditional_or_arithmetic(following)
                    )
                ):
                    skip = at + 1
                continue
        # A loop header's variable runs nothing, and `in` or `do` after it ends that part.
        if header == "variable":
            header = "after"
            if token.value.startswith("((") and not token.quoted:
                segment.append(unresolvable(token))
            continue
        if header == "after":
            if token.quoted or token.value not in {"in", "do"}:
                return None
            if token.value == "in":
                header = "values"
            else:
                end_segment(";")
                keywords.append(Word("do", "plain word"))
            continue
        # The values of a `for` or `select` loop reach its body through the loop
        # variable, so they stay words of a segment that runs no program.
        if not segment and redirect is None and _reserved(token, _LIST_LOOPS):
            open_compound(token.value)
            open_segment(Word(token.value, "plain word"))
            header = "variable"
            continue
        if token.here_document:
            # A body bash expands is unresolvable, and still shows the paths written in it.
            if token.active:
                segment.append(Word(token.value, "unresolvable", directories.evidence(token.value), redirect, True))
            else:
                segment.append(Word(token.value, "here-document", (), redirect, True))
            redirect = None
            continue
        # Bash reads a reserved word only as the first word of a command: after an
        # assignment or a redirection, `if` is the name of the program to run.
        if not segment and redirect is None and _reserved(token, _KEYWORDS):
            keywords.append(Word(token.value, "plain word"))
            if token.value in _KEYWORD_OPENERS:
                open_compound(token.value)
            elif token.value in _CLOSERS:
                close_compound(token.value)
            continue
        moved = directories.moved
        produced = _resolve(token, directories.roots(), home_known=directories.home_known)
        assigns = not has_command and is_assignment(token.raw)
        is_command = not has_command and not assigns and redirect is None
        if produced is None:
            segment.append(unresolvable(token))
        else:
            for position, value in enumerate(produced):
                kind: Kind
                if redirect:
                    kind = "redirection target"
                elif assigns:
                    kind = "assignment"
                elif is_command and position == 0:
                    kind = "command"
                elif value.startswith("-"):
                    kind = "option"
                elif set(token.active) & set("*?[") and produced == [token.value]:
                    kind = "pattern"
                elif (
                    "/" in value
                    or value.startswith("~")
                    or (cwd is not None and os.path.lexists(os.path.join(cwd, value)))
                ):
                    kind = "path candidate"
                else:
                    kind = "plain word"
                relative = not os.path.isabs(value)
                if (
                    relative
                    and (moved or cwd is None)
                    and (kind in {"path candidate", "redirection target"} or (moved and kind == "plain word"))
                ):
                    kind = "unresolvable"
                paths = directories.evidence(value) if kind == "unresolvable" else ()
                segment.append(Word(value, kind, paths, redirect, token.quoted))
        has_command |= is_command
        redirect = None
    # A loop header, a `case`, or a `function` still open never closed, which bash refuses.
    # A closing word with no opener to match is text bash cannot run.
    return None if header is not None or cases or function_name or mismatched else segments


def lex(command: str, cwd: str | None) -> list[Segment] | None:
    """Return segments with word kinds, or no reading for an unresolvable command."""
    _Budget.case_closes = _CASE_CLOSE_TRIES
    try:
        return _lex(command, cwd)
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None
