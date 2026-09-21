# Tasks: security-posture-alignment

## Working tree

The deployed hooks are symlinks into `~/.nixconfig`, and `shared/hooks.nix` enumerates `hooks/` at activation, so a file added there has no deployed symlink until the next `just nix switch home`.
A hook invoked through its deployed symlink resolves `sys.path[0]` to the repository directory it points into, so a module a hook imports is live as soon as it exists there; a file run by path, such as `tool-vocabulary.toml`, is not until activation.
`pi/default.nix` deploys the Pi extension's modules by name from `securityModules`, so a module added or removed there has no effect until activation either.
An edit in the main checkout is live in every open agent session the moment it is saved.

- [x] Do this change in a git worktree on its own branch, so the main checkout stays what the live agents run.
  `guarded-path-classes` is merged and activated; its deltas sync together with this change's.

Groups run in completion order.
The package work comes first: the end-of-turn hook move, the tool vocabulary, the package-side coverage test, and the Pi migration, which maps onto the vocabulary and is judged against the verdict tables before any TypeScript is deleted.
The cross-surface parity items follow the migration, because they need the Pi adapter to exist.
The configuration work comes next: the editor's approval values and domain list, then the editor sandbox, then the Pi sandbox, and the assessment last, because it judges every surface the earlier groups declare and its first run is this change's evidence.
The closing items, the merge, and the activation end the open work.
Completed groups follow, as the record of what this change already did.

## Guard the end-of-turn hook Claude runs

`77eaff3` registered `~/.local/bin/clean-cc-writes` as a Stop hook in every Claude settings file.
It is a Home Manager link to `modules/home/ai/claude/clean-cc-writes`, which sits beside the declared `modules/home/ai/claude/hooks/` rather than inside it, so a script Claude runs at the end of every turn is writable by any agent without a prompt.
`guarded-surface` `RepositorySourcesAreGuarded` enumerates each agent's hook directory and names the cost of enumeration: a source added outside the directory is unguarded until listed.

- [x] Move `clean-cc-writes` into `modules/home/ai/claude/hooks/` as `clean-cc-writes.sh`, and keep the `~/.local/bin/clean-cc-writes` link for the by-hand use the module comment records.
  A declaration change is not needed: the hook directory is already guarded and already inside the enforcement floor.
  The `.sh` suffix matches the two hooks already there; the `~/.local/bin` name stays bare, because it is a command an operator types.
- [x] Give every file in `modules/home/ai/claude/hooks/` a `home.file` entry in `claude/default.nix`.
  There was no hook-directory entry to deploy through: `shared/hooks.nix` enumerates `shared/hooks/` alone, and a Claude-owned hook is deployed only if it is named here.
  `42b0f48` wired `reload-skills.sh` into the four settings files and added no entry, so the post-compaction catalog reload it introduced has never run.
- [x] Point the four Claude settings files' Stop entry at the new path.
  The user commits that step, because the sandbox denies the agent those files.
- [x] Add a case to `tests/test_guarded_surface.py`: a write to the moved script asks on every agent.
- [x] Assert in `claude/default.nix` that every file in `claude/hooks/` has a `home.file` entry, so an added hook fails evaluation rather than deploying nothing.
  Only this direction is assertable: a file an operator places in `~/.claude/hooks` is outside the repository, so no entry is expected for it.
  `test_hook_wiring.py` compares a wired name against repository source files instead, which is why it passed over a hook nothing deployed.

## Declare the tool vocabulary and close the adapter fall-through

- [ ] Declare the gated tool vocabulary in `hooks/tool-vocabulary.toml`, with each harness's spelling of each tool mapped onto it and Claude's declared as identity.
  A file of its own, because `OnlyPolicyTablesExist` holds `guarded-paths.toml` to the five policy tables and `test_guarded_paths_manifest.py` enumerates them.
- [ ] Read the vocabulary in `guarded_paths.py` and replace `MUTATING_TOOLS` in `block-hook-tampering.py`, `SENSITIVE_TOOLS` in `block-secrets.py`, the tool tuple in the `main` of `block-sensitive-paths.py`, the `Bash` test in `block-destructive-ops.py`, and `_COPILOT_ASK_TOOLS` in `hook_response.py` — evidence for `VocabularyReadFromTheDeclaration`.
  No second reader is written for Pi: the adapter below maps Pi's tool names onto the declaration, and `manifest.ts` and the literals in `index.ts` are deleted with the port.
