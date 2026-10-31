#!/usr/bin/env bash
set -Eeuo pipefail

# PreToolUse hook: catch zsh expansion hazards, invalid ripgrep flags, and
# commands that bypass repository tooling.

# Exit 1 lets the call proceed on Claude and Pi, so every failure exits 2.
trap 'echo "Error: bash-command-validator.sh failed at line ${LINENO}" >&2; exit 2' ERR

if ! command -v jq > /dev/null 2>&1; then
  echo "Error: bash-command-validator.sh requires jq" >&2
  exit 2
fi

if ! command -v perl > /dev/null 2>&1; then
  echo "Error: bash-command-validator.sh requires perl" >&2
  exit 2
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

if ! jq -e . > /dev/null 2>&1 <<< "${input_json}"; then
  echo "Error: invalid JSON input" >&2
  exit 2
fi

command_text="$(jq -r '.tool_input.command // ""' <<< "${input_json}")"
if [[ -z "${command_text}" ]]; then
  exit 0
fi

patterns=()
messages=()
subjects=()

# Matched against the command as written.
rule() {
  patterns+=("$1")
  messages+=("$2")
  subjects+=("raw")
}

# Match program rules outside quoted arguments. Git rules use raw text so
# `sh -c "git commit"` still matches.
rule_command() {
  patterns+=("$1")
  messages+=("$2")
  subjects+=("unquoted")
}

strip_quoted() {
  perl -0pe 's/\x27[^\x27]*\x27/\x27\x27/g; s/"(?:[^"\\]|\\.)*"/""/g'
}

rule '(?<!<)<<[^<]' \
  "Heredocs are blocked because zsh BANG_HIST can change '!' before Bash runs. Remove '!', or write the body to \$TMPDIR/script.sh or \$TMPDIR/script.py and run the file."

rule '"[^"]*![^" \t][^"]*"' \
  "'!' in a double-quoted string triggers zsh BANG_HIST expansion. Use single quotes when no variable expansion is required. Otherwise, write the content to \$TMPDIR and run the file."

rule '(^|[[:space:];|&(])![^=[:space:]"]' \
  "Unquoted '!word' triggers zsh BANG_HIST. Single-quote the argument or remove '!'."

rule '(^|[[:space:]])\.#[a-zA-Z0-9_-]' \
  "Unquoted '.#target' uses '#' as a zsh EXTENDED_GLOB operator. Quote the flake reference: nix build '.#target' --impure"

rule '\b[0-9a-f]{6,40}\^' \
  "Unquoted '^' after a Git commit is a zsh EXTENDED_GLOB operator. Quote 'abc123^' or 'abc123^..HEAD', or use '~1'."

rule '--[a-zA-Z_-]+=\*' \
  "Unquoted '*' in '--flag=*.ext' expands before the command runs. Quote the value: --include='*.py'"

rule '/nix/store/\*' \
  "Do not glob /nix/store/*; store paths contain hashes. Use an explicit path or 'rg --files /nix/store | rg pattern'."

rule '\brg\b[^|]*[[:space:]]-[a-zA-Z]*r[a-zA-Z]*(?:=[^[:space:]]*)?(?:[[:space:]]|$)' \
  "rg is recursive by default. '-r' means '--replace', not '--recursive'. Use 'rg -n' for line numbers or 'rg -l' for file names."

# A program starts the command, follows a separator, or follows environment
# assignments. Quoted spans are stripped, so `|` inside a search pattern is data.
cmd_start='(?:^|[;|&()]{1,2})\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\x27[^\x27]*\x27|\S+)\s+)*(?:[./][\w./]*/)?'

rule_command "${cmd_start}(?:python|python3)(?:[0-9.]+)?\\s" \
  "Use 'uv run script.py' instead of python or python3. Declare dependencies in '# /// script' metadata."

rule_command "${cmd_start}pip3?\\s+(?:install|uninstall|download)\\b" \
  "Use 'uv add <pkg>' for project dependencies or 'uv run --with <pkg>' for one-off commands. For scripts, use '# /// script' metadata."

# A program after `uv run` is not in command position, so it is already exempt.
rule_command "${cmd_start}py(?:test|\\.test)\\b" \
  "Use 'uv run pytest'."

rule_command "${cmd_start}pre-commit\\s+run\\b" \
  "Use 'prek run'; it is the sandbox-compatible wrapper."

rule '(?:^|[;\n|&()]{1,2})[[:space:]]*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\x27[^\x27]*\x27|\S+)[[:space:]]+)*(?:command[[:space:]]+)?git(?:[[:space:]]+(?:(?:-[cC])[[:space:]]+\S+|-[pP]|--\S+))*[[:space:]]+commit\b' \
  "Use 'git agent-commit'; it signs with the agent key."

# Omit `|` because quoted alternations can contain `git -C`; a false positive
# blocks an unrelated command.
rule '(?:^|[;\n&()]{1,2})[[:space:]]*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\x27[^\x27]*\x27|\S+)[[:space:]]+)*(?:command[[:space:]]+)?git(?:[[:space:]]+(?:-[pP]|--\S+))*[[:space:]]+-C\b' \
  "Run 'cd <path>' in its own Bash call, then use a plain command such as 'git status --short' or 'git --no-pager diff'. The plain form avoids an approval prompt."

issues=()

command_unquoted="$(strip_quoted <<< "${command_text}")"

for idx in "${!patterns[@]}"; do
  if [[ "${subjects[idx]}" == "unquoted" ]]; then
    subject="${command_unquoted}"
  else
    subject="${command_text}"
  fi
  if matches_pattern "${patterns[idx]}" <<< "${subject}"; then
    issues+=("${messages[idx]}")
  fi
done

if ((${#issues[@]} > 0)); then
  for message in "${issues[@]}"; do
    printf -- '- %s\n' "${message}" >&2
  done
  exit 2
fi

exit 0
