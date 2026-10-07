# Tasks: security-posture-alignment

## Working tree

The deployed hooks are symlinks into `~/.nixconfig`, and `shared/hooks.nix` enumerates `hooks/` at activation, so a file added there has no deployed symlink until the next `just nix switch home`.
A hook invoked through its deployed symlink resolves `sys.path[0]` to the repository directory it points into, so a module a hook imports is live as soon as it exists there; a file run by path, such as `tool-vocabulary.toml`, is not until activation.
`pi/default.nix` deploys the hooks extension's modules by name, from `hooksModules`, so a module added or removed there has no effect until activation either.
An edit in the main checkout is live in every open agent session the moment it is saved.

- [x] Do this change in a git worktree on its own branch, so the main checkout stays what the live agents run.
  `guarded-path-classes` is merged and activated; its deltas sync together with this change's.

Groups run in dependency order, so finished groups come first and open work follows.
The classifier groups come first, because the Pi migration gives Pi the classifier they fixed.
The package work follows: the tool vocabulary, the coverage test, and the Pi migration, which is judged against the verdict tables before any TypeScript is deleted.
The configuration work comes next, and the assessment last among it, because it judges every surface the earlier groups declare.
The open groups follow: the record format for the policy tables precedes the verify findings, because `HarnessGainsATool` reads the refused list it adds.
The live checks need an activation, so they precede the merge.

## Close the record on the three retired requirements

- [x] Confirm against `git log` that `c7f3937` retired `RedirectGrepToRipgrep` and `RedirectFindToRipgrep`, and that `fba2187` replaced `RequireSignedCommits` with `RequireAgentCommitAlias`, and that no later change restored any of them.
  Both commits resolve to the subjects the removal records name.
- [x] Verify the three names appear in no baseline spec, so the removal records describe the state that exists rather than asking sync to change it.
  All three are absent from `.specs/specs/`, so each `REMOVED` block is the no-op at sync that `RemovalRecordsAreANoOpAtSync` describes.
- [x] Record the rule against editing a baseline directly in this module's `AGENTS.md`, per `RecurrenceIsAddressedByInstruction`.
  The Specs section carries it, with the two commits as the example.

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

## Fix and record the read classifier

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

## Keep the admitted set to commands that only read

- [x] Drop `uniq` and `xxd` from `READ_ONLY_UTILITIES`, and drop the now-unused `xxd` entry from `WRITE_OPTIONS`.
  Each writes a file named as an operand, and an option refusal cannot reach an operand.
- [x] Add `TestAnAdmittedUtilityWritesNoOperand`: run every admitted utility against a sentinel file as a second operand and assert the sentinel is unchanged — evidence for `UtilityWritesAFileNamedAsAnOperand`.
  The test reads the set from the hook, so a later admission is checked without editing the test.
- [x] Update the class verdict table: an admitted utility's write option still asks, an admitted read still proceeds, and a utility that writes an operand asks.
- [x] Replace the `uniq -c` stage in the pipeline read case.
  A segment running a command outside the admitted set withdraws the read carve-out from the whole pipeline, so removing a utility also removes the pipelines that pass through it.

## Judge code installed to run later

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

## Declare the rendered MCP secret and excuse the program named for it

- [x] Add `~/.config/mcp-secrets.env` to `[block]` — evidence for `SecretMaterialIsDeclaredRatherThanRecognized`.
- [x] Cover it on every surface `test_secret_floor_declarations.py` requires of the block class: a `Read` and an `Edit` deny in each of the four Claude settings files, and a `"deny"` entry in each of the three Codex configurations.
- [x] Declare `<repo>/scripts/mcp-secrets.sh` in `[[exceptions]]` under the `sensitive-path-name-heuristic` surface, with its reason.
- [x] Build `NAME_HEURISTIC_EXCEPTION_RE` in `block-sensitive-paths.py` from that table and apply it per spelling in `is_named_for_secrets` — evidence for `TheNameHeuristicIsExcusedOnlyByDeclaration`.
  The table was read by tests and by no implementation, so an entry alone changed nothing.
- [x] Add shared verdict cases: the rendered file is refused, the same file under a name carrying no heuristic term is not, the declared script is readable, and an undeclared neighbor is refused.

## Split the refusal instruction in two

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
- [x] Refuse a removal, rename, or replacement of a relative path when the payload supplies no working directory, with the stop instruction on every agent, and add `TestRelativeOperandWithoutAWorkingDirectory` — evidence for `ARelativeOperandWithNoWorkingDirectory` and `AnAbsoluteOperandWithNoWorkingDirectory`.
  The hook let such an operand through, because `encloses` cannot resolve it.
  Judging it by shape was rejected: the `*` in `<repo>/users/*/home-manager/` lets almost any single word match, so `rm -rf build` would refuse.
- [x] Gate a mode, owner, flag, or ACL change on an ancestor: `chmod` (with `+a`), `chown`, `chgrp`, `chflags`, `xattr`, and `setfacl`, naming the operands after the mode or owner.
  Probed 2026-09-30: `chmod 000 modules/home/ai` passed every hook on Claude and Codex, and a hook under a mode-000 directory then stopped running.
- [x] Gate the other programs found to destroy or overwrite a declared tree through an ancestor: `find … -delete`, `trash`, `tar -x … -C`, `unzip -d`, `ditto`, `git checkout <rev> -- <path>`, `git restore --source=… <path>`, and `git stash push -- <path>`.
  Probed 2026-09-30: each passed every hook on Claude and Codex.
- [x] Add each command above to `TestDestructiveOperationsOnAnAncestor` as a gate case on every agent.
- [x] Add a tree property test: generate a small tree and a declaration set, run each generated command on a copy in a temporary directory, and fail when a hook allows a command that changed a declared file.
  `TestDestructiveOperationsOnAnAncestor` builds its cases from the same program lists the hook reads, so it cannot find a missing program; the tree is an independent oracle.
- [x] Resolve a relative operand after a `cd` against the directory it entered, and refuse one after a `cd` the hook cannot resolve.
  The tree property test found `cd modules/home/ai/shared && rm -rf hooks` allowed: the classifier resolved the operand against the payload's directory.
- [x] Record in `path-matching` `StatedLimits`, or the `hook-tampering-blocking` ancestor requirement, that a program missing from the gate's lists passes on an ancestor.
- [x] Record in `design.md` Risks that a directly executed shell hook under an unreadable directory exits 126, which Claude treats as a non-blocking error.

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
- [x] Investigate whether every spelling of one guarded path reaches one verdict.
  Probed 2026-09-30: about 60 spellings, including letter case and the Unicode letters APFS folds (`ſ` to `s`, the Kelvin sign to `k`), each reached one verdict on Claude and Codex.
  No property test is added.
- [x] Add `~/.claude/ſettings.json` and a Kelvin-sign spelling to `TestLetterCase`, so the fold the probe confirmed is held by a test.
- [x] Investigate whether an agent that cannot show a prompt is ever allowed more than one that can.
  Probed 2026-09-30 over 285 payloads on Codex, Copilot, and an unknown agent: none was more permissive than Claude.
  It holds by construction, because every ask passes through `respond` and `supports_ask`.
  `.specs/WHEN-CODEX-CAN-ASK.md` lists it as the regression check to add when an agent gains a prompt.
