# Proposal: guardrail-ask-gate

## Intent

The tamper hook refuses every write to an enforcement file, unconditionally, with no approval dialog.
The spec calls guardrail maintenance an out-of-band act that belongs to the user alone.

Practice disagrees.
The guardrails are actively developed in this repository, so enforcement files are edited routinely — and the unconditional block is what gets routed around, not the edit.
The live hook has its entry point commented out in the working tree at the time of this proposal, which is the failure mode in one line: a guard that cannot be gated gets disabled instead.

The block predates the ability to ask.
As of the agent documentation current on 2026-08-26, two of the four agents can put a per-call decision to the user from a hook, a third can prompt from its extension API, and the fourth prompts through its sandbox escalation flow.
This change turns the unconditional block into a gate: a write to an enforcement file proceeds only when the user approves it in the moment, and is refused outright only where no prompt can reach the user.

Agent credentials are excluded.
A credential is not maintained in-session by any legitimate flow, so nothing is gained by asking, and a prompt trains approval of the one request that should never come.

Amended 2026-08-28: the change also unifies where the guarded surface is declared.
Applying the gate surfaced the cost of hand-synced copies — the same set was spelled in two Python hooks, the Pi port's mirrored literals, four Claude settings files, three Codex TOMLs, and two VS Code settings files, and every gap the 2026-08-27 audit found was a divergence between copies: sops-nix output denied on Linux and reachable on Darwin, an agent credential store declared nowhere, a `**/secrets/**` glob that misses the store's own `secrets.d` spelling, and a VS Code surface whose settings moved to a module while the conformance test kept watching the old location.
The amendment declares the surface once, in a manifest the enforcement implementations read and the conformance tests treat as the oracle, and gives deliberate loosenings a declared home so intent and drift stop looking alike.

## User Stories

- **in-session-maintenance** — As the maintainer of these guardrails, I want an agent's write to an enforcement file to require my in-the-moment approval instead of being refused, so that guardrail maintenance can happen in-session without disabling the guard that protects it.
  (North star: "what only the user may decide is put to the user".)
- **safe-degradation** — As the operator of four different agents, I want the ask gate to degrade to a refusal wherever an agent cannot prompt me, so that a loosened response never loosens the boundary.
  (North star: "degradation keeps the user in control".)
- **one-authoring-surface** — As the maintainer of these guardrails, I want every guarded path declared once, so that adding, renaming, or reclassifying a path cannot leave one implementation or one platform behind.
  (North star: "policy written once for every agent".)
- **intent-vs-drift** — As the operator, I want deliberate loosenings declared next to the guarded set, so that conformance checking can tell a chosen exception from an accidental gap instead of accepting both.
  (North star: "layers independent, any denial final"; a loosening is only acceptable when it is chosen.)
- **contract-states-its-property** — As a maintainer extending these hooks, I want the no-side-effects contract to name the property it protects rather than a mechanism it happened to ban, so that I can tell what actually violates it and do not pay for enforcement that protects nothing.
  (North star: "layers are independent, and a denial from any layer is final"; a control that no layer relies on is cost without coverage, and stating the property is what makes that visible.)

## Scope

- `hook-interface`: `NoSideEffects` prohibits modifying the state a hook is judging, rather than writing to disk outright, and binds a hook at invocation rather than everything that imports one.
  Bytecode suppression is removed from the four shared hooks, the Copilot adapter, and both test conftest files: the interpreter loads an existing cache entry whether or not the running process may write one, so suppression bought no protection while costing roughly 3ms per hook invocation.
- `hook-interface`: the ask-capable set gains Copilot, and degradation of `Ask` becomes an explicit contract.
  `Ask` degrades to `Block` where the invoking agent cannot prompt, never to `Allow`.
  Codex is the named hazard: it parses `permissionDecision: "ask"`, marks the hook run failed, and lets the tool call proceed, so the ask JSON must never be emitted to it.
- `hook-tampering-blocking`: mutation of a protected path becomes ask-gated for three of the four protected classes — deployed enforcement, repository sources, and per-user agent configuration.
  Agent credentials stay blocked unconditionally.
  The capability keeps its name; the gate is still what blocks when no prompt is possible.
- `guarded-path-declarations` (new capability, amended in): one manifest carries the protected classes (gated and credential), instruction layers, location-only roots, secret-floor representatives, and declared exceptions.
  Enforcement implementations read it; configuration surfaces are checked against it; the manifest belongs to the surface it declares; a load failure is reported, never silent.

Companion configuration, outside this specs root but inside this change's tasks:

- The Pi security extension port gates its tamper branch on `ctx.ui.confirm`, blocking where no UI exists — the same pattern its destructive-ops ask rules already use.
- The Codex `auto_review` reviewer policy routes guardrail-edit escalations to explicit user authorization (the `USER_APPROVAL_REQUIRED` pattern it already applies to network destinations) instead of flat denial, in both platform TOMLs.
- VS Code's `chat.tools.edits.autoApprove` gains `false` globs for the guarded set, in the repo-managed profile and on this machine.
  This gives Copilot the hook-fails-open fallback layer that Claude's `permissions.ask` entries provide, and narrows the accepted gap where a Copilot session edits VS Code's own settings unprompted.
