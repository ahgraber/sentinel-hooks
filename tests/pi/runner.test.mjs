import assert from "node:assert/strict"
import { mkdtemp, readFile, realpath, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, test } from "node:test"

import { runCommand } from "../../plugins/sentinel/harnesses/pi/extension/runner.ts"

let directory

beforeEach(async () => {
  directory = await realpath(await mkdtemp(join(tmpdir(), "pi-hooks-runner-")))
})

afterEach(async () => {
  await rm(directory, { recursive: true, force: true })
})

const isRunning = (pid) => {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

/**
 * A killed process answers `kill(pid, 0)` until it is reaped, and an orphaned
 * child is reaped by init some time after it dies, so poll rather than check once.
 */
const stopsRunning = async (pid) => {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (!isRunning(pid)) return true
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  return false
}

test("a hook receives the payload on standard input and runs in the given directory", async () => {
  const payload = { hook_event_name: "PreToolUse", tool_name: "bash", tool_input: { command: "ls" } }

  const result = await runCommand({
    command: 'cat > received.json; pwd > cwd.txt',
    cwd: directory,
    payload,
  })

  assert.equal(result.exitCode, 0)
  assert.deepEqual(JSON.parse(await readFile(join(directory, "received.json"), "utf8")), payload)
  assert.equal((await readFile(join(directory, "cwd.txt"), "utf8")).trim(), directory)
})

test("exit status and both outputs are returned", async () => {
  const result = await runCommand({ command: "echo out; echo err >&2; exit 3", cwd: directory, payload: {} })

  assert.deepEqual(
    { exitCode: result.exitCode, stdout: result.stdout, stderr: result.stderr, timedOut: result.timedOut },
    { exitCode: 3, stdout: "out\n", stderr: "err\n", timedOut: false },
  )
})

test("a hook that does not read its input still runs", async () => {
  const result = await runCommand({ command: "exit 0", cwd: directory, payload: { big: "x".repeat(1 << 20) } })

  assert.equal(result.exitCode, 0)
})

test("a hook and its child are ended when the hook outlives its timeout", async () => {
  const started = Date.now()

  const result = await runCommand({
    command: "sleep 30 & echo $! > child.pid; echo $$ > hook.pid; wait",
    cwd: directory,
    payload: {},
    timeoutMs: 1000,
  })

  assert.equal(result.timedOut, true)
  assert.ok(Date.now() - started < 10_000)
  const hookPid = Number(await readFile(join(directory, "hook.pid"), "utf8"))
  const childPid = Number(await readFile(join(directory, "child.pid"), "utf8"))
  assert.equal(await stopsRunning(hookPid), true)
  assert.equal(await stopsRunning(childPid), true)
})

test("a hook that answers and leaves a child holding its output finishes without waiting for the child", async () => {
  const started = Date.now()

  const result = await runCommand({ command: "echo '{}'; sleep 5 &", cwd: directory, payload: {}, timeoutMs: 4000 })

  assert.deepEqual([result.exitCode, result.timedOut, result.stdout], [0, false, "{}\n"])
  assert.ok(Date.now() - started < 2000)
})

test("a hook that ignores SIGTERM is killed", async () => {
  const started = Date.now()

  const result = await runCommand({
    command: "trap '' TERM; sleep 30 & wait; sleep 30",
    cwd: directory,
    payload: {},
    timeoutMs: 200,
  })

  assert.equal(result.timedOut, true)
  assert.ok(Date.now() - started < 5000)
})

test("a hook ended by a signal reports the signal", async () => {
  const result = await runCommand({ command: "kill -KILL $$", cwd: directory, payload: {} })

  assert.equal(result.exitCode, null)
  assert.equal(result.signal, "SIGKILL")
})

test("a directory that does not exist is a failure to start", async () => {
  const result = await runCommand({ command: "true", cwd: join(directory, "missing"), payload: {} })

  assert.match(result.startError, /ENOENT/)
})

test("output past the cap is dropped", async () => {
  const result = await runCommand({
    command: "head -c 2000000 /dev/zero | tr '\\0' 'a'",
    cwd: directory,
    payload: {},
  })

  assert.equal(result.stdout.length, 1024 * 1024)
})
