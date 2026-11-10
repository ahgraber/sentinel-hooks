import assert from "node:assert/strict"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, test } from "node:test"

import { readRegistrations } from "../../extensions/pi/registration.ts"

let directory

beforeEach(async () => {
  directory = await mkdtemp(join(tmpdir(), "pi-hooks-registration-"))
})

afterEach(async () => {
  await rm(directory, { recursive: true, force: true })
})

const write = (content) =>
  writeFile(join(directory, "hooks.json"), typeof content === "string" ? content : JSON.stringify(content))

test("a declared PreToolUse command is returned", async () => {
  await write({
    hooks: { PreToolUse: [{ matcher: "bash", hooks: [{ type: "command", command: "check.sh", timeout: 5 }] }] },
  })

  const result = readRegistrations(directory)

  assert.equal(result.usable, true)
  assert.deepEqual(result.registrations.PreToolUse, [
    { matcher: "bash", handlers: [{ command: "check.sh", timeout: 5 }] },
  ])
  assert.deepEqual(result.warnings, [])
})

test("a group without a matcher matches everything", async () => {
  await write({ hooks: { Stop: [{ hooks: [{ type: "command", command: "stop.sh" }] }] } })

  assert.equal(readRegistrations(directory).registrations.Stop[0].matcher, "")
})

test("a missing file is no registrations and no error", () => {
  assert.deepEqual(readRegistrations(directory), {
    usable: true,
    file: join(directory, "hooks.json"),
    registrations: {},
    warnings: [],
  })
})

test("text that is not JSON is unusable, naming the file and the parse error", async () => {
  await write("{ not json")

  const result = readRegistrations(directory)

  assert.equal(result.usable, false)
  assert.equal(result.file, join(directory, "hooks.json"))
  assert.match(result.problem, /does not parse as JSON/)
  let parseError
  try {
    JSON.parse("{ not json")
  } catch (error) {
    parseError = error.message
  }
  assert.ok(result.problem.includes(parseError))
})

test("a file that exists but cannot be read is unusable", async () => {
  await mkdir(join(directory, "hooks.json"))

  const result = readRegistrations(directory)

  assert.equal(result.usable, false)
  assert.match(result.problem, /cannot be read/)
})

for (const [label, content] of [
  ["`hooks` is a list", { hooks: [] }],
  ["`hooks` is missing", { PreToolUse: [] }],
  ["an event holds an object", { hooks: { PreToolUse: {} } }],
  ["a group has no `hooks` list", { hooks: { PreToolUse: [{ matcher: "bash" }] } }],
  ["a command handler has no command", { hooks: { PreToolUse: [{ hooks: [{ type: "command" }] }] } }],
  ["a timeout is not positive", { hooks: { PreToolUse: [{ hooks: [{ type: "command", command: "x", timeout: 0 }] }] } }],
  ["a timeout is a string", { hooks: { PreToolUse: [{ hooks: [{ type: "command", command: "x", timeout: "5" }] }] } }],
  ["the top level is null", null],
  ["the top level is a list", []],
  ["a handler is not an object", { hooks: { PreToolUse: [{ hooks: ["x"] }] } }],
  ["a handler has no type", { hooks: { PreToolUse: [{ hooks: [{ command: "x" }] }] } }],
  ["a matcher is not a string", { hooks: { PreToolUse: [{ matcher: 1, hooks: [] }] } }],
  ["an event name differs only in case", { hooks: { pretooluse: [{ hooks: [{ type: "command", command: "x" }] }] } }],
]) {
  test(`JSON with the wrong shape is unusable: ${label}`, async () => {
    await write(content)

    const result = readRegistrations(directory)

    assert.equal(result.usable, false)
    assert.equal(result.file, join(directory, "hooks.json"))
    assert.match(result.problem, /wrong shape/)
  })
}

test("a handler whose type is not command is reported and dropped, and its neighbor is kept", async () => {
  await write({
    hooks: {
      PreToolUse: [
        {
          matcher: "",
          hooks: [
            { type: "http", url: "https://example.invalid" },
            { type: "command", command: "check.sh" },
          ],
        },
      ],
    },
  })

  const result = readRegistrations(directory)

  assert.equal(result.usable, true)
  assert.deepEqual(result.registrations.PreToolUse[0].handlers, [{ command: "check.sh", timeout: undefined }])
  assert.equal(result.warnings.length, 1)
  assert.match(result.warnings[0], /`http` handler/)
})

test("an event this extension cannot raise is reported and skipped", async () => {
  await write({
    hooks: {
      Notification: [{ hooks: [{ type: "command", command: "notify.sh" }] }],
      Stop: [{ hooks: [{ type: "command", command: "stop.sh" }] }],
    },
  })

  const result = readRegistrations(directory)

  assert.equal(result.usable, true)
  assert.deepEqual(Object.keys(result.registrations), ["Stop"])
  assert.equal(result.warnings.length, 1)
  assert.match(result.warnings[0], /Notification/)
})

test("a timeout longer than a timer can hold is unusable", async () => {
  await write(`{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "x", "timeout": 1e400}]}]}}`)

  const result = readRegistrations(directory)

  assert.equal(result.usable, false)
  assert.match(result.problem, /timeout/)
})
