#!/usr/bin/env bash
# Hook: Inject skill-usage instructions at SessionStart.
#
# Reads using-skills-instr.md and outputs it as additionalContext
# so Claude always has skill-usage guidance in context.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENT_FILE="${SCRIPT_DIR}/using-skills-instr.md"

if [[ ! -f "$CONTENT_FILE" ]]; then
  echo "using-skills: content file not found: ${CONTENT_FILE}" >&2
  exit 0  # non-fatal — don't block the session
fi

content=$(<"$CONTENT_FILE")

# Escape for safe JSON string embedding.
to_json_string_literal() {
  local s="$1"

  if command -v jq >/dev/null 2>&1; then
    printf '%s' "${s}" | jq -Rs .
    return
  fi

  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '"%s"' "${s}"
}

escaped=$(to_json_string_literal "${content}")

# Both paths produce a complete JSON string literal (e.g. "...").
# Claude Code expects hookSpecificOutput.additionalContext (nested JSON).
# Uses printf to avoid bash 5.3+ heredoc hang.
printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": %s\n  }\n}\n' "${escaped}"
# DO NOT quote the %s in `"additionalContext": %s`!

exit 0