- The tamper hook's entry point is restored on the way through.
- `block-hook-tampering.py`, `block-sensitive-paths.py` (its agent-credential matching only), and the Pi port take their declarations from the manifest; the Pi literal mirrors and the declaration-scraping halves of the Pi conformance test retire.
- The conformance tests over Claude settings, Codex TOMLs, and VS Code edit approvals re-point at the manifest as their oracle, and learn to honour declared exceptions while failing undeclared loosenings.
- The VS Code settings relocation lands in the guarded surface: `modules/home/apps/vscode/settings.json` is now the deployed source (`mkRepoSymlink`) and carries the edit-approval enforcement block, so it joins the gated sources and the conformance oracle alongside the per-user profile copies.
- The first declared exception is recorded: `**/Code/User/workspaceStorage/**` is auto-approved deliberately (VS Code's own per-workspace state churn), while `**/Code/User/globalStorage/**` stays gated.

Out of scope:

- Every other hook keeps its current modes: secrets, sensitive paths, dangerous bash, and destructive ops are unchanged.
- Reads of protected paths remain allowed; the instruction-markdown carve-out is unchanged.
- The Claude permission layer and sandboxes are unchanged: the guarded paths are already under `ask` in the Claude settings, and Bash-level writes stay sandbox-denied as the non-promptable backstop.
  A hook `ask` preempts the permission rules, so the user sees one dialog, not two; the settings entries remain as the fallback for a hook that fails open and for tools the hook does not cover.
  Because the rules are not consulted when the hook asks, an "always allow" answer never silences the gate — an enforcement write re-prompts every time, deliberately.
- Native Codex hook `ask` support; revisit when it ships.
  Upstream tracks it as feature request openai/codex#28437, and PR openai/codex#20702 sketches the intended semantics: `ask` may tighten a decision into explicit approval, never waive policy.
  Until then the hook refuses under Codex.
  Degrading to `Allow` there and delegating the ask to the sandbox escalation prompt is a recorded alternative, not taken — see `design.md`.
- Copilot non-interactive contexts, where the platform itself degrades ask to deny.
- Generating the literal config regions from the manifest.
  The Claude settings, Codex TOMLs, and VS Code files stay hand-authored and conformance-checked; marked-region generation (the `mcp.nix` catalog pattern) is a recorded option in `design.md`, not taken now.
- The shape heuristics in `block-sensitive-paths.py` (`**/.env`, SSH key names, the credentials/secret name rule).
  They describe the world, not this repository's inventory, and stay in code.

## Approach

Keep the decision/encoding split the previous change built.
The hook's judgement changes in one place — the tamper decision becomes `Ask` for the gated classes — and the per-agent encoding helper carries the rest.

Copilot joins the ask-capable set and receives the same JSON encoding Claude Code does, on exit 0.
Copilot reaches the shared hooks through its adapter, so the encoding must be validated against the real VS Code surface, not only the documented CLI one; a cross-validation test is the evidence.

Codex keeps the exit-2 refusal as the degraded form of `Ask`.
The user-approval route under Codex is not the hook: it is the sandbox denial plus the escalation prompt, with the reviewer policy amended to put the decision to the user.

Pi does not use the shared encoder; its port expresses `Ask` as a confirm dialog and keeps `Block` where no UI is attached.

The ask explanation follows the existing `ExplanationContract`: it names the file, states that it is enforcement, and states what approving the write means.

The manifest is TOML beside the hooks, following `block-destructive-ops-patterns.toml`: the Python hooks parse it with `tomllib`, and the Pi extension parses the same file with `smol-toml`, both already in use.
Classes are sections, so the protected class of a path is structural in data exactly as this change makes it structural in code.
The hooks build their matching structures from the manifest at invocation; a manifest that fails to load degrades per the hook-interface `FailureMode` pattern — the call proceeds and the failure is reported where the agent can show it.
The exceptions section is what lets the VS Code conformance test require a `false` glob for everything guarded while accepting the one `true` glob the manifest names.

## Open Questions

- Does the VS Code Copilot surface honour `permissionDecision: "ask"` the way the Copilot CLI reference documents?
  An early empirical task answers this; until it passes, Copilot stays out of the ask-capable set.
- Does a Codex sandbox write-denial on `apply_patch` surface an escalation prompt under `approval_policy = "on-request"`, or only a failure?
  An early empirical task answers this; the reviewer-policy edit is worthwhile either way.
- Should the hook file be renamed (`block-hook-tampering.py` → `guard-hook-tampering.py`)?
  A rename ripples through hook registrations, trusted hashes, the Copilot adapter table, sandbox configuration, and the conformance test.
  Default is to keep the filename and rename nothing.
- Do the per-user VS Code profile copies (`users/*/home-manager/vscode/settings.json`) remain long-term, or does the module file become the only source?
  The conformance oracle covers both for now; retiring the copies is a later cleanup.

## Risk

An approval dialog for enforcement writes is a new habituation surface.
The mitigation is scope: the gate covers exactly the paths a maintainer edits deliberately, credentials never prompt, and the prompt text names the file and the consequence rather than a generic warning.

Copilot's ask support is documented but young.
If the empirical check fails, Copilot keeps the block encoding and loses nothing it has today.

Approving a Bash write under Claude still fails at the seatbelt layer, because the sandbox cannot prompt.
This is accepted: the Edit/Write tools are the gated route, and the refusal message can say so.

The manifest becomes the single point whose corruption disables path-based tamper protection everywhere at once.
Mitigations: the manifest is itself in the guarded set, its load failure is loud rather than silent, and the OS sandbox and permission layers do not read it, so they keep enforcing their literal entries regardless.
Two parsers (Python `tomllib`, TS `smol-toml`) read one file, so a TOML edge-case disagreement is possible; the manifest restricts itself to strings, arrays, and tables, and the shared verdict tables would surface a divergence as a behavioural diff.
