# Design: security-posture-alignment

## Context

Four of the five gaps this change closes are behaviors that already ship: network parity and the reviewer escalation, checked today by `test_network_declarations.py` and `test_reviewer_policy.py`; the end-of-turn pre-commit hook, checked by `claude/tests/test_stop_precommit.py`; and the shared verdict tables the Pi conformance tests read.
For those, the work is a requirement and a `Serves:` backlink, not code.
The two tests that read agent configuration files retire into the assessment `TheHooksAreAPackageIndependentOfAnyAgentConfiguration` introduces, and the requirements they evidenced are judged there.

The fifth is the posture floor, which has neither a requirement nor a check.
It needs a requirement and an assessment item, not a test.

The parity requirement turns known omissions into work.
The Pi extension has no `git-baseline-drift` equivalent.
`guarded-path-classes` updated its manifest reader to the class tables and nothing else, so it implements none of the class outcomes, the per-hop precedence, the enforcement floor, or the shared lexer's word kinds, and it lacks the admitted-utility set, the ancestor gate, and the fail-closed error path this change adds.
That change records the gap as a temporary verification exception, to be removed when the adapter passes the deferred cases.
Pi does implement `session-tool-checks` in its `session_start` handler, so that is not another.

Rather than port each of those, this change migrates Pi onto the shared hooks, which closes all of them at once and stops the next capability from opening another.
That makes Pi the fourth adapter rather than the only reimplementation, which changes what parity has to check: the verdict tables move from arbitrating two languages to arbitrating every surface that turns a tool call into a verdict, adapters included.

`guarded-path-classes` is merged and live but not yet synced.
Its deltas modify `ProtectedSurface`, `ReadsAreAllowed`, and `MutationIsBlocked` in `hook-tampering-blocking`, `BlockBashReadFromZeroAccessPath` in `sensitive-path-blocking`, and requirements in `guarded-path-declarations` and `path-matching`.
This change modifies `FailureMode` in `hook-tampering-blocking` and `ErrorHandlingByDamagePotential` in `hook-interface`, and neither change modifies a requirement the other does.
The two cite each other: `guarded-path-classes` rests its load-failure posture on `FailureMode` and `AnInternalErrorAsksRatherThanBlocks`, cites `agent-configuration-floor` from `guarded-surface`, and cites `TheNameHeuristicIsExcusedOnlyByDeclaration` from `sensitive-path-blocking`, so both deltas sync into one baseline in the same sitting.

## Decisions

### Decision: NoModifiedBlockOverARequirementAnotherChangeModifies

**Chosen:** four new capability specs; MODIFIED blocks over `ErrorHandlingByDamagePotential`, `ExplanationContract`, `BlockAIGuidance`, `FailureMode`, `GateResponse`, and `DriftWarning`, none of which `guarded-path-classes` touches; ADDED blocks over `hook-interface`, `hook-tampering-blocking`, and `sensitive-path-blocking`; and REMOVED-only deltas over `bash-command-validator` and `dangerous-bash-blocking`.

**Rationale:** `sdd-sync` replaces a matched baseline requirement wholesale from a MODIFIED block.
Two unsynced changes carrying MODIFIED blocks for the same requirement would have the second sync silently discard the first.
The two error-direction requirements are the ones this change has to restate, and the other change leaves them alone.

**Alternatives considered:**

- Add the floor to `guarded-path-declarations`: that capability declares paths, and a permission mode is not a path.
- Add the escalation route to `hook-interface`: that capability is the hook-to-agent protocol, and the reviewer policy is an agent configuration surface that no hook reads.
- Fold the ancestor gate and the patch judgment into `MutationIsBlocked`: `guarded-path-classes` modifies that requirement, so the two deltas would collide at sync.

### Decision: RecurrenceIsAddressedByInstruction

**Chosen:** the rule against editing a baseline directly lives in this module's `AGENTS.md`, with no repository-local test behind it.

**Rationale:** the failure is a commit that never proposed a change, so no per-change check ever runs for it.
`sdd-verify` is change-diff-scoped by its own definition and never runs baseline-wide.
A test comparing the archive against the baselines would catch only one residue of the failure — a requirement that was once archived and later vanished — and not a requirement written straight into a baseline, nor behavior changed with no spec touched.
Instruction covers all three; the test covered one and read as though it covered the rule.

**Alternatives considered:**

- A conformance test over the archive: narrow, after the fact, and its scope would be mistaken for the rule's scope.
- Root `AGENTS.md`: loaded more reliably, but SDD applies to this module rather than to the repository, so the rule belongs where the specs are.

### Decision: RemovalRecordsAreANoOpAtSync

**Chosen:** `## REMOVED Requirements` blocks for requirements already absent from the baseline.

**Rationale:** sync removes what is named and finds nothing, so the baseline does not change.
The value is in the archived change record afterward: the requirement's departure has a date, a reason, and the commit that made it.

**Alternatives considered:**

- A prose note in the baseline: unversioned against the change record, and invisible to any check.
- Amending the 2026-03-28 change to not add them: rewrites what that change did, which is the one thing the archive is for.

### Decision: ProhibitNamedValuesRatherThanAssertCurrentOnes

**Chosen:** the floor lists the values that must not appear.

**Rationale:** `defaultMode` is `"default"` for one user and `"auto"` for two others, and that difference is a per-profile judgment about how much friction that profile's work should carry.
Pinning current values makes every legitimate profile change a spec edit, and a check that has to be edited to do ordinary work is a check people learn to edit.
The dangerous values are few, named, and stable, so a prohibition catches what matters and stays quiet otherwise.

**Alternatives considered:**

- Assert each file's current value: fails on benign profile changes, so it trains edits to the assertion.
- Assert `approval_policy = "on-request"` on every Codex config: true today, but it is a mode choice like `defaultMode`, and the bypass prohibition already covers the value that matters.

### Decision: TheEditorSandboxIsPinnedOnAndClosed

**Chosen:** declare `chat.agent.sandbox.enabled` as `"on"` in both VS Code settings files, and declare `allowAutoApprove`, `allowUnsandboxedCommands`, and `retryWithAllowNetworkRequests` as `false`.

**Rationale:** Copilot is the one agent here with no OS-level layer of its own.
`copilot/AGENTS.md` records that its enforcement is hooks-only and that the write protection for its own sources comes from the other agents' configurations.
The editor's agent sandbox is the layer that closes that, so the posture wants it on.

Turning it on with the shipped defaults would cost more than it buys.
Read out of the installed build, `allowAutoApprove`, `allowUnsandboxedCommands`, and `retryWithAllowNetworkRequests` each default to permissive, so a sandbox enabled at defaults auto-approves what it accepts and lets the agent run what it refused.
That trades an approval gate for a boundary the agent can decline, which is a worse position than either layer alone.

`enabled` is declared rather than left at its `"off"` default because the build marks it experiment-controlled.
Unset, the value is the vendor's to move, and moving it brings the three permissive companions with it.

The escape hatch is closed rather than kept.
A blocked command is answered by widening the filesystem declaration, which is reviewable and shared, instead of by a per-command exemption that leaves no record.

