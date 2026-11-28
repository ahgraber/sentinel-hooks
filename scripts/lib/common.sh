#!/usr/bin/env bash
# Shared helpers for scripts/. Source this file; do not execute it.

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

die() {
  echo "error: $*" >&2
  exit 1
}

# Callers must define `usage` before invoking this.
handle_help() {
  case "${1:-}" in
    -h | --help)
      usage
      exit 0
      ;;
    *) ;;
  esac
}

require_cmd() {
  local cmd
  for cmd in "$@"; do
    if ! command -v "${cmd}" > /dev/null 2>&1; then
      die "${cmd} is not installed or not on PATH"
    fi
  done
}

require_identity_type() {
  case "${1}" in
    machine | user) ;;
    *) die "type must be 'machine' or 'user', got '${1}'" ;;
  esac
}

# NUL-delimited so callers can iterate under `set -e`; `find -exec` masks failures.
# A bare `.sops.yaml` is the recipient config, not an encrypted payload; sops rejects it.
find_sops_files() {
  find . -type f \( \
    -name '?*.sops.yaml' -o -name '?*.sops.yml' -o \
    -name '?*.sops.json' -o -name '?*.sops.env' -o -name '?*.sops.ini' \
    \) -print0
}
