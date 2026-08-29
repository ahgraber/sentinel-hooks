/** Shell lexing: the words a command names, and the paths they carry. */

/** Likely write destinations a shell command names. */
export function bashWriteTargets(command: string): string[] {
  const targets: string[] = []

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
// The lexer splits words, not shell syntax, so an operator written against its
// operand stays attached to it: `>file` and `--flag=file` arrive as one word.
const ATTACHED_OPERAND_RE = /^(?:[0-9]*(?:&?>{1,2}\|?|<{1,2}&?)|[^\s=]*=)/

/** Split a command into words the way a shell does, so a quoted path is one word. */
function shellWords(command: string): string[] {
  const words: string[] = []
  let current = ""
  let quote: string | null = null
  let started = false
  for (let i = 0; i < command.length; i += 1) {
    const c = command[i]
    if (quote) {
      if (c === quote) {
        quote = null
      } else if (c === "\\" && quote === '"' && i + 1 < command.length) {
        i += 1
        current += command[i]
      } else {
        current += c
      }
      continue
    }
    if (c === "'" || c === '"') {
      quote = c
      started = true
    } else if (c === "\\" && i + 1 < command.length) {
      i += 1
      current += command[i]
      started = true
    } else if (/\s/.test(c)) {
      if (started) words.push(current)
      current = ""
      started = false
    } else {
      current += c
      started = true
    }
  }
  if (started) words.push(current)
  return words
}

/** Each word of `command`, plus the path any word carries. */
export function pathsIn(command: string): string[] {
  const found: string[] = []
  for (const word of shellWords(command)) {
    found.push(word)
    const carried = word.replace(ATTACHED_OPERAND_RE, "")
    if (carried && carried !== word) found.push(carried)
  }
  return found
}