The sandbox is also the one layer a session-level bypass cannot remove.
The documentation states that sandboxing "is independent of the permission level": a session started at Allow all or Autopilot skips every approval prompt and is still confined.
That is why the sandbox is pinned rather than the prompts alone.

Pinning it has a network consequence the switch does not advertise.
With `allowNetwork` false, the sandbox applies `chat.agent.allowedNetworkDomains` and `chat.agent.deniedNetworkDomains` to terminal commands, and the documentation states that when both lists are empty, all domains are blocked.
So the domain list is declared before the sandbox is switched on, or every terminal command loses the network the day the pin lands.
That list is also the editor's side of `NetworkReachIsUniformPerUser`.

Two places where the documentation and the 1.136.1 build disagree are recorded so a later reader does not resolve them the wrong way: the documentation gives `allowNetwork` a default of `true` and the build gives it `false`; the change declares it, so neither default applies.
The 1.139.1 build gives it `true`, which is the default moving between releases that `ExperimentControlledDefaultsAreDeclared` anticipates.
The hooks reference says a `PreToolUse` `ask` "requires user confirmation" with no tool excepted, while `hook_response.py` records from measurement that the terminal tool does not honor it; the task list carries a re-measurement.

The 1.139.1 build no longer reads `chat.assistedPermissions.enabled` or `chat.experimental.autoApprovals.enabled`; it migrates both away.
Their place is `chat.defaultConfiguration`, an object whose `approvals` is `manual`, `assisted` ("evaluates risk before running tools"), or `allowAll`, and whose `mode` is `interactive`, `plan`, or `autopilot`, so the floor names that setting's values instead.
`chat.permissions.default` is still read beside it.
`chat.useHooks` defaults to true and is a preview setting an organization policy can turn off, so it is declared and named among the bypasses.

**Alternatives considered:**

- Enable the sandbox and keep `allowUnsandboxedCommands` at its default: the sandbox becomes advisory, and `#314996` shows the vendor treats approval bypass under sandbox as intended rather than as a defect.
- Leave the sandbox off and rely on the hooks: leaves Copilot with no OS layer, and leaves the switch under vendor control.
- Rely on `chat.tools.terminal.autoApprove` deny rules instead: bypassed under sandbox by design, per `#314996`, closed as not planned.
- Pin the sandbox on with `allowNetwork` true: keeps the filesystem boundary and gives up network parity with the other agents, which the domain list provides at the cost of one declaration.

### Decision: ThePiSandboxIsClosedFromTheManifest

**Chosen:** declare `~/.pi/agent/extensions/sandbox.json` with `denyRead` and `denyWrite` covering the manifest's `[block]` class, and add `enabled`, `ignoreViolations`, and `enableWeakerNestedSandbox` to the values `BypassModesAreRefused` names.

**Rationale:** `pi/default.nix` copies Pi's sandbox extension out of the Pi derivation and writes no configuration for it, so it runs on the defaults the vendor shipped: `denyRead` of `~/.ssh`, `~/.aws`, and `~/.gnupg`, and `denyWrite` of `.env`, `.env.*`, `*.pem`, and `*.key`.
Those are not this repository's block class.
`~/.config/mcp-secrets.env` is the case that shows the difference: this change adds it to `[block]` and covers it in four Claude settings files and three Codex configurations, and Pi's sandbox would still permit a read of it.

After the migration Pi's hook layer is the same layer the other three agents run, which makes its OS layer the only place Pi can differ, and the only one never told what this repository protects.
`ConfigurationSurfacesCoverTheDeclarations` holds every floor to the block class, so leaving Pi out makes that requirement false on one agent of four in the change that brings Pi to parity everywhere else.
The block class is also the class where a miss cannot be undone.

The extension reads a global file at `~/.pi/agent/extensions/sandbox.json` and a project file under the working directory, merging both, so the global file is the one this repository owns.
Its `filesystem` keys are the shape the other two surfaces already use.

The file is hand-authored like the Claude settings and the Codex configurations rather than generated from `guarded-paths.toml`.
Coverage is judged by the assessment, per `TheHooksAreAPackageIndependentOfAnyAgentConfiguration`, and generating one surface from the manifest while six others are written by hand puts the manifest in two relationships with its consumers.

**Alternatives considered:**

- Record Pi's sandbox as a limit the floor does not reach, as `SessionLevelBypassIsOutsideTheFloor` does for the editor's session bypasses: the editor bypass is a choice made in a chat input that no file can forbid, and this is a file.
- Generate the deny lists from the manifest in Nix with `builtins.fromTOML`: removes the transcription step for one surface and leaves the assessment reading six hand-written files and one generated one.
- Defer to a change of its own: the gap exists because Pi had no OS-layer obligation, and this is the change that gives Pi every other obligation.

### Decision: TheEditorPromptIsCopilotsEscalationSurface

**Chosen:** for Copilot, the escalation surface `GuardrailEditsRouteToTheUser` requires is the editor's own tool-approval prompt: `chat.tools.terminal.enableAutoApprove` false puts every terminal command to the user, and the guarded-path `false` entries in `chat.tools.edits.autoApprove` put every guardrail edit to the user.
The wholesale-bypass refusal is the floor: the values that would silence those prompts are the ones `BypassModesAreRefused` names.

**Rationale:** Codex routes a refused guardrail edit through its reviewer policy, which is a surface Copilot does not have.
What Copilot has is an approval layer of its own, which the hooks sit in front of.
`hook_response.py` records that Copilot honors a hook `Ask` for `Write` and `Edit` and refuses on `Bash`, so a shell-borne guardrail edit degrades to a refusal there as on Codex, and the editor prompt is what still reaches the user.
The hooks documentation for this build says a `PreToolUse` `ask` is honored without naming an exception; if a re-measurement agrees, `supports_ask` widens for Copilot and the hook prompt becomes the route, which makes this decision a fallback rather than the surface.

Per-path coverage of `chat.tools.edits.autoApprove` against the manifest is not asserted.
`guarded-path-classes` dropped that floor because the surface cannot express an ask with a carve-out beneath it, and this requirement needs only the wholesale bypasses refused.

**Alternatives considered:**

- Write a reviewer-style instruction file for Copilot: instructions are advisory, per `shell.instructions.md`'s own closing note, and the editor prompt already has enforcement behind it.
- Declare Copilot excepted from the requirement: leaves the one agent with no OS layer of its own also with no recorded route to the user.

### Decision: SessionLevelBypassIsOutsideTheFloor

**Chosen:** the floor governs configuration files.
The editor's per-session bypasses, the permissions picker, the `/autoApprove` and `/yolo` commands, and worktree isolation, which the documentation says "always uses Allow all", are recorded as a limit the floor does not reach.
The one closure the vendor offers, the `ChatToolsAutoApprove` policy, is left for the user to decide.

**Rationale:** no settings file forbids a choice made in the chat input.
The documentation is explicit that only the `ChatToolsAutoApprove` policy hides the Allow all level, the Assisted level, and the Autopilot mode, and that on macOS a policy is a `.mobileconfig` profile, which can be installed on one machine without a device-management service.
A profile is machine state outside this repository's activation path, so adopting it is a decision about how this machine is administered rather than about this module.
The sandbox is what holds under a session-level bypass, which is the previous decision.

