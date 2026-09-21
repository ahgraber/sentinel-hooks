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
  pi       Run the Pi security-extension tests
USAGE
}

run_python_suite() {
  local app="${1}"

  echo "==> Testing ${app}"
  # hypothesis carries the property suites over the read classifier, which takes
  # arbitrary command text and cannot be covered by an example table.
  uv run --with pytest --with hypothesis pytest -q "${REPO_ROOT}/modules/home/ai/${app}/tests"
}

run_pi_suite() {
  echo "==> Testing pi"
  node --test "${REPO_ROOT}/modules/home/ai/pi/security/index.test.mjs"
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
