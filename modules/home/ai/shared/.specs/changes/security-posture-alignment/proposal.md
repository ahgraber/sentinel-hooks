# Proposal: security-posture-alignment

## Intent

An audit of this specs root against the enforcement it describes found five places where a control exists with no requirement behind it, and one place where no control exists at all.

The one with no control is the baseline posture.
`defaultMode` is `"default"` for one user and `"auto"` for two others; `approval_policy` is `"on-request"` on every Codex config.
Nothing asserts any of it.
Setting `defaultMode` to `bypassPermissions` or `sandbox_mode` to `"danger-full-access"` removes the permission layer every hook in this module treats as its co-enforcer, and every check in the repository still passes.
The Codex reviewer policy forbids _approving_ such an edit, which is not the same as noticing one.

The other four are behaviors that are implemented and tested with no requirement recording them: cross-agent network parity, the reviewer escalation that restores a user decision where a hook `Ask` cannot be shown, the end-of-turn pre-commit hook, and the expectation that every agent carries every capability.
A control nobody wrote down is a control a later change can drop without contradicting anything.
The Pi port already shows the shape of that: it carries no `git-baseline-drift`, and `guarded-path-classes` left it reading the class manifest with none of the class outcomes, the per-hop precedence, or the shared lexer behind them, under a temporary verification exception recorded in that change's design.
Recording the expectation raises what it costs to meet: Pi is a second copy of the policy, so each capability this change touches needs porting there separately, and the gaps it leaves are invisible in its source.
This change therefore migrates Pi onto the shared hooks rather than porting four more capabilities into it.

The record has a second hole, in the other direction.
Three requirements `2026-03-28-bash-hook-registration-pattern` introduced are absent from the baseline with no change recording their departure: `RequireSignedCommits` was rewritten into `RequireAgentCommitAlias` by `fba2187`, and the two ripgrep redirects were replaced by `c7f3937`.
Both commits edited the baseline spec directly.
Neither produced a conflict, and eight weeks separated them, so the pattern is not one person's slip.
This change records the three retirements.
Preventing the next one is a matter of instruction rather than of test, so it lives in this module's `AGENTS.md`: no repository-local check can catch a change that was never proposed.

## User Stories

- **posture-floor-is-enforced** — As the maintainer of these guardrails, I want a configuration that disables the permission or sandbox layer to fail a check, so that the floor every other guardrail assumes cannot be removed without anything noticing.
  (North star: "layers are independent, and a denial from any layer is final"; a layer that can be switched off silently is not independent of the agent it constrains.)
- **every-agent-carries-the-policy** — As the operator of four agents, I want each of them to implement every shared capability, so that choosing an agent is not also choosing which guardrails apply.
  (North star: "the policy is written once and holds for every agent".)
- **degradation-still-reaches-the-user** — As the operator of an agent that cannot show a hook prompt, I want that agent's own escalation surface to put a guardrail decision to me, so that the degraded path still ends at my decision rather than at a refusal I work around.
  (North star: "degradation keeps the user in control".)
- **a-refusal-says-what-would-work** — As the operator of an agent that cannot show a hook prompt, I want a refusal caused by an unrecognized command to name a command that would work, so that the agent stops only where the policy refuses it.
  (North star: "response matches risk"; a command that reaches nothing the policy refuses is ordinary recoverable work, and it should proceed without friction.)
- **existing-guarantees-are-recorded** — As the maintainer of these guardrails, I want behavior that is implemented and tested to carry a requirement, so that a later change has to contradict something to remove it.
  (North star: the posture is the justification for every rule, so a rule that is not expressed anywhere cannot be checked against it.)
- **the-declared-surface-is-what-is-protected** — As the maintainer of these guardrails, I want a declared location to be reached by every spelling and by no route the hooks do not judge, so that what the manifest declares is what is actually protected.
  (North star: "a denial from any layer is final"; a route no layer judges is not a denial anyone can rely on.)
- **placeholder-files-are-readable** — As the operator of these agents, I want an agent to read the committed example files that list a project's environment variables, so that routine work does not stop on a file that holds no secret.
  (North star: "ordinary, recoverable work proceeds without friction"; a placeholder file is not credential material.)

## Scope

**In scope:**

