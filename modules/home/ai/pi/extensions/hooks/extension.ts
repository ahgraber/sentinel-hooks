/** Run command hooks registered in `hooks.json` on Pi's events, with Claude Code's hook contract. */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent"
import { type Combined, matchingHandlers, runEvent, TOOL_EVENTS } from "./combine.ts"
import { compileMatcher } from "./matcher.ts"
import { type EventName, type Registrations, readRegistrations } from "./registration.ts"

export interface HooksOptions {
  /** Pi's agent directory, which holds `hooks.json`. */
  agentDir: () => string
}

const STATUS_KEY = "hooks"
const ASK_SUMMARY_LENGTH = 300
const MESSAGE_TYPE = "hooks"

const SESSION_START_SOURCE: Record<string, string> = {
  startup: "startup",
  new: "clear",
  resume: "resume",
  fork: "fork",
}

const SESSION_END_REASON: Record<string, string> = {
  quit: "prompt_input_exit",
  new: "clear",
  resume: "resume",
}

type Level = "info" | "warning" | "error"

/** Show a message to the user, or write it to standard error when Pi has no UI. */
function report(ctx: ExtensionContext, message: string, level: Level): void {
  if (ctx.hasUI) ctx.ui.notify(message, level)
  else process.stderr.write(`pi hooks: ${message}\n`)
}

function commonFields(ctx: ExtensionContext, event: EventName): Record<string, unknown> {
  return { session_id: ctx.sessionManager.getSessionId(), cwd: ctx.cwd, hook_event_name: event }
}

const truncate = (value: string, length: number): string =>
  value.length <= length ? value : `${value.slice(0, length - 1)}…`

const textOf = (content: unknown): string =>
  Array.isArray(content)
    ? content
        .filter((part) => part?.type === "text" && typeof part.text === "string")
        .map((part) => part.text)
        .join("\n")
    : ""

