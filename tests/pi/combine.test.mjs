import assert from "node:assert/strict"
import { access, mkdtemp, realpath, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, test } from "node:test"

import { matchingHandlers, runEvent } from "../../extensions/pi/combine.ts"

let directory

beforeEach(async () => {
  directory = await realpath(await mkdtemp(join(tmpdir(), "pi-hooks-combine-")))
})

afterEach(async () => {
  await rm(directory, { recursive: true, force: true })
})

const ASK = `printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"confirm"}}'`
const BLOCK = "echo refused >&2; exit 2"
const ALLOW = "exit 0"

const commands = (...list) => list.map((command) => ({ command }))

test("ask and block combine to block in either registration order", async () => {
  for (const order of [
    [ASK, BLOCK],
    [BLOCK, ASK],
  ]) {
    const combined = await runEvent("PreToolUse", commands(...order), {}, directory)

    assert.equal(combined.decision, "block")
    assert.deepEqual(combined.reasons, ["refused"])
  }
})

test("allow and ask combine to ask", async () => {
  const combined = await runEvent("PreToolUse", commands(ALLOW, ASK), {}, directory)

  assert.equal(combined.decision, "ask")
  assert.deepEqual(combined.reasons, ["confirm"])
})

test("a hook after an ask still runs", async () => {
  await runEvent("PreToolUse", commands(ASK, "touch ran"), {}, directory)

  await access(join(directory, "ran"))
})

for (const [label, handler, pattern] of [
  ["a timeout", { command: "sleep 5", timeout: 0.2 }, /did not finish within 0\.2 seconds/],
  ["a missing command", { command: "pi-hooks-no-such-command" }, /could not start/],
  ["a signal", { command: "kill -KILL $$" }, /ended by SIGKILL/],
  ["a command inside it ended by a signal", { command: "sh -c 'kill -KILL $$' && true" }, /ended by SIGKILL/],
  ["a malformed reply", { command: "echo '{ not json'" }, /does not parse/],
]) {
  test(`a PreToolUse hook that gives no answer refuses the call, naming the hook: ${label}`, async () => {
    const combined = await runEvent("PreToolUse", [handler, { command: ALLOW }], {}, directory)

    assert.equal(combined.decision, "block")
    assert.equal(combined.reasons.length, 1)
    assert.ok(combined.reasons[0].includes(`hook \`${handler.command}\``))
    assert.match(combined.reasons[0], pattern)
  })
}

test("a PostToolUse hook that times out is reported, and the event carries no feedback from it", async () => {
  const combined = await runEvent("PostToolUse", [{ command: "sleep 5", timeout: 0.2 }], {}, directory)

  assert.equal(combined.decision, "allow")
  assert.deepEqual([combined.reasons, combined.context, combined.text], [[], [], []])
  assert.equal(combined.reports.length, 1)
  assert.match(combined.reports[0], /`sleep 5` did not finish/)
})

test("a non-blocking error is reported and the call proceeds", async () => {
  const combined = await runEvent("PreToolUse", commands("echo lint failed >&2; exit 1"), {}, directory)

  assert.equal(combined.decision, "allow")
  assert.match(combined.reports[0], /^hook `echo lint failed >&2; exit 1` reported an error: lint failed$/)
})

test("a PostToolUse block keeps its context as feedback", async () => {
  const reply = `printf '%s' '{"decision":"block","reason":"fix it","hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"see log"}}'`

  const combined = await runEvent("PostToolUse", commands(reply), {}, directory)

  assert.deepEqual([combined.decision, combined.reasons, combined.context], ["block", ["fix it"], ["see log"]])
})

test("matchers select handlers on tool events and are ignored on the others", () => {
  const groups = [
    { matcher: "bash", handlers: [{ command: "a" }] },
    { matcher: "write|edit", handlers: [{ command: "b" }] },
  ]

  assert.deepEqual(matchingHandlers("PreToolUse", groups, "Bash"), [{ command: "a" }])
  assert.deepEqual(matchingHandlers("Stop", groups), [{ command: "a" }, { command: "b" }])
})

const context = (event, value) =>
  `printf '%s' '{"hookSpecificOutput":{"hookEventName":"${event}","additionalContext":"${value}"}}'`

test("two blocks keep both reasons", async () => {
  const combined = await runEvent("PreToolUse", commands(BLOCK, "echo also >&2; exit 2"), {}, directory)

  assert.deepEqual(combined.reasons.toSorted(), ["also", "refused"])
})

test("an allowing hook's context is kept when the decision is ask", async () => {
  const combined = await runEvent("PreToolUse", commands(context("PreToolUse", "note"), ASK), {}, directory)

  assert.deepEqual([combined.decision, combined.context], ["ask", ["note"]])
})

test("an allowed PreToolUse call keeps its context", async () => {
  const combined = await runEvent("PreToolUse", commands(context("PreToolUse", "note")), {}, directory)

  assert.deepEqual([combined.decision, combined.context], ["allow", ["note"]])
})

