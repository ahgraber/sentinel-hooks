#!/usr/bin/env bash
# Stop hook: run pre-commit over every file the turn changed.
#
# End-of-turn rather than per-edit: a per-edit run fires autofixers mid-sequence
# (stripping an import before its first use lands) and never sees files written
# by Bash.
#
# Exit codes:
#   0 = proceed
#   2 = block the stop; stderr goes back to the agent to fix
set -euo pipefail

payload="$(cat)"

# Set on the pass after a block, so this caps the agent at one blocking round.
if [[ "$(jq -r '.stop_hook_active // false' <<< "${payload}")" == "true" ]]; then
  exit 0
fi

cwd="$(jq -r '.cwd // empty' <<< "${payload}")"
[[ -d "${cwd}" ]] || cwd="${CLAUDE_PROJECT_DIR:-${PWD}}"
[[ -d "${cwd}" ]] || cwd="${PWD}"

root="$(git -C "${cwd}" rev-parse --show-toplevel 2> /dev/null)" || exit 0

if [[ ! -f "${root}/.pre-commit-config.yaml" && ! -f "${root}/.pre-commit-config.yml" ]]; then
  exit 0
fi

# quotePath=false keeps non-ASCII names literal so they round-trip to the runner.
git_repo() { git -C "${root}" -c core.quotePath=false "$@"; }

files=()
while IFS= read -r file; do
  [[ -n "${file}" ]] && files+=("${file}")
done < <(
  {
    # Lowercase `d` drops deletions, which the runner cannot open.
    if git_repo rev-parse --verify --quiet HEAD > /dev/null; then
      git_repo diff --name-only --diff-filter=d HEAD
    else
      git_repo diff --cached --name-only --diff-filter=d
    fi
    git_repo ls-files --others --exclude-standard
  } | awk '!seen[$0]++'
)

((${#files[@]})) || exit 0

if command -v prek > /dev/null 2>&1; then
  runner="prek"
elif command -v pre-commit > /dev/null 2>&1; then
  runner="pre-commit"
else
  exit 0
fi

# `run --files` does no stashing; a bare `run` stashes the work tree and leaves it
# reverted if the cycle fails partway.
output="$(cd "${root}" && "${runner}" run --files "${files[@]}" 2>&1)" && exit 0

printf '%s\n' "${output}" >&2
printf '\n%s failed on the changed files. Fix the reported problems before finishing; hooks that rewrote files have already applied their changes, so re-read those files rather than trusting your in-context copy.\n' \
  "${runner}" >&2
exit 2
