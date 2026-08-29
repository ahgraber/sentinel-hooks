/** Pi security extension — port of the shared hook scripts into Pi's extension API. */

import { join } from "node:path"
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent"
import { BASH_VALIDATOR_RULES } from "./bash-validator.ts"
import {
  CLIPBOARD_RE,
  CRON_RE,
  FORK_BOMB_RE,
  LOOPBACK_DEVTCP_RE,
  LOOPBACK_NC_RE,
  LOOPBACK_RE,
  MACOS_SYS_RE,
  OBFUSCATED_RE,
  PIPE_TO_SHELL_RE,
  REVERSE_SHELL_RULES,
  SSH_KEY_MANIP_RE,
  SU_RE,
  SUDO_RE,
} from "./dangerous-bash.ts"
import { DESTRUCTIVE_RULES } from "./destructive-ops.ts"
import {
  commandMentionsCredential,
  commandMentionsProtectedPath,
  isCredentialPath,
  isProtectedPath,
  onlyInstructionMarkdown,
} from "./guarded-paths.ts"
import { GUARDED_MANIFEST_ERROR } from "./manifest.ts"
import { expandPath } from "./paths.ts"
import { changedFiles, gitRoot, hasPrecommitConfig, runPrecommit, toolExists } from "./precommit.ts"
import {
  builtinHasSecret,
  CRED_DIR_PREFIXES,
  CRED_FILE_PIPE_RE,
  CRED_STORE_RE,
  CREDENTIAL_FILE_RE,
  DNS_EXFIL_RE,
  ENV_DUMP_RE,
  hasNetworkContext,
  hasSecret,
} from "./secrets.ts"
import { isSensitivePath, NAME_HEURISTIC_EXEMPT_RE } from "./sensitive-paths.ts"
import { bashWriteTargets, pathsIn } from "./shell-words.ts"

