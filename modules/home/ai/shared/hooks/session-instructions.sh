#!/usr/bin/env bash
# SessionStart hook: inject shared instructions. Missing or empty instruction
# directories warn and do not block startup.
#
# With a fragment name, emit that one fragment; with no argument, emit every
# fragment concatenated. A harness that caps hook output per entry wires one
# handler per fragment so each entry stays under the cap; a harness that can
# disable the cap wires a single argument-less handler.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTRUCTIONS_DIR="${SCRIPT_DIR}/instructions"

usage() {
  cat << 'EOF'
usage: session-instructions.sh [fragment.md]

Emit SessionStart additionalContext as JSON on stdout.

  fragment.md   a file name in the instructions directory; omit for all of them
EOF
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  exit 0
fi

if [[ ! -d "$INSTRUCTIONS_DIR" ]]; then
  echo "session-instructions: instructions directory not found: ${INSTRUCTIONS_DIR}" >&2
  exit 0
fi

if [[ $# -gt 0 ]]; then
  # A fragment name reaches the filesystem, so refuse anything that could leave
  # the instructions directory.
  if [[ "$1" == */* || "$1" == .. || "$1" != *.md ]]; then
    echo "session-instructions: not an instruction fragment name: $1" >&2
    exit 0
  fi
  content_files=("${INSTRUCTIONS_DIR}/$1")
  if [[ ! -f "${content_files[0]}" ]]; then
    echo "session-instructions: instruction fragment not found: ${content_files[0]}" >&2
    exit 0
  fi
else
  shopt -s nullglob
  content_files=("${INSTRUCTIONS_DIR}"/*.md)
  shopt -u nullglob
fi

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

# `escaped` includes JSON quotes; keep `%s` unquoted.
# printf is intentional; heredocs hang on Bash 5.3+.
printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": %s\n  }\n}\n' "${escaped}"

exit 0
