#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Block destructive Bash commands from PreToolUse hooks.

Rules match raw and normalized command spellings. Unsupported asks block.
A pattern file that is missing, unreadable, or holds an invalid rule asks on
every call. Rules and sibling modules load from the hook's directory.
"""

import json
from pathlib import Path
import re
import sys
import tomllib
from typing import NoReturn

from guarded_paths import TOOL_VOCABULARY
from hook_response import Decision, invoking_agent, respond, supports_ask

DESTRUCTIVE_OPS_TOOLS = TOOL_VOCABULARY.group("destructive-ops")


PATTERNS_FILE = Path(__file__).parent / "block-destructive-ops-patterns.toml"
_REQUIRED_FIELDS = ("pattern", "description", "reason", "mode")
_MODES = ("block", "ask")


class RulesError(Exception):
    """The pattern file cannot be used, so no command can be judged by it."""


def _invalid(rule: object) -> str | None:
    """Return why `rule` is unusable, or `None` when it is valid."""
    if not isinstance(rule, dict):
        return "it is not a table"
    missing = [field for field in _REQUIRED_FIELDS if not rule.get(field)]
    if missing:
        return f"it has no {', '.join(missing)}"
    if rule["mode"] not in _MODES:
        return f"its mode {rule['mode']!r} is not one of {', '.join(_MODES)}"
    try:
        re.compile(rule["pattern"])
    except (re.error, TypeError) as exc:
        return f"its pattern does not compile ({exc})"
    return None


def load_rules(patterns_file: Path = PATTERNS_FILE) -> list[dict]:
    """Return the rules from flat or nested TOML; raise `RulesError` unless every rule is valid.

    A rule dropped without notice is a protection removed without notice, so one
    invalid rule makes the whole file unusable.
    """
    try:
        with open(patterns_file, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError) as exc:
        # `TOMLDecodeError` and `UnicodeDecodeError` are both `ValueError`s.
        raise RulesError(f"{patterns_file.name} could not be read: {exc}") from exc

    rules = list(data["rules"]) if isinstance(data.get("rules"), list) else []
    rules += [
        rule
        for section in data.values()
        if isinstance(section, dict) and isinstance(section.get("rules"), list)
        for rule in section["rules"]
    ]
    if not rules:
        raise RulesError(f"{patterns_file.name} holds no rules under `rules` or a `<category>.rules` table")

    for index, rule in enumerate(rules, start=1):
        fault = _invalid(rule)
        if fault:
            name = rule.get("pattern") or rule.get("description") if isinstance(rule, dict) else None
            raise RulesError(f"rule {index} ({name!r}) in {patterns_file.name} is invalid: {fault}")
    return rules


_LINE_CONTINUATION = re.compile(r"\\\n")
_QUOTED_SPAN = re.compile(r"""(['"])(.*?)\1""", re.DOTALL)
# Characters that end a shell word; a quote touching anything else splices.
_WORD_SEPARATORS = frozenset(" \t\n|&;()<>")


def _splices_word(char: str) -> bool:
    """Whether `char` joins an adjacent quoted span into one shell word."""
    return bool(char) and char not in _WORD_SEPARATORS


def normalize(command: str) -> str:
    """Remove line continuations and quote splices that hide command words.

    Preserve standalone quoted arguments and backslash-escaped word characters.
    """
    text = _LINE_CONTINUATION.sub("", command)

    def unquote(match: re.Match[str]) -> str:
        body = match.group(2)
        if any(char.isspace() for char in body):
            before = text[match.start() - 1] if match.start() else ""
            after = text[match.end()] if match.end() < len(text) else ""
            if not (_splices_word(before) or _splices_word(after)):
                return match.group(0)
        return body

    return _QUOTED_SPAN.sub(unquote, text)


def main() -> None:
    """Read the PreToolUse payload from stdin and respond to the Bash command."""
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        respond(
            Decision.BLOCK,
            "Blocked: block-destructive-ops could not parse the hook payload, "
            "so the Bash command was never checked and is refused.",
        )

    if data.get("tool_name") not in DESTRUCTIVE_OPS_TOOLS:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    normalized = normalize(command)
    candidates = (command,) if normalized == command else (command, normalized)

    agent = invoking_agent(payload=data)

    try:
        rules = load_rules()
    except RulesError as exc:
        # The fault recurs on every call, so a refusal would stop all shell work.
        _ask(
            f"block-destructive-ops cannot judge this command: {exc}. "
            "Every Bash call asks until the pattern file is fixed.",
            agent,
        )

    # A block match overrides asks. Preserve the first match within each mode.
    first_block: str | None = None
    first_ask: str | None = None

    for rule in rules:
        flags = re.IGNORECASE if rule.get("case_insensitive", False) else 0
        compiled = re.compile(rule["pattern"], flags)
        if not any(compiled.search(text) for text in candidates):
            continue

        explanation = f"{rule['description']}\n\n{rule['reason']}"
        if rule["mode"] == "block" and first_block is None:
            first_block = explanation
        elif rule["mode"] == "ask" and first_ask is None:
            first_ask = explanation

    if first_block is not None:
        respond(Decision.BLOCK, f"Blocked: {first_block}", agent=agent)

    if first_ask is not None:
        _ask(first_ask, agent)

    sys.exit(0)


def _ask(reason: str, agent: str) -> NoReturn:
    """Ask, or block where the agent cannot show a prompt."""
    if supports_ask(agent):
        respond(Decision.ASK, reason, agent=agent)
    reason += "\n\nThis agent cannot show a confirmation prompt, so this command is blocked instead of prompted."
    respond(Decision.BLOCK, f"Blocked: {reason}", agent=agent)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        # Fail closed because this hook handles only Bash.
        respond(
            Decision.BLOCK,
            "Blocked: block-destructive-ops failed; the Bash command was never checked and is refused.",
        )
