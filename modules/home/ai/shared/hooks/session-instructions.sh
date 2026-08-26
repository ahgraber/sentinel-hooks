#!/usr/bin/env bash
# Hook: Inject skill-usage instructions at SessionStart.
#
# Reads instructions/*.md and outputs the combined content as
# additionalContext so Claude always has startup guidance in context.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTRUCTIONS_DIR="${SCRIPT_DIR}/instructions"

if [[ ! -d "$INSTRUCTIONS_DIR" ]]; then
  echo "session-instructions: instructions directory not found: ${INSTRUCTIONS_DIR}" >&2
  exit 0 # non-fatal — don't block the session
fi

shopt -s nullglob
content_files=("${INSTRUCTIONS_DIR}"/*.md)
shopt -u nullglob

if [[ ${#content_files[@]} -eq 0 ]]; then
  echo "session-instructions: no instruction fragments found in: ${INSTRUCTIONS_DIR}" >&2
  exit 0 # non-fatal — don't block the session
fi

content=""
for content_file in "${content_files[@]}"; do
  fragment=$(< "$content_file")
  if [[ -n "$content" ]]; then
    content+=$'\n\n'
  fi
  content+="${fragment}"
done

# Escape for safe JSON string embedding.
to_json_string_literal() {
  local s="$1"

  if command -v jq > /dev/null 2>&1; then
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
