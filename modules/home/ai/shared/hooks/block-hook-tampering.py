#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Gate mutations to agent guardrails and stored credentials.

Guardrail mutations ask when the agent and tool support prompts and block
otherwise. Credential mutations always block. Recognized reads and existing
scripts in exec-through paths may proceed; unresolved commands gate. Writes
proceed only where every affected path has a write-through declaration.
"""

import json
import os
import sys
from typing import NoReturn

import apply_patch
import bash_commands
from bash_commands import offers_accepted_forms
from guarded_paths import TOOL_VOCABULARY, ManifestError, load_policy, spellings
from hook_response import Decision, Instruction, invoking_agent, respond, supports_ask
import shell_words
from shell_words import Word

# The hook's only view of the manifest. A load failure is carried on it rather
# than in a second name a test could set without this one.
POLICY = load_policy(invocation_path=sys.argv[0] if __name__ == "__main__" else None)
GATED = "guarded"
CREDENTIAL = "block"
MUTATING_TOOLS = TOOL_VOCABULARY.group("mutating")
SENSITIVE_PATH_TOOLS = TOOL_VOCABULARY.group("sensitive-path")
FILE_TOOLS = TOOL_VOCABULARY.group("file")


def _ask_reason(target: str, tool_name: str) -> str:
    """Build the prompt the user decides on; it addresses the user alone."""
    return (
        f"This {tool_name} call would modify agent enforcement at '{target}'. "
        "Approve only if you intend this guardrail change."
    )


def _unrecognized_reason(target: str, tool_name: str, syntax: str) -> str:
    return (
        f"This {tool_name} call may write to '{target}', and the gate could not "
        "determine what it does there. Approve only if you intend to "
        f"run it as written. Recognition stopped at {syntax}."
    ) + _hint(syntax)


def _unrecognized_refusal(target: str, tool_name: str, syntax: str) -> str:
    return (
        f"Blocked: {tool_name} may write to '{target}', and the gate could not "
        "determine what it does there; this agent cannot ask for the required "
        f"approval. Recognition stopped at {syntax}."
    ) + _hint(syntax)


def _hint(syntax: str) -> str:
    """Name the rewrite that resolves the stop, where one exists."""
    if offers_accepted_forms(syntax):
        return bash_commands.accepted_forms()
    if bash_commands.asks_for_absolute_paths(syntax):
        return bash_commands.ABSOLUTE_PATH_HINT
    return ""


def _ancestor_reason(target: str, tool_name: str) -> str:
    """Build the prompt for a destructive operation on the path to a guarded location."""
    return (
        f"This {tool_name} call would remove, rename, replace, or change the permissions of '{target}', "
        "which holds agent enforcement. Approve only if you intend to remove "
        "the directory and its guardrails."
    )


def _ancestor_refusal(target: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} would remove, rename, replace, or change the permissions of '{target}', "
        "which holds agent enforcement. This agent cannot ask for the required "
        "approval."
    )


def _unanchored_refusal(operand: str, tool_name: str) -> str:
    return (
        f"Blocked: {tool_name} would remove, rename, replace, or change the permissions of the relative path "
        f"'{operand}', and this call supplies no working directory, or an earlier "
        "`cd` names one the hook cannot resolve, so whether it holds agent "
        "enforcement is unknown."
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


def protected_class(path: str, *, operation: str = "write", cwd: str | None = None) -> str | None:
    """Return the class that requires a prompt or refusal for this operation."""
    outcome = POLICY.verdict(path, operation, cwd=cwd)
    return outcome if outcome in {GATED, CREDENTIAL} else None


def is_protected_path(path: str) -> bool:
    """Return whether a path requires a prompt or refusal for a write."""
    return protected_class(path) is not None


def _paths_in(reading: bash_commands.Reading, cwd: str | None) -> list[str]:
    """Every path the command's words name."""
    return [
        path for segment in reading.segments for word in segment.words for path in bash_commands.word_paths(word, cwd)
    ]


