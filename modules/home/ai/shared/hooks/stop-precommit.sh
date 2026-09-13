#!/usr/bin/env bash
# Stop hook: run pre-commit hooks on every file changed during the turn.
#
# Per-edit checks can remove imports before later edits use them and cannot see
# files written by Bash, so this hook runs at the end of the turn.
#
# Exit 0 to proceed or 2 to block the stop and return stderr to the agent.
set -euo pipefail

payload="$(cat)"

# Set after a block to limit the agent to one blocking round.
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

# `run --files` avoids stashing, which can leave the worktree reverted after failure.
output="$(cd "${root}" && "${runner}" run --files "${files[@]}" 2>&1)" && exit 0

printf '%s\n' "${output}" >&2
printf '\n%s failed on changed files. Fix the reported problems before finishing. Hooks may have changed files; re-read those files before editing.\n' \
  "${runner}" >&2
exit 2