- [x] Assess the generated-effect model.
  Not built: the tree property test above finds the same missing programs at a fraction of the cost, and the model needs a per-program effect catalog, which is a second classifier.

## Declare the tool vocabulary and close the adapter fall-through

- [x] Declare the gated tool vocabulary in `hooks/tool-vocabulary.toml`, with each harness's spelling of each tool mapped onto it and Claude's declared as identity.
  A file of its own, because `OnlyPolicyTablesExist` holds `guarded-paths.toml` to the five policy tables and `test_guarded_paths_manifest.py` enumerates them.
- [x] Read the vocabulary in `guarded_paths.py` and replace `MUTATING_TOOLS` in `block-hook-tampering.py`, `SENSITIVE_TOOLS` in `block-secrets.py`, the tool tuple in the `main` of `block-sensitive-paths.py`, the `Bash` test in `block-destructive-ops.py`, and `_COPILOT_ASK_TOOLS` in `hook_response.py` — evidence for `VocabularyReadFromTheDeclaration`.
  No second reader is written for Pi: the dispatcher below maps Pi's tool names onto the declaration, and `manifest.ts` and the literals in `index.ts` are deleted with the port.
- [x] Add a case asserting a spelling added to the declaration is honored by every implementation with no further edit — evidence for `SpellingDeclaredOnceReachesEveryConsumer`.
- [x] Add a case asserting an implementation holding its own tool vocabulary fails the check, so a passing suite is evidence the check can fail — evidence for `ImplementationCarriesItsOwnCopy`.
- [x] Delete the unused `copilot-vscode-hook-adapter.sh` and update `copilot/AGENTS.md` to name the Python adapter alone, so Copilot has one supported route onto the shared hooks.
- [x] Replace the `or tool_name` fall-through in `normalize_payload` in `copilot-vscode-hook-adapter.py` with a refusal, so an unmapped VS Code tool is denied rather than forwarded — evidence for `UnmappedToolIsRefused`.
- [x] Add a case asserting an unmapped tool name is refused and does not reach the shared hooks, and a case asserting a mapped name is judged under the declared vocabulary — evidence for `UnmappedToolIsRefused` and `MappedToolReachesTheGate`.
- [x] Declare a `[passthrough]` table in `tool-vocabulary.toml`, per harness, whose entries are names or `fnmatch` patterns, and have the loader refuse a spelling that is both mapped and passthrough — evidence for `SpellingMappedAndPassthrough`.
  Without it the refusal above refuses every read, search, and MCP call, because the mappings hold gated tools alone.
- [x] Have the Copilot adapter forward a declared passthrough tool unchanged, and add a case for a pattern-matched MCP tool — evidence for `DeclaredPassthroughToolProceeds`.
- [x] Declare Pi's passthrough tools from the installed build: the read-only built-ins `grep`, `find`, and `ls`, and the extension tools `mcp`, `subagent`, `intercom`, and `contact_supervisor`.
- [x] Classify every tool name in the installed Copilot build: map each tool that writes or runs code onto a gated name where the hooks can judge its input, and declare the rest passthrough with `mcp_*` for MCP tools.
  The code runners are passthrough with a comment saying so; `edit_files` is refused.
  Each table names the build it was read from.
- [x] Read `dirPath` and each `replacements[].filePath` in the Copilot adapter, so `create_directory` and `multi_replace_string_in_file` reach the hooks with their paths.
- [x] Remove the `tool_name` test from `block-dangerous-bash.sh`, `bash-command-validator.sh`, and `git-baseline.sh update`, declare a `shell` group, and have the Copilot adapter pass the three shell hooks only `shell` calls and `git-baseline.sh check` only `mutating` calls, since VS Code ignores `matcher` — evidence for `ReadDoesNotQualify` on Copilot.

## Establish parity in the package

- [x] Add `tests/test_capability_coverage.py` holding one table, capability to kind and package artifact, per `CapabilityCoverageIsCheckedFromTheSpecsRoot`.
  Enforcement rows name a hook: `bash-command-validator`, `dangerous-bash-blocking`, `destructive-ops-blocking`, `git-baseline-drift`, `hook-tampering-blocking`, `secret-access-blocking`, `sensitive-path-blocking`, `session-tool-checks`, and `end-of-turn-precommit`.
  Mechanism rows name a module: `hook-interface` is `hook_response.py`, `path-matching` and `guarded-path-declarations` are `guarded_paths.py`, `shell-lexing` is `shell_words.py`.
  The posture row, `guarded-surface`, names `guarded-paths.toml`.
  The configuration row, `agent-configuration-floor`, names no artifact.
  The conformance row, `cross-agent-capability-parity`, names this test, under `tests/`.
- [x] Assert every capability directory under `.specs/specs/` has a row, and every artifact a row names exists — evidence for `CapabilityHasAPackageArtifact` and `CapabilityWithNoRecordedKind`.
- [x] Assert every hyphenated file in `hooks/` that is not a manifest or a pattern table is named by some row — evidence for `HookClaimedByNoCapability`.
  A row names every artifact its capability runs, so `session-tool-checks` names both `session-tool-checks.sh` and `session-policy-checks.py`, which the shell script runs by path.
  `reload-skills-catalog.py` and `session-instructions.sh` are outside every capability: one rebuilds Claude's skills catalog, the other injects prompt text at session start, and neither enforces anything.
  List both in the test as tooling, hooks the check accepts by name, so the reverse check still fails on any other unclaimed hook.
- [x] Add two cases that build a temporary specs root and hooks directory: one with a capability the table lacks, one with a hook no row names, each asserted to fail, so a passing suite is evidence the check can fail.

## Migrate Pi onto the shared hooks

Pi runs the shared hooks through a hook runner, per `PiRunsTheSharedHooksThroughAHookRunner`.
The runner is specified in `modules/home/ai/pi/.specs/specs/` (`hook-registration`, `hook-execution`, `hook-events`), built in `modules/home/ai/pi/hooks/`, and deployed as `~/.pi/agent/extensions/hooks/`, where it reads `~/.pi/agent/hooks.json`.
The tasks here are what the shared side owes the runner and the evidence this change needs from it, ordered so the runner is judged against the verdict tables before the TypeScript reimplementation is deleted.

- [x] Add a dispatcher that runs the four Python hooks in one process over one payload, returning refuse, ask, or allow.
  It loads each hook by file path, captures stdout and stderr, and catches `SystemExit`, so no hook changes.
- [x] Have the dispatcher decode ask from allow by reading `permissionDecision` on stdout rather than the exit status, continue through the remaining hooks after an ask, and return the most restrictive decision reached — evidence for `AskIsNotReadAsAllow`, `EveryHookRunsAfterAnAsk`, and `BlockOutranksAsk`.
- [x] Add `PI` to the agent markers in `hook_response.py` and make `supports_ask` return true for it on every tool — evidence for `AdapterNamesARecognizedAgent`.
- [x] Add a case asserting an adapter that names no agent, or an unrecognized one, refuses a call that needed a prompt — evidence for `AdapterNamesNothingOrSomethingUnknown`.
- [x] Have `hook_response.respond()` append the instruction section to an `Ask` reason when the agent is Pi, and add a case — evidence for `AskAnAdapterMayRefuse`.
- [x] Have the dispatcher map Pi's tool names and input fields onto the declared vocabulary through `tool-vocabulary.toml`, forward a declared passthrough tool unjudged, and refuse a name that is neither — evidence for `MappedToolReachesTheGate`, `DeclaredPassthroughToolProceeds`, and `UnmappedToolIsRefused` on Pi.
  Pi's `path` becomes `file_path`, resolved against the payload's `cwd`.
