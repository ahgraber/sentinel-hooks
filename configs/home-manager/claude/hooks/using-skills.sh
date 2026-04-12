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
escape_for_json() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

escaped=$(escape_for_json "$content")

# Claude Code expects hookSpecificOutput.additionalContext (nested JSON).
# Uses printf to avoid bash 5.3+ heredoc hang.
printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "${escaped}"

exit 0
