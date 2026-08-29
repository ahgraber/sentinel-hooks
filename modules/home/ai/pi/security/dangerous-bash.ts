/** Command patterns ported from block-dangerous-bash.sh. */

export const REVERSE_SHELL_RULES: Array<{ re: RegExp; exemption: "devtcp" | "nc" | "generic" | "none"; msg: string }> =
  [
    { re: /bash\s+-i\b.*\/dev\/(tcp|udp)\//is, exemption: "devtcp", msg: "Blocked: reverse shell via /dev/tcp." },
    { re: /\/dev\/(tcp|udp)\/[^\s/]+\/[0-9]+/is, exemption: "devtcp", msg: "Blocked: direct /dev/tcp socket usage." },
    { re: /\b(nc|ncat)\b[^;|&\n]*\s-(e|c)\s/is, exemption: "nc", msg: "Blocked: netcat reverse shell (-e/-c)." },
    { re: /\bmkfifo\b[^;|&\n]*\|\s*.*\bnc\s/is, exemption: "nc", msg: "Blocked: named-pipe netcat reverse shell." },
    {
      re: /\bsocat\b[^;|&\n]*(exec:|system:)[^;|&\n]*(sh|bash|zsh)/is,
      exemption: "generic",
      msg: "Blocked: socat reverse shell.",
    },
    {
      re: /\btelnet\s+\S+\s+[0-9]+\s*\|.*\b(sh|bash)\b/is,
      exemption: "generic",
      msg: "Blocked: telnet reverse shell.",
    },
    {
      re: /\bpython[0-9.]?\b[^;|&\n]*socket[^;|&\n]*(exec|connect)/is,
      exemption: "generic",
      msg: "Blocked: Python socket reverse shell.",
    },
    { re: /\bperl\b[^;|&\n]*-e[^;|&\n]*socket/is, exemption: "generic", msg: "Blocked: Perl socket reverse shell." },
    {
      re: /\bruby\b[^;|&\n]*-e[^;|&\n]*TCPSocket/is,
      exemption: "generic",
      msg: "Blocked: Ruby TCPSocket reverse shell.",
    },
    {
      re: /\bphp\b[^;|&\n]*-r[^;|&\n]*fsockopen/is,
      exemption: "generic",
      msg: "Blocked: PHP fsockopen reverse shell.",
    },
  ]

export const LOOPBACK_DEVTCP_RE = /\/dev\/(tcp|udp)\/(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\//is
export const LOOPBACK_NC_RE = /\bnc\b[^;|&\n]*(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\s+[0-9]/is
export const LOOPBACK_RE = /(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)/i

export const PIPE_TO_SHELL_RE = /(curl|wget|fetch)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?|ruby)\b/is
export const OBFUSCATED_RE =
  /base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?)|\|\s*base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh)|\beval\s*\$\(|\beval\s*`|xxd\s+-r\b[^|]*\|\s*(ba?sh|zsh)/is
export const CLIPBOARD_RE =
  /\bpbpaste\b|\bxclip\b[^;|&\n]*(--output|-o)\b|\bxsel\b[^;|&\n]*(--output|-o)\b|\bwl-paste\b|\bGet-Clipboard\b/is
export const FORK_BOMB_RE = /:\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*:\s*&[^}]*\}/s
export const CRON_RE = /\|\s*crontab\b|\bcrontab\s+-\s*$|\bcrontab\s+[^\-\s]/is
export const SSH_KEY_MANIP_RE =
  />>?\s*~?\/?[^\s]*\.ssh\/authorized_keys|\bcp\b[^;|&\n]*\.ssh\/(?:id_|authorized_keys)/is
export const SUDO_RE = /(?:^|[;\n|&]\s*)sudo\b/m
export const SU_RE = /(?:^|[;\n|&]\s*)su\b/m
export const MACOS_SYS_RE = /\bosascript\b|\bdefaults\s+write\b/is
