// Live check of the hooks extension in a real Pi session over RPC.
//
// Usage: node live-rpc-driver.mjs [events|unusable]
//
// Pi loads the extension from this checkout with `-e`, and `PI_CODING_AGENT_DIR`
// points at a fresh temporary directory holding test hooks, so nothing needs to be
// installed and the user's own agent directory is not read. The model is the local
// `omlx` server's Qwen3.6-35B-A3B-4bit; any model that calls tools when told to works.
import { spawn } from "node:child_process"
import { appendFileSync, chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

// The checkout root is the nearest ancestor holding `flake.nix`, so this file still
// finds it after the change directory moves into the archive.
let REPO = dirname(fileURLToPath(import.meta.url))
while (!existsSync(join(REPO, "flake.nix"))) {
  if (dirname(REPO) === REPO) throw new Error("no flake.nix above this file")
  REPO = dirname(REPO)
}
const mode = process.argv[2] ?? "events"
const root = mkdtempSync(join(tmpdir(), "pi-live-"))
const agentDir = join(root, "agent")
const project = join(root, "project")
mkdirSync(agentDir)
mkdirSync(project)
writeFileSync(
  join(agentDir, "models.json"),
  JSON.stringify({
    providers: {
      omlx: {
        baseUrl: "http://localhost:11434",
        api: "anthropic-messages",
        apiKey: "omlx",
        models: [{ id: "Qwen3.6-35B-A3B-4bit", reasoning: true, contextWindow: 200000, maxTokens: 32768 }],
      },
    },
  }),
)
writeFileSync(join(agentDir, "settings.json"), JSON.stringify({ defaultProvider: "omlx", defaultModel: "Qwen3.6-35B-A3B-4bit" }))

const pre = join(root, "pre.sh")
writeFileSync(
  pre,
  `#!/bin/sh
input=$(cat)
case "$input" in
  *DENYME*) echo "Commands containing DENYME are refused by the test hook." >&2; exit 2;;
  *ASKME*) printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"test hook asks"}}';;
  *) printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"HOOKCTX-42"}}';;
esac
`,
)
const stop = join(root, "stop.sh")
writeFileSync(
  stop,
  `#!/bin/sh
cat >> ${root}/stop.log; echo >> ${root}/stop.log
case "$(tail -n 1 ${root}/stop.log)" in
  *'"stop_hook_active":false'*) echo "Before stopping, reply with the single word CONTINUED." >&2; exit 2;;
esac
exit 0
`,
)
chmodSync(pre, 0o755)
chmodSync(stop, 0o755)

if (mode === "unusable") {
  writeFileSync(join(agentDir, "hooks.json"), "{ not json")
} else {
  writeFileSync(
    join(agentDir, "hooks.json"),
    JSON.stringify({
      hooks: {
        SessionStart: [
          {
            hooks: [
              {
                type: "command",
                command: `cat >> ${root}/session.log; echo >> ${root}/session.log; echo 'SESSIONCTX: the project codename is BLUEFIN.'`,
              },
            ],
          },
        ],
        SessionEnd: [{ hooks: [{ type: "command", command: `cat >> ${root}/session.log; echo >> ${root}/session.log` }] }],
        PreToolUse: [{ matcher: "Bash", hooks: [{ type: "command", command: pre }] }],
        Stop: [{ hooks: [{ type: "command", command: stop }] }],
      },
    }),
  )
}

const log = join(root, "events.jsonl")
const child = spawn(
  "pi",
  ["--mode", "rpc", "--no-extensions", "-e", join(REPO, "modules/home/ai/pi/hooks/index.ts"), "--no-session"],
  { cwd: project, env: { ...process.env, PI_CODING_AGENT_DIR: agentDir }, stdio: ["pipe", "pipe", "pipe"] },
)
child.stderr.on("data", (chunk) => appendFileSync(join(root, "stderr.log"), chunk))

const send = (object) => child.stdin.write(`${JSON.stringify(object)}\n`)
let responded
const confirmAnswers = [true, false]
let settled
let buffer = ""
child.stdout.on("data", (chunk) => {
  buffer += chunk
  let index
  while ((index = buffer.indexOf("\n")) !== -1) {
    const line = buffer.slice(0, index).replace(/\r$/, "")
    buffer = buffer.slice(index + 1)
    if (line === "") continue
    appendFileSync(log, `${line}\n`)
    let event
    try {
      event = JSON.parse(line)
    } catch {
      continue
    }
    if (event.type === "extension_ui_request" && event.method === "confirm") {
      const confirmed = confirmAnswers.shift() ?? false
      console.log(`CONFIRM ${JSON.stringify(event.title)} ${JSON.stringify(event.message)} -> ${confirmed}`)
      send({ type: "extension_ui_response", id: event.id, confirmed })
    }
    if (event.type === "extension_ui_request" && (event.method === "notify" || event.method === "setStatus")) {
      console.log(`UI ${event.method} ${JSON.stringify(event.notifyType ?? event.statusKey)} ${JSON.stringify(event.message ?? event.statusText)}`)
    }
    if (event.type === "tool_execution_end") {
      const text = (event.result?.content ?? []).map((part) => part.text).join(" | ")
      console.log(`TOOL ${event.toolName} isError=${event.isError} ${JSON.stringify(text).slice(0, 300)}`)
    }
    if (event.type === "response" && event.command === "new_session") {
      console.log(`RESPONSE new_session ${JSON.stringify(event.data)}`)
      responded?.()
    }
    if (event.type === "agent_start") console.log("AGENT_START")
    if (event.type === "message_end" && event.message?.role === "assistant") {
      const text = (event.message.content ?? []).filter((part) => part.type === "text").map((part) => part.text).join(" ")
      if (text) console.log(`ASSISTANT ${JSON.stringify(text).slice(0, 300)}`)
    }
    if (event.type === "agent_settled" && settled) {
      const resolve = settled
      settled = undefined
      resolve()
    }
  }
})

const waitSettled = (ms) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timed out waiting for agent_settled")), ms)
    settled = () => {
      clearTimeout(timer)
      resolve()
    }
  })