- [ ] Add a case asserting a spelling added to the declaration is honored by every implementation with no further edit — evidence for `SpellingDeclaredOnceReachesEveryConsumer`.
- [ ] Add a case asserting an implementation holding its own tool vocabulary fails the check, so a passing suite is evidence the check can fail — evidence for `ImplementationCarriesItsOwnCopy`.
- [ ] Replace the `or tool_name` fall-through in `normalize_payload` in `copilot-vscode-hook-adapter.py` with a refusal, so an unmapped VS Code tool is denied rather than forwarded — evidence for `UnmappedToolIsRefused`.
- [ ] Add a case asserting an unmapped tool name is refused and does not reach the shared hooks, and a case asserting a mapped name is judged under the declared vocabulary — evidence for `UnmappedToolIsRefused` and `MappedToolReachesTheGate`.

## Establish parity in the package

- [ ] Add `tests/test_capability_coverage.py`: enumerate the capability directories under `.specs/specs/`, map each to the hook in `shared/hooks/` that implements it, and assert none is unimplemented — evidence for `EveryAgentImplementsEveryCapability` on the package side.
  `guarded-surface` is posture, evidenced by `test_guarded_surface.py` rather than by a module.
  Whether each agent's configuration registers every hook is judged by the assessment recipe, which reads the registrations `hooks.json`, `security-policy.json`, the Claude settings, and the Pi extension declare — evidence for `CapabilityMissingFromOneAgent`.
- [ ] Give that test a declared-exception path reading the manifest's `[[exceptions]]` tables, so a deliberate omission passes and an undeclared one fails.
- [ ] Add a case asserting a capability with no hook in the package fails the check, so a passing suite is evidence the check can fail.

## Migrate Pi onto the shared hooks

Pi has a temporary exception from the class outcomes and lexer behavior introduced by `guarded-path-classes`.
The reader update preserves manifest loading and credential blocking, but does not establish parity.

Ordered so the dispatcher is judged against the verdict tables before any TypeScript is deleted.

`pi/security/shell-words.ts` has none of the word kinds, the word-expansion handling, the ancestor closure, or the fail-closed error path the shared hooks now carry, and `guarded-paths.ts` implements none of the class outcomes or the per-hop precedence.
Deleting both is a task below, so the gap is carried until then rather than ported into code this change removes.

- [ ] Add a dispatcher that runs every shared hook in one process over one payload, returning refuse, ask, or allow.
  It loads each hook by file path, captures stdout and stderr, and catches `SystemExit`, so no hook changes.
- [ ] Have the dispatcher decode ask from allow by reading `permissionDecision` on stdout rather than the exit status, and continue through the remaining hooks after an ask — evidence for `AskIsNotReadAsAllow` and `EveryHookRunsAfterAnAsk`.
- [ ] Have the dispatcher return the most restrictive decision reached — evidence for `BlockOutranksAsk`.
- [ ] Add `PI` to the agent markers in `hook_response.py` and make `supports_ask` return true for it on every tool — evidence for `AdapterNamesARecognizedAgent`.
- [ ] Add a case asserting an adapter that names no agent, or an unrecognized one, refuses a call that needed a prompt — evidence for `AdapterNamesNothingOrSomethingUnknown`.
- [ ] Write the Pi adapter in `pi/security/`: normalize the payload onto the declared tool vocabulary, set the agent name, carry the tool call's working directory as `cwd`, dispatch, and translate the verdict into Pi's shape.
  The `cwd` is load-bearing: a relative path with no supplied directory is unresolvable and gates, per `path-matching` `TextMatchingIsForTextThatMayHoldNoPath`.
- [ ] Have the adapter run `ctx.ui.confirm` on an ask when a UI is attached and refuse when none is, so the ask never becomes an allow.
- [ ] Have the adapter catch its own dispatch failures and refuse with an explanation carrying `AI_INSTRUCTIONS`, rather than letting the raw exception reach the agent.
- [ ] Add a case asserting a missing interpreter refuses the call and that the refusal carries the explanation — evidence that the adapter owns its failures rather than relying on the harness.
- [ ] Judge the Pi adapter against `guarded-path-cases.json` and `sensitive-path-cases.json`, asserting it reaches the same outcomes as a direct invocation — evidence for `AdapterDiverges`.
- [ ] Add cases covering a credential write staying a refusal on an ask-capable agent, a recognized read under a skills directory proceeding, and a guarded write reaching an ask.
- [ ] Record which properties the Pi surface is held to once it reads the shared classifier, so the generated cases arbitrate both surfaces the way the verdict tables do.
- [ ] Verify all deferred class outcomes, per-hop precedence, and lexer cases through the Pi adapter; remove the temporary Pi exception and its divergence records only when they pass.
- [ ] Drop `AGENT_INSTRUCTIONS` from `index.ts`, a paraphrase of `AI_INSTRUCTIONS` in `hook_response.py`.
  A refusal reaching the adapter already carries its own text, so the constant is an eleventh copy of policy wording with no reader.
