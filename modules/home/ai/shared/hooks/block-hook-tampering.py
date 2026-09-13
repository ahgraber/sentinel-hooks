#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Gate mutations to agent guardrails and stored credentials.

Guardrail mutations ask when the agent and tool support prompts and block
otherwise. Credential mutations always block. Recognized reads and existing
scripts in exec-through paths may proceed; unresolved commands gate. Markdown
directly under instruction directories has a narrow write exemption.
"""

import glob as globbing
import json
import os
import re
import shlex
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from guarded_paths import (
    MANIFEST_PATH,
    GuardedLocations,
    ManifestError,
    fragment,
    load_manifest,
    spellings,
)
from hook_response import Decision, invoking_agent, respond, supports_ask

PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (?P<path>.+)$",
    re.MULTILINE,
)


def build_guarded(manifest_path: Path = MANIFEST_PATH):
    """Load guard sets from `manifest_path`.

    On failure, return empty sets and an error string instead of raising.
    """
    try:
        manifest = load_manifest(manifest_path)
        gated = manifest["gated"]
        guarded_files = tuple(gated["deployed"]) + tuple(gated["sources"])
        credential_files = tuple(manifest["credentials"]["paths"])
        instruction_layers = tuple(
            tuple(pair) for pair in manifest["instruction-layers"]["layers"]
        )
        location_only = tuple(manifest["location-only"]["paths"])
        read_through = tuple(manifest["read-through"]["paths"])
        exec_through = tuple(manifest["exec-through"]["paths"])
        error = None
    except (ManifestError, KeyError, TypeError) as exc:
        guarded_files = credential_files = instruction_layers = location_only = ()
        read_through = exec_through = ()
        error = str(exc)

    guarded = GuardedLocations(
        guarded_files + tuple(location for location, _ in instruction_layers),
        location_only=location_only,
    )
    credentials = GuardedLocations(credential_files)
    return (
        guarded,
        credentials,
        guarded_files,
        credential_files,
        instruction_layers,
        location_only,
        error,
        GuardedLocations(read_through),
        GuardedLocations(exec_through),
    )


(
    GUARDED,
    CREDENTIALS,
    GUARDED_FILES,
    CREDENTIAL_FILES,
    INSTRUCTION_LAYERS,
    LOCATION_ONLY,
    MANIFEST_ERROR,
    READ_THROUGH,
    EXEC_THROUGH,
) = build_guarded()

GATED = "gated"
CREDENTIAL = "credential"

MUTATING_TOOLS = ("Write", "Edit", "apply_patch", "Bash")

INSTRUCTION_BASES = tuple(
    GUARDED.normalize(fragment(location) + layer)
    for location, layer in INSTRUCTION_LAYERS
)


def _ask_reason(target: str, tool_name: str) -> str:
    """The prompt the user decides on. It addresses the user alone."""
    return (
        f"This {tool_name} call would modify agent enforcement at '{target}'. "
        "Approve only if you intend this guardrail change."
    )


def _accepted_forms() -> str:
    return (
        " Recognized reads use: "
        + ", ".join(sorted(READ_ONLY_UTILITIES))
        + ". Existing scripts can run directly or as file arguments to: "
        + ", ".join(sorted(INTERPRETERS))
        + ". The classifier rejects redirection, environment assignments, "
        "inline code, variables, command substitutions, and brace expansions. "
        "Globs such as `*.md` are checked against their current matches."
    )


def _unrecognized_read_reason(target: str, tool_name: str) -> str:
    return (
        f"This {tool_name} call targets '{target}' but is not recognized as a "
        "read or existing script run. It may write there. Approve only if you "
        "intend to run it as written." + _accepted_forms()
    )


def _unrecognized_read_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} on '{target}' is not a recognized read or "
        "existing script run. It may write, and this agent cannot ask for the "
        "required approval." + _accepted_forms()
    )


def _ancestor_reason(target: str, tool_name: str) -> str:
    """The prompt for a destructive operation on the path to a guarded location."""
    return (
        f"This {tool_name} call would remove, rename, or replace '{target}', "
        "which holds agent enforcement. Approve only if you intend to remove "
        "the directory and its guardrails."
    )


def _ancestor_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} would remove, rename, or replace '{target}', "
        "which holds agent enforcement. This agent cannot ask for the required "
        "approval."
    )


def _degraded_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} targets agent enforcement at '{target}'. "
        "This agent cannot ask for the required approval."
    )


def _credential_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} targets stored agent credentials at '{target}'. "
        "In-session changes to agent authentication cannot be approved."
    )


def is_instruction_markdown(path: str) -> bool:
    """Return whether `path` resolves to Markdown directly under an instructions directory."""
    if not path:
        return False
    normalized = GUARDED.normalize(spellings(path)[-1])
    if not normalized.endswith(".md"):
        return False
    for base in INSTRUCTION_BASES:
        if base not in normalized:
            continue
        name = normalized.rsplit(base, 1)[1]
        if name and "/" not in name:
            return True
    return False


def is_protected_path(path: str) -> bool:
    """True if a tool call naming `path` must not proceed unexamined."""
    return not is_instruction_markdown(path) and (
        GUARDED.contains(path) or CREDENTIALS.contains(path)
    )


def protected_class(path: str) -> str | None:
    """Return `path`'s protected class, giving credentials precedence, or `None`."""
    if CREDENTIALS.contains(path):
        return CREDENTIAL
    if is_protected_path(path):
        return GATED
    return None


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