- [x] Have the dispatcher fail closed: count a hook that raises an unhandled error as a refusal, and end any error of its own in exit 2 with the stop form, never exit 1; add a case for each — evidence for `HookFailsInsideASharedProcess`.
- [x] Have the dispatcher encode its combined verdict in the hook contract, exit 2 with the reasons on stderr or the ask JSON on stdout, so the runner decodes it like any other hook.
- [x] Register the shared hooks for Pi in `pi/security/hooks.json`, deployed from `pi/default.nix` as `~/.pi/agent/hooks.json`, the file the runner reads, on the events `copilot/hooks/security-policy.json` uses, with each command setting `AI_HOOK_AGENT=pi` so the hooks resolve Pi.
  The four Python hooks are one `PreToolUse` entry, `hook-dispatch.py`; the shell hooks are their own entries under a `bash` matcher, and `git-baseline.sh check` under `bash|write|edit`.
  The shared hooks deploy to `~/.pi/agent/hooks/` beside the dispatcher, as they do for Claude and Codex.
- [x] Add the runner's files to the enforcement floor and the guarded class: `~/.pi/agent/hooks.json`, `~/.pi/agent/hooks/`, `~/.pi/agent/extensions/hooks/`, and `<repo>/modules/home/ai/pi/hooks/`, with cases in `test_enforcement_floor.py` and `guarded-path-cases.json`.
  The TypeScript extension's entries leave the floor with its deletion.
- [x] Port the dispatcher's cases to pytest in `pi/tests/`, run them from `scripts/apps-test.sh pi` beside the runner's suite, update `scripts/tests/test-apps-test.sh`, and delete `pi/security/hook-dispatch.test.mjs`.
- [x] Decide whether a missing required tool at session start ends a Pi session, as `session-tool-checks.sh` does on the other agents, or only notifies, as the ported check does; the registration then runs `session-tool-checks.sh` unchanged or records Pi as a declared exception.
  Decided: the registration runs `session-tool-checks.sh` unchanged, and the runner shows a `SessionStart` block's reason to the user as an error while the session continues (`hook-events` `SessionHooksBracketTheSession`, scenario `StartBlocked`).
  A missing `uv`, `jq`, or `perl` leaves the hooks unable to run, and each tool call they judge is then refused, so the session cannot act unguarded.
- [x] Add runner cases asserting a dangerous command is refused, a validator rule fires, and a baseline drift is reported, so the two enforcement capabilities Pi loses when its TypeScript copies go are shown to arrive through the runner.
  `pi/tests/registration.test.mjs` runs `pi/security/hooks.json` through the runner over the layout `pi/default.nix` deploys.
- [x] Widen the shell alternative in `block-dangerous-bash.sh`'s pipe-to-shell and decoded-content rules from `ba?sh` to `b?a?sh\b`, so a download or decoded content piped to plain `sh` is refused as `dangerous-bash-blocking` `BlockPipeToShell` and `BlockObfuscatedExec` state; add `| sh` cases and a `| shasum` case that proceeds.
- [x] Judge the runner against `guarded-path-cases.json` and `sensitive-path-cases.json`, asserting it reaches the same outcomes as a direct invocation — evidence for `AdapterDiverges`.
  `pi/tests/registration.test.mjs` judges each guarded case as a write, each sensitive case as a read, and each of the sensitive table's `bash_cases` as a command; the direct outcome is the most restrictive of the hooks Claude Code registers for the tool, each run alone on Claude Code's payload.
- [x] Add cases covering a credential write staying a refusal on an ask-capable agent, a recognized read under a skills directory proceeding, and a guarded write reaching an ask.
- [x] Record which properties the Pi surface is held to once it reads the shared classifier, so the generated cases arbitrate both surfaces the way the verdict tables do.
  Recorded in `PiRunsTheSharedHooksThroughAHookRunner`; the dispatcher's mapping has its own generated property in `pi/tests/test_hook_dispatch.py`.
- [x] Verify all deferred class outcomes, per-hop precedence, and lexer cases through the runner; remove the temporary Pi exception and its divergence records only when they pass.
  `pi/tests/registration.test.mjs` covers the write-through and exec-through outcomes, links that cross classes, and the lexer's redirection and brace forms, each against a direct invocation.
  The `pi_blocked` record is removed from `guarded-path-cases.json`, and the override in `guarded-path-classes` is closed.
- [x] Judge the runner's end-of-turn path against the `end-of-turn-precommit` scenarios, so the contract has second-surface evidence without a second implementation.
  Twelve scenarios hold through the runner in `pi/tests/registration.test.mjs`.
  `UnresolvableWorkingDirectory` does not arise: the runner starts each hook in the session directory, which is also the payload's `cwd`.
- [x] Confirm the runner passes the removal test in `EveryAgentImplementsEveryCapability`: with the shared hooks and their registration removed, it refuses no tool call for what the call does — evidence for `HarnessExtensionWithTheHooksRemoved`.
- [x] Delete the TypeScript extension from `pi/security/`, its modules, `security-extension-package.json`, and `index.test.mjs`, and its entries in `pi/default.nix`, once the runner and Pi's registration replace it; `hooks.json` and `hook-dispatch.py` stay.
  That removes `AGENT_INSTRUCTIONS`, a paraphrase of `AI_INSTRUCTIONS`; the ported `session_start` tool list, whose divergence from `session-tool-checks.sh` the Pi change decides; `precommit.ts`, a line-for-line port of `stop-precommit.sh`; and both dependencies, `shell-quote` and `smol-toml`.
- [x] Delete `tests/test_pi_guarded_declarations.py`, which reads the port's source for manifest literals and was paused by `guarded-path-classes`; the runner's verdict-table case above replaces it.
  Its instruction-markdown check moved to `test_guarded_path_cases.py`; the rest read the port's source.
- [x] Restore a Pi check to `outputs.checks` in `flake.nix` and `_test-pi` to `_test-all` in `justfiles/apps.just`, both unhooked by `guarded-path-classes` until the migration landed.
  `scripts/apps-test.sh pi` already runs the runner's suite; the check restored here runs it together with the cases this group adds.
  The check is `pi-hook-tests`; it runs pytest and node directly, since `uv run --with` cannot fetch packages in the build sandbox.
- [x] Update `modules/home/ai/shared/AGENTS.md`: Pi reaches the hooks through a hook runner like the other three agents' native ones, its suite judges the runner rather than a second implementation, and a harness extension is held to the removal test.
- [x] Run `pytest -q` over the shared, claude, codex, and copilot suites, the Pi suite, and `nix build .#checks.aarch64-darwin.shared-hook-tests`.
  On 2026-09-26: shared 1,550 passed and 1 skipped; claude 570 passed and 2 expected failures; codex 49; copilot 51; pi 27 pytest and 250 node; `shared-hook-tests`, `pi-hook-tests`, and `apps-test-dispatcher-tests` build.
- [x] Exercise a live `pi` session over RPC: a refused credential write, an ask-gated guardrail edit answered both ways, a recognized read under a skills directory, and a script run under one.
  Drive it the way the runner's own live check does, `evidence/live-rpc-driver.mjs` in the archived `pi-hook-runner` change, with the deployed registration in place of its test hooks.
  `evidence/pi-live-rpc-driver.mjs`, output in `evidence/pi-live-rpc-output.txt`: Pi 0.86.1 with the local Qwen3.6-35B-A3B-4bit, on 2026-09-26.