def command_mentions_protected_path(command: str) -> bool:
    """Return whether a Bash command names a path that requires a prompt or refusal."""
    return command_protected_class(command) is not None


def _exec_through_script(token: str, cwd: str | None = None) -> bool:
    if POLICY.verdict(token, "run", cwd=cwd) != "exec-through":
        return False
    target = os.path.expanduser(token)
    if not os.path.isabs(target) and cwd:
        target = os.path.join(cwd, target)
    resolved = spellings(target)[-1]
    return os.path.isfile(resolved) and (
        os.path.splitext(resolved)[1].casefold() in bash_commands.SCRIPT_SUFFIXES or os.access(resolved, os.X_OK)
    )


def _script_exec_segment(segment: list[Word], cwd: str | None = None) -> bool:
    # `_reading_class` judges redirection targets by direction.
    words = [word for word in segment if word.kind != "redirection target"]
    if not words or any(word.kind in bash_commands.OPAQUE_KINDS for word in words):
        return False
    name, *args = words
    direct = _exec_through_script(name.value, cwd)
    if not direct and name.value not in bash_commands.INTERPRETERS:
        return False
    scripts = int(direct)
    for word in args:
        if word.kind == "option":
            if word.value.split("=", 1)[0] in bash_commands.INLINE_CODE_OPTIONS:
                return False
            if any(protected_class(path, cwd=cwd) for path in bash_commands.word_paths(word, cwd)):
                return False
        elif _exec_through_script(word.value, cwd):
            scripts += 1
        elif any(protected_class(path, cwd=cwd) for path in bash_commands.word_paths(word, cwd)):
            return False
    return scripts == 1


def _segment_class(segment: bash_commands.SegmentReading, cwd: str | None, operation: str = "write") -> str | None:
    classes = []
    for program in segment.programs:
        if POLICY.classes[CREDENTIAL].mentioned_in(program):
            classes.append(CREDENTIAL)
        elif operation != "read" and POLICY.guarded.mentioned_in(program):
            classes.append(GATED)
    for word in segment.words:
        for path in bash_commands.word_paths(word, cwd):
            if word.kind == "unresolvable":
                if POLICY.classes[CREDENTIAL].mentioned_in(path):
                    classes.append(CREDENTIAL)
                elif POLICY.guarded.mentioned_in(path):
                    classes.append(GATED)
            classes.append(protected_class(path, operation=operation, cwd=cwd))
    return _most_restrictive(*classes)


def _recognized(reading: bash_commands.Reading, segment: bash_commands.SegmentReading, cwd: str | None) -> bool:
    """Whether a segment is a recognized read, a recognized run, or does nothing but redirect."""
    return not reading.has_builder and (
        segment.read_only or bash_commands.only_redirects(segment.words) or _script_exec_segment(segment.words, cwd)
    )


def _written_targets(segment: bash_commands.SegmentReading, cwd: str | None) -> list[str]:
    """Paths the segment's output redirections open for writing."""
    return [
        path
        for word in segment.words
        if bash_commands.redirect_writes(word)
        for path in bash_commands.word_paths(word, cwd)
    ]


def _redirected_write(reading: bash_commands.Reading, cwd: str | None) -> tuple[str, str] | None:
    """Return the first gated output target of a fully recognized command, with its class.

    A command with any unrecognized segment keeps the recognition reason, which
    says it may do more than this write.
    """
    if not all(_recognized(reading, segment, cwd) for segment in reading.segments):
        return None
    for segment in reading.segments:
        for path in _written_targets(segment, cwd):
            cls = protected_class(path, cwd=cwd)
            if cls is not None:
                return path, cls
    return None


def destroys_a_guarded_ancestor(command: str, cwd: str | None = None) -> str | None:
    """Return a guarded ancestor removed, renamed, or replaced by `command`."""
    return _destroyed_ancestor(bash_commands.read(command, cwd), cwd)