- [ ] Have the `agent_settled` handler run `stop-precommit.sh` rather than the ported logic, feeding it a payload carrying `cwd`, and translating exit 2 with its stderr into the follow-up message Pi already sends.
  Keep `reportedThisStreak`: it is the `stop_hook_active` analogue, and capping the agent at one blocking round is harness state rather than policy.
  Keep a spawn timeout too — `precommit.ts` caps the run at five minutes and the shell script caps it at nothing, so dropping the port drops the only bound on it.
- [ ] Judge the adapter's end-of-turn path against the `end-of-turn-precommit` scenarios, so the contract has second-surface evidence without a second implementation.
- [ ] Reduce `pi/security/index.ts` to event wiring and the adapter calls for tool payloads and the turn boundary; keep the current `session_start` behavior until the deferred startup-policy decision.
- [ ] Delete the reimplementation modules and their cases, `precommit.ts` and `manifest.ts` among them, and update the `securityModules` list in `pi/default.nix`, which fails at extension load rather than at build when a name is missing.
- [ ] Delete `tests/test_pi_guarded_declarations.py`, which reads the port's source for manifest literals and was paused by `guarded-path-classes`; the adapter's verdict-table case above replaces it.
- [ ] Restore a Pi check to `outputs.checks` in `flake.nix` and `_test-pi` to `_test-all` in `justfiles/apps.just`, both unhooked by `guarded-path-classes` until the migration landed.
- [ ] Update `modules/home/ai/shared/AGENTS.md`: Pi reaches the hooks through an adapter like the other three agents, and its suite judges the adapter rather than a second implementation.
- [ ] Revert both dependencies from `security-extension-package.json`: `shell-quote`, whose only consumer was the deleted lexer, and `smol-toml`, whose only consumers were `destructive-ops.ts` and `manifest.ts`.
  The extension reads no declaration of its own once the dispatcher judges the payload, so nothing is left that parses TOML.
- [ ] Run `pytest -q` over the shared, claude, and copilot suites, `node --test ai/pi/security/index.test.mjs`, and `nix build .#checks.aarch64-darwin.shared-hook-tests`.
- [ ] Exercise a live `pi` session over RPC: a refused credential write, an ask-gated guardrail edit answered both ways, a recognized read under a skills directory, and a script run under one.
- [ ] Have the `session_start` handler run `session-tool-checks.sh` rather than the ported list, translating its output into `ctx.ui.notify`.
  Name the agent as Pi on that call too, so the `CLAUDE_CODE_SHELL` check stays silent per `session-tool-checks` `AnotherAgent` while the manifest validation still runs.
  Pi carries its own copy of the required set (`uv`, `jq`, `perl`), the recommended set (`gitleaks`, `rg`, `prek`), and the split between them.
  Decide the divergence while replacing it: the shell exits 2 on a missing required tool, which ends the session, and Pi only notifies.
  Nothing records which is intended, and the tool-dependency check is the one guardrail whose failure makes the others unreliable rather than absent.

## Judge every surface against the verdict tables

- [ ] Assert `guarded-path-cases.json` and `sensitive-path-cases.json` are judged by every surface that reaches a verdict, and that a table entry no surface covers fails — evidence for `SharedTableAgrees` and `ReimplementationDiverges`.

- [ ] Add a case pinning `CapabilityAmendedInOnePlace`: an entry added to a verdict table with only one verdict-reaching surface updated fails.

- [ ] Confirm each scenario in `end-of-turn-precommit` maps to a case in `claude/tests/test_stop_precommit.py`, and name the mapping in the verify record.

`precommit.ts` is a line-for-line port of `stop-precommit.sh` — the same runner preference, the same `HEAD`-or-`--cached` selection, the same `--diff-filter=d`, the same `run --files`, the same failure text, and the same three explanatory comments word for word.
It is the second copy of the policy that `PiAdaptsRatherThanReimplements` exists to remove, so the second write-site it would need cases for is a write-site this change deletes.
Pi already spawns subprocesses to do this work, so it can run the shared script instead.
The contract is therefore evidenced through the adapter, under the migration group above, rather than by adding cases here.

## Align the editor's approval configuration

The two VS Code settings files are JSONC and already carry comments, so each declared value carries its reason beside it; `check-json` excludes them.
`modules/home/apps/vscode/settings.json` serves every user without a `users/<name>/home-manager/vscode/settings.json` of their own, per `settingsSource` in the VS Code module, so it is mithras's file and alex.graber's is their own.
Values and defaults below are from the VS Code documentation and the 1.136.1 build; where the two disagree the build governs and the disagreement is recorded in `TheEditorSandboxIsPinnedOnAndClosed`.

