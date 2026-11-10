import assert from "node:assert/strict"
import { test } from "node:test"

import { decode } from "../../extensions/pi/decode.ts"

const run = (fields) => ({ exitCode: 0, signal: null, timedOut: false, stdout: "", stderr: "", ...fields })
const reply = (hookSpecificOutput, extra = {}) =>
  run({ stdout: JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", ...hookSpecificOutput }, ...extra }) })

test("exit 2 is a block with standard error as the reason", () => {
  assert.deepEqual(decode(run({ exitCode: 2, stderr: "no rm -rf\n" }), 60_000, "PreToolUse"), { kind: "block", reason: "no rm -rf" })
})

test("exit 0 with permissionDecision ask is an ask, not an allow", () => {
  assert.deepEqual(decode(reply({ permissionDecision: "ask", permissionDecisionReason: "confirm" }), 60_000, "PreToolUse"), {
    kind: "ask",
    reason: "confirm",
    context: undefined,
  })
})

test("exit 0 with permissionDecision deny is a block", () => {
  assert.deepEqual(decode(reply({ permissionDecision: "deny", permissionDecisionReason: "no" }), 60_000, "PreToolUse"), {
    kind: "block",
    reason: "no",
    context: undefined,
  })
})

test("exit 0 with permissionDecision allow is an allow carrying its context", () => {
  assert.deepEqual(decode(reply({ permissionDecision: "allow", additionalContext: "note" }), 60_000, "PreToolUse"), {
    kind: "allow",
    context: "note",
  })
})

test("exit 0 with decision block is a block with its reason", () => {
  assert.deepEqual(decode(run({ stdout: JSON.stringify({ decision: "block", reason: "keep going" }) }), 60_000, "PreToolUse"), {
    kind: "block",
    reason: "keep going",
    context: undefined,
  })
})

test("exit 0 with plain text is an allow carrying the text", () => {
  assert.deepEqual(decode(run({ stdout: "  remember this\n" }), 60_000, "PreToolUse"), { kind: "allow", text: "remember this" })
})

test("exit 0 with no output is an allow", () => {
  assert.deepEqual(decode(run({}), 60_000, "PreToolUse"), { kind: "allow" })
})

test("exit 1 is a non-blocking error carrying standard error", () => {
  assert.deepEqual(decode(run({ exitCode: 1, stderr: "lint failed\n" }), 60_000, "PreToolUse"), {
    kind: "error",
    message: "lint failed",
  })
})

test("exit 2 takes its reason from the JSON reply's blocking decision", () => {
  const denied = reply({ permissionDecision: "deny", permissionDecisionReason: "from json" })

  assert.equal(decode({ ...denied, exitCode: 2, stderr: "from stderr" }, 60_000, "PreToolUse").reason, "from json")
})

test("exit 2 blocks with standard error when the reply does not block", () => {
  const asked = reply({ permissionDecision: "ask", permissionDecisionReason: "confirm" })

  assert.deepEqual(decode({ ...asked, exitCode: 2, stderr: "from stderr" }, 60_000, "PreToolUse"), {
    kind: "block",
    reason: "from stderr",
  })
})

test("exit 2 with a reply that does not parse still blocks with standard error", () => {
  assert.deepEqual(decode(run({ exitCode: 2, stdout: "{ not json", stderr: "no" }), 60_000, "PreToolUse"), {
    kind: "block",
    reason: "no",
  })
})

test("on another exit status the JSON reply decides", () => {
  const denied = reply({ permissionDecision: "deny", permissionDecisionReason: "no" })

  assert.equal(decode({ ...denied, exitCode: 1, stderr: "noise" }, 60_000, "PreToolUse").kind, "block")
})

test("permissionDecision is ignored outside PreToolUse", () => {
  const denied = reply({ permissionDecision: "deny", permissionDecisionReason: "no", additionalContext: "note" })

  assert.deepEqual(decode(denied, 60_000, "Stop"), { kind: "allow", context: "note" })
})

for (const [label, fields, pattern] of [
  ["timed out", { exitCode: null, signal: "SIGTERM", timedOut: true }, /within 1\.5 seconds/],
  ["not started", { exitCode: null, startError: "spawn /bin/sh ENOENT" }, /could not start: spawn/],
  ["command not found", { exitCode: 127, stderr: "sh: nope: command not found\n" }, /could not start \(exit 127\)/],
  ["not executable", { exitCode: 126 }, /could not start \(exit 126\)/],
  ["ended by a signal", { exitCode: null, signal: "SIGKILL" }, /ended by SIGKILL/],
  ["a command inside the hook ended by a signal", { exitCode: 137 }, /ended by SIGKILL \(exit 137\)/],
  ["a malformed { reply", { stdout: "{ not json" }, /does not parse/],
  ["an unknown permissionDecision", { stdout: JSON.stringify({ hookSpecificOutput: { permissionDecision: "defer" } }) }, /unknown permissionDecision/],
]) {
  test(`a hook that gave no answer is a failure: ${label}`, () => {
    const outcome = decode(run(fields), 1500, "PreToolUse")

    assert.equal(outcome.kind, "failure")
    assert.match(outcome.problem, pattern)
  })
}