def _destroyed_ancestor(reading: bash_commands.Reading, cwd: str | None) -> str | None:
    """Return the guarded ancestor `reading` destroys.

    Where no reading exists, inspect every candidate and favor asking.
    """
    if reading.unlexable is not None:
        named = any(name in reading.command.split() for name in bash_commands.DESTRUCTIVE)
        candidates = (
            (*shell_words.unresolved_paths(reading.command), *shell_words.text_paths(reading.command, cwd))
            if named
            else ()
        )
    else:
        candidates = [operand for segment in reading.segments for operand in segment.destroyed]
    for candidate in candidates:
        if (
            POLICY.guarded.encloses(candidate, cwd=cwd)
            or POLICY.classes[CREDENTIAL].encloses(candidate, cwd=cwd)
            # Reached through a `cd`, the declaration itself names no fragment the word rules see.
            # The lexer has expanded every `~` it should, so the join keeps the rest literal.
            or protected_class(os.path.join(cwd or "", candidate)) is not None
        ):
            return candidate
    return None


def _unanchored_operand(reading: bash_commands.Reading, cwd: str | None) -> str | None:
    """Return a relative operand `reading` destroys when its directory is unknown.

    Such an operand may name any directory, including an ancestor of a
    declaration. It is refused rather than guessed at from its shape, because a
    `*` in a declaration lets almost any word match one.
    """
    for segment in reading.segments:
        if cwd is not None and segment.anchored:
            continue
        for operand in segment.destroyed:
            if not os.path.isabs(os.path.expanduser(operand)):
                return operand
    return None


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


def command_protected_class(command: str, cwd: str | None = None) -> str | None:
    """Judge resolved paths by operation and unresolved words by their text."""
    return _reading_class(bash_commands.read(command, cwd), cwd)


def _reading_class(reading: bash_commands.Reading, cwd: str | None) -> str | None:
    """Return the class `reading` reaches, judging its paths and its unresolved text."""
    if reading.unlexable is not None:
        # The whole text, and each path spelling in it with quotes and escapes removed.
        spellings = (reading.command, *shell_words.text_paths(reading.command, cwd))
        if any(POLICY.classes[CREDENTIAL].mentioned_in(spelling) for spelling in spellings):
            return CREDENTIAL
        return GATED if any(POLICY.guarded.mentioned_in(spelling) for spelling in spellings) else None
    classes = []
    for program in reading.piped_programs:
        if POLICY.classes[CREDENTIAL].mentioned_in(program):
            return CREDENTIAL
        if POLICY.guarded.mentioned_in(program):
            classes.append(GATED)
    for segment in reading.segments:
        if _segment_class(segment, cwd, "read") == CREDENTIAL:
            return CREDENTIAL
        if _recognized(reading, segment, cwd):
            # The read above judged every input target; an output target is a write.
            classes.extend(protected_class(path, cwd=cwd) for path in _written_targets(segment, cwd))
            continue
        classes.append(_segment_class(segment, cwd))
        classes.extend(protected_class(target, operation="run", cwd=cwd) for target in segment.run_targets)
    return _most_restrictive(*classes)


def _with_policy_findings(message: str) -> str:
    if POLICY and POLICY.findings:
        return message + "\n" + "\n".join(POLICY.findings)
    return message


def _ask(message: str, agent: str, tool_name: str, instruction: Instruction = Instruction.STOP) -> NoReturn:
    respond(Decision.ASK, _with_policy_findings(message), agent=agent, tool_name=tool_name, instruction=instruction)


def _block(message: str, agent: str, instruction: Instruction = Instruction.STOP) -> NoReturn:
    respond(Decision.BLOCK, _with_policy_findings(message), agent=agent, instruction=instruction)


