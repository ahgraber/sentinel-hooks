#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Gate any tool call that would modify the files constraining an agent.

Every other guardrail here depends on this one: a hook script, a permission
rule, or a hook registration is enforcement, so an edit to it removes or
reshapes a constraint rather than changing a program. That is the user's
decision alone — where the invoking agent can put the decision to the user for
the tool in play, the mutation proceeds only on their approval, and everywhere
else it is refused. Agent credentials are the exception: no legitimate flow
maintains one in-session, so a credential write is refused on every agent, with
no prompt to habituate. One hook carries every agent's protected set, because an
agent able to rewrite another agent's guardrails has removed a constraint that
applies to itself the moment that agent runs.

Reads are allowed. On Linux the sandbox cannot express a read-deny over these
paths — they are Home Manager symlinks into the Nix store, and bubblewrap aborts
every sandboxed command rather than refusing the one read. Write protection is
the boundary here; concealment is not.

A Bash call states no intent, so one naming a guarded path gates either way.
Under a read-through location it is classified first, from the command line
alone: a recognised read proceeds, everything else gates.

Markdown held directly in an instructions directory is prompt text rather than
enforcement and stays writable. The carve-out is narrow: markdown only, one
level deep only, judged by where the path resolves rather than by what it is
called, and a shell command qualifies only when every guarded path it names
qualifies.
"""

import json
import re
import shlex
import sys
from collections.abc import Callable
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
    """Build the matching structures this hook uses from the manifest at `manifest_path`.

    On failure every structure is empty and the trailing `error` is set, so
    `protected_class` returns `None` for everything rather than guessing; the
    caller is responsible for reporting `error` rather than silently checking
    nothing.
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
        error = None
    except (ManifestError, KeyError, TypeError) as exc:
        guarded_files = credential_files = instruction_layers = location_only = ()
        read_through = ()
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
        f"This {tool_name} call would modify '{target}', which is enforcement: "
        "hook scripts, permission rules, hook registrations, and agent "
        "settings constrain what an agent may do. Approving lets this one "
        "change land in a live guardrail, and the constraint it implements "
        "changes with it. Approve only if you are deliberately changing this "
        "guardrail now."
    )


def _accepted_readers() -> str:
    return (
        " Every command in it must come from this list: "
        + ", ".join(sorted(READ_ONLY_UTILITIES))
        + ". No redirection, command substitution, environment assignment, or "
        "option built from a variable."
    )


def _unrecognised_read_reason(target: str, tool_name: str) -> str:
    return (
        f"This {tool_name} call names '{target}', where a read proceeds without "
        "a prompt. This command was not recognised as a read, so it may write "
        "there. Approve only if you meant to run it as written." + _accepted_readers()
    )


def _unrecognised_read_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} on '{target}' is not a recognised read. A read "
        "of this path proceeds, but a command that may write needs the user's "
        "approval, and this agent cannot put that decision to the user."
        + _accepted_readers()
    )


def _degraded_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} targeting agent enforcement path '{target}'.\n"
        "Hook scripts, rules, permissions, and settings constrain what an "
        "agent may do. Changing one requires the user's in-the-moment "
        "approval, and this agent cannot put that decision to the user, so "
        "the mutation is refused."
    )


def _credential_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} targeting stored agent credentials '{target}'.\n"
        "No legitimate flow maintains agent authentication material "
        "in-session, so no approval can permit this write."
    )


def is_instruction_markdown(path: str) -> bool:
    """True if `path` resolves to markdown held directly in an instructions directory.

    Only the resolved destination is judged. A link is a write to whatever it
    points at, so a name that qualifies does not make the write qualify.
    """
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
    """The protected class `path` falls in, or None.

    Credentials are judged first: a credential also resolves into a guarded
    location, and the most restrictive class must win.
    """
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


# The lexer splits words, not shell syntax, so `>file` and `--flag=file` arrive
# as one token each. Strip the operator, or `>alias` reaches what `> alias` is
# refused for.
_ATTACHED_RE = re.compile(r"^(?:[0-9]*(?:&?>{1,2}\|?|<{1,2}&?)|[^\s=]*=)")


def _paths_in(command: str) -> list[str]:
    """Each token of `command`, plus the path any token carries."""
    found = []
    for token in _tokens(command):
        found.append(token)
        carried = _ATTACHED_RE.sub("", token, count=1)
        if carried and carried != token:
            found.append(carried)
    return found


def command_mentions_protected_path(command: str) -> bool:
    """True if `command` reaches a guarded location, by its text or by a path it names.

    Text alone misses a path that reaches a guarded location without naming it,
    such as a symbolic link. Tokens alone miss a command the lexer cannot parse.
    """
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


