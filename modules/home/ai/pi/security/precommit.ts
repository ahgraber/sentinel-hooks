/** Pre-commit runner discovery and invocation, ported from stop-precommit.sh. */

import { type ExecFileException, execFile as execFileCb, execFileSync } from "node:child_process"
import { existsSync } from "node:fs"
import { join } from "node:path"

export function toolExists(name: string): boolean {
  try {
    execFileSync("which", [name], { stdio: "pipe" })
    return true
  } catch {
    return false
  }
}

const PRECOMMIT_TIMEOUT_MS = 300_000

// quotePath=false keeps non-ASCII names literal so they round-trip to the runner.
function gitLines(root: string, args: string[]): string[] {
  try {
    const out = execFileSync("git", ["-C", root, "-c", "core.quotePath=false", ...args], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    })
    return out.split("\n").filter((line) => line.length > 0)
  } catch {
    return []
  }
}

export function gitRoot(cwd: string): string | null {
  const lines = gitLines(cwd, ["rev-parse", "--show-toplevel"])
  return lines[0] ?? null
}

export function hasPrecommitConfig(root: string): boolean {
  return existsSync(join(root, ".pre-commit-config.yaml")) || existsSync(join(root, ".pre-commit-config.yml"))
}

export function changedFiles(root: string): string[] {
  // Lowercase `d` drops deletions, which the runner cannot open.
  const tracked =
    gitLines(root, ["rev-parse", "--verify", "--quiet", "HEAD"]).length > 0
      ? gitLines(root, ["diff", "--name-only", "--diff-filter=d", "HEAD"])
      : gitLines(root, ["diff", "--cached", "--name-only", "--diff-filter=d"])
  return [...new Set([...tracked, ...gitLines(root, ["ls-files", "--others", "--exclude-standard"])])]
}

// null means the runner passed or could not be started. `run --files` must stay:
// a bare `run` stashes the work tree and leaves it reverted if the cycle fails partway.
export async function runPrecommit(runner: string, root: string, files: string[]): Promise<string | null> {
  return new Promise((res) => {
    execFileCb(
      runner,
      ["run", "--files", ...files],
      { cwd: root, timeout: PRECOMMIT_TIMEOUT_MS, maxBuffer: 10 * 1024 * 1024 },
      (err: ExecFileException | null, stdout: string, stderr: string) => {
        if (err === null || (err as NodeJS.ErrnoException).code === "ENOENT") {
          res(null)
          return
        }
        res(`${stdout}${stderr}`.trim() || err.message)
      },
    )
  })
}
