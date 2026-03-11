#!/usr/bin/env bash
set -euo pipefail

root="${CLAUDE_PROJECT_DIR:-$PWD}"

if [[ -f "$root/.pre-commit-config.yaml" ]]; then
  :
elif [[ -f "$root/.pre-commit-config.yml" ]]; then
  :
else
  exit 0
fi

mapfile -t files < <(
  jq -r '[.tool_input.file_path, (.tool_input.file_paths[]?)] | .[] | select(type=="string" and length>0)' \
    | awk '!seen[$0]++'
)

((${#files[@]})) || exit 0

if command -v prek >/dev/null 2>&1; then
  prek run --files "${files[@]}"
elif command -v pre-commit >/dev/null 2>&1; then
  pre-commit run --files "${files[@]}"
else
  exit 0
fi
