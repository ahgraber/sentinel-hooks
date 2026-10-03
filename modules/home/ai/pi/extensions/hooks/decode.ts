/** Turn a hook's exit status and output into an outcome, following Claude Code's hook contract. */

import { constants } from "node:os"

import type { EventName } from "./registration.ts"
import type { RunResult } from "./runner.ts"

export type Outcome =
  /** `text` is plain standard output; `context` is `additionalContext` from a JSON reply. */
  | { kind: "allow"; text?: string; context?: string }
  | { kind: "ask"; reason: string; context?: string }
  | { kind: "block"; reason: string; context?: string }
  /** A non-blocking error: the event proceeds and `message` is reported. */
  | { kind: "error"; message: string }
  /** The hook gave no answer: it timed out, did not start, died on a signal, or wrote a broken reply. */
  | { kind: "failure"; problem: string }

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

const text = (value: unknown): string | undefined => (typeof value === "string" && value !== "" ? value : undefined)

const SIGNAL_NAMES = new Map(Object.entries(constants.signals).map(([name, number]) => [number, name]))

/**
 * Decode one hook run.
 *
 * `/bin/sh` exits 127 for a command it cannot find and 126 for one it cannot
 * execute, so those two statuses are failures to start rather than a hook's own
 * non-blocking error. It exits 128 plus the signal number when a command inside
 * the hook is ended by a signal, so 129 through 159 count as the hook being ended
 * by one.
 *
 * A JSON reply is read on every exit status, as Claude Code reads it. Exit 2
 * blocks whatever the reply says and takes its reason from the reply's blocking
 * decision, or from standard error. On any other status the reply decides.
 * `permissionDecision` is read on `PreToolUse` alone, as Claude Code reads it, so a
 * reply on another event cannot ask or deny through it.
 */
export function decode(result: RunResult, timeoutMs: number, event: EventName): Outcome {
  if (result.startError !== undefined) return { kind: "failure", problem: `could not start: ${result.startError}` }
  if (result.timedOut) return { kind: "failure", problem: `did not finish within ${timeoutMs / 1000} seconds` }
  if (result.signal !== null) return { kind: "failure", problem: `was ended by ${result.signal}` }
  const status = result.exitCode ?? 0
  if (status === 126 || status === 127) {
    const detail = result.stderr.trim()
    return { kind: "failure", problem: `could not start (exit ${status})${detail ? `: ${detail}` : ""}` }
  }
  if (status > 128 && status < 160) {
    const name = SIGNAL_NAMES.get(status - 128) ?? `signal ${status - 128}`
    return { kind: "failure", problem: `was ended by ${name} (exit ${status})` }
  }

  const stderr = result.stderr.trim()
  const output = result.stdout.trim()
  let reply: Record<string, unknown> | undefined
  if (output.startsWith("{")) {
    try {
      // Text that starts with `{` and parses is always an object.
      reply = JSON.parse(output)
    } catch (error) {
      if (status !== 2) {
        return { kind: "failure", problem: `wrote a JSON reply that does not parse: ${(error as Error).message}` }
      }
    }
  }

  if (reply === undefined) {
    if (status === 2) return { kind: "block", reason: stderr || "the hook exited 2 without a reason" }
    if (status !== 0) return { kind: "error", message: stderr || `the hook exited ${status}` }
    return output === "" ? { kind: "allow" } : { kind: "allow", text: output }
  }

  const outcome = fromReply(reply, event)
  if (status !== 2) return outcome
  return outcome.kind === "block" ? outcome : { kind: "block", reason: stderr || "the hook exited 2 without a reason" }
}

/** Read the decision a JSON reply carries. */
function fromReply(reply: Record<string, unknown>, event: EventName): Outcome {
  const specific = isObject(reply.hookSpecificOutput) ? reply.hookSpecificOutput : {}
  const context = text(specific.additionalContext)
  const decision = event === "PreToolUse" ? specific.permissionDecision : undefined
  const decisionReason = text(specific.permissionDecisionReason)

  if (decision === "deny") {
    return { kind: "block", reason: decisionReason ?? "the hook denied the call without a reason", context }
  }
  if (decision === "ask") return { kind: "ask", reason: decisionReason ?? "the hook asks for approval", context }
  if (decision !== undefined && decision !== "allow") {
    return { kind: "failure", problem: `wrote an unknown permissionDecision ${JSON.stringify(decision)}` }
  }
  if (reply.decision === "block") {
    return { kind: "block", reason: text(reply.reason) ?? "the hook blocked without a reason", context }
  }
  return context === undefined ? { kind: "allow" } : { kind: "allow", context }
}