async function prompt(message) {
  console.log(`\n=== PROMPT ${message}`)
  const done = waitSettled(240_000)
  send({ type: "prompt", message })
  await done
  // A Stop continuation settles again after its own turn.
  await new Promise((resolve) => setTimeout(resolve, 1500))
  if (settled === undefined) {
    const again = waitSettled(240_000)
    await Promise.race([again, new Promise((resolve) => setTimeout(resolve, 60_000))])
  }
}

try {
  if (mode === "unusable") {
    await prompt("Run the bash command `echo hello` and report its output.")
  } else {
    await prompt("What is the project codename? Answer in one sentence without using tools.")
    await prompt("Call the bash tool with the command `echo DENYME`. Do not answer until the tool returns, then report exactly what the tool returned, including any text after the command output.")
    await prompt("Call the bash tool with the command `echo ASKME-one`. Do not answer until the tool returns, then report exactly what the tool returned.")
    await prompt("Call the bash tool with the command `echo ASKME-two`. Do not answer until the tool returns, then report exactly what the tool returned.")
    await prompt("Call the bash tool with the command `echo plain`. Do not answer until the tool returns, then report exactly what the tool returned, including any text after the command output.")
    // Replace the session: Pi raises `session_shutdown` then `session_start`, both with reason `new`.
    console.log("\n=== NEW SESSION")
    await new Promise((resolve) => {
      responded = resolve
      send({ type: "new_session" })
    })
    await new Promise((resolve) => setTimeout(resolve, 1500))
    for (const line of readFileSync(join(root, "session.log"), "utf8").trim().split("\n")) {
      const payload = JSON.parse(line)
      console.log(`SESSION HOOK ${payload.hook_event_name} ${payload.source ?? payload.reason}`)
    }
  }
} catch (error) {
  console.log(`ERROR ${error.message}`)
} finally {
  console.log(`\nlogs in ${root}`)
  child.kill()
}