test("a blocked PreToolUse call drops context and text", async () => {
  const combined = await runEvent("PreToolUse", commands(context("PreToolUse", "note"), "echo hi", BLOCK), {}, directory)

  assert.deepEqual([combined.context, combined.text], [[], []])
})

test("plain text is kept on SessionStart and UserPromptSubmit and dropped elsewhere", async () => {
  for (const event of ["SessionStart", "UserPromptSubmit"]) {
    assert.deepEqual((await runEvent(event, commands("echo hi"), {}, directory)).text, ["hi"])
  }
  for (const event of ["PreToolUse", "PostToolUse", "Stop"]) {
    assert.deepEqual((await runEvent(event, commands("echo hi"), {}, directory)).text, [])
  }
})

for (const [label, command] of [
  ["a missing command", "pi-hooks-no-such-command"],
  ["a signal", "kill -KILL $$"],
  ["a malformed reply", "echo '{ not json'"],
]) {
  test(`a failure outside PreToolUse is reported and does not decide: ${label}`, async () => {
    const combined = await runEvent("PostToolUse", commands(command, context("PostToolUse", "note")), {}, directory)

    assert.deepEqual([combined.decision, combined.reasons, combined.context], ["allow", [], ["note"]])
    assert.equal(combined.reports.length, 1)
  })
}

test("a long command is truncated in the hook's name and a long report is truncated", async () => {
  const long = `echo ${"x".repeat(5000)} >&2; exit 1`

  const combined = await runEvent("PreToolUse", commands(long), {}, directory)

  assert.ok(combined.reports[0].length <= 2000)
  assert.match(combined.reports[0], /^hook `echo x+ … \d+ characters left out … x+ >&2; exit 1`/)
})

test("a long error report keeps its start and its end", async () => {
  const traceback = `printf 'Traceback\\n%s\\nKeyError: tool_input' "$(printf 'x%.0s' $(seq 5000))" >&2; exit 1`

  const combined = await runEvent("PostToolUse", commands(traceback), {}, directory)

  assert.ok(combined.reports[0].length <= 2000)
  assert.match(combined.reports[0], /reported an error: Traceback\n/)
  assert.match(combined.reports[0], /characters left out/)
  assert.match(combined.reports[0], /KeyError: tool_input$/)
})

test("a long report that could not start keeps its end, and the count of left-out characters is exact", async () => {
  const failing = `printf 'start\\n%s\\nmissing interpreter' "$(printf 'x%.0s' $(seq 5000))" >&2; exit 127`

  const combined = await runEvent("PostToolUse", commands(failing), {}, directory)

  const [report] = combined.reports
  // The hook's name is shortened too, so the body's marker is the last one.
  const marker = [...report.matchAll(/ … (\d+) characters left out … /g)].at(-1)
  const [head, tail] = [report.slice(0, marker.index), report.slice(marker.index + marker[0].length)]
  const leftOut = Number(marker[1])
  assert.ok(report.length <= 2000)
  assert.match(report, /missing interpreter\.$/)
  // The cut falls inside the 5000 `x` characters the hook printed, so the kept ones and the count add up to them.
  const keptBefore = head.split("start\n")[1].length
  const keptAfter = tail.split("\nmissing interpreter")[0].length
  assert.equal(keptBefore + leftOut + keptAfter, 5000)
})

test("a refusal built from a hook that could not start is shortened like a report", async () => {
  const failing = `printf 'start\\n%s\\nmissing interpreter' "$(printf 'x%.0s' $(seq 5000))" >&2; exit 127`

  const combined = await runEvent("PreToolUse", commands(failing), {}, directory)

  assert.equal(combined.decision, "block")
  assert.ok(combined.reasons[0].length <= 2000)
  assert.match(combined.reasons[0], /characters left out/)
  assert.match(combined.reasons[0], /missing interpreter, so the call is refused\.$/)
})

test("a long systemMessage reaches the user whole", async () => {
  const message = `Warning: ${"x".repeat(3000)}`
  const notice = `printf '%s' '{"systemMessage":"${message}"}'`

  const combined = await runEvent("SessionStart", commands(notice), {}, directory)

  assert.deepEqual(combined.reports, [message])
})

test("a systemMessage is reported to the user and leaves the decision as it is", async () => {
  const notice = `printf '%s' '{"systemMessage":"Warning: hooks are off in Codex"}'`

  const started = await runEvent("SessionStart", commands(notice), {}, directory)
  const asked = await runEvent("PreToolUse", commands(notice, ASK), {}, directory)

  assert.deepEqual([started.decision, started.reports], ["allow", ["Warning: hooks are off in Codex"]])
  assert.deepEqual([asked.decision, asked.reports], ["ask", ["Warning: hooks are off in Codex"]])
})