// The entry module carries the extension's public surface: the cross-language verdict
// tables in shared/tests reach these through it.
export { commandMentionsProtectedPath, isProtectedPath } from "./guarded-paths.ts"
export { FOLDS_CASE } from "./paths.ts"
export { isSensitivePath } from "./sensitive-paths.ts"

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (_event, ctx) => {
    // A failed manifest load leaves every declaration empty, so tamper protection and
    // credential-path detection have nothing to check against. Proceeding anyway matches
    // the Python hooks; doing so silently does not, hence this one-time notice.
    if (GUARDED_MANIFEST_ERROR) {
      ctx.ui.notify(
        `⛔ guarded-paths.toml could not be loaded: ${GUARDED_MANIFEST_ERROR}\n  Tamper protection and credential-path detection are unchecked this session.`,
        "error",
      )
    }

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
      { name: "rg", hint: "brew install ripgrep" },
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

  pi.on("tool_call", async (event, ctx) => {
    const tool = event.toolName.toLowerCase()
    const inp = event.input as Record<string, unknown>

    const isRW = ["read", "write", "edit"].includes(tool)
    const isMutation = ["write", "edit"].includes(tool)
    const isBash = tool === "bash"

    // Reads pass; writes are gated by protected class (credential=refuse, gated=ask).
    const tamperTarget = (() => {
      if (isBash) {
        const command = String(inp.command ?? "")
        if (!command || !commandMentionsProtectedPath(command)) return null
        return onlyInstructionMarkdown(pathsIn(command)) ? null : command
      }
      if (!isMutation) return null
      const path = String(inp.file_path ?? inp.path ?? "")
      return isProtectedPath(path) ? path : null
    })()
    if (tamperTarget) {
      const credential = isBash ? commandMentionsCredential(tamperTarget) : isCredentialPath(tamperTarget)
      if (credential) {
        return {
          block: true,
          reason: `Blocked: ${tool} targeting stored agent credentials '${tamperTarget}'.\nNo legitimate flow maintains agent authentication material in-session, so no approval can permit this write.`,
        }
      }
      if (!ctx.hasUI) {
        return {
          block: true,
          reason: `Blocked: ${tool} targeting agent enforcement path '${tamperTarget}'.\nHook scripts, rules, permissions, and settings constrain what an agent may do. Changing one requires the user's in-the-moment approval, and no interactive user is attached, so the mutation is refused.`,
        }
      }
      const approved = await ctx.ui.confirm(
        "Modify agent enforcement?",
        `This ${tool} call would modify '${tamperTarget}', which is enforcement: hook scripts, permission rules, hook registrations, and agent settings constrain what an agent may do. Approving lets this one change land in a live guardrail, and the constraint it implements changes with it. Approve only if you are deliberately changing this guardrail now.`,
      )
      if (!approved) {
        return {
          block: true,
          reason: `Blocked: the user declined the mutation of agent enforcement path '${tamperTarget}'.`,
        }
      }
    }

    if (isRW) {
      const p = String(inp.file_path ?? inp.path ?? "")
      if (p && isSensitivePath(p)) {
        return {
          block: true,
          reason: `Blocked: ${tool} targeting zero-access path '${p}'.\nAccessing this path would expose credentials or private keys to context.`,
        }
      }
    }

    if (isBash) {
      const cmd = String(inp.command ?? "")
      if (!cmd) return

      for (const target of bashWriteTargets(cmd)) {
        if (isSensitivePath(target)) {
          return { block: true, reason: `Blocked: bash command writing to sensitive path '${target}'.` }
        }
      }

      for (const { re, exemption, msg } of REVERSE_SHELL_RULES) {
        if (re.test(cmd)) {
          let exempt = false
          if (exemption === "devtcp") exempt = LOOPBACK_DEVTCP_RE.test(cmd)
          else if (exemption === "nc") exempt = LOOPBACK_NC_RE.test(cmd)
          else if (exemption === "generic") exempt = LOOPBACK_RE.test(cmd)
          if (!exempt) return { block: true, reason: msg }
        }
      }

      if (PIPE_TO_SHELL_RE.test(cmd)) {
        return { block: true, reason: "Blocked: download-and-execute pipeline detected (curl/wget | shell)." }
      }

      if (OBFUSCATED_RE.test(cmd)) {
        return {
          block: true,
          reason: "Blocked: obfuscated execution detected (base64 decode | shell or eval $(...)).",
        }
      }

      if (CLIPBOARD_RE.test(cmd)) {
        return { block: true, reason: "Blocked: clipboard read detected (pbpaste / xclip / wl-paste)." }
      }

      if (FORK_BOMB_RE.test(cmd)) {
        return { block: true, reason: "Blocked: fork bomb pattern detected." }
      }

      if (CRON_RE.test(cmd)) {
        return { block: true, reason: "Blocked: cron injection detected." }
      }

      if (SSH_KEY_MANIP_RE.test(cmd)) {
        return { block: true, reason: "Blocked: SSH authorized_keys manipulation detected." }
      }

      if (SUDO_RE.test(cmd) || SU_RE.test(cmd)) {
        return { block: true, reason: "Blocked: privilege escalation (sudo/su). Delegate to user." }
      }

      if (MACOS_SYS_RE.test(cmd)) {
        return { block: true, reason: "Blocked: macOS system interaction (osascript / defaults write)." }
      }

      if (DNS_EXFIL_RE.test(cmd)) {
        return { block: true, reason: "Blocked: DNS exfiltration pattern detected." }
      }

      const networkCtx = hasNetworkContext(cmd)

      if (CRED_FILE_PIPE_RE.test(cmd) && networkCtx) {
        return { block: true, reason: "Blocked: credential file piped to a network command." }
      }

      if (ENV_DUMP_RE.test(cmd) && networkCtx) {
        return { block: true, reason: "Blocked: environment variable dump to network detected." }
      }

      if (CRED_STORE_RE.test(cmd) && networkCtx) {
        return { block: true, reason: "Blocked: credential store read piped to a remote network destination." }
      }

      if (CRED_STORE_RE.test(cmd)) {
        if (!ctx.hasUI) {
          return {
            block: true,
            reason: "Blocked: credential store access requires interactive confirmation.",
          }
        }
        const ok = await ctx.ui.confirm(
          "Credential store access",
          `This command reads from a system credential store:\n\n${cmd}\n\nApprove only if intentional.`,
        )
        if (!ok) return { block: true, reason: "Credential store access denied by user." }
        return
      }

      if (networkCtx && (await hasSecret(cmd, true))) {
        return { block: true, reason: "Blocked: credential detected in command with a network destination." }
      }

      if (!networkCtx && builtinHasSecret(cmd)) {
        if (!ctx.hasUI) {
          return {
            block: true,
            reason: "Blocked: command with credential pattern requires interactive confirmation.",
          }
        }
        const ok = await ctx.ui.confirm(
          "Credential pattern detected",
          `A secret pattern was found in this command:\n\n${cmd}\n\nApprove if intentional (e.g. local auth test).`,
        )
        if (!ok) return { block: true, reason: "Command with credential pattern denied by user." }
        return
      }

      for (const { re, rule } of DESTRUCTIVE_RULES) {
        if (re.test(cmd)) {
          const explanation = rule.reason ? `${rule.description}\n\n${rule.reason}` : rule.description
          if (rule.mode === "block") {
            return { block: true, reason: `Blocked: ${explanation}` }
          }
          if (rule.mode === "ask" && !ctx.hasUI) {
            return {
              block: true,
              reason: `${rule.description} requires interactive confirmation.\n\n${rule.reason ?? ""}`.trim(),
            }
          }
          if (rule.mode === "ask") {
            const ok = await ctx.ui.confirm(rule.description, `${explanation}\n\nCommand:\n${cmd}\n\nProceed?`)
            if (!ok) return { block: true, reason: `${rule.description} — denied by user.` }
            return
          }
          return
        }
      }

      const issues: string[] = []
      for (const [re, msg] of BASH_VALIDATOR_RULES) {
        if (re.test(cmd)) issues.push(msg)
      }
      if (issues.length > 0) {
        return { block: true, reason: issues.map((m) => `• ${m}`).join("\n") }
      }
    }

    if (isRW) {
      const p = String(inp.file_path ?? inp.path ?? "")
      if (!p) return

      const normP = expandPath(p)
      for (const dir of CRED_DIR_PREFIXES) {
        const prefix = expandPath(dir)
        if (normP.startsWith(`${prefix}/`) || normP === prefix) {
          if (!ctx.hasUI) {
            return {
              block: true,
              reason: `Blocked: access to credential directory '${dir}' requires interactive confirmation.`,
            }
          }
          const ok = await ctx.ui.confirm(
            "Credential directory access",
            `This operation targets '${p}' inside a credential directory (${dir}).\nApprove only if intentional.`,
          )
          if (!ok) return { block: true, reason: `Access to credential directory '${dir}' denied by user.` }
          return
        }
      }

      if (CREDENTIAL_FILE_RE.test(p) && !NAME_HEURISTIC_EXEMPT_RE.test(p)) {
        if (!ctx.hasUI) {
          return {
            block: true,
            reason: `Blocked: access to potential credential file '${p}' requires interactive confirmation.`,
          }
        }
        const ok = await ctx.ui.confirm(
          "Potential credential file",
          `This operation targets '${p}', whose name suggests it may contain credentials.\nApprove only if intentional.`,
        )
        if (!ok) return { block: true, reason: `Access to potential credential file '${p}' denied by user.` }
      }
    }
  })

  // `agent_settled` is the Stop-hook analogue: it fires only once Pi will not continue
  // on its own. `turn_end` fires per LLM response, which reintroduces the mid-sequence
  // autofix race (a fixer strips a just-added import before its first use lands) and
  // misses files written by bash rather than by the write/edit tools.
  let reportedThisStreak = false

  pi.on("message_start", async (event) => {
    // A fresh user prompt starts a new streak, so the next settle may report again.
    if (event.message.role === "user") reportedThisStreak = false
  })

  pi.on("agent_settled", async (_event, ctx) => {
    // Injecting below settles Pi again; this caps it at one round, as `stop_hook_active`
    // does for the other agents.
    if (reportedThisStreak) return

    const runner = toolExists("prek") ? "prek" : toolExists("pre-commit") ? "pre-commit" : null
    if (!runner) return

    const root = gitRoot(ctx.cwd)
    if (!root || !hasPrecommitConfig(root)) return

    const files = changedFiles(root)
    if (files.length === 0) return

    const output = await runPrecommit(runner, root, files)
    if (output === null) return

    reportedThisStreak = true
    pi.sendMessage(
      {
        customType: "security-precommit",
        content: `${runner} failed on the changed files. Fix the reported problems before finishing; hooks that rewrote files have already applied their changes, so re-read those files rather than trusting your in-context copy.\n\n${output}`,
        display: true,
      },
      { deliverAs: "followUp", triggerTurn: true },
    )
  })
}
