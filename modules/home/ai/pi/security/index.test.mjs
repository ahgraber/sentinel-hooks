import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { cp, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises"
import { homedir, tmpdir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const SOURCE_DIR = dirname(fileURLToPath(import.meta.url))

let temporaryDirectory
let validateBashCommand
let isSensitivePath
let isProtectedPath
let foldsCase
let callTool
let callToolWith

// Not a general TOML parser: it covers only the shapes this repo's manifests use
// (string and pair arrays, quoted values, `[section]` and `[[array-of-tables]]`
// headers, `#` comments), so the suite can read the real guarded-paths.toml without
// a network fetch or npm install. Production uses smol-toml itself.
const SMOL_TOML_STUB = `
function stripComments(text) {
  return text
    .split("\\n")
    .map((line) => {
      const idx = line.indexOf("#")
      return idx === -1 ? line : line.slice(0, idx)
    })
    .join("\\n")
}

function splitOnTopLevel(text, separator) {
  const items = []
  let depth = 0
  let current = ""
  for (const ch of text) {
    if (ch === "[") depth += 1
    if (ch === "]") depth -= 1
    if (ch === separator && depth === 0) {
      if (current.trim()) items.push(current.trim())
      current = ""
    } else {
      current += ch
    }
  }
  if (current.trim()) items.push(current.trim())
  return items
}

function parseValue(raw) {
  const trimmed = raw.trim()
  if (trimmed.startsWith("[")) {
    return splitOnTopLevel(trimmed.slice(1, -1), ",").map(parseValue)
  }
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1)
  }
  return trimmed
}

export function parse(text) {
  const statements = splitOnTopLevel(stripComments(text), "\\n")
  const result = {}
  let current = result
  for (const statement of statements) {
    const arrayTableMatch = statement.match(/^\\[\\[([^\\]]+)\\]\\]$/)
    if (arrayTableMatch) {
      const key = arrayTableMatch[1].trim()
      if (!result[key]) result[key] = []
      const table = {}
      result[key].push(table)
      current = table
      continue
    }
    const tableMatch = statement.match(/^\\[([^\\]]+)\\]$/)
    if (tableMatch) {
      const key = tableMatch[1].trim()
      result[key] = {}
      current = result[key]
      continue
    }
    const eq = statement.indexOf("=")
    if (eq === -1) continue
    current[statement.slice(0, eq).trim()] = parseValue(statement.slice(eq + 1))
  }
  return result
}
`

const MANIFEST_SOURCE = join(SOURCE_DIR, "..", "..", "shared", "hooks", "guarded-paths.toml")

// The extension's own modules. A fixture root is loadable only with all of them,
// because the relative imports between them resolve inside the copy.
const EXTENSION_MODULES = [
  "index.ts",
  "bash-validator.ts",
  "dangerous-bash.ts",
  "destructive-ops.ts",
  "guarded-paths.ts",
  "manifest.ts",
  "paths.ts",
  "precommit.ts",
  "secrets.ts",
  "sensitive-paths.ts",
  "shell-words.ts",
]

// A fixture root is a whole extension directory: the modules, the two TOML inputs
// read at load, and a smol-toml stand-in. Pass `manifest` to substitute the
// guarded-paths text; omit it to copy the real one. `resolveSymlinks` matters only
// where a test compares against paths the extension stored resolved, since the
// macOS temp root is itself a link.
// `manifest: null` leaves the file out entirely, and `tomlStub` replaces the
// parser, which is the only way to reach the extension's parse-failure arm: the
// stub above is lenient by design and never throws on the shapes this repo uses.
async function createExtensionRoot(prefix, { manifest, resolveSymlinks = false, tomlStub = SMOL_TOML_STUB } = {}) {
  const created = await mkdtemp(join(tmpdir(), prefix))
  const root = resolveSymlinks ? await realpath(created) : created
  const packageDirectory = join(root, "node_modules", "smol-toml")

  await mkdir(packageDirectory, { recursive: true })
  await writeFile(
    join(packageDirectory, "package.json"),
    JSON.stringify({ name: "smol-toml", type: "module", exports: "./index.js" }),
  )
  await writeFile(join(packageDirectory, "index.js"), tomlStub)
  await writeFile(join(root, "block-destructive-ops-patterns.toml"), "")

  if (manifest === undefined) {
    await cp(MANIFEST_SOURCE, join(root, "guarded-paths.toml"))
  } else if (manifest !== null) {
    await writeFile(join(root, "guarded-paths.toml"), manifest)
  }

  for (const module of EXTENSION_MODULES) {
    await cp(join(SOURCE_DIR, module), join(root, module))
  }

  return root
}

// Each root is a distinct path, so its module graph is already distinct; the query
// only separates repeated imports of the same root.
function loadExtension(root, tag) {
  return import(`${pathToFileURL(join(root, "index.ts")).href}?test=${tag}`)
}

before(async () => {
  temporaryDirectory = await createExtensionRoot("pi-security-extension-")

  const extension = await loadExtension(temporaryDirectory, Date.now())
  const registerSecurityExtension = extension.default
  isSensitivePath = extension.isSensitivePath
  isProtectedPath = extension.isProtectedPath
  foldsCase = extension.FOLDS_CASE
  const handlers = new Map()
  const pi = {
    on(eventName, handler) {
      const eventHandlers = handlers.get(eventName) ?? []
      eventHandlers.push(handler)
      handlers.set(eventName, eventHandlers)
    },
  }

  registerSecurityExtension(pi)
  const toolCallHandler = handlers.get("tool_call")?.[0]
  assert.ok(toolCallHandler, "security extension did not register its tool_call handler")

  callToolWith = (toolName, input, ctx) =>
    toolCallHandler({ toolName, toolCallId: "validator-test", input }, ctx)
  callTool = (toolName, input) =>
    callToolWith(toolName, input, {
      hasUI: false,
      ui: {
        confirm: async () => false,
        notify() {},
      },
    })
  validateBashCommand = (command) => callTool("bash", { command })
})

after(async () => {
  await rm(temporaryDirectory, { force: true, recursive: true })
})

const BLOCKED_COMMANDS = [
  ["heredoc", "cat <<EOF\nhello\nEOF", "Heredoc bodies"],
  ["double-quoted bang", 'echo "value!=expected"', "double-quoted string"],
  ["unquoted bang", "echo !history", "unquoted '!word'"],
  ["unquoted flake reference", "nix build .#host", "Quote nix flake refs"],
  ["git parent caret", "git show abc123^", "git commit hash"],
  ["unquoted flag glob", "rg --glob=*.py pattern", "Quote the value"],
  ["Nix store glob", "ls /nix/store/*", "Globbing /nix/store"],
  ["ripgrep recursive flag", "rg -lr pattern", "recursive by default"],
  ["ripgrep replace flag", "rg -r pattern", "recursive by default"],
  ["ripgrep attached replacement", "rg -r=replacement pattern", "recursive by default"],
  ["direct Python", "ENV=value python3.12 script.py", "Use 'uv run'"],
  ["absolute Python", "/usr/bin/python3 script.py", "Use 'uv run'"],
  ["Python after separator", "echo ready && python script.py", "Use 'uv run'"],
  ["pip install", "pip install package", "Use 'uv add'"],
  ["pip download", "pip download package", "Use 'uv add'"],
  ["pip3 uninstall", "pip3 uninstall package", "Use 'uv add'"],
  ["pip3 download", "pip3 download package", "Use 'uv add'"],
  ["direct pytest", "pytest tests", "Use 'uv run pytest'"],
  ["direct py.test", "py.test tests", "Use 'uv run pytest'"],
  ["pre-commit", "pre-commit run --all-files", "Use 'prek run'"],
  ["direct git commit", "git -C /repo commit -m 'unsigned'", "Use 'git agent-commit'"],
  ["git config then commit", "git -c user.name=Agent commit -m 'unsigned'", "Use 'git agent-commit'"],
  ["git long option then commit", "git --git-dir=/repo/.git commit -m 'unsigned'", "Use 'git agent-commit'"],
  ["git after separator", "echo ready && git commit --amend", "Use 'git agent-commit'"],
  ["command-wrapped git commit", "command git --no-pager commit --amend", "Use 'git agent-commit'"],
]

test("Pi blocks every active Claude validator rule", async (t) => {
  for (const [name, command, expectedReason] of BLOCKED_COMMANDS) {
    await t.test(name, async () => {
      const result = await validateBashCommand(command)

      assert.equal(result?.block, true)
      assert.match(result.reason, new RegExp(expectedReason.replaceAll(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"))
    })
  }
})

const ALLOWED_COMMANDS = [
  ["here-string", "cat <<<hello"],
  ["single-quoted bang", "echo 'value!=expected'"],
  ["comparison bang", "[[ value != expected ]]"],
  ["quoted flake reference", "nix build '.#host'"],
  ["git parent with tilde", "git show abc123~1"],
  ["quoted flag glob", "rg --glob='*.py' pattern"],
  ["explicit Nix store path", "ls /nix/store/aaaaaaaa-package"],
  ["supported ripgrep flag", "rg -n pattern"],
  ["uv Python", "uv run python script.py"],
  ["pip query", "pip list"],
  ["pip3 query", "pip3 show package"],
  ["uv add", "uv add package"],
  ["uv pip", "uv pip install package"],
  ["uv run with", "uv run --with package script.py"],
  ["uv pytest", "uv run pytest tests"],
  ["uv py.test", "uv run py.test tests"],
  ["prek", "prek run --all-files"],
  ["agent commit", "git agent-commit -m 'signed'"],
  ["commit config key", "git -c commit.gpgsign=true status"],
  ["commit option value", "git -C commit status"],
  ["non-commit long option", "git --git-dir=/repo/.git status"],
  ["commit search argument", "rg -n 'git commit' ."],
  ["commit echo argument", "echo 'git commit is prohibited'"],
  ["grep", "grep pattern file"],
  ["find", "find . -name '*.py'"],
]

test("Pi allows every Claude validator alternative", async (t) => {
  for (const [name, command] of ALLOWED_COMMANDS) {
    await t.test(name, async () => {
      const result = await validateBashCommand(command)

      assert.equal(result, undefined)
    })
  }
})

test("Pi reports every matching Claude validator issue", async () => {
  const result = await validateBashCommand("rg -rn pattern; python script.py")

  assert.equal(result?.block, true)
  assert.match(result.reason, /recursive by default/)
  assert.match(result.reason, /Use 'uv run'/)
})

// This port cannot import the Python it mirrors, so a shared table of verdicts
// is what keeps the two from drifting. The Python suite asserts the same file.
const SENSITIVE_PATH_CASES = JSON.parse(
  await readFile(join(SOURCE_DIR, "..", "..", "shared", "tests", "sensitive-path-cases.json"), "utf8"),
).cases

test("Pi agrees with the shared zero-access verdicts", async (t) => {
  assert.ok(SENSITIVE_PATH_CASES.length > 20, "shared case table did not load")

  for (const { path, blocked, why } of SENSITIVE_PATH_CASES) {
    await t.test(`${blocked ? "blocks" : "allows"} ${path}`, () => {
      assert.equal(isSensitivePath(path.replace(/^~/, homedir())), blocked, why)
    })
  }
})

const GUARDED_PATH_CASES = JSON.parse(
  await readFile(join(SOURCE_DIR, "..", "..", "shared", "tests", "guarded-path-cases.json"), "utf8"),
).cases

test("Pi agrees with the shared tamper-protection verdicts", async (t) => {
  assert.ok(GUARDED_PATH_CASES.length > 20, "shared case table did not load")

  for (const { path, blocked, why } of GUARDED_PATH_CASES) {
    await t.test(`${blocked ? "blocks" : "allows"} ${path}`, () => {
      assert.equal(isProtectedPath(path.replace(/^~/, homedir())), blocked, why)
    })
  }
})

// A static table cannot express a link, so this case builds one. The Python
// suite covers the same ground in shared/tests/test_tamper_path_resolution.py.
test("Pi judges an instruction-named link by where it leads", async (t) => {
  const checkout = join(temporaryDirectory, "checkout")
  const hooks = join(checkout, "modules", "home", "ai", "shared", "hooks")
  const instructions = join(hooks, "instructions")

  await mkdir(instructions, { recursive: true })
  // A `<repo>` declaration is judged against the repository containing the
  // path, so the fixture has to be one.
  await mkdir(join(checkout, ".git"), { recursive: true })
  await writeFile(join(hooks, "block-destructive-ops.py"), "original\n")
  await writeFile(join(instructions, "00-style.md"), "prompt text\n")
  await symlink("../block-destructive-ops.py", join(instructions, "notes.md"))
  await symlink("../block-secrets.py", join(instructions, "dangling.md"))

  await t.test("allows genuine instruction markdown", () => {
    assert.equal(isProtectedPath(join(instructions, "00-style.md")), false)
  })

  await t.test("blocks a link that leads to a hook", () => {
    assert.equal(isProtectedPath(join(instructions, "notes.md")), true)
  })

  await t.test("blocks a link whose target does not exist yet", () => {
    assert.equal(isProtectedPath(join(instructions, "dangling.md")), true)
  })
})

// A class addition in a substituted manifest must reach this extension with no code
// edit; the Python suite pins the same property in test_guarded_paths_manifest.py.
test("Pi guards a path added to a manifest class in a substituted copy", async () => {
  // The added store is named so no shape heuristic can reach it; only the manifest
  // declaration can, which is what makes the assertions below evidence of the wiring.
  const manifestText = await readFile(MANIFEST_SOURCE, "utf8")
  const substitutedManifest = manifestText.replace(
    '"~/.pi/agent/auth.json"]',
    '"~/.pi/agent/auth.json", "~/.example/session.dat"]',
  )
  assert.notEqual(substitutedManifest, manifestText, "the manifest text did not change")

  const substitutedDirectory = await createExtensionRoot("pi-security-extension-manifest-", {
    manifest: substitutedManifest,
  })
  const extension = await loadExtension(substitutedDirectory, Date.now())

  const added = join(homedir(), ".example", "session.dat")
  try {
    assert.equal(extension.isProtectedPath(added), true, "the added store is not write-gated")
    assert.equal(extension.isSensitivePath(added), true, "the added store is not read-gated")
    assert.equal(extension.isProtectedPath(join(homedir(), ".example", "other-file.json")), false)
    assert.equal(extension.isSensitivePath(join(homedir(), ".example", "other-file.json")), false)
  } finally {
    await rm(substitutedDirectory, { force: true, recursive: true })
  }
})

// A store added to the manifest must not land with only half its protection. The
// Python suite pins the same property in test_guarded_paths_manifest.py.
test("Pi refuses every declared credential store at both gates", async () => {
  const manifestText = await readFile(MANIFEST_SOURCE, "utf8")
  const declared = [...manifestText.matchAll(/"(~\/[^"]*)"/g)]
    .map((m) => m[1])
    .filter((p) => p.endsWith("auth.json") || p.endsWith(".credentials.json"))

  assert.ok(declared.length >= 3, `expected the manifest to declare credential stores, found ${declared.length}`)
  for (const path of declared) {
    const absolute = path.replace(/^~/, homedir())
    assert.equal(isSensitivePath(absolute), true, `${path} is not read-gated`)
    assert.equal(isProtectedPath(absolute), true, `${path} is not write-gated`)
  }
})

// Every declaratively managed file has this shape — inside a guarded directory as
// written, resolving outside it, because Home Manager writes the real file into the
// Nix store and sops-nix into its secrets mount. Judging only the resolved spelling
// would leave the guarded directory holding nothing either side can see. Pinned on
// the Python side by shared/tests/test_guarded_paths.py.
test("Pi guards a file that leads out of a guarded directory", async () => {
  // Home is supplied, not borrowed: the extension builds its location list from
  // homedir() at load, and this must not write into the operator's real guarded dirs.
  // Resolved up front because on macOS the temp root is itself a symlink and the
  // extension stores locations resolved, so an unresolved path would miss spuriously.
  const sandbox = await createExtensionRoot("pi-security-extension-containment-", { resolveSymlinks: true })
  const fakeHome = join(sandbox, "home")
  const store = join(sandbox, "store")

  // Named to match no declared fragment, so containment is the only thing that can
  // catch it; the fragment check would otherwise mask the behaviour under test.
  await mkdir(store, { recursive: true })
  await writeFile(join(store, "session-abc123.jsonl"), "{}\n")
  await mkdir(join(fakeHome, ".claude", "projects"), { recursive: true })
  const deployed = join(fakeHome, ".claude", "projects", "session.jsonl")
  await symlink(join(store, "session-abc123.jsonl"), deployed)

  const realHome = process.env.HOME
  process.env.HOME = fakeHome
  try {
    const extension = await loadExtension(sandbox, `containment-${Date.now()}`)
    assert.equal(extension.isProtectedPath(deployed), true)
  } finally {
    process.env.HOME = realHome
    await rm(sandbox, { force: true, recursive: true })
  }
})

// A path written through a symlinked home resolves somewhere the guarded location
// list would not otherwise name. The shared verdict tables cannot reach this — they
// run against whatever home the suite has — so it is pinned here and by
// `_home_prefixes` in guarded_paths.py.
test("Pi guards a path written through a symlinked home directory", async () => {
  const sandbox = await createExtensionRoot("pi-security-extension-homelink-", { resolveSymlinks: true })
  const realHome = join(sandbox, "real-home")
  const homeLink = join(sandbox, "home")
  const store = join(sandbox, "store")

  await mkdir(join(realHome, ".claude", "projects"), { recursive: true })
  await mkdir(store, { recursive: true })
  await symlink(realHome, homeLink)
  const target = join(store, "session-abc.jsonl")
  await writeFile(target, "")
  await symlink(target, join(realHome, ".claude", "projects", "session.jsonl"))

  const realEnvHome = process.env.HOME
  process.env.HOME = homeLink
  try {
    const extension = await loadExtension(sandbox, `homelink-${Date.now()}`)
    assert.equal(extension.isProtectedPath(join(homeLink, ".claude", "projects", "session.jsonl")), true)
  } finally {
    process.env.HOME = realEnvHome
    await rm(sandbox, { force: true, recursive: true })
  }
})

test("Pi judges a guarded location by where a path leads", async (t) => {
  const alias = join(temporaryDirectory, "claude-alias")
  await symlink(join(homedir(), ".claude"), alias)

  await t.test("blocks a guarded file reached through a link", () => {
    assert.equal(isProtectedPath(join(alias, "settings.json")), true)
  })

  await t.test("blocks a file that does not exist yet under that link", () => {
    assert.equal(isProtectedPath(join(alias, "settings.local.json")), true)
  })

  // Case folding is a property of the volume, not the OS, so the expected verdict
  // follows the extension's own probe rather than a platform check.
  await t.test("blocks a case variant where the filesystem folds case", () => {
    assert.equal(isProtectedPath(join(homedir(), ".CLAUDE", "settings.json")), foldsCase)
  })
})

// Write protection is the boundary; concealment is not. The Linux sandbox cannot
// express a read-deny over these paths, so blocking reads here would be enforcement
// only one agent applies.
test("Pi lets a protected path be read", async (t) => {
  const settings = join(homedir(), ".claude", "settings.json")

  await t.test("allows a read", async () => {
    assert.equal(await callTool("read", { file_path: settings }), undefined)
  })

  await t.test("still blocks a write", async () => {
    const result = await callTool("write", { file_path: settings })

    assert.equal(result?.block, true)
  })

  await t.test("still blocks an edit", async () => {
    const result = await callTool("edit", { file_path: settings })

    assert.equal(result?.block, true)
  })
})

// The no-UI arm is pinned above by "still blocks a write".
test("Pi gates an enforcement mutation on the user's confirmation", async (t) => {
  const settings = join(homedir(), ".claude", "settings.json")
  const uiContext = (answer, prompts) => ({
    hasUI: true,
    ui: {
      confirm: async (title, message) => {
        prompts.push({ title, message })
        return answer
      },
      notify() {},
    },
  })

  await t.test("proceeds when the user approves", async () => {
    const prompts = []
    const result = await callToolWith("write", { file_path: settings }, uiContext(true, prompts))

    assert.equal(result, undefined)
    assert.equal(prompts.length, 1)
    assert.ok(prompts[0].message.includes("settings.json"), "the prompt names the file")
    assert.ok(prompts[0].message.includes("enforcement"), "the prompt states what the file is")
  })

  await t.test("blocks when the user declines", async () => {
    const prompts = []
    const result = await callToolWith("write", { file_path: settings }, uiContext(false, prompts))

    assert.equal(result?.block, true)
    assert.equal(prompts.length, 1)
  })
})

test("Pi refuses a credential write without ever prompting", async (t) => {
  const credentials = [
    join(homedir(), ".claude", ".credentials.json"),
    join(homedir(), ".codex", "auth.json"),
    join(homedir(), ".pi", "agent", "auth.json"),
  ]

  for (const credential of credentials) {
    await t.test(`blocks ${credential} with a user attached, confirm never called`, async () => {
      const prompts = []
      const result = await callToolWith(
        "write",
        { file_path: credential },
        {
          hasUI: true,
          ui: {
            confirm: async (title, message) => {
              prompts.push({ title, message })
              return true
            },
            notify() {},
          },
        },
      )

      assert.equal(result?.block, true)
      assert.ok(result.reason.includes("credential"), result.reason)
      assert.equal(prompts.length, 0)
    })

    await t.test(`blocks ${credential} without a user attached`, async () => {
      const result = await callTool("write", { file_path: credential })

      assert.equal(result?.block, true)
      assert.ok(result.reason.includes("credential"), result.reason)
    })
  }
})

test("Pi withholds the markdown carve-out from a mixed command", async (t) => {
  const instruction = join(homedir(), ".claude", "hooks", "instructions", "00-response-style.md")
  const enforcement = join(homedir(), ".codex", "config.toml")

  await t.test("blocks when an enforcement path rides along", async () => {
    const result = await validateBashCommand(`sed -i '' s/x/y/ ${enforcement} && cat ${instruction}`)

    assert.equal(result?.block, true)
  })

  await t.test("blocks regardless of which path comes last", async () => {
    const result = await validateBashCommand(`cat ${instruction} && sed -i '' s/x/y/ ${enforcement}`)

    assert.equal(result?.block, true)
  })

  await t.test("allows a command naming only instruction markdown", async () => {
    const result = await validateBashCommand(`cat ${instruction}`)

    assert.equal(result, undefined)
  })
})

// A root loaded on its own handlers, so a fixture can drive session_start as well
// as tool_call. The shared `before` hook keeps only the tool_call handler.
async function registerExtension(root, tag) {
  const extension = await loadExtension(root, tag)
  const handlers = new Map()

  extension.default({
    on(eventName, handler) {
      const registered = handlers.get(eventName) ?? []
      registered.push(handler)
      handlers.set(eventName, registered)
    },
  })

  return {
    sessionStart: handlers.get("session_start")?.[0],
    toolCall: handlers.get("tool_call")?.[0],
  }
}

// Throws on the guarded-paths text only. The fixture's other TOML input is
// empty, and failing that one too would raise an unrelated error from the
// destructive-ops loader rather than the arm under test.
const THROWING_TOML_STUB = `
export function parse(text) {
  if (text.trim() === "") return {}
  throw new SyntaxError("Invalid TOML document: expected a table header")
}
`

// A manifest that will not load leaves every guarded structure empty, so the
// extension is judging nothing. The Python hooks answer that with a Warn; the
// extension has no per-call reporting channel, so it notifies once instead. What
// both must never do is check nothing quietly. The Python suite pins the same
// property in test_guarded_paths_manifest.py.
test("Pi reports a manifest it cannot load and lets the call through", async (t) => {
  const arms = [
    ["missing", { manifest: null }],
    ["unparsable", { tomlStub: THROWING_TOML_STUB }],
  ]

  for (const [label, options] of arms) {
    await t.test(`notifies and proceeds when the manifest is ${label}`, async () => {
      const root = await createExtensionRoot(`pi-security-extension-${label}-`, options)

      try {
        const { sessionStart, toolCall } = await registerExtension(root, `${label}-${Date.now()}`)
        assert.ok(sessionStart, "the extension registered no session_start handler")

        const notices = []
        await sessionStart(
          {},
          { hasUI: true, ui: { confirm: async () => false, notify: (message, level) => notices.push({ message, level }) } },
        )

        const reported = notices.filter((notice) => notice.message.includes("guarded-paths.toml"))
        assert.equal(reported.length, 1, `expected one manifest notice, saw ${JSON.stringify(notices)}`)
        assert.equal(reported[0].level, "error")

        // Proceeding is the deliberate half of the contract: the OS sandbox and
        // the permission layers never read the manifest and keep enforcing.
        const result = await toolCall(
          { toolName: "write", toolCallId: "manifest-failure", input: { file_path: join(homedir(), ".claude", "settings.json") } },
          { hasUI: false, ui: { confirm: async () => false, notify() {} } },
        )
        assert.equal(result, undefined, "a hook that cannot judge must not refuse")
      } finally {
        await rm(root, { force: true, recursive: true })
      }
    })
  }
})

// A refusal that only explains itself leaves the agent free to look for another
// way, which is what GateResponse's second clause exists to stop.
test("Pi's enforcement refusals close off the route around them", async (t) => {
  const settings = join(homedir(), ".claude", "settings.json")
  const declining = { hasUI: true, ui: { confirm: async () => false, notify() {} } }
  const unattended = { hasUI: false, ui: { confirm: async () => true, notify() {} } }

  const cases = [
    ["a credential write", join(homedir(), ".codex", "auth.json"), declining],
    ["an enforcement write with no user attached", settings, unattended],
    ["an enforcement write the user declined", settings, declining],
  ]

  for (const [label, path, ctx] of cases) {
    await t.test(label, async () => {
      const result = await callToolWith("write", { file_path: path }, ctx)

      assert.equal(result?.block, true)
      assert.match(result.reason, /AI INSTRUCTIONS:/, "the refusal carries no agent instruction")
      assert.match(result.reason, /Do NOT look for an alternative/, "the refusal does not close off other routes")
      assert.match(result.reason, /report to the user/, "the refusal does not send the decision back to the user")
    })
  }
})