export function registerHooks(pi: ExtensionAPI, options: HooksOptions): void {
  let registrations: Registrations = {}
  /** Context from `SessionStart` and `UserPromptSubmit`, returned by the next `before_agent_start`. */
  let promptContext: string[] = []
  /** `PreToolUse` context, keyed by tool call, returned with that call's result. */
  const toolContext = new Map<string, string[]>()
  /** True while the running turn was started by a `Stop` hook's block. */
  let stopHookActive = false
  /** How the latest agent run ended, from its last assistant message. */
  let lastStopReason: string | undefined
  /** The session and reason of the last `session_start` handled, until a `session_shutdown`. */
  let lastStart: string | undefined

  async function run(ctx: ExtensionContext, event: EventName, fields: Record<string, unknown>, toolName?: string) {
    const handlers = matchingHandlers(event, registrations[event] ?? [], toolName)
    if (handlers.length === 0) return undefined
    const combined = await runEvent(event, handlers, { ...commonFields(ctx, event), ...fields }, ctx.cwd)
    for (const message of combined.reports) report(ctx, message, "warning")
    return combined
  }

  const holdForPrompt = (combined: Combined) => promptContext.push(...combined.text, ...combined.context)

  pi.on("session_start", async (event, ctx) => {
    // Pi 0.86.1 raises `session_start` twice when a session is replaced, with the same
    // session ID and reason; a repeat is not a new start, so its hooks do not run again.
    const start = `${ctx.sessionManager.getSessionId()} ${event.reason}`
    if (start === lastStart) return
    lastStart = start

    const result = readRegistrations(options.agentDir())
    if (result.usable) {
      registrations = result.registrations
      for (const warning of result.warnings) report(ctx, warning, "warning")
      // An invalid matcher silences only its own group, so the other hooks keep running,
      // and the report stays in view because that group may hold a guard.
      let invalidMatchers = 0
      for (const [event, groups] of Object.entries(registrations)) {
        if (!TOOL_EVENTS.has(event as EventName)) continue
        for (const group of groups ?? []) {
          const problem = compileMatcher(group.matcher).problem
          if (problem === undefined) continue
          invalidMatchers += 1
          report(ctx, `${result.file}: ${problem}. Its hooks do not run in this session.`, "error")
        }
      }
      if (ctx.hasUI) {
        const status =
          invalidMatchers > 0 ? `hooks.json: ${invalidMatchers} invalid matcher(s), their hooks do not run` : undefined
        ctx.ui.setStatus(STATUS_KEY, status)
      }
    } else {
      registrations = {}
      report(ctx, `${result.file} ${result.problem}. No hooks run in this session.`, "error")
      if (ctx.hasUI) ctx.ui.setStatus(STATUS_KEY, "hooks.json unusable: no hooks run")
    }

    // A reload rebinds the runtime; the session neither starts nor ends.
    if (event.reason === "reload") return
    const combined = await run(ctx, "SessionStart", { source: SESSION_START_SOURCE[event.reason] ?? event.reason })
    if (combined === undefined) return
    // A session cannot be refused once it has started, so a block reaches the user
    // and the session continues.
    if (combined.decision === "block") for (const reason of combined.reasons) report(ctx, reason, "error")
    holdForPrompt(combined)
  })

  pi.on("session_shutdown", async (event, ctx) => {
    lastStart = undefined
    if (event.reason === "reload") return
    await run(ctx, "SessionEnd", { reason: SESSION_END_REASON[event.reason] ?? "other" })
  })

  pi.on("input", async (event, ctx) => {
    // A message an extension sends, such as a `Stop` continuation, is not the user's prompt.
    if (event.source === "extension") return undefined
    stopHookActive = false

    const combined = await run(ctx, "UserPromptSubmit", { prompt: event.text })
    if (combined === undefined) return undefined
    if (combined.decision === "block") {
      report(ctx, `The prompt was blocked by a hook: ${combined.reasons.join("\n")}`, "warning")
      return { action: "handled" }
    }
    // A prompt typed while the agent runs is queued and raises no `before_agent_start`,
    // so its context is queued beside it rather than held for a later prompt.
    if (event.streamingBehavior !== undefined) {
      const content = [...combined.text, ...combined.context].join("\n\n")
      if (content !== "") {
        pi.sendMessage({ customType: MESSAGE_TYPE, content, display: true }, { deliverAs: event.streamingBehavior })
      }
      return undefined
    }
    holdForPrompt(combined)
    return undefined
  })

  pi.on("before_agent_start", async () => {
    if (promptContext.length === 0) return undefined
    const content = promptContext.join("\n\n")
    promptContext = []
    return { message: { customType: MESSAGE_TYPE, content, display: true } }
  })

  pi.on("tool_call", async (event, ctx) => {
    const combined = await run(
      ctx,
      "PreToolUse",
      { tool_name: event.toolName, tool_input: event.input, tool_use_id: event.toolCallId },
      event.toolName,
    )
    if (combined === undefined) return undefined

    const reason = combined.reasons.join("\n")
    if (combined.decision === "block") return { block: true, reason }
    if (combined.decision === "ask") {
      if (!ctx.hasUI) return { block: true, reason }
      const summary = truncate(JSON.stringify(event.input), ASK_SUMMARY_LENGTH)
      const approved = await ctx.ui.confirm(`A hook asks before ${event.toolName} runs`, `${reason}\n\n${summary}`)
      if (!approved) return { block: true, reason: `The user declined this call. The hook asked: ${reason}` }
    }
    if (combined.context.length > 0) toolContext.set(event.toolCallId, combined.context)
    return undefined
  })

  pi.on("tool_result", async (event, ctx) => {
    const feedback = toolContext.get(event.toolCallId) ?? []
    toolContext.delete(event.toolCallId)

    const hookEvent: EventName = event.isError ? "PostToolUseFailure" : "PostToolUse"
    const result = event.isError
      ? { error: textOf(event.content) }
      : { tool_response: { content: event.content, details: event.details } }
    const combined = await run(
      ctx,
      hookEvent,
      { tool_name: event.toolName, tool_input: event.input, tool_use_id: event.toolCallId, ...result },
      event.toolName,
    )
    if (combined !== undefined) {
      if (combined.decision === "block") feedback.push(...combined.reasons)
      feedback.push(...combined.context)
    }

    if (feedback.length === 0) return undefined
    return { content: [...event.content, { type: "text", text: feedback.join("\n\n") }] }
  })

  pi.on("agent_end", async (event) => {
    const assistant = event.messages.findLast((message) => message.role === "assistant")
    lastStopReason = assistant?.stopReason
  })

  pi.on("agent_settled", async (_event, ctx) => {
    // A call that another extension blocked, or that was aborted, raises no `tool_result`.
    toolContext.clear()
    // The user interrupted the agent or the model call failed; a continuation would
    // undo the interruption or repeat the failing call.
    if (lastStopReason === "aborted" || lastStopReason === "error") {
      stopHookActive = false
      return
    }
    const combined = await run(ctx, "Stop", { stop_hook_active: stopHookActive })
    // The next turn was started by a `Stop` block only if this run blocked; any other
    // turn, including one another extension starts, sees the flag false.
    stopHookActive = combined?.decision === "block"
    if (combined?.decision !== "block") return
    pi.sendMessage(
      { customType: MESSAGE_TYPE, content: combined.reasons.join("\n"), display: true },
      { triggerTurn: true },
    )
  })
}