- [ ] Declare in both files, each with a one-line comment stating what it closes: `chat.tools.global.autoApprove` false, `chat.permissions.default` `"default"`, `chat.assistedPermissions.enabled` false, and `chat.tools.terminal.enableAutoApprove` false, which is already declared and gains its comment.
  `TheEditorPromptIsCopilotsEscalationSurface` is the reason for the last: with it false, every terminal command reaches the user.
- [ ] Add a comment on the `~/.copilot/hooks` entry of `chat.hookFilesLocations` stating that it is the only thing loading this repository's hooks, because the directory is not among the editor's defaults.
- [ ] Read the default of `chat.useHooks` from the build; if it can switch hook execution off, declare it true with a comment, and add it to `BypassModesAreRefused` beside `chat.hookFilesLocations`.
- [ ] Declare `chat.agent.allowedNetworkDomains` in both files as the same host set the file's owner declares for Claude and Codex, and `chat.agent.networkFilter` true so the same list governs the fetch tool and the integrated browser.
  This precedes the sandbox pin below: under an enabled sandbox an empty list blocks every domain for terminal commands.
- [ ] Add the editor's approval values and `chat.agent.allowedNetworkDomains` to the assessment recipe, so `EditorApprovalBypassed` and the editor's side of `NetworkReachIsUniformPerUser` are judged with the other two agents.
- [ ] Re-measure, against a live 1.136.1 session, whether the terminal tool honors a `PreToolUse` `ask`; the hooks reference says it does and `_COPILOT_ASK_TOOLS` says it does not.
  If it does, widen `supports_ask` for Copilot and record the change in `hook-interface` `ExitCodes`, which names the Copilot encoding.
- [ ] Update `copilot/AGENTS.md`: the sandbox is Copilot's OS-level layer once pinned, the editor prompt is its escalation surface, and the session-level bypasses are recorded as the limit `SessionLevelBypassIsOutsideTheFloor` names.

## Close the editor sandbox

Values read from the installed VS Code build rather than the docs, which lag it.
Confirm they still exist before applying: the keys carry a `preview` tag and `minimumVersion` of 1.116, and this repo runs 1.136.1.
The domain list in the group above lands first.

- [ ] Declare `chat.agent.sandbox.enabled` as `"on"` in `modules/home/apps/vscode/settings.json` and in `users/alex.graber/home-manager/vscode/settings.json`, whose chat blocks are currently identical.
- [ ] Declare `chat.agent.sandbox.allowAutoApprove`, `chat.agent.sandbox.allowUnsandboxedCommands`, and `chat.agent.sandbox.retryWithAllowNetworkRequests` as `false` in both files, and `chat.agent.sandbox.allowNetwork` as `false` so the value is stated rather than inherited, each with a comment naming what it closes.
- [ ] Add the three permissive sandbox values and the declared sandbox switch to the assessment recipe — evidence for `EditorSandboxLetsTheAgentPastIt`, `ExperimentControlledSettingLeftUnset`, and `ExperimentControlledSettingDeclared`.
- [ ] Verify against a live VS Code agent session that a command reaching a guarded path is refused by the sandbox and that no unsandboxed retry is offered, then record the observed behavior in the verify record.
- [ ] Declare `chat.agent.sandbox.fileSystem.mac` and `chat.agent.sandbox.fileSystem.linux` `denyRead` and `denyWrite` lists covering the manifest's `[block]` class by concrete path, so the editor sandbox refuses what the other floors refuse.
  Hand-authored rather than generated from `guarded-paths.toml`, for the reason `ThePiSandboxIsClosedFromTheManifest` gives: the assessment judges every surface the same way, and a generated surface beside hand-written ones puts the manifest in two relationships with its consumers.
  The block class alone: `guarded-path-declarations` `ConfigurationSurfacesCoverTheDeclarations` holds every floor to it, because no surface can express the ask-with-carve-out the guarded class carries.
  Until it lands, the sandbox restricts reach but does not know this repository's block set.

## Close the Pi sandbox

`pi/default.nix` copies the sandbox extension out of Pi's derivation and writes no configuration, so it runs on the vendor defaults.
The extension merges a global `~/.pi/agent/extensions/sandbox.json` with a project file under the working directory; the global file is the one this repository owns.
This group is independent of the migration above: it is Pi's OS layer, not its hook layer.

- [ ] Declare `~/.pi/agent/extensions/sandbox.json` from `pi/default.nix`, with `filesystem.denyRead` and `filesystem.denyWrite` covering the manifest's `[block]` class by concrete path, each entry carrying the reason the other surfaces carry.
  Hand-authored rather than generated from `guarded-paths.toml`, per `ThePiSandboxIsClosedFromTheManifest`.