**Alternatives considered:**

- Ship the profile from nix-darwin: possible in principle, and a separate change if wanted, because it moves a vendor policy mechanism into the system layer.
- Treat the picker as out of scope without recording it: the next audit finds the same hole and has to rediscover why it is open.

### Decision: ParityJudgedByVerdictTables

**Chosen:** conformance runs every surface that reaches a verdict over `guarded-path-cases.json` and `sensitive-path-cases.json` and compares outcomes.
On Pi that surface is the runner with Pi's registration, compared with a direct invocation of the same hooks.

**Rationale:** this is what already catches Pi drift.
The archived `guardrail-ask-gate` change retired the literal-scraping comparisons for the same reason: a pattern that looks right and does not match is the failure the check exists to catch, and source comparison cannot see it.

**Alternatives considered:**

- Compare the declaration literals across languages: retired once already.
- Require the Pi port to import the Python: different runtime, no shared process.

### Decision: ToolVocabularyIsDeclaredBesideTheManifest

**Chosen:** declare the gated tool vocabulary and each harness's spellings in `hooks/tool-vocabulary.toml`, beside `guarded-paths.toml`; have the hooks read it; and have every adapter refuse a tool name it cannot map.

It is a file of its own because `guarded-path-declarations` `OnlyPolicyTablesExist` holds `guarded-paths.toml` to the five policy tables, and `test_guarded_paths_manifest.py` enumerates them.
A harness spelling is an adapter mapping, not a path policy, so it does not belong in the file an operator reads to learn what is guarded.

**Rationale:** the vocabulary is undeclared today.
It is Claude's four names plus Codex's `apply_patch`, hardcoded as `MUTATING_TOOLS` in `block-hook-tampering.py`, `SENSITIVE_TOOLS` in `block-secrets.py`, the tool tuple in the `main` of `block-sensitive-paths.py`, the `Bash` test in `block-destructive-ops.py`, and `_COPILOT_ASK_TOOLS` in `hook_response.py`, and spelled a sixth time in the Pi port, which the migration deletes.
Six copies of a cross-harness vocabulary is the shape `AddedPathReachesEveryConsumer` already rejects for paths, and the same argument applies: a name spelled in code leaves the other implementations behind.

It also decides who the vocabulary belongs to.
Undeclared, it is whichever harness the shared code was written against, and every other harness is then described by its difference from that one.
Declared, each harness states its own spellings, and Claude's are an identity mapping rather than the default by accident.

The refusal matters more than the declaration.
The hooks allow any tool outside the vocabulary, and must: Claude also sends Glob, Grep, Task, and WebFetch, which no hook judges.
So no hook can separate a tool it does not gate from a tool it should gate but does not recognize, and only the adapter — which knows its own harness's tool set — can tell the difference.

The adapter learns that difference from the declaration too: a `[passthrough]` table lists, per harness, the tools it emits that no hook checks.
A refusal with only the mappings to consult refuses every read, search, and MCP call, because the mappings hold gated tools alone.
In the Copilot 0.64.1 build that is most of the tools the editor offers, and in Pi it is `grep`, `find`, `ls`, and every extension tool.
An entry may be an `fnmatch` pattern.
The editor names an MCP tool `mcp_<server>_<tool>`, so the set grows whenever a server is configured, and naming each tool would turn every new server into a refusal until someone edits the file.
The cost is that a pattern admits a later tool that writes.
MCP tools are unchecked on every agent today, so the pattern admits nothing the hooks judged before.
The loader refuses a declaration that lists a spelling as passthrough and also maps it, directly or through a pattern.

A Copilot tool that writes or runs code is mapped onto a gated name where the hooks can read its input: `multi_replace_string_in_file`, `edit_notebook_file`, `create_directory`, and `send_to_terminal`.
The editor's code runners (`run_task`, `create_and_run_task`, `run_notebook_cell`, `run_playwright_code`, `run_vscode_command`, `runTests`, `install_extension`) and its two project generators carry input no hook can read, and are declared passthrough, each with a comment saying it is less secure unchecked.
They ran unchecked before this change, and refusing them would take tools from Copilot users that no hook could have judged anyway.
The `edit_files` placeholder is in neither table, so it is refused.
Each table names the harness build it was read from, because the tool set is the vendor's and moves between releases.

The three shell hooks read no tool name.
`block-dangerous-bash.sh`, `bash-command-validator.sh`, and `git-baseline.sh update` judge every call they receive, and each agent's registration selects the calls: a `matcher` on Claude, Codex, and Pi, and the adapter on Copilot, because VS Code runs every registered hook on every call and ignores `matcher`.
The adapter's `HOOK_SCOPES` keys each tool-specific hook to a declared group, `shell` for the three shell hooks and `mutating` for `git-baseline.sh check`, so the shell tool's spellings stay in the declaration and a Pi payload reaches the shell hooks unchanged.
A harness that runs every hook on every call and has no adapter to select calls runs the shell hooks on reads and passthrough tools.
Two of them allow a call with no `command`; `git-baseline.sh update` would record HEAD after any call, including one a passthrough runner made.

**Alternatives considered:**

- Case-fold `tool_name` in the shared hooks: makes each hook accept another harness's spelling, which is the coupling this removes, and it is redundant once each boundary normalizes.
- Leave the vocabulary in code and add a cross-implementation literal comparison: retired once already, for the reason in `ParityJudgedByVerdictTables`.
- A sixth table in `guarded-paths.toml`: `OnlyPolicyTablesExist` forbids it, and amending that requirement to admit a non-path table gives up the property that the manifest reads as policy.
- Exact names only in `[passthrough]`: the refusal holds for every tool, and each configured MCP server is refused until its tools are listed.
- Refuse only an unmapped built-in tool and forward extension tools: weakens the requirement, and neither harness was shown to mark which of its tools are built in.

### Decision: EveryPolicyTableEntryIsARecord

**Chosen:** `guarded-paths.toml` and the passthrough and refused tables of `tool-vocabulary.toml` declare one record per entry, each with a required `reason`, in the shape `block-destructive-ops-patterns.toml` already uses.
A class or harness is a table holding a description or source and its records.
A tool sits in one of mapped, passthrough, and refused at most.

**Rationale:** a reason in a comment is read by no loader, so an entry with none loads and a stale one goes unnoticed.
A required field makes the loader refuse an unexplained entry.
The refused table separates a tool refused on purpose from a new one, so the assessment reports only the second.
`load_manifest` reduces the records to the path lists `PathPolicy` reads, so no consumer of the policy changes.

**Alternatives considered:**

- Keep reasons in comments and have the assessing agent read them: each run repeats a judgment, and a refused tool reads the same as a new one until someone reads the prose.
- A flat `[[refused]]` list with a `harness` field: one shape for every harness, but the source build each table was read from has no table to sit on.

### Decision: HarnessesWithoutAnAdapterRefuseThroughAHook

