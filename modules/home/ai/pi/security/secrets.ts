/** Secret detection and exfiltration context, ported from block-secrets.py. */

import { type ExecFileException, execFile as execFileCb } from "node:child_process"

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
export const ENV_DUMP_RE = /\b(?:env\b|printenv\b|export\s+-p\b)/i
export const DNS_EXFIL_RE = /\$\([^)]+\)\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}|\b(?:nslookup|dig|host)\s+.*\$\(/
export const CRED_FILE_PIPE_RE =
  /\b(?:cat|less|head|tail|bat)\s+[^\s|;&#]*(?:\.env\b|\.envrc\b|\.npmrc\b|\.netrc\b|\.git-credentials\b|\.aws\/credentials\b|\.ssh\/id_\w+\b|\.kube\/config\b|credentials\b|secret\b)[^|;&#]*\|/i
export const CRED_STORE_RE =
  /\bsecurity\s+find-(?:generic|internet)-password\b|\bvault\s+(?:read|kv\s+get)\b|\bop\s+(?:read|item\s+get|run)\b|\baws\s+secretsmanager\b|\bkubectl\s+get\s+secret\b/i
export const CREDENTIAL_FILE_RE =
  /(?:^|[/\\])(?:id_rsa|id_ed25519|id_ecdsa|id_dsa|[^/\\]*\.(?:key|pem|keystore|jks|p12|pfx)|[^/\\]*(?:token|password|passwd|api[_-]?key|auth_key|secret|credential)[^/\\]*|\.npmrc|\.netrc|\.git-credentials)$/i
export const CRED_DIR_PREFIXES = ["~/.ssh/", "~/.aws/", "~/.kube/", "~/.gnupg/"]

export function builtinHasSecret(text: string): boolean {
  return BUILTIN_SECRET_RES.some((re) => re.test(text))
}

export function hasNetworkContext(cmd: string): boolean {
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

export async function hasSecret(text: string, deep = false): Promise<boolean> {
  if (builtinHasSecret(text)) return true
  if (deep) {
    const result = await gitleaksScan(text)
    if (result !== null) return result
  }
  return false
}
