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

# ── Tool registration ─────────────────────────────────────────────────────────
# require_tool   <name> <install_hint>  — exits 2 if tool is missing
# recommend_tool <name> <install_hint>  — warns if missing, session proceeds

required_tools=()
recommended_tools=()

require_tool()   { required_tools+=("$1" "$2"); }
recommend_tool() { recommended_tools+=("$1" "$2"); }

# ── Required tools ────────────────────────────────────────────────────────────

require_tool uv \
  "Install: curl -LsSf https://astral.sh/uv/install.sh | sh
  Or via Homebrew: brew install uv

  uv is required for Python-based security hooks."

require_tool jq \
  "Install: brew install jq
  More options: https://jqlang.github.io/jq/download/

  jq is required by bash-based hooks for JSON input parsing."

require_tool perl \
  "Install: pre-installed on macOS; on Linux use your package manager
  (apt install perl, dnf install perl)

  perl is required by block-dangerous-bash.sh for PCRE pattern matching."

# ── Recommended tools ─────────────────────────────────────────────────────────

recommend_tool gitleaks \
  "Install: brew install gitleaks
  More options: https://github.com/gitleaks/gitleaks#installing

  Secret detection will fall back to built-in patterns with reduced coverage."

# ── Evaluation ────────────────────────────────────────────────────────────────

for (( i = 0; i < ${#required_tools[@]}; i += 2 )); do
  name="${required_tools[i]}"
  hint="${required_tools[i+1]}"
  if ! command -v "${name}" >/dev/null 2>&1; then
    printf '⚠️  %s is not installed or not in PATH.\n\n' "${name}" >&2
    printf '  %s\n' "${hint}" >&2
    exit 2
  fi
done

for (( i = 0; i < ${#recommended_tools[@]}; i += 2 )); do
  name="${recommended_tools[i]}"
  hint="${recommended_tools[i+1]}"
  if ! command -v "${name}" >/dev/null 2>&1; then
    printf '⚠️  %s is not installed or not in PATH.\n\n' "${name}" >&2
    printf '  %s\n' "${hint}" >&2
    # exit 0: recommended tools are not required — session proceeds
  fi
done

exit 0