**Chosen:** Claude Code and Codex, which send their tool names to the hooks directly, register one more shared hook, `refuse-unlisted-tools.py`, for every tool call.
It refuses a tool its harness's vocabulary table neither maps nor lists as passthrough, which is the refusal an adapter makes for Copilot and Pi.
Each harness gains a `[passthrough]` list read from its installed build.
Copilot and Pi do not register the hook; their adapters already refuse, and a `capability-coverage` exception records why for each.

**Rationale:** Claude Code 2.1.284 fires `PreToolUse` for every tool, and six of its tools that write or run code were judged by no hook: `NotebookEdit`, `PowerShell`, `Monitor`, `EnterWorktree`, `ExitWorktree`, and `CronCreate`.
Codex 0.157.0 has no such tool today, so for Codex the hook is the notice that an update added one.
A refusal names the tool, so each new vendor tool reaches the user, who maps it, lists it as passthrough, or leaves it refused.
That friction is accepted on each vendor update.

The hook is a new file registered on its own, not an existing hook re-registered for every tool.
The shell hooks read no tool name, so running them on every call would run them on reads and passthrough tools, for the reason the decision above gives.

The hook refuses every call when the vocabulary cannot be read, which locks Claude and Codex out until the file is repaired by hand.
The manifest's failure proceeds because the sandbox and the permission lists keep enforcing without it; no other layer knows which tools exist, so proceeding here would let every unlisted tool through exactly when the list is gone.
`hook_response.py` imports the vocabulary for Copilot's ask support only, so it tolerates a failed load, and the refusal still carries the stop instruction.

MCP tools pass through by the pattern `mcp__*`, so the hook adds no MCP protection; exact names were rejected above because each configured server would be refused until listed.
Codex's `write_stdin` and code-mode `exec` run code without firing `PreToolUse`, so neither this hook nor any other judges them; the Codex sandbox is what confines them.

The hooks do not convert tool names; the boundary does, per the case-folding alternative above, and Claude Code and Codex have no boundary.
So for these two harnesses a mapping counts as listed only when it maps a tool to its own name, and the hook refuses a mapping to another name rather than let it pass as judged.
Judging a Claude or Codex tool under another name would take three changes per tool: a name conversion in each Python hook, a translation of its input fields, and a matcher edit in every settings file, because Claude's matchers are exact lists and Codex's are anchored.

`NotebookEdit`, `Glob`, and `Grep` are passthrough on Claude Code for that reason, with Claude's own permission layer as their check.
Its documentation says `Edit` rules apply to `NotebookEdit`, and `Read` rules to `Grep` and `Glob` as a best effort; the Claude settings ask on the guarded hook paths and deny every credential path.

Pi's `grep` is mapped onto `Read`, because it reads file contents and nothing else in Pi refuses a credential path to it; the dispatcher already turns its `path` into the `file_path` a `Read` is judged by.
Pi's `find` and `ls`, Claude's `Glob`, and Copilot's `file_search` and `list_dir` list names, not contents, and stay passthrough.
Two content reads remain unjudged: Copilot's `grep_search`, whose input holds a query and a glob but no path, and any search aimed at a directory that holds a credential, because a read beneath a declared ancestor is not gated.

**Alternatives considered:**

- Convert tool names in every Python hook: reverses the boundary decision, and each mapped tool still needs its fields translated and every settings file's matcher edited.
- Refuse only at the adapters, and have the assessment compare every harness's tool set against the vocabulary: a new tool that writes runs unjudged until the next assessment.
- Proceed and report when the vocabulary cannot be read, as the manifest does: removes the lockout and removes the refusal while the file is broken.

### Decision: PiRunsTheSharedHooksThroughAHookRunner

**Chosen:** Pi runs the shared hooks through a hook runner, an extension that gives Pi the registered-hook mechanism Claude Code, Codex, and Copilot provide natively.
The runner reads registrations in the shape of Claude Code's `hooks` setting and holds no policy.
Its TypeScript reimplementation of the policy is deleted.
The runner is a capability of Pi's harness, specified in `modules/home/ai/pi/.specs/specs/` (`hook-registration`, `hook-execution`, `hook-events`) and deployed as `~/.pi/agent/extensions/hooks/`; this change specifies the registration that uses it and what the shared side owes it.

**Rationale:** the north star says onboarding an agent means expressing this posture in that agent's vocabulary, not writing a new one.
Pi wrote a new one, and the cost shows up as this change's own work: parity is otherwise satisfied by porting `git-baseline-drift`, then the class model and its precedence, then the enforcement floor, then the shared lexer, then the admitted-utility set, then the ancestor gate, then the fail-closed error path — one port per capability change, each of which the other three agents got by editing one file.
Every future capability carries the same tax, and `VerdictSurfacesAgree` exists to catch the divergence the tax produces.

The line between the runner and the deleted extension is the one `EveryAgentImplementsEveryCapability` draws.
The runner runs what a registration names and carries each hook's outcome to Pi; with the hooks removed, it refuses nothing for what a call does.
The deleted extension held its own patterns, path lists, and tool-name checks, which is a second copy of the policy.

Feasibility was measured against a live `pi` rather than argued.
Pi awaits a `tool_call` handler across a subprocess boundary and honors the verdict it returns; a handler that blocks stops the tool, and the same handler returning an allow lets it run.
One dispatcher running the four Python hooks under `uv run --script` costs about 31-44ms per tool call, against 84-117ms for the deployed one-subprocess-per-hook shape that Claude already pays.
No hook needs changing: each is `main()` over stdin JSON exiting through `hook_response.respond()`.

Four properties of the runner's contract shape what the shared side builds.
A hook receives Pi's own tool names and input, such as `bash` and `path`, and a matcher compares tool names without regard to case.
Exit 2 blocks; on any other status a JSON reply decides, and a hook that exits 1 with no reply lets the call proceed with a warning to the user.
A `PreToolUse` hook that times out, cannot start, is ended by a signal, or writes a reply that does not parse refuses the call, with a reason naming the hook.
An ask becomes Pi's confirm dialog, and a refusal where Pi shows no user interface.

The shared side owes the runner two things.
The dispatcher must fail closed: a hook that raises an error it does not handle counts as a refusal, and any error in the dispatcher itself ends in exit 2 with the stop form of `AI INSTRUCTIONS`, never in exit 1, which the runner lets through.
That applies on reads too, where a hook's own handled error warns; an error that escapes a hook is a hook that gave no answer, which the runner refuses as well.
Because the runner shows a hook's standard error on exit 1 and lets the call proceed, Pi can express `Warn`, and `hook_response.py` encodes it for Pi as it does for Claude; the dispatcher reads exit 1 as a warning and an escaped error as a failure, so the two stay apart.
`hook-dispatch.py` is registered as one PreToolUse entry that runs the four Python hooks in one process; it maps Pi's tool names through `tool-vocabulary.toml` and refuses a name that is neither mapped nor passthrough, so the declaration keeps one reader and the runner knows no tool names.
The three shell hooks read no tool name, so the runner passes Pi's payload to them unchanged, a `bash` matcher selects their calls, and they keep their own processes.