- `bash-command-validator`: the removal records for `RedirectGrepToRipgrep`, `RedirectFindToRipgrep`, and `RequireSignedCommits`, each naming the commit that retired it and why.
- `end-of-turn-precommit` (new capability): the Stop-hook contract already implemented by `stop-precommit.sh` and `pi/security/precommit.ts` — when it runs, which files it selects, when it does nothing, and how it blocks.
- `agent-configuration-floor` (new capability): the values an agent's configuration must not express, the escalation route that carries a guardrail decision where a hook `Ask` cannot, per-user network parity between agents, and that every hook an agent registers lies in the enforcement floor.
- Enabling the editor's agent sandbox and closing the three values that let an agent past it, in both VS Code settings files.
  Copilot is the one agent here with no OS-level layer of its own, and the sandbox is what closes that.
  The values matter more than the switch: each of `allowAutoApprove`, `allowUnsandboxedCommands`, and `retryWithAllowNetworkRequests` defaults to permissive, so a sandbox enabled at defaults would drop the approval prompt this repository currently enforces.
  The switch itself is experiment-controlled by the vendor, so leaving it unset leaves the decision outside this repository.
- Aligning the editor's approval configuration with the other two agents, in the same two files.
  The editor has approval bypasses apart from the sandbox, a global auto-approve, a default permission level, terminal auto-approval, and model-delegated approval, and its hooks load only because the settings name the deployed directory.
  Each is declared with its reason beside it, and the editor's domain list is declared before the sandbox is pinned, because an enabled sandbox with an empty list reaches no host.
  The editor's own approval prompt is recorded as Copilot's escalation surface, and the per-session bypasses no settings file can forbid are recorded as a limit.
- `cross-agent-capability-parity` (new capability): every agent implements every capability in this specs root, and every surface that turns a tool call into a verdict reaches the outcome the shared tables declare, whether it reimplements the policy or adapts onto it.
- An assessment recipe that judges every agent's configuration files against the floor, the escalation route, and network parity, and writes a dated record.
  No test in the hooks package reads an agent's configuration: the package works with any configuration, and a test over one pins the package to one vendor's keys and one repository's layout.
  The four tests that do so today, `test_secret_floor_declarations.py`, `test_guardrail_declarations.py`, `test_network_declarations.py`, and `test_reviewer_policy.py`, retire into the assessment.
- A conformance test asserting the hooks package carries an implementation for every capability in this specs root.
- Migrating the Pi extension onto the shared hooks through a hook runner, the Pi extension `pi-hook-runner` built for it in `modules/home/ai/pi/`, and deleting its TypeScript reimplementation of the policy.
  Parity otherwise means porting `git-baseline-drift`, the class model with its per-hop precedence and enforcement floor, the shared lexer with its word kinds, the admitted-utility set, the ancestor gate, and the fail-closed error path, each of which the other three agents got by editing one file.
  Adapting closes all of them at once and stops the next capability opening another.
- `hook-interface`: the obligation on a surface consuming a hook's outcome to decode the whole encoding rather than the exit status, to run every hook, and to combine their decisions restrictively; and the obligation on an adapter to name a recognized agent.
  `Allow` and `Ask` share an exit status, so a consumer reading the status alone turns every prompt into an allow with nothing recording it.
- `hook-tampering-blocking`: the criterion admitting a utility to the read classifier, and the two routes by which a utility meets it.
  The classifier refused a banner between two reads, which made an agent that cannot show a hook prompt unable to read a skill's own instructions.
  Fixing that raised the question of which utilities belong in the set, and the set had no stated criterion, so every absence from it read as an oversight.
  Ripgrep is the worked example and is admitted.
  Its four options that run a program are refused by name, and `--no-config` turns off the configuration file that would otherwise supply options the command never states.
  Leaving it out costs a task each time it happens, because ripgrep is the search tool the agents reach for and the skills directories are guarded.
- `hook-tampering-blocking`: judging a command that installs code for the shell to run later, rather than leaving it to the segment rule.
  The segment rule assumes each segment runs on its own, and a `trap` body does not: the shell runs it beside the recognized read that follows it.
  `trap '<body>' DEBUG; cat <guarded file>` was allowed by all five Bash hooks, in the `ERR` and `EXIT` forms as well, and with a copy over a guarded file in the body.
  The body is one quoted word, so every path inside it reached no path rule.
