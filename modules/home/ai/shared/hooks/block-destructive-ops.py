#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse hook blocking destructive Bash commands, per block-destructive-ops-patterns.toml.

Each rule is matched against the command as written and against a normalized
spelling of it, so a rule written for `rm -rf /` still fires on `r'm' -rf /`;
matching both can only add matches, never drop one.

An `ask` rule needs an agent that honors PreToolUse prompts, so where that
cannot be confirmed the rule blocks instead — fail closed. A missing or
unreadable pattern file fails open, rather than refusing every Bash command over
this hook's own configuration error.

Rules are read from this file's own directory, so a caller substituting rules
runs a copy of this script elsewhere, and every sibling module imported here has
to travel with that copy; `SIBLING_MODULES` in the tests is the list.
"""

import json
import re
import sys
from pathlib import Path

import tomllib
from hook_response import Decision, invoking_agent, respond, supports_ask


def load_rules() -> list[dict]:
    """Load rules from the co-located TOML file, flat or nested, flattened into one list. Return [] on any error."""
    patterns_file = Path(__file__).parent / "block-destructive-ops-patterns.toml"
    try:
        with open(patterns_file, "rb") as f:
            data = tomllib.load(f)
    except Exception:  # noqa: BLE001
        return []

    if "rules" in data and isinstance(data["rules"], list):
        return data["rules"]

    all_rules: list[dict] = []
    for section in data.values():
        if isinstance(section, dict) and "rules" in section:
            all_rules.extend(section["rules"])
    return all_rules


_LINE_CONTINUATION = re.compile(r"\\\n")
_QUOTED_SPAN = re.compile(r"""(['"])(.*?)\1""", re.DOTALL)
# Characters that end a shell word; a quote touching anything else splices.
_WORD_SEPARATORS = frozenset(" \t\n|&;()<>")


def _splices_word(char: str) -> bool:
    """Whether `char` joins an adjacent quoted span into one shell word."""
    return bool(char) and char not in _WORD_SEPARATORS


def normalize(command: str) -> str:
    """Rewrite shell spellings that hide a command word from the rule patterns.

    A line continuation splits a word across lines and a quote pair splices into
    the middle of one, so `r'm' -rf /` reaches the shell as `rm -rf /` while the
    patterns are written against the plain spelling. Quotes are dropped only
    where they cannot be delimiting an argument, so `grep 'rm -rf /'` keeps its
    quotes and searching for a string is never rewritten into running it.
    Backslash-escaped word characters are left as written; undoing those needs
    quote-context tracking, which this does not do.
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
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        respond(
            Decision.BLOCK,
            "block-destructive-ops could not parse the hook payload, so the "
            "command in it was never checked. This hook covers Bash alone, "
            "where an unchecked command can delete work, rewrite history, or "
            "reach past this machine, so it is refused rather than let through.",
        )

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    normalized = normalize(command)
    candidates = (command,) if normalized == command else (command, normalized)

    agent = invoking_agent(payload=data)

    rules = load_rules()
    if not rules:
        sys.exit(0)

    # A `block` must win over an `ask` regardless of file order, or an earlier
    # ask rule (`git add -A`) masks a later block (`rm -rf /`) in a chained
    # command and downgrades it to a prompt. Hence one first match per mode.
    first_block: str | None = None
    first_ask: str | None = None

    for rule in rules:
        pattern = rule.get("pattern", "")
        if not pattern:
            continue

        flags = re.IGNORECASE if rule.get("case_insensitive", False) else 0
        try:
            compiled = re.compile(pattern, flags)
        except re.error:
            continue

        if not any(compiled.search(text) for text in candidates):
            continue

        description = rule.get("description", "")
        reason = rule.get("reason", "")
        mode = rule.get("mode", "block")

        explanation = description
        if reason:
            explanation += f"\n\n{reason}"

        if mode == "block" and first_block is None:
            first_block = explanation
        elif mode == "ask" and first_ask is None:
            first_ask = explanation

    if first_block is not None:
        respond(Decision.BLOCK, f"Blocked: {first_block}", agent=agent)

    if first_ask is not None:
        if supports_ask(agent):
            respond(Decision.ASK, first_ask, agent=agent)
        first_ask += (
            "\n\nThis agent cannot require confirmation from a PreToolUse "
            "hook, so this command is blocked instead of prompted."
        )
        respond(Decision.BLOCK, f"Blocked: {first_ask}", agent=agent)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        # Bash is the only tool here, and it is sensitive: fail closed.
        respond(
            Decision.BLOCK,
            "block-destructive-ops failed while checking this command, so the "
            "command was never checked. This hook covers Bash alone, where an "
            "unchecked command can delete work, rewrite history, or reach past "
            "this machine, so it is refused rather than let through.",
        )
