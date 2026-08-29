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
    const gated = (data.gated ?? {}) as { deployed?: string[]; sources?: string[] }
    const credentials = (data.credentials ?? {}) as { paths?: string[] }
    const instructionLayers = (data["instruction-layers"] ?? {}) as { layers?: Array<[string, string]> }
    const locationOnly = (data["location-only"] ?? {}) as { paths?: string[] }
    return {
      manifest: {
        gatedDeployed: gated.deployed ?? [],
        gatedSources: gated.sources ?? [],
        credentialPaths: credentials.paths ?? [],
        instructionLayers: instructionLayers.layers ?? [],
        locationOnlyPaths: locationOnly.paths ?? [],
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

// Instruction markdown stays writable; only enforcement is gated.
export const INSTRUCTION_LAYERS: Array<[string, string]> = GUARDED_MANIFEST ? GUARDED_MANIFEST.instructionLayers : []

// Matched by resolved location only; text matching would over-refuse.
export const LOCATION_ONLY = GUARDED_MANIFEST ? GUARDED_MANIFEST.locationOnlyPaths : []
