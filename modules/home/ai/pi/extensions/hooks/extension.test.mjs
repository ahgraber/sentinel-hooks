import assert from "node:assert/strict"
import { access, mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, test } from "node:test"

import { registerHooks } from "./extension.ts"

let agentDir
let project

beforeEach(async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "pi-hooks-extension-")))
  agentDir = join(root, "agent")
  project = join(root, "project")
  await mkdir(agentDir)
  await mkdir(project)
})

afterEach(async () => {
  await rm(join(agentDir, ".."), { recursive: true, force: true })
})

const exists = (path) =>
  access(path).then(
    () => true,
    () => false,
  )

const register = (hooks) => writeFile(join(agentDir, "hooks.json"), JSON.stringify({ hooks }))
const command = (text, matcher = "") => [{ matcher, hooks: [{ type: "command", command: text }] }]

/** A stand-in for Pi's extension API that records what the handlers return and call. */
function standIn(options = {}) {
  const hasUI = options.hasUI ?? true
  // Pi answers `false` for a dismissed dialog; an explicit `undefined` is tested too, so
  // it must not fall back to approval.
  const confirm = "confirm" in options ? options.confirm : true
  const handlers = {}
  const calls = { notify: [], status: [], sent: [], confirms: [] }
  const pi = {
    on: (name, handler) => {
      handlers[name] = handler
    },
    sendMessage: (message, options) => calls.sent.push({ message, options }),
  }
  const ctx = {
    hasUI,
    cwd: project,
    sessionManager: { getSessionId: () => "session-1" },
    ui: {
      notify: (message, level) => calls.notify.push({ level, message }),
      setStatus: (key, value) => calls.status.push({ key, value }),
      confirm: async (title, message) => {
        calls.confirms.push({ title, message })
        return confirm
      },
    },
  }
  registerHooks(pi, { agentDir: () => agentDir })
  const emit = (name, event = {}) => handlers[name](event, ctx)
  return { emit, calls }
}

async function started(options) {
  const pi = standIn(options)
  await pi.emit("session_start", { reason: "startup" })
  return pi
}

const toolCall = (toolName = "bash", input = { command: "ls" }) => ({ toolName, toolCallId: "call-1", input })
const toolResult = (isError = false) => ({
  toolName: "bash",
  toolCallId: "call-1",
  input: { command: "ls" },
  content: [{ type: "text", text: "output" }],
  details: {},
  isError,
})

async function captureStderr(action) {
  const original = process.stderr.write
  let written = ""
  process.stderr.write = (chunk) => {
    written += chunk
    return true
  }
  try {
    await action()
  } finally {
    process.stderr.write = original
  }
  return written
}

// Reading the registration

for (const [label, content, pattern] of [
  ["a file that does not parse", "{ not json", /does not parse as JSON/],
  ["a file with the wrong shape", JSON.stringify({ hooks: [] }), /wrong shape/],
]) {
  test(`${label} is reported as an error naming the file, and the indicator is set`, async () => {
    await writeFile(join(agentDir, "hooks.json"), content)

    const { calls } = await started()

    const errors = calls.notify.filter((call) => call.level === "error")
    assert.equal(errors.length, 1)
    assert.ok(errors[0].message.includes(join(agentDir, "hooks.json")))
    assert.match(errors[0].message, pattern)
    assert.deepEqual(calls.status.at(-1), { key: "hooks", value: "hooks.json unusable: no hooks run" })
  })
}

test("without a UI an unusable file is reported on standard error", async () => {
  await writeFile(join(agentDir, "hooks.json"), "{ not json")

  const written = await captureStderr(() => started({ hasUI: false }))

  assert.match(written, /hooks\.json does not parse as JSON/)
})

test("a tool call proceeds while the file is unusable", async () => {
  await writeFile(join(agentDir, "hooks.json"), "{ not json")
  const { emit } = await started()

  assert.equal(await emit("tool_call", toolCall()), undefined)
})