## Judge every surface against the verdict tables

- [x] Assert `guarded-path-cases.json` and `sensitive-path-cases.json` are judged by every surface that reaches a verdict, and that a table entry no surface covers fails — evidence for `SharedTableAgrees` and `ReimplementationDiverges`.
  `tests/verdict_conformance.py` holds the rule; each table declares one hook's verdict, so each surface runs that hook alone.
  The direct hooks are judged under Claude and Codex in `tests/test_verdict_conformance.py`, Copilot's adapter in `copilot/tests/test_verdict_tables.py`, and Pi's dispatcher in `pi/tests/test_hook_dispatch.py`; stand-in surfaces show a diverging reimplementation, an adapter whose payload misses the gate, and a skipped input each fail.

- [x] Add a case pinning `CapabilityAmendedInOnePlace`: an entry added to a verdict table with only one verdict-reaching surface updated fails.
  `test_a_contract_amended_on_one_surface_only_fails`.

- [x] Confirm each scenario in `end-of-turn-precommit` maps to a case in `claude/tests/test_stop_precommit.py`, and name the mapping in the verify record.
  `PassingRunIsSilent` → `test_passing_run_stays_silent`; `ModifiedTrackedFile` → `test_modified_tracked_file_reaches_the_runner`; `UntrackedFile` → `test_untracked_file_reaches_the_runner`; `StagedFile` → `test_staged_file_reaches_the_runner`; `IgnoredFile` → `test_ignored_file_is_excluded`; `DeletedFile` → `test_deleted_file_is_excluded`; `RepositoryWithNoCommits` → `test_repo_without_head_uses_the_staged_diff`; `OutsideARepository` → `test_non_git_directory_is_a_no_op`; `NoPreCommitConfiguration` → `test_repo_without_precommit_config_is_a_no_op`; `NoChangedFiles` → `test_repo_without_changes_is_a_no_op`; `UnresolvableWorkingDirectory` → `test_unresolvable_payload_cwd_falls_back_to_the_process_directory`; `FailingRunBlocks` → `test_failure_blocks_the_stop_and_explains_itself`; `SecondPassAfterABlock` → `test_loop_guard_skips_run`.

`precommit.ts` is a line-for-line port of `stop-precommit.sh` — the same runner preference, the same `HEAD`-or-`--cached` selection, the same `--diff-filter=d`, the same `run --files`, the same failure text, and the same three explanatory comments word for word.
It is the second copy of the policy that `PiRunsTheSharedHooksThroughAHookRunner` exists to remove, so the second write-site it would need cases for is a write-site this change deletes.
Pi's hook runner runs the shared script instead.
The contract is therefore evidenced through the runner, under the migration group above, rather than by adding cases here.

## Align the editor's approval configuration

The two VS Code settings files are JSONC and already carry comments, so each declared value carries its reason beside it; `check-json` excludes them.
`modules/home/apps/vscode/settings.json` serves every user without a `users/<name>/home-manager/vscode/settings.json` of their own, per `settingsSource` in the VS Code module, so it is mithras's file and alex.graber's is their own.
Values and defaults below are from the VS Code documentation and the 1.136.1 build; where the two disagree the build governs and the disagreement is recorded in `TheEditorSandboxIsPinnedOnAndClosed`.

- [x] Declare in both files, each with a one-line comment stating what it closes: `chat.tools.global.autoApprove` false, `chat.permissions.default` `"default"`, `chat.assistedPermissions.enabled` false, and `chat.tools.terminal.enableAutoApprove` false, which is already declared and gains its comment.
  `TheEditorPromptIsCopilotsEscalationSurface` is the reason for the last: with it false, every terminal command reaches the user.
  The installed 1.139.1 build no longer reads `chat.assistedPermissions.enabled`; `chat.defaultConfiguration` with `mode` `interactive` and `approvals` `manual` is declared in its place, and `BypassModesAreRefused` names that setting's bypass values.
  Both files also gain the Pi hook paths in `chat.tools.edits.autoApprove`.
- [x] Add a comment on the `~/.copilot/hooks` entry of `chat.hookFilesLocations` stating that it is the only thing loading this repository's hooks, because the directory is not among the editor's defaults.
- [x] Read the default of `chat.useHooks` from the build; if it can switch hook execution off, declare it true with a comment, and add it to `BypassModesAreRefused` beside `chat.hookFilesLocations`.
  It defaults to true, and a user setting or an organization policy can turn it off.
- [x] Declare `chat.agent.allowedNetworkDomains` in both files as the same host set the file's owner declares for Claude and Codex, and `chat.agent.networkFilter` false, so the fetch tool and the integrated browser ask before any other host rather than refusing it, as Claude's fetch tool does.
  This precedes the sandbox pin below: under an enabled sandbox an empty list blocks every domain for terminal commands.
  `chat.tools.urls.autoApprove` keeps only hosts in the list, `pypi.org`; `docs.python.org` now asks.
  Decided 2026-09-26: with the filter on, every host outside the list is blocked with no prompt, which is stricter than Claude and leaves Copilot unable to read documentation.
- [x] Re-measure, against a live 1.136.1 session, whether the terminal tool honors a `PreToolUse` `ask`; the hooks reference says it does and `_COPILOT_ASK_TOOLS` says it does not.
  If it does, widen `supports_ask` for Copilot and record the change in `hook-interface` `ExitCodes`, which names the Copilot encoding.
  Not established on 1.139.1, 2026-09-26: a probe hook's ask on `run_in_terminal` reached VS Code, and the user saw an approval prompt carrying a model-written summary rather than the hook's reason.
  The control failed: a workspace that auto-approves `echo` still prompted for a plain `echo`, after a reload and in a trusted workspace, so the prompt cannot be attributed to the hook.
  `supports_ask` stays narrow, so a Copilot terminal ask remains a refusal, which is safe whichever way the editor treats it.
- [x] Update `copilot/AGENTS.md`: the sandbox is Copilot's OS-level layer once pinned, the editor prompt is its escalation surface, and the session-level bypasses are recorded as the limit `SessionLevelBypassIsOutsideTheFloor` names.

## Close the editor sandbox

Values read from the installed VS Code build rather than the docs, which lag it.
Confirm they still exist before applying: the keys carry a `preview` tag and `minimumVersion` of 1.116, and this repo runs 1.136.1.
The domain list in the group above lands first.

- [x] Declare `chat.agent.sandbox.enabled` as `"on"` in `modules/home/apps/vscode/settings.json` and in `users/alex.graber/home-manager/vscode/settings.json`, whose chat blocks are currently identical.
  With `allowWrite` empty, a sandboxed command writes only in the workspace, the workspace storage, and a sandbox temp directory, so `uv`, `prek`, `cargo`, and Nix would fail in Copilot's terminal.
  Decided 2026-09-27: both files list the tool caches the other agents write, `~/.cache/uv`, `~/.local/share/uv`, `~/.cache/prek`, `~/.cargo`, `~/.rustup`, `~/.cache/fontconfig`, `~/.cache/nix`, and `~/.local/state/nix`, for macOS and Linux.
  Whether the sandbox reaches the Nix daemon's socket is unknown until the live check below.
