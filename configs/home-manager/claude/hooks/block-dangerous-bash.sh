#!/usr/bin/env bash
# Claude Code Hook: Block dangerous bash patterns
#
# PreToolUse hook for the Bash tool.
# Blocks reverse shells, pipe-to-shell, obfuscated exec, clipboard reads,
# and fork bombs before they can be executed.
#
# Exit codes:
#   0 = allow
#   2 = block (hard block, no recovery path in current invocation)

set -uo pipefail

# Helper: return 0 if stdin text matches the given Perl-compatible regex
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

# Read stdin; fail closed on any error (Bash-only hook)
input_json="$(cat)" || exit 2

tool_name="$(jq -re '.tool_name // empty' 2>/dev/null <<< "${input_json}")" || exit 2
[[ "${tool_name}" == "Bash" ]] || exit 0

command_text="$(jq -r '.tool_input.command // ""' 2>/dev/null <<< "${input_json}")" || exit 2
[[ -n "${command_text}" ]] || exit 0

# Loopback check for /dev/tcp and /dev/udp: the host segment immediately after
# the device path must be a loopback address.  Checking anywhere in the command
# (the naive approach) is bypassable by appending e.g. "; echo localhost".
# For scripting-language reverse shells the host is embedded inside a string
# argument, so a perfect check requires parsing; this covers the common forms.
readonly LOCAL_DEVTCP_RE='\/dev\/(tcp|udp)\/(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\/'
readonly LOCAL_NC_RE='\bnc\b[^;|&\n]*(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\s+[0-9]'
readonly LOCAL_GENERIC_RE='(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)'

# ── Reverse shells ─────────────────────────────────────────────────────────────
# Patterns that establish an interactive shell connection back to a remote host.
# Each entry is "exemption_type:pattern" where exemption_type controls which
# localhost check applies:
#   devtcp  — positional check: loopback in /dev/tcp/<host>/ path segment
#   nc      — positional check: loopback as nc host argument
#   generic — broad check: loopback anywhere in command (scripting languages)
#   none    — no localhost exemption (socat, telnet, mkfifo — mixed patterns)

reverse_shell_entries=(
  # bash -i redirected to /dev/tcp or /dev/udp
  'devtcp:bash\s+-i\b.*/dev/(tcp|udp)/'
  # Direct /dev/tcp or /dev/udp socket usage (e.g. exec 5<>/dev/tcp/host/port)
  'devtcp:/dev/(tcp|udp)/[^/\s]+/[0-9]+'
  # netcat / ncat with -e (exec) or -c (command)
  'nc:\b(nc|ncat)\b[^;|&\n]*\s-(e|c)\s'
  # Named pipe (mkfifo) piped through nc — bidirectional shell over netcat
  'nc:\bmkfifo\b[^;|&\n]*\|\s*.*\bnc\s'
  # socat forwarding to an interactive shell
  'generic:\bsocat\b[^;|&\n]*(exec:|system:)[^;|&\n]*(sh|bash|zsh)'
  # telnet piped to a shell
  'generic:\btelnet\s+\S+\s+[0-9]+\s*\|.*\b(sh|bash)\b'
  # Scripting language one-liner reverse shells
  'generic:\bpython[0-9.]?\b[^;|&\n]*socket[^;|&\n]*(exec|connect)'
  'generic:\bperl\b[^;|&\n]*-e[^;|&\n]*socket'
  'generic:\bruby\b[^;|&\n]*-e[^;|&\n]*TCPSocket'
  'generic:\bphp\b[^;|&\n]*-r[^;|&\n]*fsockopen'
)

for entry in "${reverse_shell_entries[@]}"; do
  exemption="${entry%%:*}"
  pattern="${entry#*:}"
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    # Exempt loopback targets (local development tooling is permitted).
    # Apply the exemption check appropriate to the pattern family to prevent
    # bypass via appended text like "; echo localhost".
    case "${exemption}" in
      devtcp)
        matches_pattern "${LOCAL_DEVTCP_RE}" <<< "${command_text}" && continue
        ;;
      nc)
        matches_pattern "${LOCAL_NC_RE}" <<< "${command_text}" && continue
        ;;
      generic)
        matches_pattern "${LOCAL_GENERIC_RE}" <<< "${command_text}" && continue
        ;;
    esac
    block "Blocked: reverse shell pattern detected.
This command opens a network connection back to a remote host and executes an interactive shell, giving the remote host full command-line control over this system."
  fi
done