test("a skipped handler is reported as a warning", async () => {
  await register({ PreToolUse: [{ hooks: [{ type: "http", url: "https://example.invalid" }] }] })

  const { calls } = await started()

  assert.ok(calls.notify.some((call) => call.level === "warning" && /`http` handler/.test(call.message)))
})

test("hooks in the project's files do not run", async () => {
  const marker = join(project, "ran")
  const declared = { hooks: { PreToolUse: command(`touch ${marker}`), SessionStart: command(`touch ${marker}`) } }
  await mkdir(join(project, ".pi"))
  await mkdir(join(project, ".claude"))
  await writeFile(join(project, ".pi", "hooks.json"), JSON.stringify(declared))
  await writeFile(join(project, ".claude", "settings.json"), JSON.stringify(declared))

  const { emit } = await started()
  await emit("tool_call", toolCall())

  assert.equal(await exists(marker), false)
})

// PreToolUse

test("an allowing hook lets the tool run", async () => {
  await register({ PreToolUse: command("exit 0", "Bash") })
  const { emit } = await started()

  assert.equal(await emit("tool_call", toolCall()), undefined)
})

test("a deny returns a block with the reason and without terminate", async () => {
  const deny = `printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"not here"}}'`
  await register({ PreToolUse: command(deny) })
  const { emit } = await started()

  assert.deepEqual(await emit("tool_call", toolCall()), { block: true, reason: "not here" })
})

test("an allowing hook's context appears in that call's result", async () => {
  const note = `printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"mind the cache"}}'`
  await register({ PreToolUse: command(note) })
  const { emit } = await started()

  await emit("tool_call", toolCall())
  const patched = await emit("tool_result", toolResult())

  assert.deepEqual(patched.content, [
    { type: "text", text: "output" },
    { type: "text", text: "mind the cache" },
  ])
})

test("the PreToolUse payload carries the common fields and Pi's tool name, and no transcript path", async () => {
  const received = join(project, "payload.json")
  await register({ PreToolUse: command(`cat > ${received}`) })
  const { emit } = await started()

  await emit("tool_call", toolCall())

  assert.deepEqual(JSON.parse(await readFile(received, "utf8")), {
    session_id: "session-1",
    cwd: project,
    hook_event_name: "PreToolUse",
    tool_name: "bash",
    tool_input: { command: "ls" },
    tool_use_id: "call-1",
  })
})

// Asks

const ASK = `printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"confirm this"}}'`

test("an approved ask runs the tool, and the dialog shows the reason and the call", async () => {
  await register({ PreToolUse: command(ASK) })
  const { emit, calls } = await started({ confirm: true })

  assert.equal(await emit("tool_call", toolCall()), undefined)
  assert.equal(calls.confirms[0].message, 'confirm this\n\n{"command":"ls"}')
})

for (const [label, answer] of [
  ["declined", false],
  ["dismissed", false],
  ["unanswered", undefined],
]) {
  test(`a ${label} ask blocks and tells the model the user declined`, async () => {
    await register({ PreToolUse: command(ASK) })
    const { emit } = await started({ confirm: answer })

    const result = await emit("tool_call", toolCall())

    assert.equal(result.block, true)
    assert.match(result.reason, /user declined/)
  })
}

test("an ask without a UI blocks with the hook's reason", async () => {
  await register({ PreToolUse: command(ASK) })
  const { emit } = await started({ hasUI: false })

  assert.deepEqual(await emit("tool_call", toolCall()), { block: true, reason: "confirm this" })
})

// PostToolUse and PostToolUseFailure

test("context after a successful call reaches the result", async () => {
  const note = `printf '%s' '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"formatted"}}'`
  await register({ PostToolUse: command(note) })
  const { emit } = await started()

  const patched = await emit("tool_result", toolResult())

  assert.equal(patched.content.at(-1).text, "formatted")
})

