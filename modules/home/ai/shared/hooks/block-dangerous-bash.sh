#!/usr/bin/env bash
# Claude Code Hook: Block dangerous bash patterns
#
# PreToolUse hook for the Bash tool.
# Blocks reverse shells, pipe-to-shell, obfuscated exec, clipboard reads,
# and fork bombs before they can be executed.
#
# Each rule is tested against the command as written and against a normalized
# spelling of it (see normalize_text), so a rule written for `| bash` still
# fires on `| b'a'sh`. Testing both can only add matches, never drop one.
#
# Exit codes:
#   0 = allow
#   2 = block (hard block, no recovery path in current invocation)

set -uo pipefail

# Returns 0 if stdin matches the given Perl-compatible regex.
matches_pattern() {
  local pattern="${1}"
  VALIDATION_PATTERN="${pattern}" perl -0e '
    my $pattern = $ENV{VALIDATION_PATTERN};
    my $text = do { local $/; <STDIN> };
    my $regex = eval { qr{$pattern}si };
    exit 1 if $@;
    exit($text =~ $regex ? 0 : 1);
  '
}

# Rewrites shell spellings that hide a command word from the rules.
#
# Quotes are dropped only where they cannot be delimiting an argument: an empty
# pair, a span with no internal whitespace, or a span glued to an adjacent word
# character. A standalone quoted argument such as `grep 'curl | bash'` keeps its
# quotes, so searching for a string is never rewritten into running it.
#
# Backslash-escaped word characters are left as written; undoing those needs
# quote-context tracking this does not do.
normalize_text() {
  perl -0e '
    my $text = do { local $/; <STDIN> };
    $text =~ s/\\\n//g;
    my $src = $text;
    my $seps = " \t\n|&;()<>";
    $text =~ s{([\x27"])(.*?)\1}{
      my $body  = $2;
      my $whole = $&;
      my $s     = $-[0];
      my $e     = $+[0];
      my $keep  = 0;
      if ($body =~ /\s/) {
        my $before = $s > 0 ? substr($src, $s - 1, 1) : "";
        my $after  = $e < length($src) ? substr($src, $e, 1) : "";
        my $splices = 0;
        $splices = 1 if length($before) && index($seps, $before) < 0;
        $splices = 1 if length($after) && index($seps, $after) < 0;
        $keep = $splices ? 0 : 1;
      }
      $keep ? $whole : $body;
    }gse;
    print $text;
  '
}

_AI_INSTRUCTIONS="
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed"

block() {
  printf '%s\n%s\n' "${1}" "${_AI_INSTRUCTIONS}" >&2
  exit 2
}

# Bash is the only tool here, and it is sensitive: fail closed on any error.
input_json="$(cat)" || exit 2

tool_name="$(jq -re '.tool_name // empty' 2> /dev/null <<< "${input_json}")" || exit 2
[[ "${tool_name}" == "Bash" ]] || exit 0

command_text="$(jq -r '.tool_input.command // ""' 2> /dev/null <<< "${input_json}")" || exit 2
[[ -n "${command_text}" ]] || exit 0

normalized_text="$(normalize_text <<< "${command_text}")" || exit 2

candidate_texts=("${command_text}")
if [[ "${normalized_text}" != "${command_text}" ]]; then
  candidate_texts+=("${normalized_text}")
fi

# The /dev/tcp and nc checks are positional (host segment), so appended text
# such as "; echo localhost" cannot buy the loopback exemption.
readonly LOCAL_DEVTCP_RE='\/dev\/(tcp|udp)\/(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\/'
readonly LOCAL_NC_RE='\bnc\b[^;|&\n]*(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\s+[0-9]'
readonly LOCAL_GENERIC_RE='(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)'

# rule <exemption> <pattern> <message>
#   exemption: devtcp | nc | generic | none
#   pattern:   PCRE matched case-insensitively with dot-matches-newline
#   message:   block reason passed to block()

rules=()

rule() { rules+=("$1" "$2" "$3"); }

_MSG_REVERSE_SHELL="Blocked: reverse shell pattern detected.
This command opens a network connection back to a remote host and executes an interactive shell, giving the remote host full command-line control over this system."

_MSG_PIPE_TO_SHELL="Blocked: download-and-execute pipeline detected.
This command downloads a script from the internet and immediately executes it, bypassing any opportunity to inspect what the script will do before it runs."

_MSG_OBFUSCATED="Blocked: obfuscated execution detected.
This command decodes hidden content at runtime and executes it as a shell script, making the actual payload invisible to static code review."

_MSG_CLIPBOARD="Blocked: clipboard read detected.
This command reads the system clipboard, which may contain passwords, tokens, or other sensitive data the user recently copied."

_MSG_FORK_BOMB="Blocked: fork bomb detected.
This command defines a function that recursively spawns processes until system memory is exhausted, causing a system crash."

_MSG_CRON="Blocked: cron injection detected.
This command installs or modifies cron jobs, which can establish persistent backdoors that survive reboots and run arbitrary code on a schedule."

_MSG_SSH_KEY="Blocked: SSH key manipulation detected.
This command modifies SSH keys or authorized_keys, which could grant persistent unauthorized access to this system or to remote systems."

_MSG_PRIVILEGE="Blocked: privilege escalation detected.
This command elevates to root or another user's privileges.
Claude Code should operate within the current user's permissions.
Delegate these commands to the user to run manually if they are necessary for the task."

_MSG_MACOS="Blocked: macOS system interaction detected.
This command launches applications, runs AppleScript, or modifies system preferences, which can have side effects outside the development environment."

rule devtcp 'bash\s+-i\b.*/dev/(tcp|udp)/' "${_MSG_REVERSE_SHELL}"
rule devtcp '/dev/(tcp|udp)/[^/\s]+/[0-9]+' "${_MSG_REVERSE_SHELL}"
rule nc '\b(nc|ncat)\b[^;|&\n]*\s-(e|c)\s' "${_MSG_REVERSE_SHELL}"
rule nc '\bmkfifo\b[^;|&\n]*\|\s*.*\bnc\s' "${_MSG_REVERSE_SHELL}"
rule generic '\bsocat\b[^;|&\n]*(exec:|system:)[^;|&\n]*(sh|bash|zsh)' "${_MSG_REVERSE_SHELL}"
rule generic '\btelnet\s+\S+\s+[0-9]+\s*\|.*\b(sh|bash)\b' "${_MSG_REVERSE_SHELL}"
rule generic '\bpython[0-9.]?\b[^;|&\n]*socket[^;|&\n]*(exec|connect)' "${_MSG_REVERSE_SHELL}"
rule generic '\bperl\b[^;|&\n]*-e[^;|&\n]*socket' "${_MSG_REVERSE_SHELL}"
rule generic '\bruby\b[^;|&\n]*-e[^;|&\n]*TCPSocket' "${_MSG_REVERSE_SHELL}"
rule generic '\bphp\b[^;|&\n]*-r[^;|&\n]*fsockopen' "${_MSG_REVERSE_SHELL}"

rule none '(curl|wget|fetch)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?|ruby)\b' "${_MSG_PIPE_TO_SHELL}"

rule none 'base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?)' "${_MSG_OBFUSCATED}"
rule none '\|\s*base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh)' "${_MSG_OBFUSCATED}"
rule none '\beval\s*\$\(' "${_MSG_OBFUSCATED}"
rule none '\beval\s*`' "${_MSG_OBFUSCATED}"
rule none 'xxd\s+-r\b[^|]*\|\s*(ba?sh|zsh)' "${_MSG_OBFUSCATED}"

rule none '\bpbpaste\b' "${_MSG_CLIPBOARD}"
rule none '\bxclip\b[^;|&\n]*(--output|-o)\b' "${_MSG_CLIPBOARD}"
rule none '\bxsel\b[^;|&\n]*(--output|-o)\b' "${_MSG_CLIPBOARD}"
rule none '\bwl-paste\b' "${_MSG_CLIPBOARD}"
rule none '\bGet-Clipboard\b' "${_MSG_CLIPBOARD}"

# The canonical bash fork bomb, :(){ :|:& };:
rule none ':\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*:\s*&[^}]*\}' "${_MSG_FORK_BOMB}"

rule none '\|\s*crontab\b' "${_MSG_CRON}"
rule none '\bcrontab\s+-\s*$' "${_MSG_CRON}"
rule none '\bcrontab\s+[^-\s]' "${_MSG_CRON}"

rule none '>>\s*~?/?\S*\.ssh/authorized_keys' "${_MSG_SSH_KEY}"
rule none '>\s*~?/?\S*\.ssh/authorized_keys' "${_MSG_SSH_KEY}"
rule none '\bcp\b[^;|&\n]*\.ssh/(?:id_|authorized_keys)' "${_MSG_SSH_KEY}"

rule none '(?:^|[;\n|&]\s*)sudo\b' "${_MSG_PRIVILEGE}"
rule none '(?:^|[;\n|&]\s*)su\b' "${_MSG_PRIVILEGE}"

rule none '\bosascript\b' "${_MSG_MACOS}"
rule none '\bdefaults\s+write\b' "${_MSG_MACOS}"

for ((i = 0; i < ${#rules[@]}; i += 3)); do
  exemption="${rules[i]}"
  pattern="${rules[i + 1]}"
  message="${rules[i + 2]}"

  # The exemption is judged against whichever spelling matched, so a loopback
  # target exempts the rewritten text too and not only the original.
  for text in "${candidate_texts[@]}"; do
    matches_pattern "${pattern}" <<< "${text}" || continue
    case "${exemption}" in
      devtcp)
        matches_pattern "${LOCAL_DEVTCP_RE}" <<< "${text}" && continue
        ;;
      nc)
        matches_pattern "${LOCAL_NC_RE}" <<< "${text}" && continue
        ;;
      generic)
        matches_pattern "${LOCAL_GENERIC_RE}" <<< "${text}" && continue
        ;;
      none) ;; # no exemption — fall through to block()
      *)
        printf 'block-dangerous-bash.sh: unknown exemption type "%s"\n' "${exemption}" >&2
        exit 2
        ;;
    esac
    block "${message}"
  done
done

exit 0