- [x] Declare `chat.agent.sandbox.allowAutoApprove`, `chat.agent.sandbox.allowUnsandboxedCommands`, and `chat.agent.sandbox.retryWithAllowNetworkRequests` as `false` in both files, and `chat.agent.sandbox.allowNetwork` as `false` so the value is stated rather than inherited, each with a comment naming what it closes.
  Read from 1.139.1: every key exists, and `allowNetwork` now defaults to `true`.
- [x] Declare `chat.agent.sandbox.fileSystem.mac` and `chat.agent.sandbox.fileSystem.linux` `denyRead` and `denyWrite` lists covering the manifest's `[block]` class by concrete path, so the editor sandbox refuses what the other floors refuse.
  Hand-authored rather than generated from `guarded-paths.toml`, for the reason `ThePiSandboxIsClosedFromTheManifest` gives: the assessment judges every surface the same way, and a generated surface beside hand-written ones puts the manifest in two relationships with its consumers.
  The block class alone: `guarded-path-declarations` `ConfigurationSurfacesCoverTheDeclarations` holds every floor to it, because no surface can express the ask-with-carve-out the guarded class carries.
  Until it lands, the sandbox restricts reach but does not know this repository's block set.

## Close the Pi sandbox

`pi/default.nix` copies the sandbox extension out of Pi's derivation and writes no configuration, so it runs on the vendor defaults.
The extension merges a global `~/.pi/agent/extensions/sandbox.json` with a project file under the working directory; the global file is the one this repository owns.
This group is independent of the migration above: it is Pi's OS layer, not its hook layer.

- [x] Declare `~/.pi/agent/extensions/sandbox.json` from `pi/default.nix`, with `filesystem.denyRead` and `filesystem.denyWrite` covering the manifest's `[block]` class by concrete path, each entry carrying the reason the other surfaces carry.
  Hand-authored rather than generated from `guarded-paths.toml`, per `ThePiSandboxIsClosedFromTheManifest`.
  Declared per user, from `users/<name>/home-manager/pi/sandbox.json`, because the host set below is the user's; `mithras` and `nrl` import Pi.
  The extension reads the file with `JSON.parse`, so the reasons are in `pi/README.md` rather than in the file.
  A key the file sets replaces that key's built-in list, so the file restates the built-in denies; `allowWrite` adds the tool caches, as the editor sandbox does.
- [x] Declare `network.allowedDomains` as the same host set the file's owner declares for Claude and Codex — evidence for `NetworkReachIsUniformPerUser` on the fourth agent.
- [x] Add `enabled`, `ignoreViolations`, and `enableWeakerNestedSandbox` to `BypassModesAreRefused` in the `agent-configuration-floor` delta, and declare the first true and the other two false in the file.
  `ignoreViolations` is a map of violation kinds, so it is declared empty.
- [x] Update `pi/README.md` and `modules/home/ai/shared/AGENTS.md`: Pi's OS layer is the sandbox extension, and this repository writes its deny lists.

## Assess the configuration floor

No test reads an agent's configuration file, per `TheHooksAreAPackageIndependentOfAnyAgentConfiguration`.
The requirements in `agent-configuration-floor`, and `ConfigurationSurfacesCoverTheDeclarations` from `guarded-path-classes`, are judged by an assessment an agent runs on request.

- [x] Write the assessment recipe as a skill: for each requirement in `agent-configuration-floor` and for `ConfigurationSurfacesCoverTheDeclarations`, state for each scenario whether the configuration satisfies it and which value shows it, and write a dated record to `.specs/assessments/<date>.md`.
  The record names the agent versions it was run against, because the keys it reads are the vendor's.
  The recipe is `modules/home/ai/shared/skills/assess-agent-configuration/SKILL.md`, linked into the repository's `.claude/skills/` and `.agents/skills/` at activation; the secret-store representatives are listed in it.
  `[[exceptions]]` accepts the `capability-coverage` surface, which no hook reads.
- [x] Have the recipe discover its own scope from `modules/home/ai/`: judge which directories there configure an agent that runs tools, then find each one's configuration surfaces wherever they live, `users/*/home-manager/` included.
  `agentsview`, `mcp`, `ds4`, and `shared` sit there and are not harnesses, so the step is a judgment rather than a glob.
- [x] Have the record enumerate every file the run read, so two records side by side show a surface appearing or disappearing with nobody maintaining a list.
- [x] Add the agent side to the assessment recipe: for each enforcement row, read what each agent registers, `hooks.json`, `security-policy.json`, the Claude settings, and the Pi extension, and report a hook an agent does not run — evidence for `CapabilityCarriedByEveryAgent` and `CapabilityMissingFromOneAgent`.
  A deliberate omission is declared in `[[exceptions]]` under a `capability-coverage` surface, with the agent and the hook as the pattern and its reason as `why`, and the recipe honors it.
- [x] Add the editor's approval values and `chat.agent.allowedNetworkDomains` to the assessment recipe, so `EditorApprovalBypassed` and the editor's side of `NetworkReachIsUniformPerUser` are judged with the other two agents.
- [x] Add the three permissive sandbox values and the declared sandbox switch to the assessment recipe — evidence for `EditorSandboxLetsTheAgentPastIt`, `ExperimentControlledSettingLeftUnset`, and `ExperimentControlledSettingDeclared`.
- [x] Add the Pi sandbox file to the assessment recipe, judged against the block class by concrete path like the other surfaces.
- [x] Have the assessment recipe compare each harness's current tool set, read from the harness rather than from this repository, against the mapping in `tool-vocabulary.toml` — evidence for `HarnessGainsATool`.
  A test cannot know a vendor's tool set, so this is an assessment item rather than `tests/test_tool_vocabulary.py`.
- [x] Have the recipe judge the block floor against `SECRET_FLOOR_REPRESENTATIVES` plus the manifest's `[block]` class, by concrete path rather than by pattern text, as the requirement states.
- [x] Have the recipe compare the three agents' unprompted host sets per user, under the `settingsSource` owner rule for the editor, and report the differences — evidence for `NetworkReachIsUniformPerUser`.
- [x] Have the recipe read each Codex reviewer policy for the `USER_APPROVAL_REQUIRED` routing and the wholesale-bypass refusal, and the editor's approval settings for the values `TheEditorPromptIsCopilotsEscalationSurface` names — evidence for `GuardrailEditsRouteToTheUser`.
- [x] Retire `tests/test_secret_floor_declarations.py`, `tests/test_guardrail_declarations.py`, `tests/test_network_declarations.py`, and `tests/test_reviewer_policy.py`.
  They are the only Python readers of `CLAUDE_SETTINGS`, `CODEX_CONFIGS`, and `SECRET_FLOOR_REPRESENTATIVES`, so drop the two globs from `tests/conformance.py` and move the representative paths to where the recipe reads values from.
  `tests/conformance.py` had no reader left and is deleted.
- [x] Run the assessment once against the current configurations and commit the record as this change's evidence for the four requirements; a finding becomes a task here, not a waiver.
  `.specs/assessments/2026-09-27.md`, run by an agent given only the recipe; its unclear points were fixed in the recipe.
