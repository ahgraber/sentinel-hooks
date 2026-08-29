/** Destructive-operation rules, loaded from the TOML the Python hook also reads. */

import { existsSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { parse as parseToml } from "smol-toml"

export interface DestructiveRule {
  pattern: string
  description: string
  reason: string
  mode: "block" | "ask"
  case_insensitive?: boolean
}

function loadDestructiveRules(): DestructiveRule[] {
  const tomlPath = join(dirname(new URL(import.meta.url).pathname), "block-destructive-ops-patterns.toml")
  if (!existsSync(tomlPath)) {
    console.warn(`[security] TOML patterns file not found: ${tomlPath}`)
    return []
  }
  try {
    const data = parseToml(readFileSync(tomlPath, "utf8")) as Record<string, unknown>
    const rules: DestructiveRule[] = []
    if (Array.isArray(data.rules)) {
      rules.push(...(data.rules as DestructiveRule[]))
    } else {
      for (const section of Object.values(data)) {
        if (
          section &&
          typeof section === "object" &&
          "rules" in section &&
          Array.isArray((section as { rules: unknown }).rules)
        ) {
          rules.push(...(section as { rules: DestructiveRule[] }).rules)
        }
      }
    }
    return rules
  } catch (err) {
    console.error("[security] Failed to parse TOML patterns:", err)
    return []
  }
}

export const DESTRUCTIVE_RULES: Array<{
  re: RegExp
  rule: DestructiveRule
}> = loadDestructiveRules().flatMap((rule) => {
  try {
    const flags = rule.case_insensitive ? "si" : "s"
    return [{ re: new RegExp(rule.pattern, flags), rule }]
  } catch {
    console.warn(`[security] Invalid pattern skipped: ${rule.pattern}`)
    return []
  }
})