test("a reason after a failed call reaches the result, and no PostToolUse hook runs", async () => {
  const marker = join(project, "post-ran")
  await register({
    PostToolUse: command(`touch ${marker}`),
    PostToolUseFailure: command("echo try again >&2; exit 2"),
  })
  const { emit } = await started()

  const patched = await emit("tool_result", toolResult(true))

  assert.equal(patched.content.at(-1).text, "try again")
  assert.equal(await exists(marker), false)
})

// UserPromptSubmit

test("a blocked prompt is handled and the reason is shown", async () => {
  await register({ UserPromptSubmit: command("echo not now >&2; exit 2") })
  const { emit, calls } = await started()

  assert.deepEqual(await emit("input", { text: "hello", source: "interactive" }), { action: "handled" })
  assert.ok(calls.notify.some((call) => /not now/.test(call.message)))
})

test("text a UserPromptSubmit hook prints reaches the model through before_agent_start", async () => {
  await register({ UserPromptSubmit: command("echo branch is main") })
  const { emit } = await started()

  await emit("input", { text: "hello", source: "interactive" })
  const injected = await emit("before_agent_start", { prompt: "hello" })

  assert.equal(injected.message.content, "branch is main")
  assert.equal(await emit("before_agent_start", { prompt: "again" }), undefined)
})

test("a prompt an extension sends runs no UserPromptSubmit hook", async () => {
  const marker = join(project, "prompt-ran")
  await register({ UserPromptSubmit: command(`touch ${marker}`) })
  const { emit } = await started()

  await emit("input", { text: "continue", source: "extension" })

  assert.equal(await exists(marker), false)
})

// Stop

test("a Stop block starts a new turn, and the next Stop sees stop_hook_active true", async () => {
  const seen = join(project, "stop.jsonl")
  await register({ Stop: command(`cat >> ${seen}; echo >> ${seen}; echo keep going >&2; exit 2`) })
  const { emit, calls } = await started()

  await emit("input", { text: "hello", source: "interactive" })
  await emit("agent_settled")
  await emit("agent_settled")

  const flags = (await readFile(seen, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).stop_hook_active)
  assert.deepEqual(flags, [false, true])
  assert.equal(calls.sent[0].message.content, "keep going")
  assert.deepEqual(calls.sent[0].options, { triggerTurn: true })
})

test("a turn the user starts resets stop_hook_active", async () => {
  const seen = join(project, "stop.jsonl")
  await register({ Stop: command(`cat >> ${seen}; echo >> ${seen}; exit 2`) })
  const { emit } = await started()

  await emit("agent_settled")
  await emit("input", { text: "next", source: "interactive" })
  await emit("agent_settled")

  const flags = (await readFile(seen, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).stop_hook_active)
  assert.deepEqual(flags, [false, false])
})

test("an allowing Stop hook starts no turn", async () => {
  await register({ Stop: command("exit 0") })
  const { emit, calls } = await started()

  await emit("agent_settled")

  assert.deepEqual(calls.sent, [])
})

// SessionStart and SessionEnd

test("startup context reaches the model before its first response, with source startup", async () => {
  const seen = join(project, "start.json")
  await register({ SessionStart: command(`cat > ${seen}; echo project notes`) })
  const { emit } = await started()

  const injected = await emit("before_agent_start", { prompt: "hello" })

  assert.equal(JSON.parse(await readFile(seen, "utf8")).source, "startup")
  assert.equal(injected.message.content, "project notes")
})

test("a SessionStart block shows its reason to the user, and the session continues", async () => {
  await register({
    SessionStart: [...command("echo 'required tool uv is missing' >&2; exit 2"), ...command("echo project notes")],
  })
  const { emit, calls } = await started()

  const errors = calls.notify.filter((call) => call.level === "error").map((call) => call.message)
  assert.deepEqual(errors, ["required tool uv is missing"])
  const injected = await emit("before_agent_start", { prompt: "hello" })
  assert.equal(injected.message.content, "project notes")
})

