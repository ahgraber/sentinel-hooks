/** Read-gated path shapes, ported from block-sensitive-paths.py. */

import { CREDENTIAL_FILES } from "./manifest.ts"
import { spellings } from "./paths.ts"

const EXTENSION_RE = /\.(pem|key|p12|pfx|crt|cer|tfstate|tfstate\.backup)$/i
const DOTENV_RE = /(?:^|[/\\*])\.env(?:\.[^/\\]+|\*)?$/i
const ENVRC_RE = /(?:^|[/\\*])\.envrc$/i
const SSH_KEY_RE = /(?:^|[/\\])id_(?:rsa|dsa|ecdsa|ed25519)[^/\\]*$/i
const CRED_FILE_RE =
  /(?:^|[/\\])(?:\.netrc|\.npmrc|\.pypirc|\.git-credentials|service-account[^/\\]*\.json|credentials\.json)$/i
const DOCKER_CONFIG_RE = /(?:^|[/\\])\.docker[/\\]config\.json$/i
// Built from the manifest's [credentials] class, so a store added there gates both read and write.
function credentialAlternation(paths: string[]): string {
  return paths
    .map((p) =>
      p
        .replace(/^~\//, "")
        .replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
        .replace(/\//g, "[/\\\\]"),
    )
    .join("|")
}

// `(?!)` never matches, so a manifest that failed to load leaves this gate covering
// nothing; session_start reports the failure rather than letting it narrow silently.
const AGENT_CREDENTIAL_RE = new RegExp(
  CREDENTIAL_FILES.length > 0 ? `(?:^|[/\\\\])(?:${credentialAlternation(CREDENTIAL_FILES)})[^/\\\\]*$` : "(?!)",
  "i",
)
const CRED_DIR_RE = /(?:^|[/\\])\.(?:ssh|aws|kube|gnupg|azure)(?:[/\\]|$)/i
const ZERO_ACCESS_FILES = /(?:^|[/\\])\.(bash_history|zsh_history|sh_history|node_repl_history|python_history)$/i
const NAME_PATTERN_RE = /credentials|secret/i
// Must match guarded_paths.py's NAME_HEURISTIC_EXEMPT_RE; shared/tests/sensitive-path-cases.json catches drift.
export const NAME_HEURISTIC_EXEMPT_RE =
  /(?:^|[/\\])(?:\.venv|venv|site-packages|node_modules|\.claude|(?:claude|codex|copilot|shared)[/\\](?:hooks|tests))(?:[/\\]|$)/i

function isZeroAccess(p: string): boolean {
  return (
    EXTENSION_RE.test(p) ||
    DOTENV_RE.test(p) ||
    ENVRC_RE.test(p) ||
    ZERO_ACCESS_FILES.test(p) ||
    SSH_KEY_RE.test(p) ||
    CRED_FILE_RE.test(p) ||
    DOCKER_CONFIG_RE.test(p) ||
    CRED_DIR_RE.test(p) ||
    AGENT_CREDENTIAL_RE.test(p)
  )
}

function isNamedForSecrets(p: string): boolean {
  const basename = p.split(/[/\\]/).pop() ?? ""
  return NAME_PATTERN_RE.test(basename) && !NAME_HEURISTIC_EXEMPT_RE.test(p)
}

export function isSensitivePath(rawPath: string): boolean {
  if (!rawPath) return false
  return spellings(rawPath).some((p) => isZeroAccess(p) || isNamedForSecrets(p))
}