- [ ] Declare `network.allowedDomains` as the same host set the file's owner declares for Claude and Codex — evidence for `NetworkReachIsUniformPerUser` on the fourth agent.
- [ ] Add `enabled`, `ignoreViolations`, and `enableWeakerNestedSandbox` to `BypassModesAreRefused` in the `agent-configuration-floor` delta, and declare the first true and the other two false in the file.
- [ ] Add the Pi sandbox file to the assessment recipe, judged against the block class by concrete path like the other surfaces.
- [ ] Verify against a live `pi` session that a read of `~/.config/mcp-secrets.env` is refused by the sandbox with the hooks disabled, so the layer is shown to deny on its own.
- [ ] Update `pi/README.md` and `modules/home/ai/shared/AGENTS.md`: Pi's OS layer is the sandbox extension, and this repository writes its deny lists.

## Assess the configuration floor

No test reads an agent's configuration file, per `TheHooksAreAPackageIndependentOfAnyAgentConfiguration`.
The requirements in `agent-configuration-floor`, and `ConfigurationSurfacesCoverTheDeclarations` from `guarded-path-classes`, are judged by an assessment an agent runs on request.

- [ ] Write the assessment recipe as a skill: for each requirement in `agent-configuration-floor` and for `ConfigurationSurfacesCoverTheDeclarations`, state for each scenario whether the configuration satisfies it and which value shows it, and write a dated record to `.specs/assessments/<date>.md`.
  The record names the agent versions it was run against, because the keys it reads are the vendor's.
- [ ] Have the recipe discover its own scope from `modules/home/ai/`: judge which directories there configure an agent that runs tools, then find each one's configuration surfaces wherever they live, `users/*/home-manager/` included.
  `agentsview`, `mcp`, `ds4`, and `shared` sit there and are not harnesses, so the step is a judgment rather than a glob.
- [ ] Have the record enumerate every file the run read, so two records side by side show a surface appearing or disappearing with nobody maintaining a list.
- [ ] Have the assessment recipe compare each harness's current tool set, read from the harness rather than from this repository, against the mapping in `tool-vocabulary.toml` — evidence for `HarnessGainsATool`.
  A test cannot know a vendor's tool set, so this is an assessment item rather than `tests/test_tool_vocabulary.py`.
- [ ] Have the recipe judge the block floor against `SECRET_FLOOR_REPRESENTATIVES` plus the manifest's `[block]` class, by concrete path rather than by pattern text, as the requirement states.
- [ ] Have the recipe compare the three agents' unprompted host sets per user, under the `settingsSource` owner rule for the editor, and report the differences — evidence for `NetworkReachIsUniformPerUser`.
- [ ] Have the recipe read each Codex reviewer policy for the `USER_APPROVAL_REQUIRED` routing and the wholesale-bypass refusal, and the editor's approval settings for the values `TheEditorPromptIsCopilotsEscalationSurface` names — evidence for `GuardrailEditsRouteToTheUser`.
- [ ] Retire `tests/test_secret_floor_declarations.py`, `tests/test_guardrail_declarations.py`, `tests/test_network_declarations.py`, and `tests/test_reviewer_policy.py`.
  They are the only Python readers of `CLAUDE_SETTINGS`, `CODEX_CONFIGS`, and `SECRET_FLOOR_REPRESENTATIVES`, so drop the two globs from `tests/conformance.py` and move the representative paths to where the recipe reads values from.
- [ ] Run the assessment once against the current configurations and commit the record as this change's evidence for the four requirements; a finding becomes a task here, not a waiver.
- [ ] Update `modules/home/ai/shared/AGENTS.md`: the conformance tests no longer check the other surfaces against the manifest; the assessment does, and the Layout and Rules sections say so.

## Close the guarded set over ancestors

A declaration names a directory and protects what is inside it.
It does not protect the path to it, so an operation on an ancestor destroys the declared tree without any token equalling or containing the declaration.
Verified against every hook in this directory; none of the six refuses any of these:

| command                                | verdict                    |
| -------------------------------------- | -------------------------- |
| `rm -rf modules/home/ai/pi/security`   | gated                      |
| `rm -rf modules/home/ai/pi`            | **allowed, names nothing** |
| `rm -rf modules/home/ai`               | **allowed, names nothing** |
| `mv modules/home/ai/pi /tmp/elsewhere` | **allowed, names nothing** |
| `cp -r /tmp/evil modules/home/ai/pi`   | **allowed, names nothing** |

`~/.claude` gates because the agent home is a guarded declaration.
No other layer closes this.
Guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, which means the sandbox permits the write by design.

- [x] Add `GuardedLocations.encloses`, asking whether a path is a proper ancestor of a declaration.
  Compared component by component rather than by string prefix, so `modules/home/ai-backup` is not read as an ancestor of `modules/home/ai/`.