test("a resumed session runs SessionStart with source resume, and a reload runs nothing", async () => {
  const seen = join(project, "start.jsonl")
  await register({ SessionStart: command(`cat >> ${seen}; echo >> ${seen}`) })
  const { emit } = standIn()

  await emit("session_start", { reason: "resume" })
  await emit("session_start", { reason: "reload" })

  const sources = (await readFile(seen, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).source)
  assert.deepEqual(sources, ["resume"])
})

test("quitting runs SessionEnd, and a reload does not", async () => {
  const seen = join(project, "end.jsonl")
  await register({ SessionEnd: command(`cat >> ${seen}; echo >> ${seen}`) })
  const { emit } = await started()

  await emit("session_shutdown", { reason: "reload" })
  await emit("session_shutdown", { reason: "quit" })

  const reasons = (await readFile(seen, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).reason)
  assert.deepEqual(reasons, ["prompt_input_exit"])
})

test("a later usable reload clears the indicator", async () => {
  await writeFile(join(agentDir, "hooks.json"), "{ not json")
  const { emit, calls } = await started()

  await register({})
  await emit("session_start", { reason: "reload" })

  assert.deepEqual(calls.status.at(-1), { key: "hooks", value: undefined })
})

test("a skipped event is reported as a warning", async () => {
  await register({ Notification: command("exit 0") })

  const { calls } = await started()

  const warnings = calls.notify.filter((call) => call.level === "warning").map((call) => call.message)
  assert.ok(warnings.some((message) => /Notification/.test(message)))
})

test("an invalid matcher is an error with the indicator in view, and the other groups still run", async () => {
  const marker = join(project, "valid-ran")
  await register({
    PreToolUse: [
      { matcher: "bash(", hooks: [{ type: "command", command: "exit 2" }] },
      { matcher: "bash", hooks: [{ type: "command", command: `touch ${marker}` }] },
    ],
  })

  const { emit, calls } = await started()
  await emit("tool_call", toolCall())

  const errors = calls.notify.filter((call) => call.level === "error").map((call) => call.message)
  assert.equal(errors.length, 1)
  assert.ok(errors[0].startsWith(`${join(agentDir, "hooks.json")}: matcher "bash(" is not a valid regular expression`))
  assert.ok(errors[0].endsWith("Its hooks do not run in this session."))
  assert.match(calls.status.at(-1).value, /1 invalid matcher/)
  assert.equal(await exists(marker), true)
})

test("additionalContext from a UserPromptSubmit hook reaches the model", async () => {
  const note = `printf '%s' '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"on call"}}'`
  await register({ UserPromptSubmit: command(note) })
  const { emit } = await started()

  await emit("input", { text: "hello", source: "interactive" })

  assert.equal((await emit("before_agent_start", { prompt: "hello" })).message.content, "on call")
})

test("context for a prompt typed while the agent runs is queued with that prompt", async () => {
  await register({ UserPromptSubmit: command("echo for the steer") })
  const { emit, calls } = await started()

  await emit("input", { text: "also this", source: "interactive", streamingBehavior: "steer" })

  assert.equal(calls.sent[0].message.content, "for the steer")
  assert.deepEqual(calls.sent[0].options, { deliverAs: "steer" })
  assert.equal(await emit("before_agent_start", { prompt: "next" }), undefined)
})

test("context held for a call that raised no result is cleared when the agent settles", async () => {
  const note = `printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"stale"}}'`
  await register({ PreToolUse: command(note) })
  const { emit } = await started()

  await emit("tool_call", toolCall())
  await emit("agent_settled")

  assert.equal(await emit("tool_result", toolResult()), undefined)
})

for (const [label, stopReason, runs] of [
  ["an interrupted turn", "aborted", false],
  ["a failed turn", "error", false],
  ["a turn that ends normally", "stop", true],
]) {
  test(`Stop hooks after ${label} ${runs ? "run" : "do not run"}`, async () => {
    const marker = join(project, "stop-ran")
    await register({ Stop: command(`touch ${marker}; echo again >&2; exit 2`) })
    const { emit, calls } = await started()

    await emit("agent_end", { messages: [{ role: "user" }, { role: "assistant", stopReason }] })
    await emit("agent_settled")

    assert.equal(await exists(marker), runs)
    assert.equal(calls.sent.length, runs ? 1 : 0)
  })
}

