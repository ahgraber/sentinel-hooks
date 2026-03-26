#!/usr/bin/env bash
# Claude Code Hook: Session tool checks
#
# SessionStart hook that verifies required security tools are available.
# - uv: required (blocks session if missing — Python hooks depend on it)
# - jq: required (blocks session if missing — bash hooks need it for JSON parsing)
# - perl: required (blocks session if missing — block-dangerous-bash.sh needs PCRE)
# - gitleaks: recommended (warns if missing — block-secrets.py falls back to
#   built-in patterns with reduced coverage)
#
# Read more about hooks here: https://docs.anthropic.com/en/docs/claude-code/hooks

set -uo pipefail

# ── Required tools (block session if missing) ────────────────────────────────

if ! command -v uv >/dev/null 2>&1; then
  printf '⚠️  uv is not installed or not in PATH.\n\n' >&2
  printf '  Install: curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
  printf '  Or via Homebrew: brew install uv\n\n' >&2
  printf '  uv is required for Python-based security hooks.\n' >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  printf '⚠️  jq is not installed or not in PATH.\n\n' >&2
  printf '  Install: brew install jq\n' >&2
  printf '  More options: https://jqlang.github.io/jq/download/\n\n' >&2
  printf '  jq is required by bash-based hooks for JSON input parsing.\n' >&2
  exit 2
fi

if ! command -v perl >/dev/null 2>&1; then
  printf '⚠️  perl is not installed or not in PATH.\n\n' >&2
  printf '  Install: pre-installed on macOS; on Linux use your package manager\n' >&2
  printf '  (apt install perl, dnf install perl)\n\n' >&2
  printf '  perl is required by block-dangerous-bash.sh for PCRE pattern matching.\n' >&2
  exit 2
fi

# ── Recommended tools (warn if missing, don't block) ─────────────────────────

if ! command -v gitleaks >/dev/null 2>&1; then
  printf '⚠️  gitleaks is not installed or not in PATH.\n\n' >&2
  printf '  Install: brew install gitleaks\n' >&2
  printf '  More options: https://github.com/gitleaks/gitleaks#installing\n\n' >&2
  printf '  Secret detection will fall back to built-in patterns with reduced coverage.\n' >&2
  # exit 0: gitleaks is recommended, not required — built-in fallback exists
fi

exit 0