- `hook-interface`: a refusal says whether the policy refused the operation or the hook did not recognize the command, and gives the agent the instruction that matches.
  Every refusal carries the same instruction today: stop, report, and do not run a different command that does the same thing.
  On an unrecognized command that contradicts the list of accepted commands in the same message.
  An agent that follows the instruction gives up work no declaration refuses, and only agents that cannot show a prompt are stopped.
- `hook-tampering-blocking`: judging a patch by the files its headers declare rather than by the text it inserts.
  The gate matched the whole patch body, so a patch was refused for naming a guarded path in the content it wrote.
  That refuses a changelog entry, an incident note, and a spec citing the hook it specifies, and it refuses them only on the agent whose gate is a refusal rather than a prompt — the agent that then cannot record why it was stopped.
- `sensitive-path-blocking`: requiring a live credential to be refused by declaration rather than by the name heuristic, and making a declared `[[exceptions]]` entry excuse the name heuristic one spelling at a time.
  The declarations themselves are posture, recorded in `guarded-surface`: `~/.config/mcp-secrets.env` in the block class, and `scripts/mcp-secrets.sh` as the exception.
  That file holds the API keys the MCP servers start with, and until now the whole of its protection was the guess that a name carrying "secrets" holds some — a `*.env` suffix reaches no strong rule, and no deny entry on any surface covered it.
  The same guess refuses `scripts/mcp-secrets.sh`, a tracked program that renders it and holds nothing, which is what made the gap visible.
- `hook-tampering-blocking`: gating an operation that removes, renames, or replaces a directory holding a declared location.
  A declaration protects what is inside a directory and says nothing about the path to it, so `rm -rf modules/home/ai/pi` takes the declared `pi/security/` away while matching no declaration.
  All six hooks allowed it, and the permission layer permits it by design, because guarded paths are declared `ask` so the prompt can reach the user.
- `hook-interface` and `hook-tampering-blocking`: choosing the error direction by the tool the payload names.
  The tamper hook exited 0 on any unexpected error, against `ErrorHandlingByDamagePotential`, which already required a sensitive tool not to proceed on a hook crash.
  `os.path.expanduser` raises on a null byte and every containment test runs through it, so `~\x00` reached that branch and allowed the call.
- `destructive-ops-blocking` and `hook-interface`: refusing to judge by a pattern file that does not validate.
  The hook allowed every command when its file was missing or unreadable, and skipped a rule with an unknown mode or a pattern that did not compile, so a wrong value such as `mode = "deny"` turned a protection off with nothing reporting it.
  An unusable file now reaches `Ask` on every `Bash` call, with the fault named.
- `sensitive-path-blocking` and `guarded-surface`: reading a placeholder dotenv file, `.env.example`, `.env.sample`, `.env.template`, or `.env.op`, where the manifest declares its name.
  The dotenv rule refused these along with `.env.local`, and the Claude sandbox's `**/.env.*` deny hid them from every process, so an agent session could not read or `git` stat a file committed to hold placeholders.
  Writes stay refused.
  Claude's sandbox re-allows the same three names with `allowRead`; Codex cannot reopen a file inside a deny glob and still refuses them.
- `hook-tampering-blocking` and `sensitive-path-blocking`: judging a redirection's target by its direction rather than refusing recognition for any redirection.
  An input target is a read and an output target a write, in both hooks, so `cat <file> 2>/dev/null` is a read and `cat x > <guarded file>` a write.
- `hook-interface`: the retry form states nothing that holds for one hook alone, since a write the tamper hook puts to the user is one the sensitive-path hook refuses.
- Declaring the gated tool vocabulary once, with each harness's spellings, in a file beside the manifest, and requiring every adapter to refuse a tool name it cannot map.
  The vocabulary is undeclared and copied across six implementation sites, and `normalize_payload` in `copilot-vscode-hook-adapter.py` forwards an unmapped name unchanged, which reaches the hooks as a tool they do not gate and is allowed.
  A registered hook chain that does not gate is the same hole as an unimplemented capability, so it belongs with parity rather than beside it.

**Out of scope:**

- Changing any current `defaultMode` or `approval_policy` value.
  The floor forbids the bypass values; it does not pick between `"default"` and `"auto"`, which is a per-profile judgment.