const flagsIn = async (file) =>
  (await readFile(file, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).stop_hook_active)

test("a turn another extension starts after an allowing Stop sees stop_hook_active false", async () => {
  const seen = join(project, "stop.jsonl")
  // Blocks once, then allows.
  await register({
    Stop: command(`cat >> ${seen}; echo >> ${seen}; grep -q '"stop_hook_active":true' ${seen} || { echo again >&2; exit 2; }`),
  })
  const { emit } = await started()

  await emit("agent_settled")
  await emit("agent_settled")
  await emit("agent_settled")

  assert.deepEqual(await flagsIn(seen), [false, true, false])
})

// Reports reach the user

test("a PreToolUse hook that exits 1 is reported to the user naming the hook, and the call proceeds", async () => {
  await register({ PreToolUse: command("echo lint failed >&2; exit 1") })
  const { emit, calls } = await started()

  assert.equal(await emit("tool_call", toolCall()), undefined)
  assert.ok(
    calls.notify.some(
      (call) => call.level === "warning" && call.message === "hook `echo lint failed >&2; exit 1` reported an error: lint failed",
    ),
  )
})

test("a PostToolUse hook that times out is reported to the user, and the result is unchanged", async () => {
  await writeFile(
    join(agentDir, "hooks.json"),
    JSON.stringify({ hooks: { PostToolUse: [{ hooks: [{ type: "command", command: "sleep 5", timeout: 0.2 }] }] } }),
  )
  const { emit, calls } = await started()

  assert.equal(await emit("tool_result", toolResult()), undefined)
  assert.ok(calls.notify.some((call) => call.level === "warning" && /`sleep 5` did not finish/.test(call.message)))
})

test("a failing UserPromptSubmit hook is reported and the prompt proceeds", async () => {
  await register({ UserPromptSubmit: command("pi-hooks-no-such-command") })
  const { emit, calls } = await started()

  assert.equal(await emit("input", { text: "hello", source: "interactive" }), undefined)
  assert.ok(calls.notify.some((call) => call.level === "warning" && /could not start/.test(call.message)))
})

// Payloads

const record = (file) => `cat > ${file}; pwd > ${file}.cwd`
const common = (event) => ({ session_id: "session-1", cwd: project, hook_event_name: event })

test("the UserPromptSubmit payload carries the prompt and the common fields, and the hook runs in the working directory", async () => {
  const received = join(agentDir, "prompt.json")
  await register({ UserPromptSubmit: command(record(received)) })
  const { emit } = await started()

  await emit("input", { text: "hello there", source: "interactive" })

  assert.deepEqual(JSON.parse(await readFile(received, "utf8")), { ...common("UserPromptSubmit"), prompt: "hello there" })
  assert.equal((await readFile(`${received}.cwd`, "utf8")).trim(), project)
})

test("the PostToolUse payload carries the result as tool_response", async () => {
  const received = join(agentDir, "post.json")
  await register({ PostToolUse: command(record(received)) })
  const { emit } = await started()

  await emit("tool_result", toolResult())

  assert.deepEqual(JSON.parse(await readFile(received, "utf8")), {
    ...common("PostToolUse"),
    tool_name: "bash",
    tool_input: { command: "ls" },
    tool_use_id: "call-1",
    tool_response: { content: [{ type: "text", text: "output" }], details: {} },
  })
})

test("the PostToolUseFailure payload carries the result's text as error", async () => {
  const received = join(agentDir, "failure.json")
  await register({ PostToolUseFailure: command(record(received)) })
  const { emit } = await started()

  await emit("tool_result", toolResult(true))

  assert.deepEqual(JSON.parse(await readFile(received, "utf8")), {
    ...common("PostToolUseFailure"),
    tool_name: "bash",
    tool_input: { command: "ls" },
    tool_use_id: "call-1",
    error: "output",
  })
})

