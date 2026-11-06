#!/usr/bin/env bash

set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat << 'USAGE'
Usage: isolated-harness.sh <command> [args...]

Run one command with the home directory of every supported harness moved under
tmp/homes/ in this repository. A plugin installs and runs there, and the real
homes are not read or changed.

Managed and system settings still apply. Pass credentials through the
environment, such as GH_TOKEN or ANTHROPIC_API_KEY, or log in inside the
isolated home. Remove tmp/homes/ to start over.

Examples:
  GH_TOKEN=... isolated-harness.sh copilot plugin install <git URL>
  isolated-harness.sh code .
USAGE
}

main() {
  handle_help "${1:-}"
  if [[ $# -eq 0 ]]; then
    usage >&2
    exit 2
  fi
  require_cmd "${1}"

  # Each directory keeps its real name, because Sentinel names the agent from it in a hook's path.
  local homes="${REPO_ROOT}/tmp/homes"
  export CLAUDE_CONFIG_DIR="${homes}/.claude"
  export CODEX_HOME="${homes}/.codex"
  export COPILOT_HOME="${homes}/.copilot"
  export PI_CODING_AGENT_DIR="${homes}/.pi/agent"
  export VSCODE_AGENT_PLUGINS="${homes}/.vscode/agent-plugins"
  local user_data="${homes}/.vscode/user-data"
  mkdir -p "${CLAUDE_CONFIG_DIR}" "${CODEX_HOME}" "${COPILOT_HOME}" "${PI_CODING_AGENT_DIR}" \
    "${VSCODE_AGENT_PLUGINS}" "${user_data}"

  # VS Code reads its user settings, and the hooks they register, from the user data directory.
  if [[ "$(basename -- "${1}")" == "code" ]]; then
    exec "$@" --user-data-dir "${user_data}"
  fi
  exec "$@"
}

main "$@"
