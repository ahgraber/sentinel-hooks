/** Path canonicalization shared by the path-judging modules; mirrors guarded_paths.py. */

import { existsSync, lstatSync, readlinkSync, realpathSync, statSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join, normalize, resolve } from "node:path"

export function expandPath(p: string): string {
  return normalize(p.replace(/^~/, homedir()))
}

// realpathSync gives up on a path whose leaf does not exist yet, but a write creates
// what is missing, so resolve to the longest existing ancestor with the rest appended.
// Matches Python's os.path.realpath, and keeps a path under a link to a guarded
// directory guarded.
export function resolveLinks(p: string): string {
  const missing: string[] = []
  let current = resolve(p)
  for (let step = 0; step < 64; step += 1) {
    try {
      return join(realpathSync(current), ...missing)
    } catch {
      // Not there. It may still be a link the caller wrote by hand.
    }
    try {
      current = resolve(dirname(current), readlinkSync(current))
      continue
    } catch {
      // Not a link either, so walk up.
    }
    const parent = dirname(current)
    if (parent === current) break
    missing.unshift(current.slice(parent.length + 1))
    current = parent
  }
  return join(current, ...missing)
}

/** Every form a path must be judged in: as written, expanded, and resolved. */
export function spellings(rawPath: string): string[] {
  const expanded = expandPath(rawPath)
  return [rawPath, expanded, resolveLinks(expanded)]
}

const swapCase = (name: string) =>
  name.replace(/\p{L}/gu, (c) => (c === c.toLowerCase() ? c.toUpperCase() : c.toLowerCase()))

/** True where the filesystem holding `p` treats two spellings differing only in case as one file. */
function foldsCase(p: string): boolean {
  let current = resolve(p)
  for (;;) {
    const parent = dirname(current)
    const name = current.slice(parent.length + 1)
    if (!name || parent === current) return false
    const swapped = swapCase(name)
    if (swapped !== name && existsSync(current)) {
      try {
        const here = statSync(current)
        const there = statSync(join(parent, swapped))
        return here.dev === there.dev && here.ino === there.ino
      } catch {
        return false
      }
    }
    current = parent
  }
}

// Probed, not assumed: case folding is a property of the volume, not the OS. Default
// macOS folds; a case-sensitive volume on the same machine does not.
export const FOLDS_CASE = foldsCase(homedir())

/** Put text in the form comparisons are made in. */
export function normalizeForMatch(text: string): string {
  const forward = text.replace(/\\/g, "/")
  return FOLDS_CASE ? forward.toLowerCase() : forward
}
/** Python `fnmatch.fnmatchcase` as a regular expression: `*` crosses `/`, `?` is one character. */
export function globToRegExp(pattern: string): RegExp {
  let source = ""
  for (let i = 0; i < pattern.length; i += 1) {
    const c = pattern[i]
    if (c === "*") {
      source += "[\\s\\S]*"
    } else if (c === "?") {
      source += "[\\s\\S]"
    } else if (c === "[") {
      const close = pattern.indexOf("]", i + 1)
      if (close === -1) {
        source += "\\["
      } else {
        const body = pattern.slice(i + 1, close).replace(/\\/g, "\\\\")
        source += `[${body.startsWith("!") ? `^${body.slice(1)}` : body}]`
        i = close
      }
    } else {
      source += c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    }
  }
  return new RegExp(`^${source}$`)
}
const REPO_ROOT_CACHE = new Map<string, string | null>()

/** The repository holding `p`, or null. A worktree's `.git` is a file, not a directory. */
export function repositoryRootOf(p: string): string | null {
  const cached = REPO_ROOT_CACHE.get(p)
  if (cached !== undefined) return cached

  let current = p
  try {
    if (!statSync(p).isDirectory()) current = dirname(p)
  } catch {
    current = dirname(p)
  }
  let found: string | null = null
  for (;;) {
    try {
      lstatSync(join(current, ".git"))
      found = current
      break
    } catch {
      // Not a repository root. Keep walking.
    }
    const parent = dirname(current)
    if (parent === current) break
    current = parent
  }
  REPO_ROOT_CACHE.set(p, found)
  return found
}