// Session lifecycle

test("a new session runs SessionStart with source clear, and a fork with source fork", async () => {
  const seen = join(project, "start.jsonl")
  await register({ SessionStart: command(`cat >> ${seen}; echo >> ${seen}`) })
  const { emit } = standIn()

  await emit("session_start", { reason: "new" })
  await emit("session_start", { reason: "fork" })

  const sources = (await readFile(seen, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).source)
  assert.deepEqual(sources, ["clear", "fork"])
})

test("a reload from a usable file to an unusable one is reported and sets the indicator", async () => {
  const marker = join(project, "ran")
  await register({ PreToolUse: command(`touch ${marker}`) })
  const { emit, calls } = await started()

  await writeFile(join(agentDir, "hooks.json"), "{ not json")
  await emit("session_start", { reason: "reload" })
  await emit("tool_call", toolCall())

  assert.ok(calls.notify.some((call) => call.level === "error" && /does not parse/.test(call.message)))
  assert.deepEqual(calls.status.at(-1), { key: "hooks", value: "hooks.json unusable: no hooks run" })
  assert.equal(await exists(marker), false)
})

test("a matcher on an event without a tool is ignored, so it is not reported and its hooks run", async () => {
  const marker = join(project, "stop-ran")
  await register({ Stop: [{ matcher: "bash(", hooks: [{ type: "command", command: `touch ${marker}` }] }] })

  const { emit, calls } = await started()
  await emit("agent_settled")

  assert.deepEqual(calls.notify, [])
  assert.deepEqual(calls.status.at(-1), { key: "hooks", value: undefined })
  assert.equal(await exists(marker), true)
})

test("an interrupted continuation clears stop_hook_active for the next turn", async () => {
  const seen = join(project, "stop.jsonl")
  await register({ Stop: command(`cat >> ${seen}; echo >> ${seen}; echo again >&2; exit 2`) })
  const { emit } = await started()

  // The first Stop blocks and starts a continuation, which the user interrupts.
  await emit("agent_settled")
  await emit("agent_end", { messages: [{ role: "assistant", stopReason: "aborted" }] })
  await emit("agent_settled")
  // Another extension then starts a turn that ends normally.
  await emit("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] })
  await emit("agent_settled")

  assert.deepEqual(await flagsIn(seen), [false, false])
})

test("a replaced session runs SessionEnd with its reason", async () => {
  const seen = join(project, "end.jsonl")
  await register({ SessionEnd: command(`cat >> ${seen}; echo >> ${seen}`) })
  const { emit } = await started()

  for (const reason of ["new", "resume", "fork"]) await emit("session_shutdown", { reason })

  const reasons = (await readFile(seen, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).reason)
  assert.deepEqual(reasons, ["clear", "resume", "other"])
})

test("hooks declared in Pi's settings.json do not run", async () => {
  const marker = join(project, "ran")
  await writeFile(join(agentDir, "settings.json"), JSON.stringify({ hooks: { PreToolUse: command(`touch ${marker}`) } }))

  const { emit } = await started()
  await emit("tool_call", toolCall())

  assert.equal(await exists(marker), false)
})

test("with no hooks.json nothing is reported and the indicator is clear", async () => {
  const { calls } = await started()

  assert.deepEqual(calls.notify, [])
  assert.deepEqual(calls.status, [{ key: "hooks", value: undefined }])
})

test("a session start Pi reports twice runs SessionStart once, and a start after a shutdown runs it again", async () => {
  const seen = join(project, "start.jsonl")
  await register({ SessionStart: command(`cat >> ${seen}; echo >> ${seen}`) })
  const { emit, calls } = standIn()

  await emit("session_start", { reason: "new" })
  await emit("session_start", { reason: "new" })
  await emit("session_shutdown", { reason: "quit" })
  await emit("session_start", { reason: "new" })

  const sources = (await readFile(seen, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line).source)
  assert.deepEqual(sources, ["clear", "clear"])
  assert.equal(calls.status.length, 2)
})