- [x] Gate a segment that removes, renames, or replaces such an ancestor, with `DESTROYS_EVERY_OPERAND` and `DESTROYS_LAST_OPERAND` naming which operands each program takes away.
  Reads and additions beneath an ancestor stay unprompted, which is the decision recorded below.
- [x] Add `TestDestructiveOperationsOnAnAncestor`: eleven destructive spellings gate on every agent, and eight ordinary operations beneath the same ancestors proceed.
- [x] Record the residual: an ancestor carries no declaration fragment, so it is found only by resolving it.
  A relative spelling resolves against the working directory the payload supplies, and where the payload supplies none the word is unresolvable and gates, per `path-matching` `TextMatchingIsForTextThatMayHoldNoPath`.
  Recorded in the `hook-tampering-blocking` delta, under the ancestor requirement.
- [ ] Cover mode, owner, and extended-attribute changes, or record them as out of scope.
  The chosen reading is remove, rename, or replace; `chmod -R` on an ancestor is none of those and reaches the same tree.
- [ ] Add the property Sol ranks sixth, `protected namespace closure`, over a generated tree: an operation's exact namespace effect is compared with each declaration's closure.
  This is what found the gap, and an example table would not have.

**The decision, recorded:** gate only an operation that takes the ancestor away.
Gating every command naming a prefix of a declaration reaches `modules/`, `~`, and the repository root, which would prompt on ordinary work.
Reading, searching, and creating files beneath an ancestor are ordinary and stay unprompted.

## Give the classifier a test method that finds these

Every hole closed above was found by a person or an agent reading the classifier.
`guarded-path-classes` gave the lexer and the matcher generated cases: a differential property against bash, metamorphic and totality properties, and stateful link-retargeting tests.
The hook's own verdict has fewer.
`test_classifier_properties.py` holds that a guarded operand never makes a verdict more permissive and that a trailing separator does not change it, and the items below are stated over the verdict.

- [x] Replace the blanket `except Exception: sys.exit(0)` with `internal_error`, which chooses its direction by the tool named in the payload.
  The hook contradicted `ErrorHandlingByDamagePotential`, which already required a sensitive tool not to proceed on a hook crash; its comment claimed a mixed tool set, which is true of the registration and not of the four tools it judges.
  `Ask` rather than the `Block` that requirement named, because this hook runs on every call to a sensitive tool and most of them reach nothing it guards, so a recurring fault would refuse every mutation with no route left for the user.
  Recorded as a MODIFIED requirement on `hook-interface`, which now states the `Ask` allowance and its condition.
- [x] Record the agent and the tool in `_CALL` as the payload is read, and have `internal_error` read them rather than recompute them.
  Naming the agent is itself a step that can fail, and a failure path that repeats the failing step reaches no decision at all.
  The tool is recorded before the agent, so a failure in naming the agent is still judged by the tool it would have applied to.
- [x] Add `TestFailClosedOnInternalError`: six injection sites — path resolution, the containment test, pathname expansion, filesystem metadata, executable lookup, and naming the agent — each asserted to ask under Claude and refuse under Codex.
  Also a read that proceeds with the failure reported, and an unparsable payload that warns.
- [ ] Add the spelling property: every spelling of one guarded path reaches one verdict.
  Needs an identity precondition first — a trailing separator on a regular file is an error rather than the same path, and a `..` component across a symlink selects another object — so compare spellings only after the kernel confirms they denote one object.
- [ ] Add the degradation property: for any payload, the decision on an agent that cannot show a prompt is never more permissive than the decision on one that can.
- [ ] Consider the generated-effect model Sol ranks first: build the command as structured data with known effects, render it to text, and require that an allow implies the model reports no effect on a guarded path.
  It does not recover meaning from the rendered text, which is the production failure mode the current oracle shares.

## Organization

- [ ] consider whether/how to expand property testing
- [ ] simplify and refactor audit
- [ ] consider whether to define as uv python project with pyproject.toml
- standardize kebab vs snake case hook script names

## Merge and activate

- [ ] Merge to `main`, then run `just nix switch home` once, before any session relies on the vocabulary file or any Pi session relies on the adapter.

## Completed

These groups are done and stay here as the record of what this change already did.
Each names the test that carries its evidence.

### Close the record on the three retired requirements

- [x] Confirm against `git log` that `c7f3937` retired `RedirectGrepToRipgrep` and `RedirectFindToRipgrep`, and that `fba2187` replaced `RequireSignedCommits` with `RequireAgentCommitAlias`, and that no later change restored any of them.
  Both commits resolve to the subjects the removal records name.
- [x] Verify the three names appear in no baseline spec, so the removal records describe the state that exists rather than asking sync to change it.
  All three are absent from `.specs/specs/`, so each `REMOVED` block is the no-op at sync that `RemovalRecordsAreANoOpAtSync` describes.
