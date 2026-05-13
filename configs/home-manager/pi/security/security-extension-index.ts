/**
 * Pi Security Extension
 *
 * Full port of Claude Code security hooks:
 *   - block-dangerous-bash.sh      → dangerousBashRules
 *   - block-sensitive-paths.py     → isSensitivePath / bashWriteTargets
 *   - block-destructive-ops.py     → loadDestructiveRules (TOML-driven)
 *   - block-secrets.py             → hasSecret / gitleaks integration
 *   - bash-command-validator.sh    → BASH_VALIDATOR_RULES
 *   - block-hook-tampering.py      → PROTECTED_PATH_FRAGMENTS
 *   - session-tool-checks.sh       → session_start tool checks
 *   - posttooluse-precommit.sh     → tool_result pre-commit spawn
 *   - using-skills.sh              → context injection (Pi native skills)
 *   - reload-skills-catalog.py     → Pi surfaces skills natively; no hook needed
 *
 * Dependencies: smol-toml (install via `npm install smol-toml` in this dir)
 *
 * Place this file at:   ~/.pi/agent/extensions/security/index.ts
 * Place the TOML at:    ~/.pi/agent/extensions/security/block-destructive-ops-patterns.toml
 *
 * package.json in this directory:
 *   { "dependencies": { "smol-toml": "^1.6.1" } }
 */

import { type ExecFileException, execFile as execFileCb, execFileSync } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join, normalize, resolve } from "node:path"
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent"
import { parse as parseToml } from "smol-toml"

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface DestructiveRule {
  pattern: string
  description: string
  reason: string
  mode: "block" | "ask"
  case_insensitive?: boolean
}

// ─────────────────────────────────────────────────────────────────────────────
// TOML rule loader
// ─────────────────────────────────────────────────────────────────────────────