`pi/security/` is Pi's counterpart of `copilot/hooks/`: it holds the registration, `hooks.json`, deployed as `~/.pi/agent/hooks.json`, and `hook-dispatch.py`, and nothing else once the TypeScript extension is deleted.
The dispatcher's cases are pytest cases in `pi/tests/`, as Copilot's adapter cases are in `copilot/tests/`, and `scripts/apps-test.sh pi` runs them beside the runner's suite.
Until the deletion lands, the directory holds both the old extension and the new registration.

Pi runs the shared classifier, so every property the generated cases hold of it, of the lexer, and of the matcher holds on Pi without a copy.
What Pi adds is the dispatcher's mapping of its tool names and `path` onto the declared vocabulary, and one generated property covers it: for any declared location, spelling, and file tool, the dispatcher reaches the same decision from Pi's call as from the same Claude call.
The verdict tables arbitrate the runner end to end, in `pi/tests/registration.test.mjs`.

A community runner was assessed and not adopted.
Of four published Claude-hooks extensions for Pi, three turn an ask or a refusal into an allow, and the closest, `pi-code`, reads hooks only from Claude's settings, allows a malformed reply or a hook killed by a signal, and lets a trusted project disable the user's hooks.
It is also about 20,000 lines with a large dependency tree, placed in the path that decides whether a tool call runs.

**Alternatives considered:**

- Keep the reimplementation and port each capability as it lands: the status quo, and the reason four ports sit in this change's task list.
- Keep it and adopt a third-party shell lexer so the two implementations tokenize alike: narrows one class of divergence in the current capability and leaves the tax on every later one.
- Adapt but keep the TypeScript as a fallback when the dispatcher fails: two policies again, and the fallback runs precisely when something is already wrong.
- Let a crashed hook inside the dispatcher reach `Ask` where `ErrorHandlingByDamagePotential` permits it and `Block` elsewhere: gives a dialog in place of a refusal for three of the four hooks, at the cost of a per-hook table in the dispatcher kept in step with the hooks.
- A Pi-specific adapter inside the security extension that spawns each hook itself: holds the event wiring and the tool-name mapping in TypeScript, which is Pi's registration written as code and a second reader of the vocabulary.
- Adopt `pi-code` or another published runner: rejected on the grounds above; its combination and process-handling design is reused under its MIT license.
- Port the three shell hooks to Python so one process runs everything: the closing task in `guarded-path-classes` already weighs a single-binary rewrite, and this change does not decide it.

### Decision: TheAdapterOwnsDegradationAndItsOwnFailures

**Chosen:** the shared layer declares Pi able to express `Ask`, and Pi's hook runner decides per call whether a prompt can be shown.

**Rationale:** Pi prompts through `ctx.ui.confirm`, which is available whenever a UI is attached and is uniform across tools — measured over RPC on `bash`, `write`, and `read`, where approve ran the tool, decline blocked it, and cancel blocked it.
So the tool is not the variable; `ctx.hasUI` is, and it is a per-session property no Python hook can observe.
`supports_ask` is a static table over agent and tool, so it cannot carry the answer, and the runner is the only layer that can.

The runner builds a refusal from the ask's reason when it cannot show the prompt or the user declines it, so for Pi the ask's reason carries the `AI INSTRUCTIONS` section that `BlockAIGuidance` requires on a refusal.
`hook_response.respond()` appends it when the agent is Pi.
The section also appears in Pi's confirm dialog, under the message; the runner holds no policy, so it cannot add the section itself.

The runner also owns its own failures.
A `PreToolUse` hook that gives no answer refuses the call with a reason naming the hook and what went wrong, and Pi blocks a tool whose handler throws, so no failure the runner sees lets a call through.

**Alternatives considered:**

- Pass `ctx.hasUI` into the hooks as an environment variable: makes a static capability table dynamic for one agent, and every hook would have to honor it.
- Declare Pi unable to express `Ask`: every guardrail gate becomes a refusal on an agent that can perfectly well ask, which is degradation with nothing forcing it.
- Rely on Pi's implicit block when the handler throws: fail-closed but unexplained, so the refusal does not carry `AI_INSTRUCTIONS`.
- Have the runner append refusal wording when it turns an ask into a refusal: puts this repository's policy text into a runner that holds none.
- Leave the ask reason as the message alone: Pi's refusals from an ask would be the only refusals without the instruction section.

### Decision: TheHooksAreAPackageIndependentOfAnyAgentConfiguration

**Chosen:** tests cover the hooks and the manifest, and nothing else.
No test reads an agent's configuration file.
Whether a configuration satisfies `agent-configuration-floor`, or covers the block class as `ConfigurationSurfacesCoverTheDeclarations` requires, is judged by an assessment: a recipe an agent runs on request, walking each requirement over the discovered configuration files and writing a dated record under `.specs/assessments/`.
`test_secret_floor_declarations.py`, `test_guardrail_declarations.py`, `test_network_declarations.py`, and `test_reviewer_policy.py` retire into it, and `test_posture_floor.py` is not written.

The recipe discovers its own scope rather than taking it from Python.
`modules/home/ai/` is the anchor: each directory there is a candidate harness, and the recipe judges which of them configures an agent that runs tools, then finds that agent's configuration surfaces wherever they live, including under `users/*/home-manager/`.
Not every directory qualifies, so the predicate is judgment rather than a glob, which is what an agent supplies and a test cannot.
The dated record names every file the run read.
`CLAUDE_SETTINGS`, `CODEX_CONFIGS`, and `SECRET_FLOOR_REPRESENTATIVES` in `conformance.py` lose their last Python readers when those four tests retire, so the two globs go and the representative paths move to where the recipe reads values from.

**Cadence is the operator's.**
The recipe runs when the operator runs it, and nothing in this repository checks whether a record is current.
No staleness check, no pre-commit trigger, and no scheduled routine, because each is a second surface that goes stale on its own and none can judge what it would be checking.
A posture claim is therefore as current as the last record, by design.

**Rationale:** the hooks are one package that any agent's configuration may register, so a test that reads a configuration pins the package to one vendor's keys and one repository's layout.
The keys move: the editor's approval settings have been renamed and re-defaulted across releases, and a test naming them either breaks on a rename or, worse, keeps passing against a key the vendor no longer reads.
A requirement that names the behavior stays checkable by a reader whatever the key is called, and an agent reading the current configuration against it is the check that survives the rename.
The secret floor is the hardest case, because a block-class miss cannot be undone, and it is retired on the same grounds: what it checks is that this machine's permission lists cover this manifest's block class, which is a property of the configuration, not of the package.
The hook refuses the block class on its own, and that is what the package promises.

**Alternatives considered:**

- Keep the secret-floor test as a carve-out: keeps the coupling for the one case where it feels safest, and the next contributor reads it as license to add the next one.
- A scheduled routine, or a check comparing a record against the inputs it names: both put a second surface behind a judgment the operator owns, and a stale record is visible to the person reading it.
- Scope the recipe to the files `conformance.py` globs: adding a harness becomes a Python edit, which is the coupling this decision removes.
- Declare the harnesses in a file beside the manifest: a maintained list fails silently when someone adds a harness and forgets the entry, which is the failure `CapabilityCoverageIsCheckedFromTheSpecsRoot` rejects for capabilities.
- Keep the tests and mark them `xfail` on a vendor change: keeps a check nobody reads.