- [x] Update `modules/home/ai/shared/AGENTS.md`: the conformance tests no longer check the other surfaces against the manifest; the assessment does, and the Layout and Rules sections say so.
- [x] Add `RegisteredHooksLieInTheEnforcementFloor` to `agent-configuration-floor`, and a step to the assessment recipe that compares the directory of every registered hook, and the repository directory its deployed link resolves to, with `HOOK_DIRECTORIES`.
  The user asked for it on 2026-10-06, while `guarded-path-classes` still defers a rule that discovers hook directories, so a directory left out of the list is reported rather than silently outside the floor.
  Checked by hand the same day: every registered hook sits in `~/.claude/hooks/`, `~/.codex/hooks/`, `~/.copilot/hooks/`, or `~/.pi/agent/shared-hooks/`, and their links resolve to `claude/hooks/`, `copilot/hooks/`, `pi/security/`, and `shared/hooks/`; all eight are listed.
  The next full assessment records it.

### Findings from the 2026-09-27 assessment

- [x] Restore `block-sensitive-paths.py` and `block-hook-tampering.py` to the `^(Bash|Read|Write|Edit|apply_patch)$` group in `users/mithras/home-manager/codex/hooks.json`, or declare their omission as a `capability-coverage` exception.
  An uncommitted edit in this worktree removed both; nothing in this change records why, `nrl`'s file keeps them, and `HEAD` has them.
  Restored from `HEAD`.
- [x] Add the secret stores, `~/.config/sops-nix`, `~/.config/sops`, and `~/.local/state/sops-nix`, to `denyRead` and `denyWrite` in the editor sandbox lists and the Pi sandbox files, as the Claude lists deny them.
- [x] Turn off the two vendor-default entries `chat.tools.urls.autoApprove` keeps, `https://code.visualstudio.com` and `https://github.com/microsoft/vscode/wiki/*`: the editor merges the setting with its defaults, so the fetch tool reached them without asking.
- [x] Declare `chat.agent.sandbox.advanced.runtime` with `enableWeakerNestedSandbox` false, and `chat.experimental.permissionsSandboxToggle.enabled` false, which removes the picker's per-session switch that turns the sandbox off; name both in `BypassModesAreRefused`.
- [x] Record in `tool-vocabulary.toml` that Pi's optional Windows `powershell` tool is refused on purpose, because the shell hooks read a command as Bash.
- [x] Correct the `~/.copilot/hooks` comment and the `BypassModesAreRefused` text: the 1.139.1 build lists `~/.copilot/hooks` among its default hook locations, so the declaration keeps the entry rather than being the only thing that adds it.
- [x] Run the assessment again once the Codex registration is settled, and commit that record beside the first.
  `.specs/assessments/2026-09-27-2.md`, run by a Codex agent given only the skill and its references; it found no failures.
- [x] Reword the edit-approval bypass in `BypassModesAreRefused` to an entry this repository declares that approves every path, and update the Copilot reference to match.
  The editor merges `chat.tools.edits.autoApprove` with a default that holds `"**/*": true`, so the literal reading failed every configuration; approving ordinary workspace edits is the posture, and the hooks put a guardrail edit to the user.
  The installed extension scans the patterns in order and the last match decides, so the declared guardrail entries still prompt.

## Refuse unlisted tools on the harnesses with no adapter

Claude Code and Codex send their tool names to the hooks directly, so a tool no vocabulary table lists was judged by nothing.
Claude Code 2.1.284 had six such tools that write or run code; Codex 0.157.0 had none that fire `PreToolUse`.
The decision is `HarnessesWithoutAnAdapterRefuseThroughAHook`.

- [x] Let `hook_response.py` load when the vocabulary cannot, so a refusal still carries the stop instruction.
- [x] Add `hooks/refuse-unlisted-tools.py` and `tests/test_unlisted_tool_refusal.py` — evidence for every scenario of `UnlistedToolIsRefused` and `UnreadableVocabularyRefusesEveryCall`.
- [x] Declare `[passthrough]` lists for Claude Code and Codex, read from the installed builds, with the tools left refused until decided named in the comment above each.
- [x] Add the `unlisted-tool-refusal` row to `CAPABILITIES`, and `capability-coverage` exceptions for Copilot and Pi, whose adapters refuse unlisted tools themselves.
- [x] Register the hook with no `matcher` in the four Claude settings files, and as the last `PreToolUse` group in both Codex `hooks.json` files, so no earlier hook moves and loses its recorded trust.
  The user commits the Claude settings files.
- [x] Judge every agent under `HarnessGainsATool` in the assessment skill, with how to read the Claude Code and Codex tool sets in their references.
- [x] Refuse a Claude Code or Codex tool mapped to another name, since no hook converts names for them, and add the case — evidence for `MappedToAnotherName`.
- [x] List `NotebookEdit`, `Glob`, and `Grep` as Claude Code passthrough, each commented with the Claude permission rules that check it.
- [x] Map Pi's `grep` onto `Read`, and add dispatcher cases for a credential and an ordinary file.
  Pi ships as a compiled binary, so its `grep` field name `path` is taken from the dispatcher's handling of Pi's file tools, not read from the build; confirm it in a live Pi session.
- [x] Decide each Claude Code tool left refused: list it as passthrough with what it leaves unjudged, or keep it refused with the reason in a vocabulary comment.
  `PowerShell`, `Monitor`, `SendUserFile`, and `Artifact` are refused on purpose, with the reasons and `Monitor`'s friction in the vocabulary comment.
  `PushNotification`, `ScheduleWakeup`, `CronCreate`, `RemoteTrigger`, `EnterWorktree`, and `ExitWorktree` are passthrough, each commented with what it leaves unjudged.
  The user chose passthrough for `RemoteTrigger` knowing its Routines run in the cloud outside every guardrail, and for `ExitWorktree` knowing it can discard a worktree without a prompt.
- [x] Decide Codex's plugin installation tools: `list_available_plugins_to_install` and `request_plugin_install` are passthrough, because installing asks the user through a form Codex shows.

## Record what waits on a prompt

- [x] Write `.specs/WHEN-CODEX-CAN-ASK.md`, listing the decisions made because Codex cannot show a hook prompt, and point to it from the posture section of `modules/home/ai/shared/AGENTS.md`.

## Declare each policy table entry as a record

`block-destructive-ops-patterns.toml` declares each rule as a record with its reason.
`tool-vocabulary.toml` and `guarded-paths.toml` declare names and paths in arrays, with any reason in a comment that no reader checks.
No spec pins either file's shape, so the change is to the files, their loaders, and their tests.

- [x] Declare refused records in `tool-vocabulary.toml`, one table per harness, each record with a required `tool` and `reason`, for every tool refused on purpose: Claude Code's `PowerShell`, `Monitor`, `SendUserFile`, and `Artifact`, Pi's `powershell`, and Copilot's `edit_files`.
- [x] Declare each passthrough entry as a record with a required `tool` and `reason`, one table per harness, taking the reason from the existing comment where one exists.
- [x] Have the vocabulary loader refuse a record with no reason, and a tool declared in more than one of mapped, passthrough, and refused.
- [x] Update every reader of the passthrough list: `refuse-unlisted-tools.py`, the Copilot adapter, the Pi dispatcher, their tests, and the assessment skill and its references.
- [x] Declare each path in `guarded-paths.toml` `[guarded]`, `[block]`, `[exec-through]`, and `[write-through]` as a record with a required `path` and `reason`, and rename `why` to `reason` in `[[exceptions]]`.
- [x] Update the manifest loader in `guarded_paths.py`, `test_guarded_paths_manifest.py`, every test that writes a manifest, and every document that quotes the manifest's shape.
- [x] Record the format in `design.md`: one record per entry, a required `reason`, and the same field names in every policy table.

