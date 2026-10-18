"""Read Bash command text for path-judging hooks without running it.

Across lines only plain commands are read. An unquoted newline ends a command
as `;` does, except after `;`, `&`, `|`, `|&`, `&&`, or `||`, where bash reads
on; a quoted newline is part of its word. A here-document body is one word,
read on the command's standard input; a here-document whose body never ends,
or whose delimiter holds an expansion, refuses the whole command. A multi-line
command holding a line continuation, a parenthesis, or a reserved word in
command position refuses the whole command, as do a carriage return and a null
byte.
A substitution, `$(…)`, `${…}`, or a backquote, ends where bash ends it, quotes
and nesting included; one holding a here-document or a `case` pattern refuses
the whole command. Substitutions, `((…))`, and brace expansions retain their
written paths but are unresolvable, except a leading `$HOME`, which expands as
a leading `~` does.
Each segment carries the directories it may run in; a relative path after a
directory change is unresolvable and carries its spelling in each of them.
"""

from __future__ import annotations

from dataclasses import dataclass
import glob
import os
import re
from typing import Literal

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
    """

    def __init__(self, words: list[Word], separator: str, directories: tuple[str, ...] | None = ("",)) -> None:
        super().__init__(words)
        self.separator = separator
        self.directories = directories


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


_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# `~+`, `~-`, and `~N` name entries of the shell's directory stack, which the hook does not track.
_STACK_TILDE = re.compile(r"~(?:[+-]\d*|\d+)(?:/|$)")
# A descriptor before a redirection: a number, or `{name}`, in which bash stores the one it opens.
_DESCRIPTOR_NAME = re.compile(r"[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?\}")
_REDIRECTION = re.compile(rf"&>>|&>|(?:{_DESCRIPTOR_NAME.pattern})?(?:>>|<<-|<<|<>|>&|<&|>\||>|<)")
# A path inside an unresolvable word starts where a word or an operator ends, as in
# `${X:-/etc/file}`; a `/` after a name character or a `.` continues a relative path.
_PATH = re.compile(r"(?<![\w.])[~/][^{}$(),`\"'\s]*")
_BREAKS = {";", "|", "||", "&", "&&", "(", ")"}
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


# Deeper nesting than this leaves the command with no reading rather than recursing further.
_MAX_NESTING = 32


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


def _expansion_end(command: str, start: int, depth: int = 0) -> int | None:  # noqa: C901
    """Return the index after the `$(…)`, `$((…))`, `${…}`, or backquote that opens at `start`.

    The contents are not read, only their boundary, which follows bash: quotes
    and nested expansions inside are matched, a comment inside `$(…)` runs to
    its newline, and a backquote ends at the first unescaped backquote.
    `None` where the text ends first, nesting runs deeper than `_MAX_NESTING`,
    or the boundary depends on grammar the scan does not follow: a
    here-document or a `case` pattern inside `$(…)`, a quote inside `$((…))`,
    or `$((` that closes as two nested subshells.
    """
    if depth > _MAX_NESTING:
        return None
    if command[start] == "`":
        index = start + 1
        while index < len(command):
            if command[index] == "\\":
                index += 2
            elif command[index] == "`":
                return index + 1
            else:
                index += 1
        return None
    arithmetic = command.startswith("$((", start)
    braced = command.startswith("${", start)
    opening, closing = ("{", "}") if braced else ("(", ")")
    index = start + (3 if arithmetic else 2)
    level = 0
    word_start = True
    while index < len(command):
        char = command[index]
        if char == "\\":
            index += 2
            word_start = False
            continue
        if arithmetic and char in "'\"":
            return None
        if char == "'":
            end = command.find("'", index + 1)
            if end < 0:
                return None
            index, word_start = end + 1, False
            continue
        if char == '"':
            end = _double_quote_end(command, index, depth)
            if end is None:
                return None
            index, word_start = end, False
            continue
        if _opens_substitution(command, index):
            end = _expansion_end(command, index, depth + 1)
            if end is None:
                return None
            index, word_start = end, False
            continue
        if not braced and not arithmetic:
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
                return None
            if word_start and re.match(r"case\b", command[index:]):
                return None
        if char == opening:
            level += 1
        elif char == closing:
            if level:
                level -= 1
            elif not arithmetic:
                return index + 1
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


def _reserved_in_command_position(words: list[_Token]) -> bool:
    """Return whether an unquoted reserved word stands in command position.

    Command position is the first word, or the first after a control operator.
    An assignment or a redirection before a word takes the position, so in
    `X=1 if` and `echo done` the reserved word is a name or an argument.
    """
    position = True
    for word in words:
        if word.operator:
            position = not _REDIRECTION.fullmatch(word.value)
            continue
        if position and not word.quoted and word.value in _MULTI_LINE_RESERVED:
            return True
        position = False
    return False


def _here_document(command: str, index: int, delimiter: _Token, strip: bool) -> tuple[_Token, int] | None:
    """Read one here-document body from `index`; return its token and the index after the delimiter line.

    `None` where the body never ends, the delimiter holds an expansion, or a
    line under an unquoted delimiter ends in a line continuation.
    """
    if set(delimiter.active) & {"$", "`"} or delimiter.home:
        return None
    quoted = delimiter.quoted
    lines = []
    while index < len(command):
        end = command.find("\n", index)
        line = command[index:] if end < 0 else command[index:end]
        index = len(command) if end < 0 else end + 1
        if strip:
            line = line.lstrip("\t")
        if line == delimiter.value:
            break
        # Under an unquoted delimiter a trailing backslash joins the next line, delimiter included.
        if end < 0 or (not quoted and line.endswith("\\")):
            return None
        lines.append(line + "\n")
    else:
        return None
    body = "".join(lines)
    expands = not quoted and any(char in body for char in "$`")
    if not quoted and not expands:
        body = body.replace("\\\\", "\\")
    return _Token(body, "$" if expands else "", quoted, raw=body, here_document=True), index


def _split_words(command: str) -> list[_Token] | None:  # noqa: C901
    words: list[_Token] = []
    value: list[str] = []
    active: set[str] = set()
    quoted = started = tilde = home_reference = literal_glob = False
    index = 0
    word_start = 0
    # A here-document operator waits for its delimiter word; each delimiter
    # read waits, by its place in `words`, for the body after the line ends.
    awaiting_delimiter: str | None = None
    awaiting_body: list[tuple[int, bool]] = []
    multi_line = "\n" in command

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
        # A line continuation joins the lines before bash reads operators or comments.
        if command.startswith("\\\n", index):
            return None
        if char == "\n":
            flush()
            if awaiting_delimiter is not None:
                return None
            index += 1
            # The bodies of the line's here-documents start on the next line, in order.
            for position, strip in awaiting_body:
                body = _here_document(command, index, words[position], strip)
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
        if not started and command.startswith("((", index) and not multi_line and awaiting_delimiter is None:
            end = _arithmetic_end(command, index)
            if end is None:
                return None
            text = command[index:end]
            words.append(_Token(text, "$", raw=text))
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
            if command[index : index + 3] == "&>>":
                end += 2
            elif end < len(command) and command[index : end + 1] in {
                "&&",
                "||",
                "&>",
                ">>",
                "<<",
                "<>",
                ">&",
                "<&",
                ">|",
                "|&",
                ";;",
            }:
                end += 1
            operator = descriptor + command[index:end]
            # A parenthesis opens a subshell or arithmetic, where `<<` may be a shift.
            if multi_line and operator in {"(", ")"}:
                return None
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
        ansi = command[index : index + 2] == "$'"
        if char == "'" or ansi:
            begin = index + (2 if ansi else 1)
            end = begin
            while end < len(command):
                if ansi and command[end] == "\\":
                    end += 2
                elif command[end] == "'":
                    break
                else:
                    end += 1
            if end >= len(command):
                return None
            body = command[begin:end]
            literal(_ansi_c(body) if ansi else body)
            quoted = True
            index = end + 1
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
                        return None
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
    if multi_line and _reserved_in_command_position(words):
        return None
    return words


def is_assignment(value: str) -> bool:
    """Return whether a word has the shape `NAME=`, wherever it stands.

    The `assignment` kind marks only the leading words the shell assigns; a
    later word of the same shape is an operand such as `dd of=`.
    """
    return _ASSIGNMENT.match(value) is not None


def unresolved_paths(value: str) -> tuple[str, ...]:
    """Keep possible path spellings from text the lexer cannot resolve."""
    pieces = [value, *re.split(r"[{},()\s\"']", value), *_PATH.findall(value)]
    return tuple(dict.fromkeys(piece for piece in pieces if piece))


def _resolve(token: _Token, roots: list[str | None], *, home_known: bool = True) -> list[str] | None:
    active = set(token.active)
    if active & {"$", "`"}:
        return None
    if (token.tilde or token.home) and not home_known:
        return None
    if ("{" in active) != ("}" in active):
        return None
    if "{" in active and ("," in active or ".." in token.value):
        return None
    if token.tilde and _STACK_TILDE.match(token.value):
        return None
    value = os.path.expanduser(token.value) if token.tilde else token.value
    if _ASSIGNMENT.match(token.raw):
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


# Reserved words and wrappers that leave the word after them in command position.
_RESERVED = {"!", "{", "}", "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "time"}
# Reserved words a multi-line command may not hold in command position: across
# lines, which newline ends a command depends on compound-command grammar this
# lexer does not parse.
_MULTI_LINE_RESERVED = _RESERVED | {"for", "case", "esac", "select", "function", "coproc", "[["}
# Reserved words that are not the program they precede. `time` stays a word,
# because readers treat it as a wrapper that takes options.
_KEYWORDS = _RESERVED - {"time"}
# Builtins that run text or change the shell in ways these words do not show.
_OPAQUE = {"eval", "source", ".", "trap", "shopt"}
# Assignments that change where `cd` goes or what `~` and `$HOME` mean.
_DIRECTORY_VARIABLES = re.compile(r"^(?:HOME|CDPATH)(?:=|$)")
# Reserved words that open a loop, whose body may run any number of times.
_LOOPS = {"while", "until", "for", "select"}
# What a segment does to the directory, where it names no path: distinct objects,
# so no directory name can be mistaken for one.
_UNKNOWN = object()
_STAYS = object()
_FAILS = object()


def _reserved(word: Word, names: set[str] = _RESERVED) -> bool:
    """Return whether `word` is one of the reserved `names`; quoting makes it an ordinary word."""
    return not word.quoted and word.value in names


def _expands(value: str) -> bool:
    """Return whether an unresolvable word's text holds an expansion, not only a relative path."""
    return any(char in value for char in "$`{*?[")


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
    if not rest:
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
    directories = _Directories(cwd)
    for token in [*tokens, _Token(";", operator=True)]:
        if token.operator:
            if redirect:
                return None
            if _REDIRECTION.fullmatch(token.value):
                redirect = token.value
                continue
            if token.value not in _BREAKS:
                return None
            if segment:
                segments.append(Segment(segment, token.value, directories.spelled()))
            directories.follow(keywords + segment, token.value)
            segment, keywords = [], []
            has_command = False
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
        if not segment and redirect is None and not token.quoted and token.value in _KEYWORDS:
            keywords.append(Word(token.value, "plain word"))
            continue
        moved = directories.moved
        produced = _resolve(token, directories.roots(), home_known=directories.home_known)
        is_assignment = not has_command and bool(_ASSIGNMENT.match(token.raw))
        is_command = not has_command and not is_assignment and redirect is None
        if produced is None:
            segment.append(
                Word(token.value, "unresolvable", directories.evidence(token.value), redirect, token.quoted)
            )
        else:
            for position, value in enumerate(produced):
                kind: Kind
                if redirect:
                    kind = "redirection target"
                elif is_assignment:
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
    return segments


def lex(command: str, cwd: str | None) -> list[Segment] | None:
    """Return segments with word kinds, or no reading for an unresolvable command."""
    try:
        return _lex(command, cwd)
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None
