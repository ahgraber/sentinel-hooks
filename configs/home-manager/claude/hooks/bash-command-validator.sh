#!/usr/bin/env bash
set -euo pipefail

# Claude Code Hook: Bash Command Validator
#
# This hook runs as a PreToolUse hook for the Bash tool. It validates bash
# commands against a set of rules before execution. Rules: redirects grep to rg,
# find -name to rg, and python/pip invocations to uv.
#
# Read more about hooks here: https://docs.anthropic.com/en/docs/claude-code/hooks
#
# {
#   "hooks": {
#     "PreToolUse": [
#       {
#         "matcher": "Bash",
#         "hooks": [
#           {
#             "type": "command",
#             "command": "/path/to/bash-command-validator.sh"
#           }
#         ]
#       }
#     ]
#   }
# }

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required for bash-command-validator.sh" >&2
  exit 1
fi

if ! command -v perl >/dev/null 2>&1; then
  echo "Error: perl is required for bash-command-validator.sh" >&2
  exit 1
fi

matches_pattern() {
  local pattern="${1}"

  VALIDATION_PATTERN="${pattern}" perl -0e '
    my $pattern = $ENV{VALIDATION_PATTERN};
    my $text = do { local $/; <STDIN> };
    my $regex = eval { qr{$pattern} };
    exit 1 if $@;
    exit($text =~ $regex ? 0 : 1);
  '
}

input_json="$(cat)"

if ! jq -e . >/dev/null 2>&1 <<<"${input_json}"; then
  echo "Error: Invalid JSON input" >&2
  exit 1
fi

tool_name="$(jq -r '.tool_name // ""' <<<"${input_json}")"
if [[ "${tool_name}" != "Bash" ]]; then
  exit 0
fi

command_text="$(jq -r '.tool_input.command // ""' <<<"${input_json}")"
if [[ -z "${command_text}" ]]; then
  exit 0
fi

patterns=()
messages=()

rule() {
  patterns+=("$1")
  messages+=("$2")
}

rule '^grep\b(?!.*\|)' \
  "Use 'rg' (ripgrep) instead of 'grep' for better performance and features"

rule '^find\s+\S+\s+-name\b' \
  "Use 'rg --files | rg pattern' or 'rg --files -g pattern' instead of 'find -name' for better performance"

rule "(?:^|[;|&()]{1,2})\\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\\S+)\\s+)*(?:[./][\\w./]*/)?(?:python|python3)(?:[0-9.]+)?\\s" \
  "Use 'uv run' instead of invoking python/python3 directly. For scripts with dependencies, use uv inline script metadata (# /// script) and run with 'uv run script.py'"

rule '(?<!\w)pip\s+(install|uninstall|download)\b' \
  "Use 'uv add' or 'uv run --with <pkg>' instead of pip. For one-off scripts, declare dependencies inline with uv script metadata (# /// script)"

rule '(?<!\w)pip3\s+(install|uninstall|download)\b' \
  "Use 'uv add' or 'uv run --with <pkg>' instead of pip3. For one-off scripts, declare dependencies inline with uv script metadata (# /// script)"

rule '(?<!\w)(?<!uv run )py(?:test|\.test)\b' \
  "Use 'uv run pytest' instead of invoking pytest/py.test directly"

rule '\bpre-commit\s+run\b' \
  "Use 'prek run' instead of 'pre-commit run' — prek is the sandbox-compatible wrapper available in PATH"

rule '\bgit\s+commit\b(?!.*(?:-[A-Za-z]*S[A-Za-z]*\b|--gpg-sign\b))' \
  "Git commits must be signed. Use 'git commit -S'"

issues=()

for idx in "${!patterns[@]}"; do
  if matches_pattern "${patterns[idx]}" <<<"${command_text}"; then
    issues+=("${messages[idx]}")
  fi
done

if ((${#issues[@]} > 0)); then
  for message in "${issues[@]}"; do
    printf '• %s\n' "${message}" >&2
  done
  exit 2
fi

exit 0