# ── Pipe-to-shell ──────────────────────────────────────────────────────────────
# Download-and-execute pipelines that run remote code without prior inspection.

pipe_to_shell_patterns=(
  '(curl|wget|fetch)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?|ruby)\b'
)

for pattern in "${pipe_to_shell_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: download-and-execute pipeline detected.
This command downloads a script from the internet and immediately executes it, bypassing any opportunity to inspect what the script will do before it runs."
  fi
done

# ── Obfuscated execution ───────────────────────────────────────────────────────
# Commands that decode hidden content at runtime and execute it as code.

obfuscated_patterns=(
  # base64 decode piped directly to a shell
  'base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?)'
  # pipeline that decodes base64 before passing to a shell
  '\|\s*base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh)'
  # eval of a command substitution (classic arbitrary-code injection)
  '\beval\s*\$\('
  '\beval\s*`'
  # hex decode piped to a shell
  'xxd\s+-r\b[^|]*\|\s*(ba?sh|zsh)'
)

for pattern in "${obfuscated_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: obfuscated execution detected.
This command decodes hidden content at runtime and executes it as a shell script, making the actual payload invisible to static code review."
  fi
done

# ── Clipboard reads ────────────────────────────────────────────────────────────
# Commands that read the system clipboard, which may contain passwords or tokens.

clipboard_patterns=(
  '\bpbpaste\b'                           # macOS
  '\bxclip\b[^;|&\n]*(--output|-o)\b'    # Linux X11 (xclip)
  '\bxsel\b[^;|&\n]*(--output|-o)\b'     # Linux X11 (xsel)
  '\bwl-paste\b'                          # Linux Wayland
  '\bGet-Clipboard\b'                     # PowerShell
)

for pattern in "${clipboard_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: clipboard read detected.
This command reads the system clipboard, which may contain passwords, tokens, or other sensitive data the user recently copied."
  fi
done

# ── Fork bomb ─────────────────────────────────────────────────────────────────
# Recursive process-spawning that exhausts system memory.

fork_bomb_patterns=(
  # Canonical bash fork bomb: :(){ :|:& };:
  ':\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*:\s*&[^}]*\}'
)

for pattern in "${fork_bomb_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: fork bomb detected.
This command defines a function that recursively spawns processes until system memory is exhausted, causing a system crash."
  fi
done

# ── Cron injection ────────────────────────────────────────────────────────────
# Commands that install persistent cron jobs (potential backdoor persistence).

cron_injection_patterns=(
  '\|\s*crontab\b'
  '\bcrontab\s+-\s*$'
  '\bcrontab\s+[^-\s]'
)

for pattern in "${cron_injection_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: cron injection detected.
This command installs or modifies cron jobs, which can establish persistent backdoors that survive reboots and run arbitrary code on a schedule."
  fi
done

# ── SSH key manipulation ─────────────────────────────────────────────────────
# Commands that inject SSH keys (potential unauthorized access persistence).

ssh_key_patterns=(
  # Appending to authorized_keys
  '>>\s*~?/?\S*\.ssh/authorized_keys'
  # Writing to authorized_keys
  '>\s*~?/?\S*\.ssh/authorized_keys'
  # Copying an SSH key file into .ssh
  '\bcp\b[^;|&\n]*\.ssh/(?:id_|authorized_keys)'
)

for pattern in "${ssh_key_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: SSH key manipulation detected.
This command modifies SSH keys or authorized_keys, which could grant persistent unauthorized access to this system or to remote systems."
  fi
done

# ── Privilege escalation ──────────────────────────────────────────────────────
# Commands that elevate privileges beyond the current user.

privilege_patterns=(
  '(?:^|[;\n|&]\s*)sudo\b'
  '(?:^|[;\n|&]\s*)su\b'
)

for pattern in "${privilege_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: privilege escalation detected.
This command elevates to root or another user's privileges.
Claude Code should operate within the current user's permissions.
Delegate these commands to the user to run manually if they are necessary for the task."
  fi
done

# ── macOS system interaction ─────────────────────────────────────────────────
# Commands that launch applications or modify system configuration.

macos_patterns=(
  '\bosascript\b'                 # Execute arbitrary AppleScript
  '\bdefaults\s+write\b'         # Modify macOS system/app preferences
)

for pattern in "${macos_patterns[@]}"; do
  if matches_pattern "${pattern}" <<< "${command_text}"; then
    block "Blocked: macOS system interaction detected.
This command launches applications, runs AppleScript, or modifies system preferences, which can have side effects outside the development environment."
  fi
done

exit 0