- [x] Record the rule against editing a baseline directly in this module's `AGENTS.md`, per `RecurrenceIsAddressedByInstruction`.
  The Specs section carries it, with the two commits as the example.

### Fix and record the read classifier

- [x] Admit `echo` and `printf` to `READ_ONLY_UTILITIES` in `block-hook-tampering.py`.
  Both reach standard output only, and redirection is already refused as opaque text, so a banner between two reads no longer gates the reads around it.
- [x] Add read cases for a `printf` banner and an `echo` banner between two reads, and gate cases for `echo` and `printf` redirection, a `tee` pipeline, and a command substitution.
- [x] Admit `rg` to `READ_ONLY_UTILITIES`, refuse `--pre`, `--hostname-bin`, `--search-zip`, and a short cluster holding `z` through `WRITE_OPTIONS`, and require `--no-config` in the first argument position through a new per-utility mapping beside it.
  The admitted-utility set needs no Pi port: the migration has Pi read the same classifier rather than carry one.
- [x] Add read cases for `rg --no-config` with each of `-n`, `--files`, `-l`, and `--pre-glob` over a guarded location — evidence for `ExternalConfigurationIsDisabledByTheCommand`.
- [x] Add a gate case for `rg -n` with no `--no-config` — evidence for `TheDisablingOptionIsAbsent`.
- [x] Add gate cases for `rg -e --no-config` and `rg --files --no-config`, each supplying the required option somewhere other than first — evidence for `TheDisablingOptionIsNotFirst`.
- [x] Add gate cases for `rg --no-config` with each of `--pre`, `--pre=<program>`, `-z`, `-nz`, `--search-zip`, and `--hostname-bin` — evidence for `ARefusedOptionAccompaniesTheDisablingOption`.
- [x] State the required option in `_accepted_forms()`, built from the mapping rather than written for ripgrep, so the refusal names the accepted spelling.
- [x] Judge `apply_patch` by the files its headers declare, falling back to the command text only where no header parses — evidence for `APatchIsJudgedByTheFilesItNames`.
- [x] Drop the now-unreachable `targets` parameter and `exempt_pool` branch from `command_protected_class`, leaving each target judged on its own by `protected_class`.
- [x] Add `TestPatchIsJudgedByItsTargets`: content naming a guarded path proceeds on every agent, each of the four header forms is read as a target, a mixed patch gates, a block target refuses everywhere, instruction markdown asks, and a body with no header is judged by its text.
- [x] Update the Claude, Codex, and Copilot tamper suites, each of which asserted that a plain `cat` of a repository hook gates; split each into a recognized read that proceeds and a write that still gates.
- [x] Judge only the segments naming a guarded location in `command_protected_class`, using `_read_segment` and `_script_exec_segment`, so a segment reaching nothing guarded no longer gates the command around it.
- [x] Match a declaration fragment at path boundaries in `guarded_paths.py`, closing both the bare directory name that matched nothing and the longer name that matched wrongly.
  This precedes the segment change: without it a relative path after a `cd` would have reached a guarded location unjudged.
- [x] Anchor the program-name rules in `bash-command-validator.sh` to command position and match them against the command with quoted spans emptied, so a program named in a search pattern, a filename, or prose no longer refuses the command.
  The git rules keep the command as written: `sh -c "git commit"` is a real invocation, and missing it leaves an unsigned commit.

### Declare the rendered MCP secret and excuse the program named for it

- [x] Add `~/.config/mcp-secrets.env` to `[block]` — evidence for `SecretMaterialIsDeclaredRatherThanRecognized`.
- [x] Cover it on every surface `test_secret_floor_declarations.py` requires of the block class: a `Read` and an `Edit` deny in each of the four Claude settings files, and a `"deny"` entry in each of the three Codex configurations.
- [x] Declare `<repo>/scripts/mcp-secrets.sh` in `[[exceptions]]` under the `sensitive-path-name-heuristic` surface, with its reason.
- [x] Build `NAME_HEURISTIC_EXCEPTION_RE` in `block-sensitive-paths.py` from that table and apply it per spelling in `is_named_for_secrets` — evidence for `TheNameHeuristicIsExcusedOnlyByDeclaration`.
  The table was read by tests and by no implementation, so an entry alone changed nothing.
- [x] Add shared verdict cases: the rendered file is refused, the same file under a name carrying no heuristic term is not, the declared script is readable, and an undeclared neighbor is refused.

### Keep the admitted set to commands that only read

- [x] Drop `uniq` and `xxd` from `READ_ONLY_UTILITIES`, and drop the now-unused `xxd` entry from `WRITE_OPTIONS`.
  Each writes a file named as an operand, and an option refusal cannot reach an operand.
