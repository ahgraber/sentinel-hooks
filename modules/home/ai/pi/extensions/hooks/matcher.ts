/** Decide whether a matcher group's `matcher` selects a tool, compared without regard to case. */

export interface CompiledMatcher {
  matches(toolName: string): boolean
  /** Set when the matcher is an invalid regular expression, which matches nothing. */
  problem?: string
}

const NAME_LIST = /^[A-Za-z0-9_\- ,|]+$/

/**
 * Compile a matcher as Claude Code reads one for a tool event.
 *
 * An empty matcher or `*` matches every tool. A matcher of letters, digits, `_`,
 * `-`, spaces, `,`, and `|` is a list of exact names separated by `|` or `,`.
 * Anything else is a regular expression found anywhere in the name. Case is
 * ignored throughout, so a matcher written for Claude Code's `Bash` selects Pi's
 * `bash`.
 */
export function compileMatcher(matcher: string): CompiledMatcher {
  if (matcher === "" || matcher === "*") {
    return { matches: () => true }
  }

  if (NAME_LIST.test(matcher)) {
    const names = new Set(
      matcher
        .toLowerCase()
        .split(/[|,]/)
        .map((name) => name.trim())
        .filter((name) => name !== ""),
    )
    return { matches: (toolName) => names.has(toolName.toLowerCase()) }
  }

  let pattern: RegExp
  try {
    pattern = new RegExp(matcher, "i")
  } catch (error) {
    return {
      matches: () => false,
      problem: `matcher ${JSON.stringify(matcher)} is not a valid regular expression, so it matches nothing: ${(error as Error).message}`,
    }
  }
  return { matches: (toolName) => pattern.test(toolName) }
}