# Utilities that cannot write or execute. Anything driven by a script or a
# helper program is out: `awk` has `system()`, `sed` has `e` and `w`,
# `rg --pre` and the pagers run a helper, `yq -i` edits in place.
READ_ONLY_UTILITIES = frozenset(
    {
        "basename", "cat", "cksum", "column", "comm", "cut", "diff", "dirname",
        "du", "egrep", "fgrep", "file", "find", "fold", "grep", "head", "jq",
        "ls", "md5sum", "nl", "od", "readlink", "realpath", "rev", "sha1sum",
        "sha256sum", "shasum", "sort", "stat", "strings", "tail", "tr", "uniq",
        "wc", "xxd",
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

# A destination or a command this classifier never sees.
OPAQUE_TEXT = (">", "`", "$(", "\n", "\r")

# `shlex` with `punctuation_chars` emits a run of these as one token, so an
# unlisted run such as `|&` is rejected rather than read as an argument.
SEGMENT_BREAKS = frozenset({";", ";;", "|", "||", "&", "&&", "(", ")", "<", "<<"})
PUNCTUATION = set("();<>|&")

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


def is_read_only_command(command: str) -> bool:
    """True if `command` is recognisably a read. Anything unresolved is False."""
    if any(marker in command for marker in OPAQUE_TEXT):
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False

    checked = 0
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token and set(token) <= PUNCTUATION and token not in SEGMENT_BREAKS:
            return False
        if token not in SEGMENT_BREAKS:
            segment.append(token)
            continue
        if segment:
            if not _read_only_segment(segment):
                return False
            checked += 1
        segment = []
    return checked > 0


def only_read_through(command: str) -> bool:
    """True if every guarded path `command` names is read-through.

    One guarded path outside those locations refuses the whole command.
    """
    named = [path for path in _paths_in(command) if GUARDED.contains(path)]
    return bool(named) and all(READ_THROUGH.contains(path) for path in named)


def reads_through(command: str) -> bool:
    """True if `command` is a recognised read of read-through locations alone."""
    return only_read_through(command) and is_read_only_command(command)


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


def command_protected_class(
    command: str, targets: list[str] | None = None
) -> str | None:
    """The most restrictive protected class `command` reaches, or None.

    The instruction-markdown exemption is judged over `targets` where the caller
    extracted them (a patch body names its files explicitly), and over the paths
    the command names otherwise.
    """
    candidates = _paths_in(command)
    if CREDENTIALS.mentioned_in(command) or any(
        CREDENTIALS.contains(path) for path in candidates
    ):
        return CREDENTIAL
    named = GUARDED.mentioned_in(command) or any(
        GUARDED.contains(path) for path in candidates
    )
    exempt_pool = candidates if targets is None else targets
    if named and not _only_instruction_markdown(exempt_pool):
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
    """Decide the outcome of a protected mutation and exit.

    A credential refuses on every agent. A gated class asks; where no prompt is
    honoured for this (agent, tool) pairing the ask degrades to a refusal worded
    for the agent rather than the user.
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


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (OSError, ValueError):
        # Unjudgeable, so the call proceeds — but silently checking nothing is
        # how a harness change goes unnoticed, so warn rather than exit 0.
        respond(
            Decision.WARN,
            "block-hook-tampering could not parse the hook payload; "
            "this tool call was not checked.",
        )

    agent = invoking_agent(payload=data)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # The registration covers Read too, though nothing below judges one. This
    # must stay ahead of the manifest check, or a broken manifest reports itself
    # on every call this hook would have passed regardless.
    if tool_name not in MUTATING_TOOLS:
        sys.exit(0)

    if MANIFEST_ERROR is not None:
        # A broken manifest leaves nothing to judge against, so the call
        # proceeds rather than guessing, and the break is reported.
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
            cls = _most_restrictive(
                command_protected_class(command, targets),
                *(protected_class(path) for path in targets),
            )
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
            if cls == GATED and only_read_through(command):
                if is_read_only_command(command):
                    cls = None
                else:
                    ask = _unrecognised_read_reason
                    refuse = _unrecognised_read_refusal
            if cls is not None:
                gate(
                    _first_in_class(_paths_in(command), cls) or command,
                    tool_name,
                    cls,
                    agent,
                    ask,
                    refuse,
                )

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        # Fail open: the tool mix here is sensitive and read-only both, so an
        # unexpected error implies no damage potential. The blind catch is
        # deliberate — an escaping error exits non-zero, which one agent reads
        # as a refusal.
        sys.exit(0)