function loadDestructiveRules(): DestructiveRule[] {
  const tomlPath = join(dirname(new URL(import.meta.url).pathname), "block-destructive-ops-patterns.toml")
  if (!existsSync(tomlPath)) {
    console.warn(`[security] TOML patterns file not found: ${tomlPath}`)
    return []
  }
  try {
    const data = parseToml(readFileSync(tomlPath, "utf8")) as Record<string, unknown>
    const rules: DestructiveRule[] = []
    // Support both flat [[rules]] and nested [[category.rules]]
    if (Array.isArray(data.rules)) {
      rules.push(...(data.rules as DestructiveRule[]))
    } else {
      for (const section of Object.values(data)) {
        if (
          section &&
          typeof section === "object" &&
          "rules" in section &&
          Array.isArray((section as { rules: unknown }).rules)
        ) {
          rules.push(...(section as { rules: DestructiveRule[] }).rules)
        }
      }
    }
    return rules
  } catch (err) {
    console.error("[security] Failed to parse TOML patterns:", err)
    return []
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Compiled destructive rules (loaded once at extension startup)
// ─────────────────────────────────────────────────────────────────────────────

const DESTRUCTIVE_RULES: Array<{
  re: RegExp
  rule: DestructiveRule
}> = loadDestructiveRules().flatMap((rule) => {
  try {
    const flags = rule.case_insensitive ? "si" : "s"
    return [{ re: new RegExp(rule.pattern, flags), rule }]
  } catch {
    console.warn(`[security] Invalid pattern skipped: ${rule.pattern}`)
    return []
  }
})

// ─────────────────────────────────────────────────────────────────────────────
// Dangerous bash patterns (from block-dangerous-bash.sh)
// ─────────────────────────────────────────────────────────────────────────────

const REVERSE_SHELL_RULES: Array<{ re: RegExp; exemption: "devtcp" | "nc" | "generic" | "none"; msg: string }> = [
  { re: /bash\s+-i\b.*\/dev\/(tcp|udp)\//is, exemption: "devtcp", msg: "Blocked: reverse shell via /dev/tcp." },
  { re: /\/dev\/(tcp|udp)\/[^\s/]+\/[0-9]+/is, exemption: "devtcp", msg: "Blocked: direct /dev/tcp socket usage." },
  { re: /\b(nc|ncat)\b[^;|&\n]*\s-(e|c)\s/is, exemption: "nc", msg: "Blocked: netcat reverse shell (-e/-c)." },
  { re: /\bmkfifo\b[^;|&\n]*\|\s*.*\bnc\s/is, exemption: "nc", msg: "Blocked: named-pipe netcat reverse shell." },
  {
    re: /\bsocat\b[^;|&\n]*(exec:|system:)[^;|&\n]*(sh|bash|zsh)/is,
    exemption: "generic",
    msg: "Blocked: socat reverse shell.",
  },
  { re: /\btelnet\s+\S+\s+[0-9]+\s*\|.*\b(sh|bash)\b/is, exemption: "generic", msg: "Blocked: telnet reverse shell." },
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
  { re: /\bphp\b[^;|&\n]*-r[^;|&\n]*fsockopen/is, exemption: "generic", msg: "Blocked: PHP fsockopen reverse shell." },
]

const LOOPBACK_DEVTCP_RE = /\/dev\/(tcp|udp)\/(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\//is
const LOOPBACK_NC_RE = /\bnc\b[^;|&\n]*(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)\s+[0-9]/is
const LOOPBACK_RE = /(127\.0\.0\.1|localhost|::1|0\.0\.0\.0)/i

const PIPE_TO_SHELL_RE = /(curl|wget|fetch)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?|ruby)\b/is
const OBFUSCATED_RE =
  /base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh|python[0-9.]?)|\|\s*base64\s+(-d|--decode)\b[^|]*\|\s*(ba?sh|zsh)|\beval\s*\$\(|\beval\s*`|xxd\s+-r\b[^|]*\|\s*(ba?sh|zsh)/is
const CLIPBOARD_RE =
  /\bpbpaste\b|\bxclip\b[^;|&\n]*(--output|-o)\b|\bxsel\b[^;|&\n]*(--output|-o)\b|\bwl-paste\b|\bGet-Clipboard\b/is
const FORK_BOMB_RE = /:\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*:\s*&[^}]*\}/s
const CRON_RE = /\|\s*crontab\b|\bcrontab\s+-\s*$|\bcrontab\s+[^\-\s]/is
const SSH_KEY_MANIP_RE = />>?\s*~?\/?[^\s]*\.ssh\/authorized_keys|\bcp\b[^;|&\n]*\.ssh\/(?:id_|authorized_keys)/is
const SUDO_RE = /(?:^|[;\n|&]\s*)sudo\b/m
const SU_RE = /(?:^|[;\n|&]\s*)su\b/m
const MACOS_SYS_RE = /\bosascript\b|\bdefaults\s+write\b/is

// ─────────────────────────────────────────────────────────────────────────────
// Sensitive path detection (from block-sensitive-paths.py)
// ─────────────────────────────────────────────────────────────────────────────

const EXTENSION_RE = /\.(pem|key|p12|pfx|crt|cer|tfstate|tfstate\.backup)$/i
const DOTENV_RE = /(?:^|[/\\])\.env(?:\.[^/\\]+)?$/
const ENVRC_RE = /(?:^|[/\\])\.envrc$/
const ZERO_ACCESS_FILES = /(?:^|[/\\])\.(bash_history|zsh_history|sh_history|node_repl_history|python_history)$/i
const NAME_PATTERN_RE = /credentials|secret/i
const EXEMPT_DIR_RE =
  /(?:^|[/\\])(?:\.venv|venv|env|site-packages|node_modules|\.pi|\.claude|(?:claude|codex)[/\\](?:hooks|tests))(?:[/\\]|$)/i

const ZERO_ACCESS_DIR_PREFIXES = ["~/.ssh/", "~/.aws/", "~/.kube/", "~/.gnupg/"]

function expandPath(p: string): string {
  return normalize(p.replace(/^~/, homedir()))
}

function isSensitivePath(rawPath: string): boolean {
  if (!rawPath) return false
  const expanded = expandPath(rawPath)

  if (EXTENSION_RE.test(expanded)) return true
  if (DOTENV_RE.test(rawPath) || ENVRC_RE.test(rawPath)) return true
  if (ZERO_ACCESS_FILES.test(rawPath)) return true

  for (const dir of ZERO_ACCESS_DIR_PREFIXES) {
    const prefix = expandPath(dir)
    if (expanded.startsWith(prefix + "/") || expanded === prefix) return true
  }

  const basename = expanded.split(/[/\\]/).pop() ?? ""
  if (NAME_PATTERN_RE.test(basename) && !EXEMPT_DIR_RE.test(rawPath)) return true

  return false
}

/** Extract likely write-destination paths from a bash command string. */
function bashWriteTargets(command: string): string[] {
  const targets: string[] = []

  // Output redirections: > or >> path (exclude <<, 2>, etc.)
  for (const m of command.matchAll(/(?<![<2&])>>?\s*([^\s|&;><]+)/g)) {
    targets.push(m[1])
  }
  // cp / mv / install — last non-option token
  for (const cmd of ["cp", "mv", "install"]) {
    for (const m of command.matchAll(
      new RegExp(`\\b${cmd}\\b\\s+((?:(?:-[^\\s]+|--[^\\s]+|\\S+)\\s+)+?)(\\S+)\\s*(?:$|[|&;])`, "g"),
    )) {
      targets.push(m[2])
    }
  }
  // tee: tee [-ai] <file>
  for (const m of command.matchAll(/\btee\b(?:\s+-[ai]+)*\s+([^\s|&;]+)/g)) {
    targets.push(m[1])
  }
  // chmod / chown: <cmd> <mode-or-owner> <path>
  for (const cmd of ["chmod", "chown"]) {
    for (const m of command.matchAll(new RegExp(`\\b${cmd}\\b\\s+\\S+\\s+([^\\s|&;]+)`, "g"))) {
      targets.push(m[1])
    }
  }
  return targets
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook/settings tampering protection (from block-hook-tampering.py)
// ─────────────────────────────────────────────────────────────────────────────

const PROTECTED_PATH_FRAGMENTS = [
  ".pi/agent/extensions/security",
  ".pi/agent/settings.json",
  ".claude/hooks/",
  ".claude/settings.json",
  ".claude/settings.local.json",
  "configs/home-manager/claude/hooks/",
  "home-manager/claude-settings.json",
]

function isProtectedPath(raw: string): boolean {
  if (!raw) return false
  const expanded = expandPath(raw)
  const resolved = (() => {
    try {
      return resolve(expanded)
    } catch {
      return expanded
    }
  })()
  return PROTECTED_PATH_FRAGMENTS.some((f) => raw.includes(f) || expanded.includes(f) || resolved.includes(f))
}

// ─────────────────────────────────────────────────────────────────────────────
// Secret detection (from block-secrets.py)
// ─────────────────────────────────────────────────────────────────────────────

const BUILTIN_SECRET_RES = [
  /\bAKIA[0-9A-Z]{16}\b/,
  /aws_secret_access_key\s*=\s*\S{20,}/i,
  /\b(?:ghp|gho|ghs|ghr)_[a-zA-Z0-9]{36}\b/,
  /\bgithub_pat_[a-zA-Z0-9_]{22,}\b/,
  /\bsk-ant-api[0-9]+-[a-zA-Z0-9]{70,}\b/,
  /\bsk-(?:proj-)?[a-zA-Z0-9T]{48,}\b/,
  /\bxox[bpra]-[0-9]{9,}-[a-zA-Z0-9-]+\b/,
  /-----BEGIN\s+(?:\w+\s+)?PRIVATE\s+KEY-----/,
  /-----BEGIN\s+PGP\s+PRIVATE\s+KEY\s+BLOCK-----/,
  /(?:bearer|authorization)\s+[A-Za-z0-9\-_.~+/]{20,}/i,
  /(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token)\s*[=:]\s*[A-Za-z0-9+/\-_.]{16,}/i,
]

const NETWORK_CMD_RE =
  /\b(?:curl|wget|nc|ncat|netcat|ftp|sftp|scp|rsync|socat|ssh(?!-\w)|telnet)\b|\bopenssl\s+s_client\b/i
const LOCAL_URL_RE = /https?:\/\/(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)[:/\s"']/i
const LOCAL_NC_HOST_RE = /\bnc\b[^|;&\n]*(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)\s+[0-9]/i
const LOCAL_SSH_RE =
  /\b(?:scp|rsync)\b[^|;&\n]*\s(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0):|\bssh\b[^|;&\n]*\s(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)\b/i
const ENV_DUMP_RE = /\b(?:env\b|printenv\b|export\s+-p\b)/i
const DNS_EXFIL_RE = /\$\([^)]+\)\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}|\b(?:nslookup|dig|host)\s+.*\$\(/
const CRED_FILE_PIPE_RE =
  /\b(?:cat|less|head|tail|bat)\s+[^\s|;&#]*(?:\.env\b|\.envrc\b|\.npmrc\b|\.netrc\b|\.git-credentials\b|\.aws\/credentials\b|\.ssh\/id_\w+\b|\.kube\/config\b|credentials\b|secret\b)[^|;&#]*\|/i
const CRED_STORE_RE =
  /\bsecurity\s+find-(?:generic|internet)-password\b|\bvault\s+(?:read|kv\s+get)\b|\bop\s+(?:read|item\s+get|run)\b|\baws\s+secretsmanager\b|\bkubectl\s+get\s+secret\b/i
const CRED_FILE_RE =
  /(?:^|[/\\])(?:id_rsa|id_ed25519|id_ecdsa|id_dsa|[^/\\]*\.(?:key|pem|keystore|jks|p12|pfx)|[^/\\]*(?:token|password|passwd|api[_-]?key|auth_key|secret|credential)[^/\\]*|\.npmrc|\.netrc|\.git-credentials)$/i
const CRED_DIR_PREFIXES = ["~/.ssh/", "~/.aws/", "~/.kube/", "~/.gnupg/"]

function builtinHasSecret(text: string): boolean {
  return BUILTIN_SECRET_RES.some((re) => re.test(text))
}

function hasNetworkContext(cmd: string): boolean {
  return NETWORK_CMD_RE.test(cmd) && !LOCAL_URL_RE.test(cmd) && !LOCAL_NC_HOST_RE.test(cmd) && !LOCAL_SSH_RE.test(cmd)
}

async function gitleaksScan(text: string): Promise<boolean | null> {
  return new Promise((res) => {
    const proc = execFileCb(
      "gitleaks",
      ["detect", "--pipe", "--no-banner", "-l", "warn", "--redact"],
      { timeout: 8000 },
      (err: ExecFileException | null) => {
        if (err === null) {
          res(false)
          return
        }
        if (err.code === 1) {
          res(true)
          return
        }
        if ((err as NodeJS.ErrnoException).code === "ENOENT") {
          res(null)
          return
        }
        res(null)
      },
    )
    proc.stdin?.write(text)
    proc.stdin?.end()
  })
}

async function hasSecret(text: string, deep = false): Promise<boolean> {
  if (builtinHasSecret(text)) return true
  if (deep) {
    const result = await gitleaksScan(text)
    if (result !== null) return result
  }
  return false
}

// ─────────────────────────────────────────────────────────────────────────────
// Bash command validator (from bash-command-validator.sh)
// ─────────────────────────────────────────────────────────────────────────────

const BASH_VALIDATOR_RULES: Array<[RegExp, string]> = [
  [/(?:^|[;|&(])\s*grep\b/, "Use 'rg' (ripgrep) instead of 'grep' for better performance"],
  [/^find\s+\S+\s+-name\b/, "Use 'rg --files -g pattern' instead of 'find -name'"],
  [/(?:^|[;|&(])\s*(?:[./\w]*\/)?python[0-9.]?\s/, "Use 'uv run' instead of invoking python/python3 directly"],
  [/(?<!\w)pip3?\s+(install|uninstall|download)\b/, "Use 'uv add' or 'uv run --with <pkg>' instead of pip"],
  [/(?<!uv\s+run\s+)\bpy(?:test|\.test)\b/, "Use 'uv run pytest' instead of invoking pytest directly"],
  [/\bpre-commit\s+run\b/, "Use 'prek run' instead of 'pre-commit run'"],
  [/\bgit\b.*\s+commit\b/, "Use 'git agent-commit' alias instead of 'git commit'"],
]

// ─────────────────────────────────────────────────────────────────────────────
// Helper: check if a tool exists in PATH
// ─────────────────────────────────────────────────────────────────────────────

function toolExists(name: string): boolean {
  try {
    execFileSync("which", [name], { stdio: "pipe" })
    return true
  } catch {
    return false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Extension entry point
// ─────────────────────────────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ── Session startup: tool checks ─────────────────────────────────────────
  pi.on("session_start", async (_event, ctx) => {
    const required = [
      { name: "uv", hint: "brew install uv / curl -LsSf https://astral.sh/uv/install.sh | sh" },
      { name: "jq", hint: "brew install jq" },
      { name: "perl", hint: "pre-installed on macOS" },
    ]
    const recommend = [
      {
        name: "gitleaks",
        hint: "brew install gitleaks  (secret scanning falls back to built-in patterns without it)",
      },
      { name: "rg", hint: "brew install ripgrep  (bash validator enforces rg over grep)" },
      { name: "prek", hint: "install prek (sandbox-compatible pre-commit wrapper)" },
    ]

    for (const { name, hint } of required) {
      if (!toolExists(name)) {
        ctx.ui.notify(`⛔ ${name} not found — security hooks may fail.\n  Install: ${hint}`, "error")
      }
    }
    for (const { name, hint } of recommend) {
      if (!toolExists(name)) {
        ctx.ui.notify(`⚠️  ${name} not found — reduced coverage.\n  Install: ${hint}`, "warn")
      }
    }
  })

  // ── Tool interception ─────────────────────────────────────────────────────
  pi.on("tool_call", async (event, ctx) => {
    const tool = event.toolName.toLowerCase()
    const inp = event.input as Record<string, unknown>

    const isRW = ["read", "write", "edit"].includes(tool)
    const isBash = tool === "bash"

    // ── Hook/settings tampering protection ─────────────────────────────
    if (isBash || isRW) {
      const suspect = isBash ? String(inp.command ?? "") : String(inp.file_path ?? inp.path ?? "")
      if (isProtectedPath(suspect)) {
        return {
          block: true,
          reason: `Blocked: access to agent config/security path '${suspect}'.\nHook scripts and settings files enforce safety constraints. Reading enables crafting bypasses; writing disables enforcement.`,
        }
      }
    }

    // ── Sensitive path protection (Read/Write/Edit) ───────────────────
    if (isRW) {
      const p = String(inp.file_path ?? inp.path ?? "")
      if (p && isSensitivePath(p)) {
        return {
          block: true,
          reason: `Blocked: ${tool} targeting zero-access path '${p}'.\nAccessing this path would expose credentials or private keys to context.`,
        }
      }
    }

    // ── Bash-only rules ───────────────────────────────────────────────
    if (isBash) {
      const cmd = String(inp.command ?? "")
      if (!cmd) return

      // Sensitive path writes from bash commands
      for (const target of bashWriteTargets(cmd)) {
        if (isSensitivePath(target)) {
          return { block: true, reason: `Blocked: bash command writing to sensitive path '${target}'.` }
        }
      }

      // Reverse shells (with loopback exemptions)
      for (const { re, exemption, msg } of REVERSE_SHELL_RULES) {
        if (re.test(cmd)) {
          let exempt = false
          if (exemption === "devtcp") exempt = LOOPBACK_DEVTCP_RE.test(cmd)
          else if (exemption === "nc") exempt = LOOPBACK_NC_RE.test(cmd)
          else if (exemption === "generic") exempt = LOOPBACK_RE.test(cmd)
          if (!exempt) return { block: true, reason: msg }
        }
      }

      // Pipe-to-shell
      if (PIPE_TO_SHELL_RE.test(cmd)) {
        return { block: true, reason: "Blocked: download-and-execute pipeline detected (curl/wget | shell)." }
      }

      // Obfuscated execution
      if (OBFUSCATED_RE.test(cmd)) {
        return {
          block: true,
          reason: "Blocked: obfuscated execution detected (base64 decode | shell or eval $(...)).",
        }
      }

      // Clipboard reads
      if (CLIPBOARD_RE.test(cmd)) {
        return { block: true, reason: "Blocked: clipboard read detected (pbpaste / xclip / wl-paste)." }
      }

      // Fork bomb
      if (FORK_BOMB_RE.test(cmd)) {
        return { block: true, reason: "Blocked: fork bomb pattern detected." }
      }

      // Cron injection
      if (CRON_RE.test(cmd)) {
        return { block: true, reason: "Blocked: cron injection detected." }
      }

      // SSH key manipulation
      if (SSH_KEY_MANIP_RE.test(cmd)) {
        return { block: true, reason: "Blocked: SSH authorized_keys manipulation detected." }
      }

      // Privilege escalation
      if (SUDO_RE.test(cmd) || SU_RE.test(cmd)) {
        return { block: true, reason: "Blocked: privilege escalation (sudo/su). Delegate to user." }
      }

      // macOS system interaction
      if (MACOS_SYS_RE.test(cmd)) {
        return { block: true, reason: "Blocked: macOS system interaction (osascript / defaults write)." }
      }

      // DNS exfiltration
      if (DNS_EXFIL_RE.test(cmd)) {
        return { block: true, reason: "Blocked: DNS exfiltration pattern detected." }
      }

      const networkCtx = hasNetworkContext(cmd)

      // Credential file piped to network
      if (CRED_FILE_PIPE_RE.test(cmd) && networkCtx) {
        return { block: true, reason: "Blocked: credential file piped to a network command." }
      }

      // Environment dump to network
      if (ENV_DUMP_RE.test(cmd) && networkCtx) {
        return { block: true, reason: "Blocked: environment variable dump to network detected." }
      }

      // Credential store read + network
      if (CRED_STORE_RE.test(cmd) && networkCtx) {
        return { block: true, reason: "Blocked: credential store read piped to a remote network destination." }
      }

      // Credential store read (local) → confirm
      if (CRED_STORE_RE.test(cmd)) {
        if (ctx.isInteractive) {
          const ok = await ctx.ui.confirm(
            "Credential store access",
            `This command reads from a system credential store:\n\n${cmd}\n\nApprove only if intentional.`,
          )
          if (!ok) return { block: true, reason: "Credential store access denied by user." }
        }
        // In non-interactive mode, allow but don't block (matches Python hook fail-open for Read)
        return
      }

      // Secret in command with network destination → block
      if (networkCtx && (await hasSecret(cmd, true))) {
        return { block: true, reason: "Blocked: credential detected in command with a network destination." }
      }

      // Secret in command without network → ask
      if (!networkCtx && builtinHasSecret(cmd)) {
        if (ctx.isInteractive) {
          const ok = await ctx.ui.confirm(
            "Credential pattern detected",
            `A secret pattern was found in this command:\n\n${cmd}\n\nApprove if intentional (e.g. local auth test).`,
          )
          if (!ok) return { block: true, reason: "Command with credential pattern denied by user." }
        }
        return
      }

      // Destructive ops (TOML-driven)
      for (const { re, rule } of DESTRUCTIVE_RULES) {
        if (re.test(cmd)) {
          const explanation = rule.reason ? `${rule.description}\n\n${rule.reason}` : rule.description
          if (rule.mode === "block") {
            return { block: true, reason: `Blocked: ${explanation}` }
          }
          if (rule.mode === "ask" && ctx.isInteractive) {
            const ok = await ctx.ui.confirm(rule.description, `${explanation}\n\nCommand:\n${cmd}\n\nProceed?`)
            if (!ok) return { block: true, reason: `${rule.description} — denied by user.` }
            return // approved, allow
          }
          // Non-interactive ask-mode: allow (matches Python hook fail-open)
          return
        }
      }

      // Bash validator (tooling enforcement — runs last)
      const issues: string[] = []
      for (const [re, msg] of BASH_VALIDATOR_RULES) {
        if (re.test(cmd)) issues.push(msg)
      }
      if (issues.length > 0) {
        return { block: true, reason: issues.map((m) => `• ${m}`).join("\n") }
      }
    }

    // ── Secret scan for Read/Write/Edit file paths ────────────────────
    if (isRW) {
      const p = String(inp.file_path ?? inp.path ?? "")
      if (!p) return

      // Credential directory prefixes → confirm
      const normP = expandPath(p)
      for (const dir of CRED_DIR_PREFIXES) {
        const prefix = expandPath(dir)
        if (normP.startsWith(prefix + "/") || normP === prefix) {
          if (ctx.isInteractive) {
            const ok = await ctx.ui.confirm(
              "Credential directory access",
              `This operation targets '${p}' inside a credential directory (${dir}).\nApprove only if intentional.`,
            )
            if (!ok) return { block: true, reason: `Access to credential directory '${dir}' denied by user.` }
          }
          return
        }
      }

      // Credential file name patterns → confirm
      if (CRED_FILE_RE.test(p) && !EXEMPT_DIR_RE.test(p)) {
        if (ctx.isInteractive) {
          const ok = await ctx.ui.confirm(
            "Potential credential file",
            `This operation targets '${p}', whose name suggests it may contain credentials.\nApprove only if intentional.`,
          )
          if (!ok) return { block: true, reason: `Access to potential credential file '${p}' denied by user.` }
        }
      }
    }
  })

  // ── Post-write: run pre-commit ────────────────────────────────────────────
  // Cache tool call inputs so we can correlate file paths at result time.
  const pendingInputs = new Map<string, Record<string, unknown>>()

  pi.on("tool_call", async (event) => {
    if (event.toolName === "write" || event.toolName === "edit") {
      pendingInputs.set(event.toolCallId, event.input as Record<string, unknown>)
    }
  })

  pi.on("tool_result", async (event) => {
    if (event.toolName !== "write" && event.toolName !== "edit") return
    const cachedInput = pendingInputs.get(event.toolCallId)
    pendingInputs.delete(event.toolCallId)

    const p = String(cachedInput?.file_path ?? cachedInput?.path ?? "")
    if (!p) return

    const preCommit = toolExists("prek") ? "prek" : toolExists("pre-commit") ? "pre-commit" : null
    if (!preCommit) return

    // Fire-and-forget so pre-commit doesn't block the agent loop.
    // Exit code 1 means lint findings (advisory, silent); other errors are surfaced.
    execFileCb(preCommit, ["run", "--files", p], { timeout: 30000 }, (err: ExecFileException | null) => {
      if (err && err.code !== 1) {
        console.warn(`[security] ${preCommit} failed for ${p}: ${err.message}`)
      }
    })
  })
}
