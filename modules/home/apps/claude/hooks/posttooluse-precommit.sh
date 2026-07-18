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

root_abs="$(cd "${root}" && pwd -P)"
filtered=()
for f in "${files[@]}"; do
  dir="$(dirname "${f}")"
  [[ -d "${dir}" ]] || continue
  abs_dir="$(cd "${dir}" && pwd -P)"
  abs="${abs_dir}/$(basename "${f}")"
  [[ "${abs}" == "${root_abs}"/* ]] && filtered+=("${f}")
done

((${#filtered[@]})) || exit 0

if command -v prek >/dev/null 2>&1; then
  prek run --files "${filtered[@]}"
elif command -v pre-commit >/dev/null 2>&1; then
  pre-commit run --files "${filtered[@]}"
else
  exit 0
fi
