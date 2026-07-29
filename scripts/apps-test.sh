#!/usr/bin/env bash

set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat << 'USAGE'
Usage: apps-test.sh [all|claude|codex|copilot|pi]

Run the test suites for agent app configurations.

Targets:
  all      Run every app test suite (default)
  claude   Run the Claude hook tests
  codex    Run the Codex hook tests
  copilot  Run the Copilot hook-adapter tests
  pi       Run the Pi security-extension tests
USAGE
}

run_python_suite() {
  local app="${1}"

  echo "==> Testing ${app}"
  uv run --with pytest pytest -q "${REPO_ROOT}/modules/home/apps/${app}/tests"
}

run_pi_suite() {
  echo "==> Testing pi"
  node --test "${REPO_ROOT}/modules/home/apps/pi/security/security-extension-index.test.mjs"
}

main() {
  handle_help "${1:-}"

  if (( $# > 1 )); then
    usage >&2
    die "expected at most one app test target"
  fi

  case "${1:-all}" in
    all)
      require_cmd uv node
      run_python_suite claude
      run_python_suite codex
      run_python_suite copilot
      run_pi_suite
      ;;
    claude | codex | copilot)
      require_cmd uv
      run_python_suite "${1}"
      ;;
    pi)
      require_cmd node
      run_pi_suite
      ;;
    *)
      usage >&2
      die "unknown app test target: ${1}"
      ;;
  esac
}

main "$@"
