#!/usr/bin/env bash
# Codex hook: detect unexpected HEAD drift during a turn.
# Usage: git-baseline.sh <init|check|update>
#   init   — UserPromptSubmit: records HEAD at turn start
#   check  — PreToolUse: warns if HEAD moved since last checkpoint
#   update — PostToolUse(Bash): advances baseline after agent-run commands
#
# Exit codes:
#   0 = proceed (always — this hook is informational, never blocking)

set -uo pipefail

stage="${1:-}"
case "${stage}" in
    init | check | update) ;;
    *) exit 0 ;;
esac

input_json="$(cat 2>/dev/null)" || exit 0

session_id="$(jq -r '.session_id // empty' 2>/dev/null <<< "${input_json}")" || exit 0
[[ -n "${session_id}" ]] || exit 0

cwd="$(jq -r '.cwd // empty' 2>/dev/null <<< "${input_json}")"
cwd="${cwd:-"$(pwd)"}"

# Replace characters outside [a-zA-Z0-9-] with dashes for safe filename use.
safe_id="$(printf '%s' "${session_id}" | tr -c 'a-zA-Z0-9-' '-')"

# Resolve the per-worktree git directory; in a worktree this differs from .git/
if [[ -z "${GIT_DIR:-}" ]]; then
    GIT_DIR="$(git -C "${cwd}" rev-parse --git-dir 2>/dev/null)" || exit 0
    [[ "${GIT_DIR}" == /* ]] || GIT_DIR="${cwd}/${GIT_DIR}"
fi
readonly baseline="${GIT_DIR}/agent-baseline-${safe_id}"

case "${stage}" in
    init)
        head_sha="$(git -C "${cwd}" rev-parse HEAD 2>/dev/null)" || exit 0
        printf '%s' "${head_sha}" > "${baseline}" || exit 0
        ;;
    check)
        [[ -f "${baseline}" ]] || exit 0
        stored="$(< "${baseline}")" || exit 0
        head_sha="$(git -C "${cwd}" rev-parse HEAD 2>/dev/null)" || exit 0
        [[ "${head_sha}" != "${stored}" ]] || exit 0
        branch="$(git -C "${cwd}" rev-parse --abbrev-ref HEAD 2>/dev/null)" || branch="unknown"
        msg="⚠ git HEAD has moved since this turn started: ${stored:0:8} → ${head_sha:0:8} (branch: ${branch}). Re-read any files you plan to modify to avoid overwriting concurrent changes."
        jq -n --arg ctx "${msg}" \
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":$ctx}}' \
            2>/dev/null || exit 0
        ;;
    update)
        tool_name="$(jq -r '.tool_name // empty' 2>/dev/null <<< "${input_json}")" || exit 0
        [[ "${tool_name}" == "Bash" ]] || exit 0
        head_sha="$(git -C "${cwd}" rev-parse HEAD 2>/dev/null)" || exit 0
        printf '%s' "${head_sha}" > "${baseline}" || exit 0
        ;;
esac
