#!/usr/bin/env bash

set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat << 'USAGE'
Usage: apps-test.sh <shared|claude|codex|copilot|pi>

Run one agent app configuration test suite. `just apps test` composes every
suite (and `just apps test all` is its default).

Targets:
  shared   Run the tests for the hook modules every agent shares
  claude   Run the Claude hook tests
  codex    Run the Codex hook tests
  copilot  Run the Copilot hook-adapter tests
  pi       Run the Pi hook dispatcher, registration, and hooks-extension tests
USAGE
}

# The test tools are pinned in this project's lock; `--locked` fails a stale lock
# rather than resolving new versions.
run_pytest() {
  uv run --project "${REPO_ROOT}/modules/home/ai" --locked pytest -q "$@"
}

run_python_suite() {
  local app="${1}"

  echo "==> Testing ${app}"
  run_pytest "${REPO_ROOT}/modules/home/ai/${app}/tests"
}

run_pi_suite() {
  echo "==> Testing pi"
  run_pytest "${REPO_ROOT}/modules/home/ai/pi/tests"
  # Quoted so node expands the glob, which it matches against every test file.
  node --test "${REPO_ROOT}/modules/home/ai/pi/extensions/hooks/*.test.mjs" "${REPO_ROOT}/modules/home/ai/pi/tests/*.test.mjs"
}

main() {
  handle_help "${1:-}"

  if (($# != 1)); then
    usage >&2
    die "expected exactly one app test target"
  fi

  cd "${REPO_ROOT}"

  case "${1}" in
    shared | claude | codex | copilot)
      require_cmd uv
      run_python_suite "${1}"
      ;;
    pi)
      require_cmd uv
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
