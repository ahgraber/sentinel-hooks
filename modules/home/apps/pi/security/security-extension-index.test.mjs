import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { cp, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const SOURCE_DIR = dirname(fileURLToPath(import.meta.url))

let temporaryDirectory
let validateBashCommand

before(async () => {
  temporaryDirectory = await mkdtemp(join(tmpdir(), "pi-security-extension-"))
  const packageDirectory = join(temporaryDirectory, "node_modules", "smol-toml")

  await mkdir(packageDirectory, { recursive: true })
  await writeFile(
    join(packageDirectory, "package.json"),
    JSON.stringify({
      name: "smol-toml",
      type: "module",
      exports: "./index.js",
    }),
  )
  await writeFile(join(packageDirectory, "index.js"), "export function parse() { return {} }\n")
  await writeFile(join(temporaryDirectory, "block-destructive-ops-patterns.toml"), "")
  await cp(
    join(SOURCE_DIR, "security-extension-index.ts"),
    join(temporaryDirectory, "security-extension-index.ts"),
  )

  const { default: registerSecurityExtension } = await import(
    `${pathToFileURL(join(temporaryDirectory, "security-extension-index.ts")).href}?test=${Date.now()}`
  )
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

  validateBashCommand = (command) =>
    toolCallHandler(
      {
        toolName: "bash",
        toolCallId: "validator-test",
        input: { command },
      },
      {
        hasUI: false,
        ui: {
          confirm: async () => false,
          notify() {},
        },
      },
    )
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