def gate(
    target: str,
    tool_name: str,
    cls: str,
    agent: str,
    *,
    prompt: str | None = None,
    refusal: str | None = None,
    instruction: Instruction = Instruction.STOP,
) -> NoReturn:
    """Apply the protected mutation policy and exit.

    `prompt` addresses the user deciding; `refusal` addresses the agent being
    refused.
    A credential refusal always stops.
    """
    if cls == CREDENTIAL:
        _block(_credential_refusal(target, tool_name), agent)
    if supports_ask(agent, tool_name):
        _ask(prompt or _ask_reason(target, tool_name), agent, tool_name, instruction)
    _block(refusal or _degraded_refusal(target, tool_name), agent, instruction)


def _written_paths(tool_input: dict) -> list[str]:
    paths = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            paths.append(value)
    paths.extend(value for value in tool_input.get("file_paths") or [] if isinstance(value, str))
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
            f"block-hook-tampering failed ({fault}). This non-mutating call will proceed unchecked.",
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
    """Read the PreToolUse payload from stdin and gate the tool call."""
    try:
        data = json.load(sys.stdin)
    except (OSError, ValueError):
        # Warn and fail open when the payload cannot be parsed.
        respond(
            Decision.WARN,
            "block-hook-tampering could not parse the hook payload; this tool call was not checked.",
        )

    # Record the tool before agent detection can fail.
    tool_name = data.get("tool_name", "")
    _CALL["tool_name"] = tool_name
    agent = invoking_agent(payload=data)
    _CALL["agent"] = agent

    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd") or None

    # Unregistered tools do not use this policy.
    if tool_name not in SENSITIVE_PATH_TOOLS:
        sys.exit(0)

    if POLICY.error is not None:
        internal_error(ManifestError(f"guarded-paths.toml: {POLICY.error}"))

    if tool_name in FILE_TOOLS:
        paths = _written_paths(tool_input)
        cls = _most_restrictive(
            *(protected_class(path, operation="read" if tool_name == "Read" else "write", cwd=cwd) for path in paths)
        )
        if cls is not None:
            gate(_first_in_class(paths, cls) or paths[0], tool_name, cls, agent)

    elif tool_name == "apply_patch":
        command = tool_input.get("command", "")
        if isinstance(command, str) and command:
            targets = apply_patch.targets(command)
            if targets:
                cls = _most_restrictive(*(protected_class(path, cwd=cwd) for path in targets))
            else:
                cls = command_protected_class(command, cwd)
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
            # One reading answers both what the command reaches and why
            # recognition stopped, so the refusal names the reason it reached.
            reading = bash_commands.read(command, cwd)
            cls = _reading_class(reading, cwd)
            if cls is not None:
                # A recognized command writing a gated file meets the write gate, not a recognition stop.
                written = _redirected_write(reading, cwd) if cls != CREDENTIAL else None
                if written is not None:
                    gate(written[0], tool_name, written[1], agent)
                target = _first_in_class(_paths_in(reading, cwd), cls) or command
                syntax = reading.stopping_syntax()
                gate(
                    target,
                    tool_name,
                    cls,
                    agent,
                    prompt=_unrecognized_reason(target, tool_name, syntax),
                    refusal=_unrecognized_refusal(target, tool_name, syntax),
                    instruction=bash_commands.refusal_instruction(syntax),
                )

            # Read carve-outs do not permit removing their guarded ancestors.
            ancestor = _destroyed_ancestor(reading, cwd)
            if ancestor is not None:
                gate(
                    ancestor,
                    tool_name,
                    GATED,
                    agent,
                    prompt=_ancestor_reason(ancestor, tool_name),
                    refusal=_ancestor_refusal(ancestor, tool_name),
                )

            unanchored = _unanchored_operand(reading, cwd)
            if unanchored is not None:
                _block(_unanchored_refusal(unanchored, tool_name), agent, instruction=Instruction.ABSOLUTE_PATH)

    if POLICY and POLICY.findings:
        respond(Decision.WARN, "\n".join(POLICY.findings), agent=agent)
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
