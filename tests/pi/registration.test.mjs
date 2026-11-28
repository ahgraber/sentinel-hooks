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

for (const [label, content, pattern] of [
  ["bytes that are not UTF-8", Buffer.from('{"hooks": {}, "note": "\xff"}', "latin1"), /is not valid UTF-8/],
  ["NaN", '{"hooks": {}, "note": NaN}', /does not parse as JSON/],
  ["a number outside the range of a double", '{"hooks": {}, "note": 1e400}', /does not parse as JSON/],
]) {
  test(`a file a strict JSON reader rejects is unusable: ${label}`, async () => {
    await writeFile(join(directory, "hooks.json"), content)

    const result = readRegistrations(directory)

    assert.equal(result.usable, false)
    assert.match(result.problem, pattern)
  })
}

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

test("an event name in another case registers under that event", async () => {
  await write({ hooks: { pretooluse: [{ matcher: "bash", hooks: [{ type: "command", command: "check.sh" }] }] } })

  const result = readRegistrations(directory)

  assert.equal(result.usable, true)
  assert.deepEqual(result.registrations.PreToolUse, [
    { matcher: "bash", handlers: [{ command: "check.sh", timeout: undefined }] },
  ])
  assert.deepEqual(result.warnings, [])
})

test("two names for one event keep the groups of both, in file order", async () => {
  await write({
    hooks: {
      PreToolUse: [{ hooks: [{ type: "command", command: "first.sh" }] }],
      PRETOOLUSE: [{ hooks: [{ type: "command", command: "second.sh" }] }],
    },
  })

  const result = readRegistrations(directory)

  assert.deepEqual(
    result.registrations.PreToolUse.map((group) => group.handlers[0].command),
    ["first.sh", "second.sh"],
  )
})

test("a name written twice in one object is unusable, naming the name", async () => {
  const group = (command) => `[{"hooks": [{"type": "command", "command": "${command}"}]}]`
  await write(`{"hooks": {"PreToolUse": ${group("first.sh")}, "Pre\\u0054oolUse": ${group("second.sh")}}}`)

  const result = readRegistrations(directory)

  assert.equal(result.usable, false)
  assert.match(result.problem, /"PreToolUse" twice/)
})

for (const [where, text] of [
  ["a handler", '{"hooks": {"Stop": [{"hooks": [\n{"type": "command",\n"command": "a.sh", "command": "b.sh"}]}]}}'],
  ["the top level", '{"hooks": {},\n\n"hooks": {}}'],
  ["a file with carriage returns alone", '{"hooks": {},\r\r"hooks": {}}'],
]) {
  test(`a name written twice in ${where} is unusable, naming the line of the second copy`, async () => {
    await write(text)

    const result = readRegistrations(directory)

    assert.equal(result.usable, false)
    assert.match(result.problem, /twice in one object, the second time on line 3,/)
  })
}

test("quotes, colons, and braces inside a string are not read as names", async () => {
  const command = 'printf \\"{\\\\\\"a\\\\\\": 1, \\\\\\"a\\\\\\": 2}\\"'
  await write(`{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "${command}"}]}]}}`)

  const result = readRegistrations(directory)

  assert.equal(result.usable, true, result.problem)
})

test("the same name in two objects is usable", async () => {
  const handler = (command) => `{"type": "command", "command": "${command}"}`
  await write(`{"hooks": {"PreToolUse": [{"hooks": [${handler("first.sh")}, ${handler("second.sh")}]}]}}`)

  assert.equal(readRegistrations(directory).usable, true)
})

test("a handler type in another case is a command handler", async () => {
  await write({ hooks: { Stop: [{ hooks: [{ type: "Command", command: "stop.sh" }] }] } })

  const result = readRegistrations(directory)

  assert.deepEqual(result.registrations.Stop[0].handlers, [{ command: "stop.sh", timeout: undefined }])
  assert.deepEqual(result.warnings, [])
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
  await write(`{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "x", "timeout": 3000000}]}]}}`)

  const result = readRegistrations(directory)

  assert.equal(result.usable, false)
  assert.match(result.problem, /timeout/)
})