- [x] Add `TestAnAdmittedUtilityWritesNoOperand`: run every admitted utility against a sentinel file as a second operand and assert the sentinel is unchanged — evidence for `UtilityWritesAFileNamedAsAnOperand`.
  The test reads the set from the hook, so a later admission is checked without editing the test.
- [x] Update the class verdict table: an admitted utility's write option still asks, an admitted read still proceeds, and a utility that writes an operand asks.
- [x] Replace the `uniq -c` stage in the pipeline read case.
  A segment running a command outside the admitted set withdraws the read carve-out from the whole pipeline, so removing a utility also removes the pipelines that pass through it.

### Judge code installed to run later

- [x] Return a `trap` body from `_program_text`, as an `eval` body already is.
  `_segment_class` then judges the paths the body names, and `_builder_segment` withdraws the read carve-out from the rest of the command.
- [x] Name `trap` in the `_stopping_syntax` reason, so the refusal says what stopped recognition.
- [x] Add gate cases for a `DEBUG`, an `ERR`, and an `EXIT` trap beside a recognized read of a guarded location — evidence for `CodeIsInstalledBesideARecognizedRead`.
- [x] Add gate cases for a trap body that copies over a guarded file and one that removes a guarded directory — evidence for `AnInstalledBodyNamesAGuardedLocation`.
- [x] Add a refusal case for a trap body naming a block-class location — evidence for `AnInstalledBodyNamesACredential`.
- [x] Add a case for a trap installed after the read, so position does not decide the outcome.
- [x] Confirm the ordinary reads still proceed: `cat`, `rg`, `grep`, `find`, a banner between two reads, and a piped read — evidence for `NoCodeIsInstalled`.
- [x] Unwrap `builtin` in `_invocation`, so `builtin trap` reaches the same outcome as `trap` — evidence for `TheInstallingCommandCarriesADispatchPrefix`.
- [x] Install no body for `trap -p` and `trap -`, so listing and resetting handlers keep the read carve-out — evidence for `TheInstallingCommandOnlyListsOrResetsHandlers`.
- [x] Treat a function definition as installing code, in both the `name()` and `function name` spellings — evidence for `ACommandNameIsBoundToABody`.
  A definition rebinds an admitted name, so `cat() { cp /tmp/x "$1"; }; cat <guarded>` wrote the file, and `rg() { command rg "${@:2}"; }` dropped the required `--no-config` before ripgrep saw it.
- [x] Name the function definition in `_stopping_syntax`, so the refusal says what stopped recognition.

### Split the refusal instruction in two

- [x] Modify `BlockAIGuidance` to define two instruction forms and the rule that selects between them, and `ExplanationContract` to stop naming the prohibition as the only section-2 content.
  The baseline pinned one exact text for every exit 2, so adding the second form without these blocks would leave two baseline requirements contradicting each other at sync.

- [x] Let a `Block` choose its closing instruction in `respond()`, through an `Instruction` enum.
  Default to the stop instruction, so every call that does not choose keeps it.

- [x] Write the retry instruction: say no rule refused the command, tell the agent to run it again in one of the forms named above, and keep the report-to-the-user fallback for when no accepted form does the job.

- [x] Pass the retry instruction at the unrecognized-command refusal in `block-hook-tampering.py`.
  Leave the credential refusal, the degraded guardrail refusal, and the ancestor refusal on the stop instruction.
  The prompted path reaches the user and carries no instruction, so the refusal is the only site to change.

- [x] Leave `block-dangerous-bash.sh` on the stop instruction.
  It refuses a named class of command, so every call it judges is one it was registered to refuse, and no other spelling is allowed.

- [x] Add a test that a refusal naming accepted commands says to use one and omits the stop instruction — evidence for `RetryMessageFormat` and `AIRunsAnAcceptedCommand`.

- [x] Add tests that a refusal naming none carries the stop instruction, over a file-tool write and over an ancestor removal — evidence for `BlockMessageFormat` and `AIDoesNotSeekWorkaround`.

- [x] Add a test that a command naming a block-class location carries the stop instruction, whether or not the hook could read the command — evidence for `ACredentialBlockUsesTheStopForm`.

- [x] Add a test that a decision reaching the user carries neither instruction — evidence for `ExplanationContract` `AskExplanation`.

- [x] Update the block contract in each agent's `tests/conftest.py` to accept the retry form.
  `_AI_BLOCK_CHECKS` required the phrase `do not attempt` in every exit 2, which the retry instruction omits by design.
  Codex and Copilot do not honor a prompt for Bash, so the unrecognized-command refusal is the form those agents receive most.
  The helper now asserts the common sections and then exactly one closing instruction, which states the two-form rule rather than requiring one of them.
  Claude carries the same helper, so a Claude refusal that reaches the retry form is held to it too.
