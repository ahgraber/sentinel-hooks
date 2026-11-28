/** Read command-hook registrations from `hooks.json`, in the shape of Claude Code's `hooks` setting. */

import { isUtf8 } from "node:buffer"
import { readFileSync } from "node:fs"
import { join } from "node:path"

import { parseJson } from "./json.ts"

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
  /** The plugin directory, for a hook the package registers; the hook runs with it as `PLUGIN_ROOT`. */
  pluginRoot?: string
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

/** Matches, from `lastIndex`, the colon that makes the string before it a name. */
const NAME_END = /\s*:/y

/**
 * Return a name that one object in `text` holds twice, with the line of its second copy, or `undefined`.
 * `text` must be valid JSON.
 *
 * `JSON.parse` keeps only the last value of a repeated name, so the hooks under the first copy
 * would never run and nothing would say so.
 */
function repeatedName(text: string): { name: string; line: number } | undefined {
  // One entry per open object or array: the names an object holds so far, or `null` for an array.
  const open: (Set<string> | null)[] = []
  for (let index = 0; index < text.length; index++) {
    const character = text[index]
    if (character === "{") open.push(new Set())
    else if (character === "[") open.push(null)
    else if (character === "}" || character === "]") open.pop()
    else if (character === '"') {
      const start = index
      for (index++; text[index] !== '"'; index++) if (text[index] === "\\") index++
      const names = open.at(-1)
      NAME_END.lastIndex = index + 1
      if (names && NAME_END.test(text)) {
        const name = parseJson(text.slice(start, index + 1)) as string
        if (names.has(name)) return { name, line: text.slice(0, start).split(/\r\n?|\n/).length }
        names.add(name)
      }
    }
  }
  return undefined
}

/**
 * Read `hooks.json` from `directory`.
 *
 * A missing file is unusable when `required`, and otherwise no registrations and
 * no error. A file that cannot be read, is not valid UTF-8,
 * does not parse under the rule `parseJson` applies, names one key twice in an object, or does not have the registration
 * shape is unusable as a whole.
 * Event names and handler types are compared without regard to case, as matchers
 * compare tool names, and the groups of names that differ only in case are kept
 * together in file order. A handler of another type, or an event this extension
 * cannot raise, is dropped with a warning, and the rest of the file is kept.
 */
export function readRegistrations(directory: string, required = false): RegistrationResult {
  const file = join(directory, REGISTRATION_FILE)

  let bytes: Buffer
  try {
    bytes = readFileSync(file)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return required
        ? { usable: false, file, problem: "is missing" }
        : { usable: true, file, registrations: {}, warnings: [] }
    }
    return { usable: false, file, problem: `cannot be read: ${(error as Error).message}` }
  }

  if (!isUtf8(bytes)) return { usable: false, file, problem: "is not valid UTF-8" }
  const text = bytes.toString("utf8")
  let data: unknown
  try {
    data = parseJson(text)
  } catch (error) {
    return { usable: false, file, problem: `does not parse as JSON: ${(error as Error).message}` }
  }
  const repeated = repeatedName(text)
  if (repeated !== undefined) {
    return {
      usable: false,
      file,
      problem: `names ${JSON.stringify(repeated.name)} twice in one object, the second time on line ${repeated.line}, so one copy would be lost`,
    }
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
        if (handler.type.toLowerCase() !== "command") {
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
    const known = EVENTS.find((name) => name.toLowerCase() === event.toLowerCase())
    if (known === undefined) {
      warnings.push(`${file}: ${event} is not an event this extension raises, so its hooks are skipped`)
      continue
    }
    registrations[known] = [...(registrations[known] ?? []), ...parsed]
  }

  return { usable: true, file, registrations, warnings }
}
