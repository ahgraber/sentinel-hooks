#!/usr/bin/env bash
# Hook: Inject skill-usage instructions at SessionStart.
#
# A missing or empty instructions directory is reported and then ignored: the
# session starts without the guidance rather than not at all.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTRUCTIONS_DIR="${SCRIPT_DIR}/instructions"

if [[ ! -d "$INSTRUCTIONS_DIR" ]]; then
  echo "session-instructions: instructions directory not found: ${INSTRUCTIONS_DIR}" >&2
  exit 0
fi

shopt -s nullglob
content_files=("${INSTRUCTIONS_DIR}"/*.md)
shopt -u nullglob

if [[ ${#content_files[@]} -eq 0 ]]; then
  echo "session-instructions: no instruction fragments found in: ${INSTRUCTIONS_DIR}" >&2
  exit 0
fi

content=""
for content_file in "${content_files[@]}"; do
  fragment=$(< "$content_file")
  if [[ -n "$content" ]]; then
    content+=$'\n\n'
  fi
  content+="${fragment}"
done

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

# `escaped` is already a complete JSON string literal, quotes included, so the
# %s must NOT be quoted here. printf rather than a heredoc: bash 5.3+ hangs.
printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": %s\n  }\n}\n' "${escaped}"

exit 0