- The reviewer policy prose itself.
  It already routes guardrail edits to `USER_APPROVAL_REQUIRED` and already refuses wholesale bypass; this change records the requirement it satisfies.
- New enforcement extending the guarded surface.
  Nothing here declares a path, a tool, or an agent the manifest does not already cover.
  The ancestor gate above closes a route to the surface as declared: it reaches a declared location by a path no hook resolved.
- Reconciling requirements that are present in a baseline with no archived change behind them.
  There are about ten, they describe behavior that ships, and giving each one a recorded rationale is a different job from stopping requirements disappearing.
- Editing the archived changes.
  What `2026-03-28-bash-hook-registration-pattern` added is what it added; the removal records belong to the change that notices, not to the one that is being corrected.

## Approach

New capabilities where the posture has none, and no MODIFIED block over a requirement `guarded-path-classes` also modifies.
That change is merged and live but not yet synced, and `sdd-sync` replaces a matched requirement wholesale, so two deltas over one requirement would have the second sync discard the first.
This change modifies `ErrorHandlingByDamagePotential`, `ExplanationContract`, and `BlockAIGuidance` in `hook-interface`, `FailureMode` and `GateResponse` in `hook-tampering-blocking`, `DriftWarning` in `git-baseline-drift`, and `ExternalPatternFile` in `destructive-ops-blocking`, none of which `guarded-path-classes` touches; its other deltas add or remove.
The removal records name three requirements the baseline already lacks, so they rewrite nothing.

The floor is expressed as a prohibition on named values rather than as an assertion of current ones.
The bypass values are published configuration identifiers, so naming them is contract rather than mechanism, and a prohibition leaves the legitimate per-profile variation alone.

Parity is judged the way this repository already judges the Pi port: shared verdict tables in `guarded-path-cases.json` and `sensitive-path-cases.json`.
Comparing source proves nothing; comparing verdicts over the same inputs is the check that has been catching drift.
Once Pi adapts, the tables arbitrate the adapters rather than two languages, which is where the remaining divergence lives — an adapter holds no policy, so its failures are in the payload it builds and the outcome it decodes, and neither is visible in its source.

Pi adapts rather than keeps porting.
The north star already settles the direction: onboarding an agent means expressing this posture in that agent's vocabulary, not writing a new one.
Feasibility was measured against a live `pi` before this was written — the gating path awaits a subprocess and honors its verdict, and one dispatcher costs less per tool call than the per-hook shape Claude already pays.

## Resolved Questions

- 2026-10-03: the end-of-turn run checks only the files whose content the turn changed; on 2026-10-10, a missing runner stays a silent skip.
  Decided with the user.
- 2026-10-09: a refusal whose classifier stopped only on relative paths in an undetermined directory ends with a third instruction form, the absolute-path form, and `UnrecognizedCommandsAreGated` defers to `GateResponse` for what a reason offers.
  Decided with the user.
- 2026-10-09: `block-secrets.py` judges content and exfiltration only; its file-path asks move to `block-sensitive-paths.py` as `SuggestiveNamesAsk`, so the manifest's declarations hold for every path rule.
  Decided with the user.
- 2026-10-09: `block-secrets.py` is renamed `block-leaks.py`, with its two test files.
  Decided with the user.
- 2026-10-11: requirements in `hook-tampering-blocking`, `hook-interface`, `sensitive-path-blocking`, `agent-configuration-floor`, and `end-of-turn-precommit` state the general rule in place of sentences that described single bugs.
  Decided with the user.
- 2026-10-11: `.env.op` joins the declared dotenv placeholders.
  Decided with the user.
- 2026-10-12: requirements in `cross-agent-capability-parity`, `secret-access-blocking`, `sensitive-path-blocking`, `hook-tampering-blocking`, `hook-interface`, and `destructive-ops-blocking` state outcomes where they named internal routes.
  Decided with the user.
- 2026-10-12: `ToolVocabularyIsDeclared` governs how an implementation judges the calls that reach it; which calls reach a hook is agent configuration, held to the vocabulary by `RegistrationsRouteTheVocabulary` and checked by the assessment.
  Decided with the user.
- 2026-10-12: Copilot asks on `Bash`, so an authorized shell guardrail edit reaches the user in the editor's prompt, after a live check on VS Code 1.141.0.
  Decided with the user.
