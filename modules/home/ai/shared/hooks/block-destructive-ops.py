#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Block destructive Bash commands from PreToolUse hooks.

Rules match raw and normalized command spellings. Unsupported asks block.
Missing or unreadable rules fail open. Rules and sibling modules load from the
hook's directory.
"""

import json
import re
import sys
from pathlib import Path

import tomllib
from hook_response import Decision, invoking_agent, respond, supports_ask


def load_rules() -> list[dict]:
    """Return co-located rules from flat or nested TOML; return `[]` on error."""
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
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        respond(
            Decision.BLOCK,
            "Blocked: block-destructive-ops could not parse the hook payload, "
            "so the Bash command was never checked and is refused.",
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

    # A block match overrides asks. Preserve the first match within each mode.
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
            "\n\nThis agent cannot show a confirmation prompt, so this command "
            "is blocked instead of prompted."
        )
        respond(Decision.BLOCK, f"Blocked: {first_ask}", agent=agent)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        # Fail closed because this hook handles only Bash.
        respond(
            Decision.BLOCK,
            "Blocked: block-destructive-ops failed; the Bash command was never "
            "checked and is refused.",
        )
