/** Declarations in guarded-paths.toml, shared with the Python hooks. */

import { existsSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { parse as parseToml } from "smol-toml"

interface GuardedManifest {
  gatedDeployed: string[]
  gatedSources: string[]
  credentialPaths: string[]
  instructionLayers: Array<[string, string]>
  locationOnlyPaths: string[]
}

function loadGuardedManifest(): { manifest: GuardedManifest | null; error: string | null } {
  const tomlPath = join(dirname(new URL(import.meta.url).pathname), "guarded-paths.toml")
  if (!existsSync(tomlPath)) {
    return { manifest: null, error: `guarded-paths.toml not found: ${tomlPath}` }
  }
  try {
    const data = parseToml(readFileSync(tomlPath, "utf8")) as Record<string, unknown>
    const paths = (name: string): string[] => {
      const table = data[name] as { paths?: unknown } | undefined
      if (!Array.isArray(table?.paths) || !table.paths.every((path) => typeof path === "string")) {
        throw new Error(`Missing or invalid ${name}.paths`)
      }
      return table.paths
    }
    const guarded = [...paths("guarded"), ...paths("exec-through"), ...paths("write-through")]
    const blocked = paths("block")
    const writable = paths("write-through")
    if (!Array.isArray(data.exceptions)) throw new Error("Missing exceptions table")
    return {
      manifest: {
        gatedDeployed: guarded.filter((path) => !path.startsWith("<repo>/")),
        gatedSources: guarded.filter((path) => path.startsWith("<repo>/")),
        credentialPaths: blocked,
        instructionLayers: writable.filter((path) => path.endsWith("/*.md")).map((path) => [path.slice(0, -4), ""]),
        locationOnlyPaths: [],
      },
      error: null,
    }
  } catch (err) {
    return { manifest: null, error: `Failed to parse guarded-paths.toml: ${err}` }
  }
}

const { manifest: GUARDED_MANIFEST, error } = loadGuardedManifest()

export const GUARDED_MANIFEST_ERROR = error

export const GUARDED_FILES = GUARDED_MANIFEST
  ? [...GUARDED_MANIFEST.gatedDeployed, ...GUARDED_MANIFEST.gatedSources]
  : []

// Credential writes are refused outright, never prompted.
export const CREDENTIAL_FILES = GUARDED_MANIFEST ? GUARDED_MANIFEST.credentialPaths : []

// The temporary Pi port can express direct Markdown carve-outs only.
export const INSTRUCTION_LAYERS: Array<[string, string]> = GUARDED_MANIFEST ? GUARDED_MANIFEST.instructionLayers : []

// The class manifest has no location-only declarations.
export const LOCATION_ONLY = GUARDED_MANIFEST ? GUARDED_MANIFEST.locationOnlyPaths : []
