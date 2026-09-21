"""Read Bash command text for path-judging hooks without running it.

Newlines, including backslash line continuations and quoted newlines, refuse
the whole command. Substitutions and brace expansions retain their written
paths but are unresolvable. Directory changes are not tracked: later relative
paths are unresolvable. Callers should name paths absolutely.
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


class Segment(list[Word]):
    """Words passed to one command, with the control operator after it."""

    def __init__(self, words: list[Word], separator: str) -> None:
        super().__init__(words)
        self.separator = separator


@dataclass(frozen=True)
class _Token:
    value: str
    active: str = ""
    quoted: bool = False
    operator: bool = False
    tilde: bool = False
    raw: str = ""


_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIRECTION = re.compile(r"(?:[0-9]+)?(?:>>|<<|<>|>&|<&|>\||>|<)")
_PATH = re.compile(r"[~/][^{}$(),`\"'\s]*")
_BREAKS = {";", "|", "||", "&", "&&", "(", ")"}


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


def _substitution_end(command: str, start: int) -> int | None:
    """Find a balanced substitution without interpreting its contents."""
    opening = command[start + 1]
    closing = ")" if opening == "(" else "}"
    depth = 1
    quote = ""
    index = start + 2
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _split_words(command: str) -> list[_Token] | None:  # noqa: C901
    words: list[_Token] = []
    value: list[str] = []
    active: set[str] = set()
    quoted = started = tilde = False
    index = 0
    word_start = 0

    def flush() -> None:
        nonlocal value, active, quoted, started, tilde
        if started:
            words.append(
                _Token(
                    "".join(value),
                    "".join(sorted(active)),
                    quoted,
                    False,
                    tilde,
                    command[word_start:index],
                )
            )
        value, active = [], set()
        quoted = started = tilde = False

    while index < len(command):
        char = command[index]
        if char.isspace():
            flush()
            index += 1
            continue
        if char in "();<>|&":
            descriptor = ""
            if char in "<>" and not quoted and "".join(value).isdigit():
                descriptor = "".join(value)
                value, active = [], set()
                started = False
            flush()
            end = index + 1
            if end < len(command) and command[index : end + 1] in {
                "&&",
                "||",
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
            words.append(_Token(operator, operator=True))
            index = end
            continue
        if char == "#" and not started:
            break
        if not started:
            word_start = index
            tilde = char == "~"
        started = True
        if char == "\\":
            if index + 1 == len(command):
                return None
            value.append(command[index + 1])
            quoted = True
            index += 2
            continue
        if command[index : index + 2] in {"$(", "${"}:
            end = _substitution_end(command, index)
            if end is None:
                return None
            value.append(command[index:end])
            active.add("$")
            index = end
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
            value.append(_ansi_c(body) if ansi else body)
            quoted = True
            index = end + 1
            continue
        if char == '"':
            index += 1
            while index < len(command) and command[index] != '"':
                char = command[index]
                if char == "\\" and index + 1 < len(command) and command[index + 1] in '$`"\\':
                    value.append(command[index + 1])
                    index += 2
                    continue
                if char in "$`":
                    active.add(char)
                value.append(char)
                index += 1
            if index == len(command):
                return None
            quoted = True
            index += 1
            continue
        if char in "$`*?[{},":
            active.add(char)
        value.append(char)
        index += 1
    flush()
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


def _resolve(token: _Token, cwd: str | None) -> list[str] | None:
    active = set(token.active)
    if active & {"$", "`"}:
        return None
    if ("{" in active) != ("}" in active):
        return None
    if "{" in active and ("," in active or ".." in token.value):
        return None
    value = os.path.expanduser(token.value) if token.tilde else token.value
    if _ASSIGNMENT.match(token.raw) and token.raw.partition("=")[2].startswith("~"):
        name, _, operand = value.partition("=")
        value = name + "=" + os.path.expanduser(operand)
    if not active & set("*?["):
        return [value]
    if token.quoted or (cwd is None and not os.path.isabs(value)):
        return None
    return sorted(glob.glob(value, root_dir=cwd)) or [value]


def _lex(command: str, cwd: str | None) -> list[Segment] | None:
    if any(char in command for char in ("\n", "\r", "\x00")):
        return None
    tokens = _split_words(command)
    if tokens is None:
        return None
    segments: list[Segment] = []
    segment: list[Word] = []
    redirect: str | None = None
    has_command = directory_changed = False
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
                segments.append(Segment(segment, token.value))
                directory_changed |= any(
                    word.kind == "command" and word.value in {"cd", "pushd", "popd"} for word in segment
                )
            segment = []
            has_command = False
            continue
        produced = _resolve(token, cwd)
        is_assignment = not has_command and bool(_ASSIGNMENT.match(token.raw))
        is_command = not has_command and not is_assignment and redirect is None
        if produced is None:
            segment.append(Word(token.value, "unresolvable", unresolved_paths(token.value), redirect))
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
                    and (directory_changed or cwd is None)
                    and (
                        kind in {"path candidate", "redirection target"}
                        or (directory_changed and kind == "plain word")
                    )
                ):
                    kind = "unresolvable"
                paths = unresolved_paths(value) if kind == "unresolvable" else ()
                segment.append(Word(value, kind, paths, redirect))
        has_command |= is_command
        redirect = None
    return segments


def lex(command: str, cwd: str | None) -> list[Segment] | None:
    """Return segments with word kinds, or no reading for an unresolvable command."""
    try:
        return _lex(command, cwd)
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None