# Strip attached redirections and option assignments before checking paths.
_ATTACHED_RE = re.compile(r"^(?:[0-9]*(?:&?>{1,2}\|?|<{1,2}&?)|[^\s=]*=)")


def _paths_in(command: str) -> list[str]:
    """Return command tokens and paths they contain before and after expansion."""
    found = []
    for token in [
        *_tokens(command),
        *_candidate_words(command),
        *(_expanded(command) or []),
    ]:
        found.append(token)
        carried = _ATTACHED_RE.sub("", token, count=1)
        if carried and carried != token:
            found.append(carried)
    return found


def command_mentions_protected_path(command: str) -> bool:
    """Return whether command text or a named path reaches a guarded location."""
    return (
        GUARDED.mentioned_in(command)
        or CREDENTIALS.mentioned_in(command)
        or any(
            GUARDED.contains(path) or CREDENTIALS.contains(path)
            for path in _paths_in(command)
        )
    )


def _only_instruction_markdown(candidates: list[str]) -> bool:
    protected = [c for c in candidates if GUARDED.contains(c)]
    return bool(protected) and all(is_instruction_markdown(c) for c in protected)


# Allow utilities that only read arguments; exclude helper execution and
# write-capable options. `echo` and `printf` are harmless separators.
READ_ONLY_UTILITIES = frozenset(
    {
        "basename", "cat", "cksum", "column", "comm", "cut", "diff", "dirname",
        "du", "echo", "egrep", "fgrep", "file", "find", "fold", "grep", "head",
        "jq", "ls", "md5sum", "nl", "od", "printf", "readlink", "realpath",
        "rev", "sha1sum", "sha256sum", "shasum", "sort", "stat", "strings",
        "tail", "tr", "uniq", "wc", "xxd",
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
    "sort": ("o", ("--output", "--compress-program")),
}  # fmt: skip

INTERPRETERS = frozenset(
    {
        "bash", "deno", "node", "perl", "python", "python3", "ruby", "Rscript",
        "sh", "uv", "uvx", "zsh",
    }
)  # fmt: skip

# These run text from the command line instead of a file, so a path matched
# beside one is a string the interpreter never opens.
INLINE_CODE_OPTIONS = frozenset({"-c", "--command", "-e", "--eval", "--exec"})

# Accept executable files and known script suffixes.
SCRIPT_SUFFIXES = frozenset(
    {".bash", ".cjs", ".js", ".mjs", ".pl", ".py", ".r", ".rb", ".sh", ".ts", ".zsh"}
)

# A run of these is one token, so an unlisted run such as `|&` is rejected
# rather than read as an argument.
SEGMENT_BREAKS = frozenset({";", ";;", "|", "||", "&", "&&", "(", ")", "<", "<<"})
PUNCTUATION = set("();<>|&")

# Characters the shell acts on rather than passes through. Each is recorded per
# word only where it falls outside quotes, because a quoted one is text.
OPERATOR_CHARS = "();<>|&"
EXPANSION_CHARS = "$`"  # parameter, command, and arithmetic substitution
PATHNAME_CHARS = "*?["  # pathname expansion, which this classifier performs
BRACE_CHARS = "{},"  # brace expansion, which it refuses

_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _read_only_segment(segment: list[str]) -> bool:
    """True if one pipeline segment runs a utility that only reads its arguments."""
    name, *args = segment
    # A path-qualified name and a leading assignment both pick which binary runs.
    if "/" in name or "\\" in name or _ASSIGNMENT_RE.match(name):
        return False
    if name not in READ_ONLY_UTILITIES:
        return False
    letters, whole = WRITE_OPTIONS.get(name, ("", ()))
    for arg in args:
        # The shell expands this into an option the classifier cannot see.
        if arg.startswith("-") and "$" in arg:
            return False
        if arg in whole or any(arg.startswith(f"{token}=") for token in whole):
            return False
        cluster = letters and arg.startswith("-") and not arg.startswith("--")
        if cluster and any(letter in arg[1:] for letter in letters):
            return False
    return True


def _exec_through_script(token: str) -> bool:
    """Return whether `token` names an existing script in an exec-through location."""
    if not EXEC_THROUGH.contains(token):
        return False
    resolved = spellings(token)[-1]
    if not os.path.isfile(resolved):
        return False
    suffix = os.path.splitext(resolved)[1].casefold()
    return suffix in SCRIPT_SUFFIXES or os.access(resolved, os.X_OK)


def _script_exec_segment(segment: list[str]) -> bool:
    """Return whether a segment runs exactly one exec-through script, directly or through an interpreter."""
    name, *args = segment
    if _ASSIGNMENT_RE.match(name):
        return False
    if _exec_through_script(name):
        scripts = 1
    elif "/" in name or "\\" in name or name not in INTERPRETERS:
        return False
    else:
        scripts = 0
    for arg in args:
        if arg.startswith("-"):
            if "$" in arg or arg.split("=", 1)[0] in INLINE_CODE_OPTIONS:
                return False
            continue
        if _exec_through_script(arg):
            scripts += 1
    return scripts == 1


@dataclass(frozen=True)
class Word:
    """A shell word or run of operators.

    `active` lists unquoted syntax characters that can change `value`.
    """

    value: str
    active: str
    quoted: bool
    operator: bool


def _ansi_c(body: str) -> str:
    """The characters an ANSI-C quoted body stands for."""
    return body.encode("latin-1", "backslashreplace").decode("unicode_escape")


def _split_words(command: str) -> list[Word] | None:
    """Split `command` into words and operator runs; return `None` for unclosed quotes.

    Preserve quote context and decode ANSI-C quoting, which `shlex` does not.
    """
    words: list[Word] = []
    value: list[str] = []
    active: set[str] = set()
    quoted = False
    started = False
    index = 0
    length = len(command)

    def flush() -> None:
        nonlocal value, active, quoted, started
        if started:
            words.append(Word("".join(value), "".join(sorted(active)), quoted, False))
        value, active, quoted, started = [], set(), False, False

    while index < length:
        char = command[index]
        if char.isspace():
            flush()
            index += 1
            continue
        if char in OPERATOR_CHARS:
            flush()
            end = index
            while end < length and command[end] in OPERATOR_CHARS:
                end += 1
            run = command[index:end]
            words.append(Word(run, run, False, True))
            index = end
            continue

        started = True
        if char == "\\":
            if index + 1 >= length:
                return None
            value.append(command[index + 1])
            quoted = True
            index += 2
            continue
        if char == "'":
            close = command.find("'", index + 1)
            if close < 0:
                return None
            value.append(command[index + 1 : close])
            quoted = True
            index = close + 1
            continue
        if char == '"':
            index += 1
            while index < length and command[index] != '"':
                escaped = index + 1 < length and command[index + 1] in '$`"\\\n'
                if command[index] == "\\" and escaped:
                    value.append(command[index + 1])
                    index += 2
                    continue
                if command[index] in EXPANSION_CHARS:
                    active.add(command[index])
                value.append(command[index])
                index += 1
            if index >= length:
                return None
            quoted = True
            index += 1
            continue
        if char == "$" and index + 1 < length and command[index + 1] == "'":
            end = index + 2
            body: list[str] = []
            while end < length and command[end] != "'":
                if command[end] == "\\" and end + 1 < length:
                    body.append(command[end : end + 2])
                    end += 2
                    continue
                body.append(command[end])
                end += 1
            if end >= length:
                return None
            try:
                value.append(_ansi_c("".join(body)))
            except (UnicodeDecodeError, UnicodeEncodeError):
                return None
            quoted = True
            index = end + 1
            continue

        if char in EXPANSION_CHARS + PATHNAME_CHARS + BRACE_CHARS:
            active.add(char)
        value.append(char)
        index += 1

    if started:
        flush()
    return words


def _resolve(word: Word) -> list[str] | None:
    """Resolve pathname expansion; return `None` for substitutions or braces.

    Leave unmatched globs unchanged.
    """
    if set(word.active) & set(EXPANSION_CHARS):
        return None
    # Brace expansion happens before word splitting, so a group holding an
    # unquoted space arrives here as several words, none of which states the
    # whole group. A word carrying one brace without its partner is therefore
    # part of a group this word cannot be judged against. Refusing it gates the
    # command, which is the safe direction; the paths it holds stay visible to
    # `_candidate_words`.
    opened, closed = "{" in word.active, "}" in word.active
    if opened != closed:
        return None
    if opened and ("," in word.active or ".." in word.value):
        return None
    if not set(word.active) & set(PATHNAME_CHARS):
        return [word.value]
    # A partly quoted pattern globs on its unquoted half alone, and the written
    # form no longer states which half that is.
    if word.quoted:
        return None
    pattern = os.path.expanduser(word.value)
    try:
        matches = sorted(globbing.glob(pattern))
    except (OSError, ValueError, RecursionError):
        return None
    return matches or [pattern]


# Brace expansion states its words in the text, separated by these.
_BRACE_PIECE_RE = re.compile(r"[{},]")

# A path held inside text the classifier could not resolve. It starts at a
# separator, so an ordinary word is not read as one, and ends where a character
# a path cannot hold begins.
_EMBEDDED_PATH_RE = re.compile(r"[~/][^{}$,`\"'\s]*")


def _candidate_words(command: str) -> list[str]:
    """Return every path stated in `command`, including unresolved expansions."""
    words = _split_words(command)
    if words is None:
        return []
    found: list[str] = []
    for word in words:
        if word.operator:
            continue
        found.append(word.value)
        if not word.active:
            continue
        found.extend(piece for piece in _BRACE_PIECE_RE.split(word.value) if piece)
        found.extend(_EMBEDDED_PATH_RE.findall(word.value))
    return found


def _expanded(command: str) -> list[str] | None:
    """The words `command` produces, or None if any of them cannot be resolved."""
    # A newline separates commands, and one inside quotes is text this
    # classifier has no reason to judge either way. A null byte cannot survive
    # into a shell word at all, so text holding one is not the command that runs.
    if any(marker in command for marker in ("\n", "\r", "\x00")):
        return None
    words = _split_words(command)
    if words is None:
        return None
    resolved: list[str] = []
    for word in words:
        if word.operator:
            resolved.append(word.value)
            continue
        produced = _resolve(word)
        if produced is None:
            return None
        resolved.extend(produced)
    return resolved


def _segments(command: str) -> list[list[str]] | None:
    """`command` split into pipeline segments, or None if it cannot be judged."""
    tokens = _expanded(command)
    if tokens is None:
        return None

    segments: list[list[str]] = []
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token and set(token) <= PUNCTUATION and token not in SEGMENT_BREAKS:
            return None
        if token not in SEGMENT_BREAKS:
            segment.append(token)
            continue
        if segment:
            segments.append(segment)
        segment = []
    return segments or None


def _segment_names_guarded(segment: list[str]) -> bool:
    """True if any token of `segment` reaches a guarded location."""
    for token in segment:
        carried = _ATTACHED_RE.sub("", token, count=1)
        for candidate in (token, carried):
            if candidate and (
                GUARDED.contains(candidate) or CREDENTIALS.contains(candidate)
            ):
                return True
    return False


def _judged(segment: list[str]) -> bool:
    """Return whether `segment` names a guarded location and requires classification."""
    return _segment_names_guarded(segment)


def is_read_only_command(command: str) -> bool:
    """Return whether each guarded segment is a recognized read; unresolved commands return `False`."""
    segments = _segments(command)
    return segments is not None and all(
        _read_only_segment(segment) or not _judged(segment) for segment in segments
    )


def runs_exec_through_script(command: str) -> bool:
    """Return whether `command` runs an exec-through script and other guarded segments are reads."""
    segments = _segments(command)
    if segments is None:
        return False
    return any(_script_exec_segment(segment) for segment in segments) and all(
        _script_exec_segment(segment)
        or _read_only_segment(segment)
        or not _judged(segment)
        for segment in segments
    )


def _carved_out(path: str) -> bool:
    """Return whether every guarded spelling of `path` is read-through or exec-through."""
    return not any(
        GUARDED.contains(form)
        and not (READ_THROUGH.contains(form) or EXEC_THROUGH.contains(form))
        for form in spellings(path)
    )


def only_carved_out(command: str) -> bool:
    """True if every guarded path `command` names is read-through or exec-through.

    One guarded path outside those locations gates the whole command.
    """
    named = [path for path in _paths_in(command) if GUARDED.contains(path)]
    return bool(named) and all(_carved_out(path) for path in named)


# These programs can destroy a declared tree through its ancestor. `mv` destroys
# all operands; `cp`, `install`, `ln`, and `truncate` replace only the last.
DESTROYS_EVERY_OPERAND = frozenset({"mv", "rm", "rmdir", "shred", "unlink"})
DESTROYS_LAST_OPERAND = frozenset({"cp", "install", "ln", "truncate"})
DESTRUCTIVE = DESTROYS_EVERY_OPERAND | DESTROYS_LAST_OPERAND


def _destroyed_operands(segment: list[str]) -> list[str]:
    """The operands `segment` removes, renames, or replaces."""
    name, *args = segment
    if "/" in name or "\\" in name or _ASSIGNMENT_RE.match(name):
        return []
    operands = [arg for arg in args if not arg.startswith("-")]
    if name in DESTROYS_EVERY_OPERAND:
        return operands
    if name in DESTROYS_LAST_OPERAND:
        return operands[-1:]
    return []


def destroys_a_guarded_ancestor(command: str) -> str | None:
    """Return a guarded ancestor removed, renamed, or replaced by `command`.

    For commands that cannot be segmented, inspect every candidate and favor asking.
    """
    segments = _segments(command)
    if segments is None:
        tokens = _candidate_words(command) or _tokens(command)
        if not any(token in DESTRUCTIVE for token in tokens):
            return None
        candidates = tokens
    else:
        candidates = [
            operand for segment in segments for operand in _destroyed_operands(segment)
        ]

    for candidate in candidates:
        if GUARDED.encloses(candidate) or CREDENTIALS.encloses(candidate):
            return candidate
    return None


def extract_apply_patch_targets(command: str) -> list[str]:
    return [match.group("path").strip() for match in PATCH_PATH_RE.finditer(command)]


# Most restrictive first: a mutation reaching several classes takes the first.
_CLASS_ORDER = (CREDENTIAL, GATED)


def _most_restrictive(*classes: str | None) -> str | None:
    for cls in _CLASS_ORDER:
        if cls in classes:
            return cls
    return None


def _first_in_class(candidates: list[str], cls: str) -> str | None:
    for candidate in candidates:
        if protected_class(candidate) == cls:
            return candidate
    return None


def command_protected_class(command: str) -> str | None:
    """Return `command`'s most restrictive protected class, or `None`.

    Use `protected_class()` when the written paths are already known.
    """
    candidates = _paths_in(command)
    if CREDENTIALS.mentioned_in(command) or any(
        CREDENTIALS.contains(path) for path in candidates
    ):
        return CREDENTIAL
    named = GUARDED.mentioned_in(command) or any(
        GUARDED.contains(path) for path in candidates
    )
    if named and not _only_instruction_markdown(candidates):
        return GATED
    return None


def gate(
    target: str,
    tool_name: str,
    cls: str,
    agent: str,
    ask: Callable[[str, str], str] = _ask_reason,
    refuse: Callable[[str, str], str] = _degraded_refusal,
) -> NoReturn:
    """Apply the protected mutation policy and exit.

    Credentials block. Guarded paths ask when supported and block otherwise.
    """
    if cls == CREDENTIAL:
        respond(Decision.BLOCK, _credential_refusal(target, tool_name), agent=agent)
    if supports_ask(agent, tool_name):
        respond(
            Decision.ASK,
            ask(target, tool_name),
            agent=agent,
            tool_name=tool_name,
        )
    respond(Decision.BLOCK, refuse(target, tool_name), agent=agent)


def _written_paths(tool_input: dict) -> list[str]:
    paths = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            paths.append(value)
    for value in tool_input.get("file_paths") or []:
        if isinstance(value, str):
            paths.append(value)
    return paths


# Store the parsed tool and agent for failure handling. An unnamed tool follows
# the read-only path.
_CALL = {"tool_name": "", "agent": ""}


def internal_error(exc: BaseException) -> NoReturn:
    """Handle an unexpected failure: warn for reads, ask or block for writes."""
    # Reuse parsed state because recomputing the agent can repeat the failure.
    agent, tool_name = _CALL["agent"], _CALL["tool_name"]
    fault = f"{type(exc).__name__}: {exc}"
    if tool_name not in MUTATING_TOOLS:
        respond(
            Decision.WARN,
            f"block-hook-tampering failed ({fault}). This non-mutating call "
            "will proceed unchecked.",
            agent=agent,
        )
    reason = (
        f"block-hook-tampering failed while checking this {tool_name} call "
        f"({fault}). It cannot determine whether the call reaches agent "
        "enforcement. Approve only after verifying that it does not, and report "
        "the hook failure."
    )
    if supports_ask(agent, tool_name):
        respond(Decision.ASK, reason, agent=agent, tool_name=tool_name)
    respond(
        Decision.BLOCK,
        f"Blocked: block-hook-tampering failed while checking this {tool_name} "
        f"call ({fault}) and cannot determine whether it reaches agent "
        "enforcement. This agent cannot ask for the required approval.",
        agent=agent,
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (OSError, ValueError):
        # Warn and fail open when the payload cannot be parsed.
        respond(
            Decision.WARN,
            "block-hook-tampering could not parse the hook payload; "
            "this tool call was not checked.",
        )

    # Record the tool before agent detection can fail.
    tool_name = data.get("tool_name", "")
    _CALL["tool_name"] = tool_name
    agent = invoking_agent(payload=data)
    _CALL["agent"] = agent

    tool_input = data.get("tool_input", {})

    # Return before manifest checks for tools this hook does not mutate, including
    # `Read`.
    if tool_name not in MUTATING_TOOLS:
        sys.exit(0)

    if MANIFEST_ERROR is not None:
        # Report a broken manifest and fail open instead of guessing.
        respond(
            Decision.WARN,
            "block-hook-tampering could not load guarded-paths.toml "
            f"({MANIFEST_ERROR}); this tool call was not checked.",
            agent=agent,
        )

    if tool_name in ("Write", "Edit"):
        paths = _written_paths(tool_input)
        cls = _most_restrictive(*(protected_class(path) for path in paths))
        if cls is not None:
            gate(_first_in_class(paths, cls) or paths[0], tool_name, cls, agent)

    elif tool_name == "apply_patch":
        command = tool_input.get("command", "")
        if isinstance(command, str) and command:
            targets = extract_apply_patch_targets(command)
            if targets:
                cls = _most_restrictive(*(protected_class(path) for path in targets))
            else:
                cls = command_protected_class(command)
            if cls is not None:
                gate(
                    _first_in_class(targets, cls) or command,
                    tool_name,
                    cls,
                    agent,
                )

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            cls = command_protected_class(command)
            ask, refuse = _ask_reason, _degraded_refusal
            if cls == GATED and only_carved_out(command):
                if is_read_only_command(command) or runs_exec_through_script(command):
                    cls = None
                else:
                    ask = _unrecognized_read_reason
                    refuse = _unrecognized_read_refusal
            if cls is not None:
                gate(
                    _first_in_class(_paths_in(command), cls) or command,
                    tool_name,
                    cls,
                    agent,
                    ask,
                    refuse,
                )

            # Read carve-outs do not permit removing their guarded ancestors.
            ancestor = destroys_a_guarded_ancestor(command)
            if ancestor is not None:
                gate(
                    ancestor,
                    tool_name,
                    GATED,
                    agent,
                    _ancestor_reason,
                    _ancestor_refusal,
                )

    sys.exit(0)


def run() -> None:
    """Judge one tool call; convert unexpected failures to a hook response."""
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        internal_error(exc)


if __name__ == "__main__":
    run()
