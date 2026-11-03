/** Run one hook command in its own process group, with a timeout and capped output. */

import { spawn } from "node:child_process"

export const DEFAULT_TIMEOUT_MS = 60_000
export const OUTPUT_CAP_BYTES = 1024 * 1024
/** Time between `SIGTERM` and `SIGKILL` for a hook that outlives its timeout. */
export const KILL_GRACE_MS = 2_000
/**
 * Time to keep reading output after the hook exits. A background child the hook
 * started can hold the pipes open after the hook has answered, so the run ends
 * this long after exit whether or not the pipes have closed.
 */
export const DRAIN_MS = 250

export interface RunRequest {
  command: string
  cwd: string
  payload: unknown
  timeoutMs?: number
}

export interface RunResult {
  exitCode: number | null
  signal: NodeJS.Signals | null
  timedOut: boolean
  /** Set when the shell itself could not be spawned. */
  startError?: string
  stdout: string
  stderr: string
}

/** Collect a stream's bytes up to the cap, and drop the rest. */
function capped(stream: NodeJS.ReadableStream): () => string {
  const chunks: Buffer[] = []
  let size = 0
  stream.on("data", (chunk: Buffer) => {
    if (size >= OUTPUT_CAP_BYTES) return
    const kept = chunk.subarray(0, OUTPUT_CAP_BYTES - size)
    chunks.push(kept)
    size += kept.length
  })
  return () => Buffer.concat(chunks).toString("utf8")
}

function signalGroup(pid: number, signal: NodeJS.Signals): void {
  try {
    process.kill(-pid, signal)
  } catch {
    // The group has already exited.
  }
}

/**
 * Run `command` through `/bin/sh -c`, with the payload as JSON on standard input.
 *
 * The command leads a new process group, so a timeout ends the hook and every
 * child it started: `SIGTERM` to the group, then `SIGKILL` after a grace period.
 */
export function runCommand(request: RunRequest): Promise<RunResult> {
  const timeoutMs = request.timeoutMs ?? DEFAULT_TIMEOUT_MS

  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>
    try {
      child = spawn("/bin/sh", ["-c", request.command], {
        cwd: request.cwd,
        detached: true,
        stdio: ["pipe", "pipe", "pipe"],
      })
    } catch (error) {
      resolve({
        exitCode: null,
        signal: null,
        timedOut: false,
        startError: (error as Error).message,
        stdout: "",
        stderr: "",
      })
      return
    }

    const stdout = capped(child.stdout!)
    const stderr = capped(child.stderr!)
    let timedOut = false
    let killTimer: NodeJS.Timeout | undefined
    let drainTimer: NodeJS.Timeout | undefined
    let settled = false

    const timer = setTimeout(() => {
      timedOut = true
      if (child.pid === undefined) return
      signalGroup(child.pid, "SIGTERM")
      killTimer = setTimeout(() => signalGroup(child.pid!, "SIGKILL"), KILL_GRACE_MS)
    }, timeoutMs)

    const finish = (result: Omit<RunResult, "stdout" | "stderr" | "timedOut">) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      clearTimeout(killTimer)
      clearTimeout(drainTimer)
      // A timed-out hook's children may outlast the shell; end them before answering.
      // The group ID is free for reuse only once every member has exited, and this
      // runs within milliseconds of the leader's exit, so the signal reaches this
      // hook's group.
      if (timedOut && child.pid !== undefined) signalGroup(child.pid, "SIGKILL")
      resolve({ ...result, timedOut, stdout: stdout(), stderr: stderr() })
    }

    child.on("error", (error) => finish({ exitCode: null, signal: null, startError: error.message }))
    child.on("close", (exitCode, signal) => finish({ exitCode, signal }))
    child.on("exit", (exitCode, signal) => {
      drainTimer = setTimeout(() => {
        child.stdout?.destroy()
        child.stderr?.destroy()
        finish({ exitCode, signal })
      }, DRAIN_MS)
    })

    // A hook that exits without reading its input closes the pipe; that is not a failure.
    child.stdin!.on("error", () => {})
    child.stdin!.end(JSON.stringify(request.payload))
  })
}
