/** Run every matching hook for one event together and combine their outcomes. */

import { decode, type Outcome } from "./decode.ts"
import { compileMatcher } from "./matcher.ts"
import type { CommandHandler, EventName, MatcherGroup } from "./registration.ts"
import { DEFAULT_TIMEOUT_MS, runCommand } from "./runner.ts"

export type Decision = "allow" | "ask" | "block"

export interface Combined {
  decision: Decision
  /** The reasons of every hook that reached the decision; empty for an allow. */
  reasons: string[]
  /** `additionalContext` from every hook that answered; dropped when a `PreToolUse` call is blocked. */
  context: string[]
  /** Plain standard output from every allowing hook, kept on the events that read it as context. */
  text: string[]
  /** Errors and failures that did not decide the event, each naming its hook and truncated, for the user. */
  reports: string[]
}

const RANK: Record<Decision, number> = { allow: 0, ask: 1, block: 2 }

/** The events whose groups a matcher selects; on every other event the matcher is ignored. */
export const TOOL_EVENTS: ReadonlySet<EventName> = new Set(["PreToolUse", "PostToolUse", "PostToolUseFailure"])

/** Claude Code reads a hook's plain standard output as context on these events and shows it elsewhere. */
const TEXT_EVENTS: ReadonlySet<EventName> = new Set(["SessionStart", "UserPromptSubmit"])

const NAME_LENGTH = 80
const REPORT_LENGTH = 2000

const truncate = (value: string, length: number): string =>
  value.length <= length ? value : `${value.slice(0, length - 1)}…`

/** Select the handlers whose group matches `toolName`; on events without a tool, every handler. */
export function matchingHandlers(event: EventName, groups: MatcherGroup[], toolName?: string): CommandHandler[] {
  if (!TOOL_EVENTS.has(event)) return groups.flatMap((group) => group.handlers)
  return groups
    .filter((group) => compileMatcher(group.matcher).matches(toolName ?? ""))
    .flatMap((group) => group.handlers)
}

/** Name a hook by its command, truncated, since the name reaches the model in a refusal. */
export const describeHook = (handler: CommandHandler): string => `hook \`${truncate(handler.command, NAME_LENGTH)}\``

/**
 * Run `handlers` together and wait for all of them.
 *
 * On `PreToolUse` a hook that gave no answer blocks, with a reason naming it,
 * because the event exists to decide whether a call runs. On every other event
 * the same failure is reported and the event proceeds.
 */
export async function runEvent(
  event: EventName,
  handlers: CommandHandler[],
  payload: unknown,
  cwd: string,
): Promise<Combined> {
  const outcomes = await Promise.all(
    handlers.map(async (handler): Promise<[CommandHandler, Outcome]> => {
      const timeoutMs = handler.timeout === undefined ? DEFAULT_TIMEOUT_MS : handler.timeout * 1000
      const env = handler.pluginRoot === undefined ? undefined : { PLUGIN_ROOT: handler.pluginRoot }
      const result = await runCommand({ command: handler.command, cwd, payload, timeoutMs, env })
      return [handler, decode(result, timeoutMs, event)]
    }),
  )

  const combined: Combined = { decision: "allow", reasons: [], context: [], text: [], reports: [] }
  const reasonsByDecision: Record<Decision, string[]> = { allow: [], ask: [], block: [] }

  for (const [handler, outcome] of outcomes) {
    const name = describeHook(handler)
    let decision: Decision
    switch (outcome.kind) {
      case "failure":
        if (event === "PreToolUse") {
          decision = "block"
          reasonsByDecision.block.push(`${name} ${outcome.problem}, so the call is refused.`)
        } else {
          decision = "allow"
          combined.reports.push(truncate(`${name} ${outcome.problem}.`, REPORT_LENGTH))
        }
        break
      case "error":
        decision = "allow"
        combined.reports.push(truncate(`${name} reported an error: ${outcome.message}`, REPORT_LENGTH))
        break
      case "block":
        decision = "block"
        reasonsByDecision.block.push(outcome.reason)
        if (outcome.context !== undefined) combined.context.push(outcome.context)
        break
      case "ask":
        decision = "ask"
        reasonsByDecision.ask.push(outcome.reason)
        if (outcome.context !== undefined) combined.context.push(outcome.context)
        break
      case "allow":
        decision = "allow"
        if (outcome.context !== undefined) combined.context.push(outcome.context)
        if (outcome.text !== undefined && TEXT_EVENTS.has(event)) combined.text.push(outcome.text)
        break
    }
    if (RANK[decision] > RANK[combined.decision]) combined.decision = decision
  }

  combined.reasons = reasonsByDecision[combined.decision]
  // A blocked call never runs, so no result exists for its context to accompany.
  if (event === "PreToolUse" && combined.decision === "block") {
    combined.context = []
    combined.text = []
  }
  return combined
}