## Close the open verify findings

- [x] Replace `_FILE_TOOLS` in `pi/security/hook-dispatch.py` and the Copilot adapter's two literal sets with a declared `file` group, and add the Pi dispatcher and the Copilot adapter to the files `test_shared_hooks_hold_no_private_tool_vocabulary` reads — evidence for `ToolVocabularyIsDeclared`.
- [x] Reword `ExplanationContract` so an `Ask` that an adapter may refuse carries the AI instruction, as `AskAnAdapterMayRefuse` requires.
- [x] Correct `proposal.md` § Approach to name every requirement the deltas modify.
- [x] Turn `.verify/probe-exception-link.log` into `test_exception_does_not_travel_along_a_link` — evidence for `ExceptionDoesNotTravelAlongALink`.
- [x] Reword `HarnessGainsATool` so conformance fails on a tool that is neither mapped, passthrough, nor refused.

## Close the 2026-10-01 verify findings

`.verify/report.md` records the run.

- [x] Refuse a long option that abbreviates a refused one, since GNU utilities accept an unambiguous prefix: `sort --out=<path>` wrote a guarded file.
- [x] Read a `trap --` body as installed code: the classifier took `--` for the list form, and bash installs the body after it.
- [x] Take the destination of `cp`, `install`, and `ln` from `-t` or `--target-directory` when one is given.
- [x] Anchor a name-heuristic exception to the declared path inside a repository root, so `/tmp/unrelated/scripts/mcp-secrets.sh` is not excused.
- [x] Make `block-sensitive-paths.py` fail closed on an internal error for a sensitive tool, and have `block-secrets.py` warn on unparsable input that names no tool, per `ErrorHandlingByDamagePotential`; update the two tests that pin the old directions.
- [x] Add tests for the runtime-error branches of `block-secrets.py`.
- [x] Narrow `DriftWarning` for Pi, whose runner delivers the warning in the result of the call that ran.
- [x] Record the end-of-turn selection limits: a file staged in a repository with no commits and then deleted, and a filename holding a newline.
- [x] Correct the wording the run found overstated: `GateResponse` for an Ask an adapter may refuse, the Pi passthrough route, the model-compliance scenarios, the runner-availability condition in `RunsAtEndOfTurn`, and three stale statements in `design.md`.

## Refuse a pattern file that does not validate

- [x] Add a test over the shipped `block-destructive-ops-patterns.toml` that every rule has a pattern, `description`, `reason`, and a `mode` of `block` or `ask`, and that every pattern compiles.
- [x] Make `block-destructive-ops.py` validate the whole pattern file before judging, and reach `Ask` naming the file or the invalid rule when the file is missing, unreadable, unparsable, or holds an invalid rule; update its docstring, which says a missing file fails open — evidence for `ExternalPatternFile`.
- [x] Add tests for `PatternFileMissing`, `PatternFileUnparsable`, and `RuleIsInvalid` (unknown mode, missing field, pattern that does not compile, each with a command that matches a valid rule and one that matches none), and for `UnusableFileWhereNoPromptCanBeShown` on Codex — evidence for `ExternalPatternFile` and `hook-interface` `CommandHookCannotLoadItsRules`.
- [x] Update the tests that pin the fail-open on a missing or unreadable file.

## Organization

- [x] Consider whether and how to expand property testing.
  Added two properties over the four Python hooks, run in one process with `HOME` pinned to a temporary home by `tests/hook_chain.py`.
  `test_credential_read_properties.py` plants credentials holding a marker and fails when an allowed command prints one; its command catalog is kept apart from the hooks' reader list.
  `test_agent_ordering_properties.py` holds that Codex, Copilot, and an unknown agent are never allowed more than Claude; it passed on its first run.
  Running the metamorphic relations over every Bash hook was conditional on holes in the pattern-based hooks, and the read property found none there.

- [x] Track a `cd` or `pushd` in `shell_words` rather than in `bash_commands`, so `block-sensitive-paths.py` judges a relative read against the directory the command entered.
  The read property found `cd ~/.config && cat mcp-secrets.env` allowed.
  Report every directory a segment may run in: after `cd X ||`, the segment runs in the old directory when the change fails, and a `cd` inside a subshell does not carry past it; `cd /absent || cat mcp-secrets.env` from `~/.config` must be judged in `~/.config`.
  Correct the working-directory limit in `path-matching` `StatedLimits`, which says such a path is judged as unresolvable, and close the matching deferred item in `guarded-path-classes`.
  Done: each `Segment` carries `directories`, and `bash_commands.read` reads them in place of its own tracker; a relative word after a change yields its spelling in each directory.
  The tamper ancestor case `cd modules/home/ai/shared && rm -rf hooks` now reaches the direct check, so the ancestor list holds `cd modules/home/ai && rm -rf shared` and `cd /tmp; rm -rf modules` instead.

- [x] Resolve `$HOME` and `${HOME}` in `shell_words` as it resolves `~`.
  The read property found `cat "$HOME"/.config/*` allowed while `cat ~/.config/*` is refused.
  Done for a leading reference, quoted or not, where the home path holds no glob or space character; `shell-lexing` `AWordTheShellRewritesIsResolvedOrRefused` states the exception.

- [x] Hold the read property to the forms `BashReadBestEffort` leaves in scope: run every command on the block-class credentials, and leave the stated-limit forms out of the commands run on a credential only the name rules recognize.
  Done: `grep -r` is out of the catalog until `recursive-credential-read-refusal` adds it back, and the stated-limit forms run only on the declared credentials.
  Both properties passed on 2026-10-04.

- [x] Record a recursive read as a `BashReadBestEffort` limit, with the block-class sandbox floor in `ConfigurationSurfacesCoverTheDeclarations` as its boundary.
  That floor passed on every agent in the 2026-10-02 assessment, so no new floor requirement is added.
  Refusing a recursive read rooted above a declared credential is its own change, `recursive-credential-read-refusal`.

- [x] /simplify and /refactor audit; assess fragility/overspecifity Ran on 2026-10-05 in audit mode over the shared hooks, their tests, and the Copilot adapter; the ledger is `.simplify/ledger-2026-10-05-2343.md`, untracked.
  The user approved four fixes, listed below, and declined consolidating the shell and Python normalizers and adding constructor checks to `Reading` and `Word`.
  Moving `block-dangerous-bash.sh` into one rule engine and matching the lexer's spelling of a command is its own change, `single-command-rule-engine`.

- [x] Correct the `_quote` docstring in `test_guarded_paths_manifest.py`, which names the exception field `why`; the field is `reason`.

- [x] Delete `extract_bash_read_targets` and `extract_bash_write_targets` from `block-sensitive-paths.py`, which nothing calls.

- [x] Rename `SENSITIVE_TOOLS` in `block-secrets.py` to `MUTATING_TOOLS`, the name the other hooks give the same group, and update the two assertions in `test_tool_vocabulary.py`.

- [x] Move `policy()` from `test_path_class_policy.py`, and `_quote` and `_dump_minimal_toml` from `test_guarded_paths_manifest.py`, into a shared test support module, and import `HOOKS_DIR` from `hermetic`.
  The helpers went into `hermetic.py`, which already builds the temporary worlds, rather than a new module.

