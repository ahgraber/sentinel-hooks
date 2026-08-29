/** Tamper-protected locations, ported from guarded_paths.py. */

import { homedir } from "node:os"
import { isAbsolute, relative } from "node:path"
import { CREDENTIAL_FILES, GUARDED_FILES, INSTRUCTION_LAYERS, LOCATION_ONLY } from "./manifest.ts"
import { expandPath, globToRegExp, normalizeForMatch, repositoryRootOf, resolveLinks, spellings } from "./paths.ts"
import { pathsIn } from "./shell-words.ts"

/** The trailing portion of a declaration that identifies it in arbitrary text. */
function declarationFragment(declaration: string): string {
  const star = declaration.lastIndexOf("*")
  if (star !== -1) return declaration.slice(star + 1).replace(/^\/+/, "")
  for (const prefix of ["~/", "<repo>/"]) {
    if (declaration.startsWith(prefix)) return declaration.slice(prefix.length)
  }
  return declaration
}

/** The glob patterns a declaration's relative part matches; a trailing `/` also covers what is below. */
function declarationPatterns(relative: string): string[] {
  if (relative.endsWith("/")) {
    const base = relative.replace(/\/+$/, "")
    return [base, `${base}/*`]
  }
  return [relative]
}

/** Port of guarded_paths.py's GuardedLocations; shared verdict tables in shared/tests hold them in sync. */
class GuardedLocations {
  private readonly fragments: string[]
  private readonly locations: string[]
  private readonly homePrefixes: string[]
  private readonly homePatterns: RegExp[]
  private readonly repoPatterns: RegExp[]

  constructor(declarations: string[], locationOnly: string[] = []) {
    // Location-only declarations contribute no text fragment (too broad to match as text).
    this.fragments = declarations.map((d) => normalizeForMatch(declarationFragment(d)))

    const homeDeclarations = [...declarations, ...locationOnly].filter((d) => d.startsWith("~/"))

    // Both expanded and resolved, so a symlinked home directory matches under either spelling.
    this.locations = [
      ...new Set(
        homeDeclarations
          .filter((d) => !d.includes("*"))
          .flatMap((d) => {
            const expanded = expandPath(d.replace(/\/+$/, ""))
            return [expanded, resolveLinks(expanded)]
          })
          .map(normalizeForMatch),
      ),
    ]
    this.homePrefixes = [...new Set([homedir(), resolveLinks(homedir())].map(normalizeForMatch))]
    this.homePatterns = homeDeclarations
      .flatMap((d) => declarationPatterns(d.slice("~/".length)))
      .map((p) => globToRegExp(normalizeForMatch(p)))
    this.repoPatterns = declarations
      .filter((d) => d.startsWith("<repo>/"))
      .flatMap((d) => declarationPatterns(d.slice("<repo>/".length)))
      .map((p) => globToRegExp(normalizeForMatch(p)))
  }

  /** True if `text` names a guarded location anywhere within it, including a whole shell command. */
  mentionedIn(text: string): boolean {
    const normalized = normalizeForMatch(text)
    return this.fragments.some((fragment) => normalized.includes(fragment))
  }

  private withinHome(candidate: string): boolean {
    const normalized = normalizeForMatch(candidate)
    if (this.locations.some((l) => normalized === l || normalized.startsWith(`${l}/`))) return true
    for (const prefix of this.homePrefixes) {
      if (normalized.startsWith(`${prefix}/`)) {
        const relative = normalized.slice(prefix.length + 1)
        if (this.homePatterns.some((p) => p.test(relative))) return true
      }
    }
    return false
  }

  private withinRepository(candidate: string): boolean {
    if (!isAbsolute(candidate)) return false
    const root = repositoryRootOf(candidate)
    if (root === null) return false
    return this.repoPatterns.some((p) => p.test(normalizeForMatch(relative(root, candidate))))
  }

  /** True if `path` denotes a guarded location, however it is spelled. */
  contains(path: string): boolean {
    if (!path) return false
    const expanded = expandPath(path)
    if (!isAbsolute(expanded) && this.mentionedIn(path)) {
      // A relative path means whatever the working directory makes it mean, and the
      // extension is not told that directory, so refuse an ambiguous path on shape.
      return true
    }
    // Both spellings: Home Manager / sops-nix resolve outside guarded dirs; links resolve inside them.
    return [expanded, resolveLinks(expanded)].some(
      (candidate) => this.withinHome(candidate) || this.withinRepository(candidate),
    )
  }
}

const GUARDED = new GuardedLocations(
  [...GUARDED_FILES, ...CREDENTIAL_FILES, ...INSTRUCTION_LAYERS.map(([location]) => location)],
  LOCATION_ONLY,
)

const CREDENTIALS = new GuardedLocations(CREDENTIAL_FILES)

const INSTRUCTION_BASES = INSTRUCTION_LAYERS.map(([location, layer]) =>
  normalizeForMatch(declarationFragment(location) + layer),
)

function mentionsGuardedFragment(text: string): boolean {
  return GUARDED.mentionedIn(text)
}

function guardsPath(raw: string): boolean {
  return GUARDED.contains(raw)
}

/** True if `raw` denotes stored agent authentication material. */
export function isCredentialPath(raw: string): boolean {
  return CREDENTIALS.contains(raw)
}

export function commandMentionsCredential(command: string): boolean {
  return CREDENTIALS.mentionedIn(command) || pathsIn(command).some((path) => isCredentialPath(path))
}

// Judged on the resolved destination only: a link is a write to whatever it points
// at, so a qualifying name does not make the write qualify.
function isInstructionMarkdown(raw: string): boolean {
  if (!raw) return false
  const candidates = spellings(raw)
  const normalized = normalizeForMatch(candidates[candidates.length - 1])
  if (!normalized.endsWith(".md")) return false
  return INSTRUCTION_BASES.some((base) => {
    const index = normalized.lastIndexOf(base)
    if (index === -1) return false
    const name = normalized.slice(index + base.length)
    return name.length > 0 && !name.includes("/")
  })
}

export function isProtectedPath(raw: string): boolean {
  return guardsPath(raw) && !isInstructionMarkdown(raw)
}

/** Judged as text and as paths: text misses a link to a guarded location, paths miss what the splitter mishandles. */
export function commandMentionsProtectedPath(command: string): boolean {
  return mentionsGuardedFragment(command) || pathsIn(command).some((path) => guardsPath(path))
}

/** The carve-out covers a command only when every guarded path in it qualifies. */
export function onlyInstructionMarkdown(paths: string[]): boolean {
  const guarded = paths.filter((path) => guardsPath(path))
  return guarded.length > 0 && guarded.every((path) => isInstructionMarkdown(path))
}
