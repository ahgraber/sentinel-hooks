/** Read command-hook registrations from `hooks.json`, in the shape of Claude Code's `hooks` setting. */

import { readFileSync } from "node:fs"
import { join } from "node:path"

export const REGISTRATION_FILE = "hooks.json"

/** The Claude Code events this extension can raise from Pi's events. */
export const EVENTS = [
  "SessionStart",
  "UserPromptSubmit",
  "PreToolUse",
  "PostToolUse",
  "PostToolUseFailure",
  "Stop",
  "SessionEnd",
] as const

export type EventName = (typeof EVENTS)[number]

/** The longest timeout Node's timers can hold, in seconds; a longer delay fires at once. */
export const MAX_TIMEOUT_SECONDS = Math.floor((2 ** 31 - 1) / 1000)

export interface CommandHandler {
  command: string
  /** Seconds; absent means the runner's default. */
  timeout?: number
}

export interface MatcherGroup {
  matcher: string
  handlers: CommandHandler[]
}

export type Registrations = Partial<Record<EventName, MatcherGroup[]>>

export type RegistrationResult =
  | { usable: true; file: string; registrations: Registrations; warnings: string[] }
  | { usable: false; file: string; problem: string }

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

/**
 * Read `hooks.json` from `directory`.
 *
 * A missing file is no registrations and no error. A file that cannot be read,
 * does not parse, or does not have the registration shape is unusable as a whole.
 * A handler of another type, or an event this extension cannot raise, is dropped
 * with a warning, and the rest of the file is kept. An event name that differs
 * from a raised event only in case was meant as that event, so it makes the file
 * unusable rather than dropping its hooks with a warning.
 */
export function readRegistrations(directory: string): RegistrationResult {
  const file = join(directory, REGISTRATION_FILE)

  let text: string
  try {
    text = readFileSync(file, "utf8")
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return { usable: true, file, registrations: {}, warnings: [] }
    }
    return { usable: false, file, problem: `cannot be read: ${(error as Error).message}` }
  }

  let data: unknown
  try {
    data = JSON.parse(text)
  } catch (error) {
    return { usable: false, file, problem: `does not parse as JSON: ${(error as Error).message}` }
  }

  if (!isObject(data) || !isObject(data.hooks)) {
    return { usable: false, file, problem: "has the wrong shape: `hooks` must be an object of event names" }
  }

  const registrations: Registrations = {}
  const warnings: string[] = []
  for (const [event, groups] of Object.entries(data.hooks)) {
    const shapeError = (detail: string): RegistrationResult => ({
      usable: false,
      file,
      problem: `has the wrong shape: ${event} ${detail}`,
    })
    if (!Array.isArray(groups)) return shapeError("must be a list of matcher groups")

    const parsed: MatcherGroup[] = []
    for (const [index, group] of groups.entries()) {
      if (!isObject(group) || !Array.isArray(group.hooks)) {
        return shapeError(`group ${index} must be an object with a \`hooks\` list`)
      }
      if (group.matcher !== undefined && typeof group.matcher !== "string") {
        return shapeError(`group ${index} has a \`matcher\` that is not a string`)
      }
      const handlers: CommandHandler[] = []
      for (const handler of group.hooks) {
        if (!isObject(handler) || typeof handler.type !== "string") {
          return shapeError(`group ${index} has a handler without a string \`type\``)
        }
        if (handler.type !== "command") {
          warnings.push(`${file}: ${event} group ${index} has a \`${handler.type}\` handler, which is skipped`)
          continue
        }
        if (typeof handler.command !== "string" || handler.command === "") {
          return shapeError(`group ${index} has a command handler without a \`command\``)
        }
        if (
          handler.timeout !== undefined &&
          (typeof handler.timeout !== "number" || !(handler.timeout > 0) || handler.timeout > MAX_TIMEOUT_SECONDS)
        ) {
          return shapeError(
            `group ${index} has a \`timeout\` that is not a number of seconds between 0 and ${MAX_TIMEOUT_SECONDS}`,
          )
        }
        handlers.push({ command: handler.command, timeout: handler.timeout as number | undefined })
      }
      parsed.push({ matcher: (group.matcher as string | undefined) ?? "", handlers })
    }

    // Groups are validated before the event name is checked, so a malformed entry
    // under a skipped event still makes the file unusable: the file is malformed
    // whichever events it names.
    if (!(EVENTS as readonly string[]).includes(event)) {
      const intended = EVENTS.find((known) => known.toLowerCase() === event.toLowerCase())
      if (intended !== undefined) return shapeError(`differs from ${intended} only in case`)
      warnings.push(`${file}: ${event} is not an event this extension raises, so its hooks are skipped`)
      continue
    }
    registrations[event as EventName] = parsed
  }

  return { usable: true, file, registrations, warnings }
}
