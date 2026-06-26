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

# catch common mistakes in bash commands and provide guidance

rule '<<[^<]' \
  "If this heredoc body contains '!' (e.g. '!=', '!word', shebangs), zsh BANG_HIST will mangle it silently. Options: (1) rewrite the body to avoid '!'; (2) write the script to \$TMPDIR/script.sh or \$TMPDIR/script.py and run it: bash \"\$TMPDIR/script.sh\" or uv run \"\$TMPDIR/script.py\". Skip if the body has no '!'."

rule '"[^"]*![^" \t][^"]*"' \
  "'!' inside a double-quoted string is expanded by zsh BANG_HIST (e.g. \"val!=x\" mangles silently). Use single quotes if no variable expansion is needed. If \$vars are required, write the content to \$TMPDIR and run from a file."

rule '(^|[[:space:];|&(])![^=[:space:]"]' \
  "An unquoted '!word' is expanded by zsh BANG_HIST as a history reference. Single-quote the argument containing '!' to prevent expansion, or restructure to avoid '!'."

rule '(^|[[:space:]])\.#[a-zA-Z0-9_-]' \
  "'.#target' — '#' is a zsh EXTENDED_GLOB repetition operator, causing 'no matches found'. Quote nix flake refs: nix build '.#target' --impure"

rule '\b[0-9a-f]{6,40}\^' \
  "'^' after a git commit hash is a zsh EXTENDED_GLOB negation operator. Quote it: 'abc123^' or 'abc123^..HEAD', or use '~1' instead of '^'"

rule '--[a-zA-Z_-]+=\*' \
  "The '*' in '--flag=*.ext' is expanded by zsh glob before reaching the command. Quote the value: --include='*.py'"

rule '/nix/store/\*' \
  "Globbing /nix/store/* is unreliable — store paths are non-deterministic hashes. Use 'rg --files /nix/store | rg pattern' or an explicit known path."


# redirect tool calls

# rule '(?:^|[;|&(])\s*grep\b' \
#   "Use 'rg' (ripgrep) instead of 'grep' for better performance and features"

# rule '^find\s+\S+\s+-name\b' \
#   "Use 'rg --files | rg pattern' or 'rg --files -g pattern' instead of 'find -name' for better performance"

rule '\brg\b[^|]*-[a-zA-Z]*r[a-zA-Z]' \
  "rg is recursive by default — '-r' means '--replace' (substitution), not '--recursive'. 'rg -rn' replaces matches with literal 'n' and silently corrupts output. Drop the '-r': use 'rg -n' for line numbers, 'rg -l' for filenames."

rule "(?:^|[;|&()]{1,2})\\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\\S+)\\s+)*(?:[./][\\w./]*/)?(?:python|python3)(?:[0-9.]+)?\\s" \
  "Use 'uv run' instead of invoking python/python3 directly. For scripts with dependencies, use uv inline script metadata (# /// script) and run with 'uv run script.py'"

rule '(?<!\w)(?<!uv )pip\s+(install|uninstall|download)\b' \
  "Use 'uv add' or 'uv run --with <pkg>' instead of pip. For one-off scripts, declare dependencies inline with uv script metadata (# /// script)"

rule '(?<!\w)pip3\s+(install|uninstall|download)\b' \
  "Use 'uv add' or 'uv run --with <pkg>' instead of pip3. For one-off scripts, declare dependencies inline with uv script metadata (# /// script)"

rule '^(?!.*\buv\s+run\b).*\bpy(?:test|\.test)\b' \
  "Use 'uv run pytest' instead of invoking pytest/py.test directly"

rule '\bpre-commit\s+run\b' \
  "Use 'prek run' instead of 'pre-commit run' — prek is the sandbox-compatible wrapper available in PATH"

rule '\bgit\b.*\s+commit\b' \
  "Use 'git agent-commit' alias instead of 'git commit' — the alias signs with the dedicated agent key"

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
