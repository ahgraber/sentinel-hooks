# Design: guardrail-ask-gate

## Context

The previous change built the machinery this one uses: one tamper hook for every agent, a canonical decision vocabulary (`Allow`/`Warn`/`Block`/`Ask`), and a helper that encodes a decision for the invoking agent.
This change alters one judgement — tamper writes become `Ask` for three of the four protected classes — and extends the encoder to carry it.

Layer interaction facts the design rests on, checked against agent documentation on 2026-08-26/27:

- **Claude Code**: a hook `ask` escalates directly to the user and the permission rules are not consulted, so the user sees one dialog, and an "always allow" answer never silences the hook.
  The `permissions.ask` entries for the same paths remain as the fallback for a hook that fails open and for tools the hook does not cover.
- **Copilot**: the hooks reference documents `permissionDecision: "ask"` as showing a hook-permission prompt, with non-interactive surfaces treating it as a denial.
  The documented deny shape is a top-level `permissionDecision` object, not Claude's `hookSpecificOutput` wrapper, so the exact ask shape is settled empirically.
- **Codex**: `permissionDecision: "ask"` is parsed, marked a failed hook run, and the tool call proceeds — emitting it is fail-open.
  Codex's own ask surface is the sandbox escalation prompt behind `approval_policy = "on-request"`, filtered by the `auto_review` reviewer.
- **Pi**: the extension API prompts through `ctx.ui.confirm`, already used by the port's destructive-ops ask rules.

## Decisions

### Decision: AskIsDecidedByProtectedClass

**Chosen:** the gate's outcome is a function of the protected class — deployed enforcement, repository sources, and per-user configuration ask; agent credentials block.

**Rationale:** the classes already exist in the spec and separate exactly what a maintainer edits deliberately from what no legitimate flow touches.
A credential prompt has no approvable case, so offering one only trains approval of the request that should never come.

**Alternatives considered:**

- Gate everything, credentials included: simpler rule, and a habituation surface pointed at the worst target
- Per-path modes declared in data, as `block-destructive-ops-patterns.toml` does: flexible, but adds a policy file to the guarded set for a distinction with exactly two values

**Consequence:** the declarations must say which class an entry is in.
Today `GUARDED_FILES` is flat; the credential entries (`~/.codex/auth.json` is the only current member) move to their own declaration so the class is structural rather than inferred.

### Decision: AskDegradesToBlockUnderCodex

**Chosen:** under Codex the gate refuses, as it does today; the prompt encoding is never emitted there.

**Rationale:** Codex treats the prompt JSON as a failed hook and lets the call proceed, so the only safe encodings are exit 0 and exit 2.
Refusal preserves the property the ask records — the call must not proceed on the agent's judgement alone.
The cost is accepted and known: the refusal ends the tool call before the sandbox is consulted, so Codex's own escalation prompt never surfaces for hook-covered tools, and in-session guardrail maintenance stays unavailable under Codex.

**Alternatives considered:**

- **Delegate to the sandbox (recorded as a future option, not taken):** degrade the tamper `Ask` to `Allow` under Codex and let the write hit the read-only sandbox denial, which surfaces an escalation prompt the reviewer routes to the user.
  This is a real ask, but it makes the gate's floor the Codex sandbox rather than the hook: it is safe exactly when the sandbox's guarded set matches the hook's, which the conformance test pins but this change does not want to bet on, and it depends on an unverified behaviour (whether an `apply_patch` denial produces an escalation prompt or a bare failure).
  Revisit alongside the upstream work below.
- Emit the prompt JSON and hope: fail-open by documented behaviour; forbidden by `ExitCodes`.

**Upstream:** native `ask` support for Codex PreToolUse hooks is tracked in feature request openai/codex#28437; PR openai/codex#20702 sketches the semantics (`ask` may tighten a decision into explicit approval, never waive policy).
When it ships, Codex joins the ask-capable set and both this decision and the delegate option become moot.

### Decision: CopilotJoinsAskCapableOnEvidence

**Chosen:** Copilot is added to the ask-capable set only after a cross-validation probe shows the real surface holding the tool call on the hook's ask.

