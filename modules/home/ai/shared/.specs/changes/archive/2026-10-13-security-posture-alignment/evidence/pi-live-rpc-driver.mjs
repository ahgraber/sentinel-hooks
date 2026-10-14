// Live check of Pi's registration of the shared hooks in a real Pi session over RPC.
//
// Usage: node pi-live-rpc-driver.mjs
//
// Pi loads the hooks extension from this checkout with `-e`. `HOME` points at a fresh
// temporary home holding the layout `pi/default.nix` deploys, linked into this
// checkout, so the registration's `~/.pi/agent/hooks/` commands reach the hooks here
// and the user's own home is not read. The model is the local `omlx` server's
// Qwen3.6-35B-A3B-4bit; any model that calls tools when told to works.
import { spawn } from "node:child_process"
import {
  appendFileSync,
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  realpathSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { homedir, tmpdir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

// The checkout root is the nearest ancestor holding `flake.nix`, so this file still
// finds it after the change directory moves into the archive.
let REPO = dirname(fileURLToPath(import.meta.url))
while (!existsSync(join(REPO, "flake.nix"))) {
  if (dirname(REPO) === REPO) throw new Error("no flake.nix above this file")
  REPO = dirname(REPO)
}
const AI = join(REPO, "modules/home/ai")

const root = realpathSync(mkdtempSync(join(tmpdir(), "pi-live-")))
const home = join(root, "home")
const agentDir = join(home, ".pi", "agent")
const hooksDir = join(agentDir, "hooks")
const project = join(root, "project")
mkdirSync(hooksDir, { recursive: true })
mkdirSync(project)

// What `pi/default.nix` deploys.
symlinkSync(join(AI, "pi/security/hooks.json"), join(agentDir, "hooks.json"))
symlinkSync(join(AI, "pi/security/hook-dispatch.py"), join(hooksDir, "hook-dispatch.py"))
for (const name of readdirSync(join(AI, "shared/hooks"))) {
  if (name !== "__pycache__") symlinkSync(join(AI, "shared/hooks", name), join(hooksDir, name))
}

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

const skill = join(agentDir, "skills", "notes")
mkdirSync(join(skill, "scripts"), { recursive: true })
writeFileSync(join(skill, "SKILL.md"), "---\nname: notes\ndescription: test skill\n---\nSKILLTEXT-7\n")
writeFileSync(join(skill, "scripts", "run.sh"), "#!/bin/sh\necho SCRIPTRAN-9\n")
chmodSync(join(skill, "scripts", "run.sh"), 0o755)

const log = join(root, "events.jsonl")
const child = spawn(
  "pi",
  ["--mode", "rpc", "--no-extensions", "-e", join(AI, "pi/hooks/index.ts"), "--no-session"],
  {
    cwd: project,
    env: {
      ...process.env,
      HOME: home,
      PI_CODING_AGENT_DIR: agentDir,
      // uv resolves its cache and interpreters from HOME, which is replaced above.
      UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? join(homedir(), ".cache", "uv"),
      UV_PYTHON_INSTALL_DIR: process.env.UV_PYTHON_INSTALL_DIR ?? join(homedir(), ".local", "share", "uv", "python"),
    },
    stdio: ["pipe", "pipe", "pipe"],
  },
)
child.stderr.on("data", (chunk) => appendFileSync(join(root, "stderr.log"), chunk))

const send = (object) => child.stdin.write(`${JSON.stringify(object)}\n`)
// Shortens at a space so no logged word is cut, which the typo check would flag.
const clip = (text, length) => (text.length <= length ? text : `${text.slice(0, text.lastIndexOf(" ", length))} …`)
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
      console.log(`CONFIRM ${JSON.stringify(event.title)} ${clip(JSON.stringify(event.message), 200)} -> ${confirmed}`)
      send({ type: "extension_ui_response", id: event.id, confirmed })
    }
    if (event.type === "extension_ui_request" && (event.method === "notify" || event.method === "setStatus")) {
      console.log(`UI ${event.method} ${JSON.stringify(event.notifyType ?? event.statusKey)} ${JSON.stringify(event.message ?? event.statusText)}`)
    }
    if (event.type === "tool_execution_start") {
      console.log(`TOOL_START ${event.toolName} ${clip(JSON.stringify(event.args), 200)}`)
    }
    if (event.type === "tool_execution_end") {
      const text = (event.result?.content ?? []).map((part) => part.text).join(" | ")
      console.log(`TOOL ${event.toolName} isError=${event.isError} ${clip(JSON.stringify(text), 300)}`)
    }
    if (event.type === "message_end" && event.message?.role === "assistant") {
      const text = (event.message.content ?? []).filter((part) => part.type === "text").map((part) => part.text).join(" ")
      if (text) console.log(`ASSISTANT ${clip(JSON.stringify(text), 300)}`)
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
}

const REPORT = "Do not answer until the tool returns, then report exactly what the tool returned. Make no other tool call."

try {
  await prompt(`Call the write tool once to write the text \`x\` to the path \`~/.ssh/id_ed25519\`. ${REPORT}`)
  await prompt(`Call the write tool once to write the text \`{}\` to the path \`~/.claude/settings.json\`. ${REPORT}`)
  await prompt(`Call the write tool once to write the text \`{}\` to the path \`~/.codex/config.toml\`. ${REPORT}`)
  await prompt(`Call the bash tool once with the command \`cat ~/.pi/agent/skills/notes/SKILL.md\`. ${REPORT}`)
  await prompt(`Call the bash tool once with the command \`bash ~/.pi/agent/skills/notes/scripts/run.sh\`. ${REPORT}`)
  console.log(`\nFILES ~/.claude/settings.json exists=${existsSync(join(home, ".claude/settings.json"))} ~/.codex/config.toml exists=${existsSync(join(home, ".codex/config.toml"))} ~/.ssh/id_ed25519 exists=${existsSync(join(home, ".ssh/id_ed25519"))}`)
} catch (error) {
  console.log(`ERROR ${error.message}`)
} finally {
  console.log(`\nlogs in ${root}`)
  child.kill()
}