### Decision: CapabilityCoverageIsCheckedFromTheSpecsRoot

**Chosen:** the coverage test enumerates the capability directories in `.specs/specs/` and holds one table, capability to kind and package artifact.
It asserts three things: every directory has a row, every artifact a row names exists (in `hooks/`, or in `tests/` for the conformance kind), and every hook in `hooks/` (a hyphenated file, per the module's naming rule) is named by some row.
A capability of the configuration kind has a row and no artifact.
Whether a given agent's configuration registers every hook is a question for the assessment, per the previous decision.

**Rationale:** not every capability is a hook.
After sync the specs root holds nine enforcement capabilities, four mechanism capabilities implemented by imported modules, one posture capability implemented by the manifest, one configuration capability with no package artifact, and one conformance capability, this one, which the coverage and verdict-table tests implement.
A check that maps every capability to a hook fails on seven of sixteen and says nothing true about them.

The table is in the test rather than derived, because the kind is not derivable.
A spec's text does not say whether it is implemented by a hook, a module, or the manifest, and a marker in a delta spec does not survive sync, which merges requirements and drops the preamble.
The table is not the hand-written agent-to-capability table the alternative below rejects: it holds one row per capability regardless of agent, and a capability with no row fails the check.
Adding a capability therefore still extends the check; what it adds is the obligation to say how the capability is implemented, which is the fact the check exists to record.

The reverse direction is the half a derived check could not give.
A hook that no capability claims is behavior with no requirement, and the specs root cannot enumerate what it does not know about.

**Alternatives considered:**

- A hand-written table of agent-to-capability: goes stale the first time a capability is added, and its agent side is configuration, which the assessment judges.
- Map every capability to a hook: the task as first written, and false for seven of sixteen.
- Declare the kind in each spec: the delta preamble does not reach the baseline through sync, so the marker would have to be added to the baseline by hand, which is the edit `AGENTS.md` forbids.

### Decision: RipgrepIsAdmittedWithItsConfigurationRefused

**Chosen:** `rg` joins the read classifier with `--pre`, `--hostname-bin`, `-z`, and `--search-zip` refused as whole tokens, and `--no-config` required in the first argument position.
The required-option rule is a named mapping beside the refused-option mapping, keyed by utility, rather than a rule about ripgrep.

**Rationale:** once the configuration file is off, ripgrep does only what its command line says, and `--no-config` turns that file off.

Tested against ripgrep 15.1.0.
`RIPGREP_CONFIG_PATH` pointed at a file holding `--pre=<program>`.
A plain `rg needle file` ran that program.
Adding `--no-config` stopped it, both as the first option and as the last.
`--no-config` does not stop a `--pre` written on the command line, so `--pre` is refused on its own.
`-z` and `--search-zip` run a decompressor found on `PATH` whose name the command never gives, so both stay refused.

The required option must come first because an option that takes a value can swallow it.
In `rg -e --no-config pattern path`, ripgrep searches for the text `--no-config`.
The configuration file still loads, and a `--pre` in that file still runs.
Checking position one costs one comparison.
The alternative is a table of every ripgrep option that takes a value, which is a second copy of ripgrep's interface to keep current.

Ripgrep 15 does not match an abbreviated option name: it rejects `--pr`, `--search-zi`, and `--hostname-bi`.
It does not match a differently-cased name either: it rejects `--PRE`, `--Pre`, `-Z`, and `--SEARCH-ZIP`.
Each refused option therefore has one spelling, which is what makes a whole-token check enough.
The classifier compares tokens exactly, so `--PRE=<program>` passes it as a read.
Ripgrep then rejects the command, and nothing runs.

`RIPGREP_CONFIG_PATH` is the only place outside the command line that ripgrep reads options from.
The manual does not name another, and its one other mention of `XDG_CONFIG_HOME` is about where to install shell completions.
The manual also says `--no-config` will turn off any fixed configuration location ripgrep adds later, so this rule does not depend on the current source staying the only one.

The cost is one wrong refusal.
The check rejects any short cluster holding `z`, so it rejects `rg --no-config -tzsh pattern`, where `zsh` is the value of `-t`.
This errs toward refusing, never toward allowing, and both `-t zsh` and `--type=zsh` are accepted.

**Alternatives considered:**

- Leave `rg` out and point the agent at `grep`.
  The refusal already names `grep`, but the instruction attached to it tells the agent not to use a different command.
  Leaving `rg` out stopped a Codex session that was listing the files in a skills directory.
- Read `RIPGREP_CONFIG_PATH` from the hook's own environment instead of requiring the option.
  The command's shell loads the user's profile and the hook does not, so the hook cannot see a variable the profile exports.
  No shell profile is a declared location, so nothing stops an agent from writing one.
- Parse short options with their arguments, so `-z` is refused but `-tzsh` is not.
  That is a second copy of ripgrep's interface, in exchange for one wrong refusal that has a working spelling beside it.

### Decision: ATrapBodyIsReadAsProgramText

**Chosen:** `_program_text` returns a `trap` body the same way it returns an `eval` body.

**Rationale:** the segment rule says a segment naming no guarded location is not judged.
That rule assumes each segment runs on its own.
A `trap` body does not: the shell runs it beside every later command, including the recognized read that follows it.

`trap '<body>' DEBUG; cat <guarded file>` was allowed by all five Bash hooks.
So were the `ERR` and `EXIT` forms, and the same shape with `rm -rf` or `cp` over a guarded path in the body.
The `DEBUG` trap fires in bash, which is the shell this repository pins for Claude, so this is not specific to zsh.

The body is one quoted word, which is why no rule caught it.
Every path check runs per word, and `'cp /tmp/x ~/.claude/settings.json'` is a single word that does not match any declaration.
`_program_text` is the existing route for text a segment runs rather than names, and `_segment_class` already runs `mentioned_in` over what it returns.
Adding `trap` there does two things at once: the body's paths are judged, and `_builder_segment` sees program text and withdraws the read carve-out from the whole command.

This closed all six reproductions and broke none of six ordinary reads: `cat`, `rg`, `grep`, `find`, a banner between two reads, and a piped read.

Function definitions are a weaker variant.
`f() { rm -rf ~/.claude/skills; }` already gates, because a function body is lexed word by word and the path is its own word.
A definition naming nothing guarded is still judged as installing code, so it withdraws the read carve-out from the command around it.

**Alternatives considered:**

- Add `trap` to the builder set instead.
  That withdraws the carve-out but never reads the body, so `trap 'cp /tmp/x ~/.claude/settings.json' DEBUG` alone would still name a guarded path that nothing judges.
- Lex the trap body as a nested command.
  The lexer refuses nested command strings by design, and a second parser is the thing that design avoids.

### Decision: TheRefusalInstructionFollowsTheReason

**Chosen:** a refusal ends with one of two instructions, chosen where the decision is made instead of appended to every `Block`.
A refusal from a declaration keeps the current instruction: stop, report, and do not run a different command that does the same thing.
A refusal from an unrecognized command names the accepted forms and tells the agent to run the command again in one of them.

**Rationale:** the two refusals mean different things and read the same today.

A declaration refusal is the policy's answer.
Another command that reaches the same place is the same operation, so telling the agent not to try one is the point of the message.

An unrecognized command got no answer.
It named a guarded location, the classifier could not tell what it does there, and the hook refused a command it could not judge.

`_accepted_forms()` already lists every admitted utility in that message, and `respond()` appends the stop instruction to every `Block`.
One message therefore names the commands that work and then forbids them.
A Codex session ran `git diff` on a guarded hook file, read both halves, and stopped, which is what the stop instruction asks for everywhere else.

Claude sees the same case as a prompt, so the whole cost falls on agents that cannot show one.
The posture says degradation must grant no more than the full encoding would.
Here it grants less: it takes away work no declaration refuses.

`block-dangerous-bash.sh` holds its own copy of the stop instruction and keeps it.
It refuses a named class of command, so every call it judges is one it was registered to refuse, and no other spelling is allowed.

**Alternatives considered:**

- Drop the stop instruction from every refusal.
  It is correct for a declaration refusal, and removing it invites an agent to try another layer instead.
- Leave the text and admit more utilities instead.
  The admitted set is finite, so the next unrecognized command meets the same contradiction.
  `git` cannot be admitted at all, because `git -c core.pager=<program>` runs a program.

### Decision: TheRenderedSecretIsDeclaredRatherThanGuessedAt

**Chosen:** `~/.config/mcp-secrets.env` joins `[block]`, and `<repo>/scripts/mcp-secrets.sh` is excused from the name heuristic by an `[[exceptions]]` table the hook now reads.
The declarations themselves are posture, recorded in `guarded-surface` `AgentCredentialsAreBlocked` and `NameHeuristicExceptionIsDeclared`; this change carries the mechanism each rests on.

**Rationale:** the rendered file holds the API keys the MCP servers start with, and nothing declared it.
`DOTENV_RE` wants `.env` at a path boundary, so a `*.env` suffix reaches no strong rule; the whole of its protection was the guess that a name carrying "secrets" holds some.
No deny glob in any Claude settings file or Codex configuration covered it either — the `**/.env` rules match a file named `.env`, not one ending in it.
A single heuristic layer under a live credential contradicts the posture that layers are independent, and it made the file's safety depend on its name, so renaming to fix the script's false positive would have removed the protection from the secret.

Declaring it inverts that: the refusal now follows from the manifest, and `test_secret_floor_declarations.py` required eleven surface entries across seven files before it would pass, which is the measure of how far the gap ran.
Pi needs no port: the migration below has it read the shared hook.

The script is the opposite case and needs the opposite treatment.
The name heuristic guesses contents from a name, so it is the one class a file can be excused from by declaration, and this module already says a loosening belongs in `[[exceptions]]` with its reason.
That table was read by tests and by nothing else, so an entry alone would have recorded an intention while changing no behavior.
The hook now builds its exemption from it, matched one spelling at a time like every other rule there, so a link cannot borrow an excuse written for its target.
`guarded-surface` also declares a second surface, `sensitive-path-nix-hook-wrapper`, which excuses a Home Manager store symlink by its verified target under conditions the declaration states.
That is a surface of its own with its own rule; the per-spelling rule here is stated for the name-heuristic surface alone.

**Alternatives considered:**

- Rename the family: withdraws the only protection the rendered secret has, to fix a false positive on a program.
- Exempt source-code extensions from the name heuristic: unbounded, and nothing sits behind it — `block-secrets.py` judges exfiltration, not the content of a read.
- Add the script to `NAME_HEURISTIC_EXEMPT_RE`: a second place loosenings are written, and the one with no stated reason.

### Decision: APatchIsJudgedByItsTargetsNotItsText

**Chosen:** where `extract_apply_patch_targets` yields a file, the gate judges those files alone; where it yields none, it judges the command text as before.

**Rationale:** the gate ran `GUARDED.mentioned_in()` over the whole patch body, added lines included, so a patch was refused for naming a guarded path in the content it wrote.
A bridged Codex session hit this: it could not write its own log of being blocked, because the log quoted the paths that blocked it.
The same refusal covers a changelog entry, an incident note, and a spec citing the hook it specifies — which is most of the writing this module asks for.
Claude never meets it, because its gate is a prompt; the agent whose gate is a refusal is the one that cannot record the refusal.

The target list is safe to trust because the patch format declares every file it writes in a header at column zero, which is what the applying tool parses and what the extraction regex matches.
The two agree, so a non-empty list is the complete set rather than a sample.
An empty list means nothing parsed, and there the text is still all that is left.

`Write` and `Edit` never had the defect: `_written_paths` reads `file_path` and never looks at content.
Bash is unchanged, because a shell command states no intent and has no target list to extract.

This removed the last caller passing `targets` to `command_protected_class`, so that parameter and its `exempt_pool` branch went with it; each target is judged on its own by `protected_class`, which applies `guarded-path-declarations` `PrecedenceIsOneRule`.

**Alternatives considered:**

- Strip added-content lines before matching the text: same outcome by a longer route, and it reimplements patch parsing to decide what not to parse.
- Keep the body match and carve out a directory agents may write notes in: moves the problem to wherever the note has to live, and leaves specs and changelogs still refused.
- Leave it and have agents avoid naming guarded paths in prose: the paths are the subject of this module's documentation.

### Decision: DamagePotentialFollowsTheToolNotTheRegistration

**Chosen:** the tamper hook picks its error direction from the tool the payload names, rather than from the set of tools it is registered for.

**Rationale:** the hook caught every exception and exited 0, against `ErrorHandlingByDamagePotential`, which already required a sensitive tool not to proceed on a hook crash.
Its comment justified the exit as a mixed tool set — true of the registration, which covers `Read`, and false of the four tools it judges, every one of which can modify state.
The baseline did not separate the two, so the hook and the requirement disagreed on an axis neither named.
Modifying the requirement rather than only the hook is what draws that distinction: a hook registered for both chooses per call, and falls back to the read-only direction only where the payload names no tool.

This was reachable, not theoretical.
`os.path.expanduser` raises on a null byte, every containment test runs through it, and `~\x00` therefore allowed the call on every agent.

**Alternatives considered:**

- Fix the hook alone, leaving the requirement as written: the requirement says `exit 2` for sensitive tools with no account of a hook covering reads too, so the next such hook meets the same ambiguity.
- Keep failing open and rely on the sandbox and permission layer: guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, so the permission layer permits by design the write this hook exists to ask about.

### Decision: AnInternalErrorAsksRatherThanBlocks

**Chosen:** on an unexpected error judging a mutating tool, the hook reaches `Ask`, degrading to `Block` where the agent cannot show a prompt.

**Rationale:** this hook runs on every call to a sensitive tool, and most of those reach nothing it guards.
A fault in a shared step — path resolution, the containment test — recurs on every call, so `Block` would refuse every mutation the agent attempts with no route left for the user to say otherwise.
`Ask` grants nothing the full encoding would: where no prompt can be shown it is the same refusal.

The requirement now carries the condition rather than the exception.
A hook that refuses a named class of command still reaches `Block` on an error judging one call.
A command hook that cannot load its rules reaches `Ask` on the same ground; `AnUnusableRuleFileAsks` records why.

**Alternatives considered:**

- `Block`, as the baseline named: correct for a fault confined to one call, and unusable for a fault that recurs on every call.
- `Warn` for both: the tool proceeds unchecked, which is the behavior being removed.

### Decision: AnUnusableRuleFileAsks

**Chosen:** `block-destructive-ops.py` uses its pattern file only when every rule in it is valid.
A missing, unreadable, or unparsable file, or one invalid rule, reaches `Ask` on every `Bash` call, with a reason that names the fault, degrading to `Block` where the agent cannot show a prompt.
A test over the shipped pattern file checks every rule, so a typo fails the suite before it is deployed.

**Rationale:** the hook returned no rules for a missing or unreadable file and allowed every command, and it skipped a rule with an unknown mode or a pattern that did not compile.
`mode = "deny"` therefore turned one protection off with nothing reporting it.
The convention for security policy is to refuse a configuration that does not validate rather than enforce part of it: `visudo -c`, `sshd -t`, and `nginx -t` check before the configuration takes effect, and `nft -f` rejects a whole ruleset file for one bad line.
A warning on an allowed call is not a substitute: a hook that exits 0 usually does not show its stderr to the user.
The user chose `Ask` over `Block` on 2026-10-05.
The fault recurs on every `Bash` call, most of which match no rule, so `Block` would stop all shell work, including the test run that confirms the fix.
`Ask` puts each call to the user with the fault named, and grants nothing on an agent that cannot prompt.

The earlier statement that a command hook reaches `Block` "because every call it judges is one it was registered to refuse" was false for this fault: the hook judges every `Bash` call.
`ErrorHandlingByDamagePotential` now separates an error judging one call from a failure to load the rules.

**Alternatives considered:**

- Warn and continue with the valid rules: the convention for settings that enforce nothing, and silent in practice here.
- `Block` on every `Bash` call: fail-closed and simple, and leaves the user no way to keep working while the file is broken.
- Keep a missing file fail-open and refuse only an invalid rule: a deleted file would then grant more than a broken one.
  Nix deploys the file, so its absence is a deployment fault, not a choice.

### Decision: TheAssessmentChecksTheFloorsHookDirectories

**Chosen:** the assessment compares the directory of every hook an agent registers, and the repository directory each deployed link resolves to, with `HOOK_DIRECTORIES`, under the new requirement `RegisteredHooksLieInTheEnforcementFloor`.

**Rationale:** `guarded-path-classes` defers a rule that discovers hook directories, because a glob for this repository's layout pins the floor to it and deriving the floor from declared paths let a permissive spelling escape it.
Until that rule exists, a directory left out of the code-held list is outside the floor, and nothing reports it.
The registrations name every hook an agent runs, but they are vendor configuration, so a hook that read them would carry the vendor coupling `TheHooksAreAPackageIndependentOfAnyAgentConfiguration` removed from the tests.
The assessment already reads them.
The user asked for the check on 2026-10-06.

**Alternatives considered:**

- Have the hooks derive the floor's hook directories from the registrations: no list to forget, at the cost of parsing four vendors' formats on every call.
- Leave the deferral alone: a forgotten directory stays silently outside the floor until someone notices.

## Architecture

```text
.specs/specs/<capability>/          the expected set
        |
        v
 coverage test ------> claude    -> shared hooks (direct)       [inherits]
        |              codex     -> shared hooks (adapter)      [inherits]
        |              copilot   -> shared hooks (adapter)      [inherits]
        |              pi        -> shared hooks (adapter)      [inherits]
        v
 verdict tables (guarded-path-cases.json, sensitive-path-cases.json)
        |
        +--> direct invocation  --\
        +--> codex adapter      --|
        +--> copilot adapter    --+--- outcomes must match
        +--> pi adapter         --/
```

Every agent now reaches the capabilities through the shared hooks, so no surface carries a second copy of the policy.
Coverage still does not follow from hook registration alone: an adapter also has to hand the hook a payload it recognizes.
`normalize_payload` in `copilot-vscode-hook-adapter.py` ends its mapping chain with `or tool_name`, so a VS Code tool with no mapping reaches the hooks under its own name, matches no gated tool, and is allowed — a registered hook chain that does not gate.
Registration is therefore necessary and not sufficient, and `AdapterNormalizationIsTotal` carries the rest.

The verdict tables consequently arbitrate the adapters rather than two languages.
That is where the remaining divergence lives: an adapter holds no policy, so its failures are in the payload it builds and the outcome it decodes, and both are invisible in its source.

## Risks

- **The bypass list goes stale.**
  An agent adds a new escape hatch and the floor does not know its name.
  Mitigation: accepted and visible — the requirement names the values, so a reader auditing an agent's release notes has something concrete to check against.
  The assessment is what reads them, and an agent running it against a release that renamed a key is positioned to notice, where a test naming the old key would keep passing.
- **Parity makes debt into a failing check.**
  The coverage test fails until Pi reaches every capability.
  Mitigation: the migration in this change closes every gap at once.
  If it is deferred, the alternative is a declared exception with a reason, which is the mechanism `ExceptionsAreDeclared` already provides — not a skipped test.
- **The migration adds a subprocess to Pi's gating path.**
  Every Pi tool call now waits on `uv`, where it previously decided in-process.
  Mitigation: measured at 31-44ms against the 84-117ms Claude already pays, and the failure direction is safe — Pi blocks a tool whose handler throws.
  `TheAdapterOwnsDegradationAndItsOwnFailures` covers making that refusal legible.
- **The deletion is hard to reverse.**
  Ten TypeScript modules and their suite go.
  Mitigation: the verdict tables are the acceptance gate, so the migration is judged by outcomes before the deletion lands, and the modules remain in git history.
- **Pi's class behavior depends on another change.**
  `guarded-path-classes` defines the class model and is merged but not yet synced.
  Mitigation: the migration gives Pi whatever the shared hooks implement at the time it runs, so the class outcomes arrive with the adapter rather than needing their own Pi tasks, and the temporary exception that change recorded is removed when the adapter passes the deferred cases.
- **A hook under an unreadable directory stops running.**
  A shell hook run directly exits 126 when a directory above it loses its execute bit, and Claude reads 126 as a non-blocking error, so that hook stops judging.
  A hook run through `uv run --script` exits 2 instead, which every agent reads as a refusal, so the session stops rather than proceeding unjudged.
  Mitigation: the ancestor gate asks before a mode change reaches that directory.
- **Each turn hashes the working tree twice.**
  The turn-start and turn-end snapshots add every changed and untracked file that is not ignored to the object store, so a large untracked file slows every turn and leaves unreachable objects until `git gc`.
  Mitigation: the snapshots copy the real index, so unchanged tracked files are not hashed again; ignore large generated files.
