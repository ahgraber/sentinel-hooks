#!/usr/bin/env bash
# SessionStart hook: require tools used by security hooks and warn for optional tools.

set -uo pipefail

required_tools=()
recommended_tools=()

require_tool() { required_tools+=("$1" "$2"); }
recommend_tool() { recommended_tools+=("$1" "$2"); }

require_tool uv \
  "Install uv with 'brew install uv' or follow https://docs.astral.sh/uv/getting-started/installation/.
  Python security hooks require it."

require_tool jq \
  "Install jq with 'brew install jq' or see https://jqlang.github.io/jq/download/.
  Bash hooks require it to parse JSON."

require_tool perl \
  "macOS includes Perl. On Linux, install it with your package manager.
  block-dangerous-bash.sh requires it for PCRE matching."

recommend_tool gitleaks \
  "Install gitleaks with 'brew install gitleaks' or see https://github.com/gitleaks/gitleaks#installing.
  Without it, secret detection uses built-in patterns with less coverage."

for ((i = 0; i < ${#required_tools[@]}; i += 2)); do
  name="${required_tools[i]}"
  hint="${required_tools[i + 1]}"
  if ! command -v "${name}" > /dev/null 2>&1; then
    printf 'Error: required tool %s is not installed or not in PATH.\n\n' "${name}" >&2
    printf '  %s\n' "${hint}" >&2
    exit 2
  fi
done

for ((i = 0; i < ${#recommended_tools[@]}; i += 2)); do
  name="${recommended_tools[i]}"
  hint="${recommended_tools[i + 1]}"
  if ! command -v "${name}" > /dev/null 2>&1; then
    printf 'Warning: optional tool %s is not installed or not in PATH.\n\n' "${name}" >&2
    printf '  %s\n' "${hint}" >&2
  fi
done

exit 0