- [x] Stop `shell_words` cutting a relative path at a `/` into a root path.
  An unresolvable word's evidence took a fragment from any `/`, so after `cd ..` the word `hooks/<name>` also named `/<name>`.
  The name heuristic then refused a file in an exempt directory by the root spelling.
  A fragment now starts only where a word or an operator ends; `test_a_relative_path_is_not_cut_at_a_slash_into_a_root_path` and `test_a_relative_path_after_a_cd_is_judged_where_it_points` cover it.

- [x] Consider whether to make the hooks a uv Python project with a `pyproject.toml`.
  The user chose a test-only project on 2026-10-05: `modules/home/ai/pyproject.toml` and its `uv.lock` pin pytest and hypothesis, and `just apps test` runs every suite from that lock with `--locked`.
  The hooks stay standalone PEP 723 scripts, so a hook call does not check the lock or build `.venv`, and a project environment would sit in a guarded directory the agent sandboxes do not let the agents write.
  The flake checks still take the test tools from nixpkgs, because the build sandbox cannot download the locked versions.

- [x] Standardize the hook script names.
  The user confirmed on 2026-10-05 the rule in `AGENTS.md`: a hook that runs is kebab-case, and a module that is imported is snake_case, without a leading underscore.
  Every hook file already follows the rule, so no file is renamed.

- [x] assess spec drift over implementation

  > for my own edificaiton, i'm interested in how our specs drifted/evolved over the course of this implementation. please have a sonnet 5.5 subagent draft a report in .\_scratch about this. it should use at minimum the session histories and agentsview, but possibly also diff the file versions (I think vscode has filesave tracking?)

## Check the change against live sessions

Each check needs the deployed hooks to point at this branch.
Run `just nix switch home` from the worktree with `GIT_ROOT` unset or set to the worktree: the recipe falls back to its own checkout only when `GIT_ROOT` is unset, and the deployed links then point into the worktree.
Every open agent session runs this branch's hooks until the switch from `~/.nixconfig` after the merge.
A linked file that git ignores is absent from a worktree and fails evaluation: link `modules/home/apps/zed/settings.json` to the main checkout's copy first.

- [x] Deploy Pi's shared hooks to `~/.pi/agent/shared-hooks/`.
  Pi 1.0 reads `~/.pi/agent/hooks/` as its retired hooks directory and stops at startup until a key is pressed; found by the first live Pi session.
- [x] Apply the 2026-10-02 assessment's tool decisions to `tool-vocabulary.toml`: refuse Claude's `ArtifactComments`, `ArtifactData`, and `ArtifactCheck`; pass through Codex's namespaced agent and clock tools and its two async tools; pass through Pi 1.0's `mcp__*`, `tool_search`, `codemode`, and the pi-subagents tools.
  `mcpScript` was passed through too, and left the vocabulary with `pi-mcp-adapter`, which registered it.
  Codex names a namespaced tool by joining namespace and name, so the bare `spawn_agent` never matched and a live Codex session was refused `collaborationspawn_agent`.
- [x] Show live that a subagent's or a script's tool calls reach the hooks before passing their launcher through.
  2026-10-03: a Codex subagent's `python3 -c` was refused by the command validator; a Pi `codemode` script's `bash` call was refused by the same rule; a Pi `mcpScript` script's `bash` call returned `native_tool`.
- [x] Enable Pi's `grep`, `find`, and `ls` with `defaultTools` in mithras's Pi settings, and pass Codex's `image_genimagegen` through.
- [x] Move the hooks extension from `pi/hooks/` to `pi/extensions/hooks/`, so the source mirrors `~/.pi/agent/extensions/hooks/` and `hooks` no longer names three things.
- [x] Drop `pi-mcp-adapter` for every user, so Pi's built-in MCP support sends each MCP call through the tool pipeline the hooks judge.
  2026-10-03: `/mcp` inside a Pi session showed all five servers connected, exposed through `codemode`, once a `-builtin:mcp` entry Pi had written into mithras's settings was removed.
  `pi mcp list` is no evidence here: it always uses the built-in support, whatever the settings say.
- [x] Check only the files a turn changed at end of turn: `git-baseline.sh init` records a working-tree snapshot, and `stop-precommit.sh` checks the files that differ from it, or every uncommitted file without one.
  A Pi turn that changed nothing had linted every uncommitted file in the worktree.
- [x] Drop the Pi 0.x package install: Pi 1.0 installs the packages `settings.json` lists into `~/.pi/agent/npm`, so the wrapper's `NPM_CONFIG_PREFIX` and the `~/.pi/npm` activation install served nothing.
- [x] Confirm Codex asks to trust the new hook on its first session, and runs a shell call and a passthrough tool with it trusted.
  2026-10-02, Codex with `gpt-5.6-sol`: trusted, `git status` and the plan update ran.
- [x] Confirm in a live VS Code session that a Copilot subagent's tool calls reach the hooks, since the subagent tools are declared passthrough on that assumption.
  Invalid on 2026-10-03: the local model reported `1` for `python3 -c 'print(1)'`, but its transcript holds no `run_in_terminal` call for it, from the main agent or a subagent.
  The transcript shows VS Code sends `run_in_terminal` with a `command` field, which the adapter refuses for this command when run by hand.
  Rerun with a model that calls the tool, and read the hook trace log for the validator's refusal.
  2026-10-03, with a stronger model: the main agent's `python3 -c 'print(1)'` was refused by the command validator before Python ran, and the sandbox probe's request to run outside the sandbox was skipped.
  Through a subagent, the same command was denied by the command validator before execution, so the subagent tools stay passthrough.
- [x] Verify against a live VS Code agent session that a command reaching a guarded path is refused by the sandbox and that no unsandboxed retry is offered, then record the observed behavior in the verify record.
  2026-10-03: `bash /tmp/sandbox-probe.sh`, running `grep -c` over `~/.config/mcp-secrets.env` where the hooks cannot see the path, ended `Operation not permitted`, exit 2, with no unsandboxed retry offered.
- [x] Verify against a live `pi` session that a read of `~/.config/mcp-secrets.env` is refused by the sandbox with the hooks disabled, so the layer is shown to deny on its own.
  2026-10-03: the same probe, run through Pi's `bash` with the hooks unable to see the path, ended `Operation not permitted`, exit 2.
- [x] Trust the new Codex hook on the first Codex session after `just nix switch home`.
- [x] Confirm in a live `pi` session that Pi's `grep` tool names its search root `path`, as the dispatcher's mapping onto `Read` assumes.
  2026-10-03: with `grep` enabled, a `grep` over the MCP secrets file was refused by both hooks as a `Read` of the resolved path.
- [x] Confirm in a live Claude Code session and a live Codex session that `refuse-unlisted-tools.py` refuses a tool no vocabulary table lists and lets a passthrough tool proceed.
  2026-10-03: Codex was refused `collaborationspawn_agent` while it was unlisted, and ran it once listed; Claude Code ran `ToolSearch`, a passthrough tool.
  Claude Code 2.1.284 offers no unlisted tool, so its refusal is shown by tests, and by Pi's dispatcher refusing `mcpScript` live.

## Merge and activate

- [ ] Merge to `main`, then run `just nix switch home` from `~/.nixconfig`, so the deployed links point at the main checkout again before the worktree is removed.