**Rationale:** the capability is documented but young, and the documentation is ambiguous about the JSON shape (top-level `permissionDecision` versus Claude's `hookSpecificOutput` wrapper).
Copilot reaches the shared hooks through its adapter, so the probe must run through the adapter against the VS Code surface, and must also record whether the user sees one dialog or two — Copilot has its own tool-approval prompt, and a doubled prompt would be a UX regression worth knowing before enabling.

**Alternatives considered:**

- Enable from the documentation alone: if the surface ignores the ask, the fallback is Copilot's fail-closed handling of hook output, which is survivable but was not chosen knowingly
- Leave Copilot on block permanently: forfeits a documented capability on the one agent with no permission layer of its own

**Outcome (probe run 2026-08-27, record in `.verify/probes/results.md`):** the surface honours the wrapped `hookSpecificOutput` shape for file-mutation tools — the reason is displayed and the call held — and ignores both shapes for the shell tool, where the marked command proceeded.
An ignored ask is fail-open, so the shell tool gets the refusal encoding, exactly as Codex does.

**Consequence:** ask capability is a property of the (agent, tool) pairing, not of the agent alone.
The encoder's capability check takes the tool name, supplied by the calling hook, and the flat documented-for-CLI shape is not used anywhere.
The shell-side degradation costs little on this surface: every terminal command already receives Copilot's built-in confirmation, generically.

### Decision: PiExpressesAskAsConfirm

**Chosen:** the Pi port's tamper branch calls `ctx.ui.confirm`, and blocks where `ctx.hasUI` is false; its credential handling stays a block.

**Rationale:** this is the pattern the same extension already uses for destructive-ops `ask` rules and credential-directory confirmations, so the gate inherits proven behaviour rather than a new mechanism.

**Alternatives considered:**

- Route Pi through the shared encoder: Pi is not a hook consumer; its port is TypeScript with its own conformance tests, and the encoder's exit-code vocabulary means nothing to the extension API

### Decision: NoRename

**Chosen:** the hook keeps its filename and the capability keeps its name.

**Rationale:** `block-hook-tampering.py` is named in hook registrations across three agents, in trusted-hash entries, in the Copilot adapter's dispatch table, and in sandbox configuration.
A rename touches every one of those, and each is a place where a miss silently drops protection.
"Block" also remains accurate: the gate blocks whenever no prompt can be shown, and for credentials always.

**Alternatives considered:**

- Rename to `guard-hook-tampering.py`: better name, and the migration risk buys no behaviour

### Decision: ReviewerRoutesGuardrailEscalations

**Chosen:** the Codex `auto_review` policy clause covering security-hook modification changes from flat denial to the `USER_APPROVAL_REQUIRED` routing the policy already uses for network destinations, in both platform TOMLs.

**Rationale:** the hook's refusal preempts the escalation path for the tools it covers, so this clause rarely fires — but "rarely" is exactly the fallback case: a route the hook does not intercept should end at the user, not at an automated denial the posture no longer intends.
The edit also positions the config correctly for the delegate option and for upstream `ask` support.

**Alternatives considered:**

- Leave the flat denial: contradicts the posture the north star now states, in the one layer that would keep enforcing it

### Decision: EntryPointRestored

**Chosen:** `main()` is re-enabled in the tamper hook as part of this change.

**Rationale:** the disabled entry point is the motivating evidence — the unconditional block was routed around by disabling the guard.
The gate this change builds is the mechanism that makes disabling unnecessary, so the change that introduces the gate is the change that turns the guard back on.

### Decision: ManifestIsTomlBesideTheHooks

**Chosen:** the guarded surface is declared once in `guarded-paths.toml` in `modules/home/ai/shared/hooks/`, restricted to strings, arrays, and tables.

**Rationale:** both runtime consumers already parse TOML from this directory (`block-destructive-ops-patterns.toml`), so no new dependency or location is introduced, and the hooks directory is already deployed to every agent and already guarded.

**Alternatives considered:**

- JSON: no comments, and the classes deserve rationale next to the entries
- A Nix expression: evaluable by the flake but not by a hook at invocation time without spawning `nix`, which a PreToolUse hook cannot afford

**Consequence:** the manifest names itself in its own gated sources, and the deployed spellings (`~/.claude/hooks/guarded-paths.toml`, `~/.codex/hooks/guarded-paths.toml`, `~/.copilot/hooks/guarded-paths.toml`) ride on the existing hook-directory declarations without new entries.

Sections, mirroring the structure the gate gives the code:

```toml
[gated] # ask where the agent's tool surface can prompt
deployed = ["~/.claude/settings.json", "..."]
sources = ["<repo>/modules/home/ai/shared/hooks/", "..."]

[credentials] # block on every agent; zero-access reads
paths = [
  "~/.claude/.credentials.json",
  "~/.codex/auth.json",
  "~/.pi/agent/auth.json",
]

[instruction-layers] # markdown carve-out: [location, layer] pairs
layers = [["~/.claude/hooks/", "instructions/"]]

[location-only] # judged by resolution, no text fragment
paths = ["~/.claude/", "~/.codex/", "~/.copilot/"]

[secret-floor] # concrete representatives for the floor tests
paths = ["~/.local/state/sops-nix/secrets.d/1/example"]

[[exceptions]] # deliberate loosenings, one table per exception
surface = "vscode-edit-approvals"
pattern = "**/Code/User/workspaceStorage/**"
why = "VS Code's own per-workspace state churn; gating it prompts on every chat session"
```

### Decision: HooksParseTheManifestAtInvocation

**Chosen:** `block-hook-tampering.py` and the Pi port build their matching structures from the manifest each time they run; `block-sensitive-paths.py` builds its agent-credential matcher from `[credentials]` the same way.

**Rationale:** a PreToolUse hook is a fresh process per call, so there is nothing to cache into; parsing a small TOML is microseconds against a `uv run` startup; and reading follows the interface contract (`NoSideEffects` forbids writing, not reading).

**Alternatives considered:**

- Generate the Python tuples and TS literals from the manifest at build time: keeps runtime unchanged but reintroduces copies, now with a generator to also keep honest

**Consequence:** the Pi literal mirrors (`GUARDED_FILES`, `CREDENTIAL_FILES`, `INSTRUCTION_LAYERS`, `LOCATION_ONLY` in the TS) retire, and with them the literal-scraping halves of `test_pi_guarded_declarations.py`; the shared verdict tables (`guarded-path-cases.json`, `sensitive-path-cases.json`) remain the behavioural cross-check between the two languages.

### Decision: ConformanceNotGeneration

**Chosen:** the Claude settings files, Codex TOMLs, and VS Code settings stay hand-authored; the conformance tests re-point at the manifest as their oracle.

**Rationale:** those files are consumed by the agents themselves and must hold literal entries; checking them against the manifest catches divergence without making them build artifacts, and their hand-authored regions carry material the manifest does not model (modes, platform blocks, unrelated settings).

**Alternatives considered (recorded for later, not taken):**

- Marked-region generation, as the MCP catalog does: the strongest guarantee, and the right next step if hand-sync pain persists after the oracle is unified.
  Taking it later is cheap precisely because the manifest will already exist.

### Decision: ExceptionsAreManifestEntries

**Chosen:** deliberate loosenings live in `[[exceptions]]` tables naming the surface and the pattern; the first entry is VS Code's `**/Code/User/workspaceStorage/**` auto-approve.

**Rationale:** the operator chose that loosening (per-workspace state churn is VS Code's own writing, and prompting on it is noise), and the choice must be visible to the same check that would otherwise flag it.
`**/Code/User/globalStorage/**` is deliberately not an exception: it holds per-extension state including secret-storage fallbacks, and stays gated.

**Alternatives considered:**

- A comment in the settings file: invisible to conformance, so drift and intent stay indistinguishable
- An allowlist inside the test: policy hidden in test code, unreadable from the manifest

### Decision: VSCodeModuleFileJoinsTheGatedSources

**Chosen:** `<repo>/modules/home/apps/vscode/settings.json` is declared a gated source, and the conformance oracle covers it alongside the per-user profile copies.

**Rationale:** the module file is what the deployed settings symlink resolves to, and it carries the edit-approval enforcement block; a write to it is a write to a live guardrail on every host that deploys it.
Resolution-based matching already catches writes addressed through the home path, but a write addressed to the repository path needs the declaration.

### Decision: ManifestLoadFailureDegradesToWarn

**Chosen:** a hook that cannot load the manifest responds `Warn` — the call proceeds, the reason is shown where the agent can show it — and the Pi port notifies through its UI channel.

**Rationale:** this is the `FailureMode` posture the tamper spec already records for an unparsable payload, for the same reason: the hook covers a mix of sensitive and read-only tools and cannot infer damage potential, while the sandbox and permission layers — which do not read the manifest — remain in force.

**Alternatives considered:**

- Fail closed: refuses every tool call, including reads, for as long as the manifest is broken — the exact outcome `FailureMode` rejects

## Architecture

```text
                 tool call (Write/Edit/apply_patch/Bash)
                                  │
                     block-hook-tampering.py
                                  │
                   path → protected class (guarded_paths)
                                  │
              ┌───────────────────┼───────────────────┐
        not protected      enforcement /         agent credential
              │            source / user-config          │
            Allow                 │                    Block
                                Ask                (every agent)
                                  │
                        hook_response.respond()
                                  │
        ┌──────────────┬──────────┴─────┬──────────────────┐
     claude         copilot           codex             unknown
   exit 0 +      exit 0 + ask      exit 2 + stderr    exit 2 + stderr
   ask JSON      JSON (post-       (refusal; prompt   (refusal)
   (one dialog;  probe; block      never emitted —
   rules not     until then)       fail-open hazard)
   consulted)
                                  │
              Pi (separate port): ctx.ui.confirm / block if no UI
```

```text
        modules/home/ai/shared/hooks/guarded-paths.toml
        (gated / credentials / instruction-layers /
         location-only / secret-floor / exceptions)
                 │                     │
     runtime consumers            test oracle
                 │                     │
  ┌──────────────┼──────────┐          ├── test_guardrail_declarations.py
  │              │          │          │   (Claude rules, Codex TOMLs,
block-hook-   block-      pi TS        │    VS Code globs ⊇ gated sources)
tampering.py  sensitive-  port         ├── test_secret_floor_declarations.py
(all classes) paths.py    (smol-toml)  │   (both Claude layers + Codex TOMLs
              (credentials)            │    ⊇ credentials + secret-floor)
                                       └── exceptions: declared → accepted,
                                           undeclared loosening → drift
```

## Risks

An approval dialog for enforcement writes is a habituation surface.
Mitigations: credentials never prompt, the prompt names the file and what approval permits, and under Claude the rules are never consulted on a hook ask, so no "always allow" can quietly widen the gate.

Under Claude, the gate's correctness now depends on the hook being healthy: a hook that fails open leaves the permission-layer `ask` entries as the only prompt.
That fallback is exactly the entries already in the settings, so the failure mode is a second, coarser dialog rather than an open door.

The Copilot probe may show a doubled dialog or a dead ask.
Both outcomes leave Copilot on the block encoding, which is today's behaviour.

The manifest is a single point whose corruption widens every hook at once.
Mitigations: it is inside its own guarded set; load failure warns instead of passing silently; and the permission and sandbox layers keep their literal entries, so the boundary does not depend on it.

## Verification Waivers

### Waiver: hook-interface NoSideEffects

**Evidence:** two parts, both recorded here rather than in `.verify/`, which the repository's root `.gitignore` excludes along with every other dot-directory.

The interpreter clause rests on a measurement taken 2026-08-29 on CPython 3.12.13.
A module was compiled, its cache entry rewritten with the bytecode of different source while keeping the 16-byte header that validates the entry against the source's mtime and size, and the module then imported in two subprocesses — one with bytecode writing enabled, one under `-B`.
Both printed the planted value, never the source value.
To reproduce: build such a pair with `py_compile` and `importlib.util.cache_from_source`, splice the planted body onto the original header, and import under each setting.
This is the claim the requirement's second paragraph makes, and it is why removing `sys.dont_write_bytecode` costs no protection.

The behavioural clause rests on a static audit of the four shared hooks, the Copilot adapter, and both test conftest files: no hook writes any path it judges, none opens a socket, and the single subprocess on the judging path (`gitleaks`, `block-secrets.py`) is synchronous under an 8-second timeout, so nothing outlives the invocation.

**Why manual:** the requirement is a negative universal over everything a hook does while judging.
Demonstrating it would need process-table and filesystem diffing around every hook invocation — a harness larger than the hooks — and the interpreter clause is definitional, so no assertion can fail it.
The mechanism this contract used to name is gone, and what replaced it is a property, not a code path a test can enter.

**Recorded:** 2026-08-29, during this change's verification, after `sdd-verify` flagged the requirement at INSPECTED.
The measurement above is independent of the implementation — it exercises CPython, not this repository — but the waiver's provenance is the weakest of the three here and should be read that way.

### Waiver: hook-interface AskOnAgentThatPrompts (Copilot arm)

**Evidence:** the cross-validation probe recorded under this change's tasks — a gated write attempted through the VS Code Copilot surface, with the observed dialog (or its absence) and the dialog count noted in the change's `.verify/` directory.

**Why manual:** whether the VS Code surface holds the tool call on the hook's ask is a property of Copilot's closed harness, not of this repository's code.
No test in this tree can assert it; the automatable part — the encoder emitting the right JSON for the `copilot` agent — is covered by unit tests.

**Recorded:** 2026-08-27.

### Waiver: Codex escalation-prompt behaviour (delegate-option prerequisite)

**Evidence:** a probe from the user's terminal — an `apply_patch` or shell write to a sandbox read-only path under `approval_policy = "on-request"` — with the outcome (escalation prompt or bare failure) noted in the change's `.verify/` directory.

**Why manual:** the behaviour belongs to the Codex harness and requires an interactive session; the tool sandbox cannot nest the Codex sandbox.
No requirement in this change depends on the answer — it gates only the recorded delegate option — but the probe is cheap and the answer decides whether that option is real.

**Recorded:** 2026-08-27.
