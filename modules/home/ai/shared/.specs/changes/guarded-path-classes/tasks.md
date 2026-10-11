# Tasks: guarded-path-classes

## Working tree

The deployed hooks are symlinks into `~/.nixconfig`, and `shared/hooks.nix` enumerates `hooks/` at activation.
A hook invoked through its deployed symlink resolves `sys.path[0]` to the repository directory it points into, so `hooks/shell_words.py` imports as soon as it exists there and needs no activation.
`hooks/session-policy-checks.py` is run by path from `session-tool-checks.sh` rather than imported, so it has no deployed symlink until the next `just nix switch home`, and the session check reports an error until then.
An edit in the main checkout is live in every open agent session the moment it is saved.

- [x] Do every task below in the `ai-guardrails` worktree; commit there; leave the main checkout untouched until merge.
  Implementation is in the worktree.
  Commit, merge, and activation are pending the user's review.
- [x] At merge: rebase the branch onto `main`, which has moved since the fork and holds the `CLAUDE_CODE_SHELL` pin in `settings.darwin.json`; then the user fast-forwards `main` from their terminal, because that file is sandbox-denied to the agent, and runs `just nix switch home` once before any session relies on the hooks.

Groups run in build-dependency order: the pending change is revised first so the two never touch one requirement; then the lexer, which everything else imports; then the matcher and the manifest model; then the two hooks and the session check over them; then the posture evidence, which is judged against the finished mechanism; then the Pi reader, the documentation, and the closing items.

## Revise security-posture-alignment

- [x] Remove `AWordTheShellRewritesIsResolvedOrRefused` from `changes/security-posture-alignment/specs/hook-tampering-blocking/spec.md`; it is restated in this change's `shell-lexing` delta.
- [x] Remove the `ReadThroughCoversTheAgentModuleTree` decision from its `design.md`, and the read-through sentence from its proposal's scope.
- [x] Remove from its `tasks.md`: the four read-through tasks in "Fix and record the read classifier", the grep-overtrigger task, the whole "Close the lexing divergence in the option guards" group, and from "Give the classifier a test method that finds these" the `hypothesis`, `shellprobe`, differential, metamorphic, totality, generator, and hermetic-fixture tasks and the backslash-continuation task.
  Leave the `internal_error`, `_CALL`, `TestFailClosedOnInternalError`, spelling-property, degradation-property, and generated-effect items, which are about the hook and not the lexer.
- [x] Rewrite the note under "Close the guarded set over ancestors" that says `~/.claude` gates only because it is a `location-only` declaration: it gates because the home is a guarded declaration.
- [x] Run `check_modified_completeness.py --change security-posture-alignment` and the format check over its deltas, so the revised change still verifies on its own.

## shell-lexing

- [x] Create `hooks/shell_words.py` from `_split_words`, `_ansi_c`, `_resolve`, `_candidate_words`, `_expanded`, and `_segments` in `block-hook-tampering.py`, exposing `lex(command, cwd) -> list[list[Word]] | None` where `None` is the whole-command unresolvable report.
- [x] Give `Word` a `kind` field with the eight kinds, assigned in `lex`: command, option, assignment, redirection target, pattern, path candidate, plain word, unresolvable.
  The command is the first non-assignment word of a segment; an option is a word beginning with `-` in a position bash would pass; a redirection target is the operand of a redirection operator, attached or spaced.
- [x] Implement the path-candidate rule: a separator or a leading `~`, or an entry that exists relative to `cwd`.
  Run the existence test for bare words only.
  A redirection target keeps its own kind; the hooks apply their path rules to path candidates and redirection targets alike.
- [x] Keep the paths an unresolvable word holds available on the `Word`, as `_candidate_words` finds them today, so the text check has them.
- [x] Add `tests/test_shell_words.py` with parametrized examples, one table per kind: an attached redirection target, an assignment before a command, a quoted operator that does not split, a bare word that names no entry, the same word once an entry exists, a word with a separator naming no file, an input-redirection operand — evidence for `EveryWordHasAKind`, `APathCandidateDenotesAFile`, and `SegmentsFollowControlOperators`.
- [x] Move the differential, metamorphic, and totality properties from `tests/test_classifier_properties.py` into `tests/test_shell_words_properties.py`, stated over `shell_words.lex` rather than the hook, with `shellprobe` unchanged — evidence for `AWordTheShellRewritesIsResolvedOrRefused` (the containment scenario) and `LexingIsTotal`.
  Leave in `test_classifier_properties.py` the properties that are about the hook's verdict: a guarded operand never makes a verdict more permissive, and a trailing separator does not change it.
- [x] Add the parametrized examples for each resolution form: a quoted word, an ANSI-C quoted word, a pattern that matches, a pattern that matches nothing, a substitution, a brace expansion, a path inside an unresolvable word, and a newline — evidence for the remaining `AWordTheShellRewritesIsResolvedOrRefused` scenarios and `ANewlineRefusesTheCommand`.
- [x] Add the hermetic fixture: a temporary home, a temporary repository, and a substituted manifest, so a case states the world it needs rather than depending on what exists on the machine.
  Use it for every existence-dependent case in this change.
- [x] Add `tests/test_class_hook_integration.py::test_two_hooks_one_reading`: run both hooks over the command forms in the lexer example tables and assert each hook's recorded segments and words are the lexer's — evidence for `OneLexerForEveryHook`.
- [x] Establish whether backslash line continuation reaches the option-injection divergence, and record in the lexer's docstring what is refused and what is judged.
  A newline anywhere in the command still refuses it, so this is reachable only once that is narrowed to an unquoted newline.

## path-matching

- [x] Extend `guarded_paths.spellings()` to return every hop of the link chain: as written, expanded, each intermediate link, and the final target.
- [x] Hold each declaration as its chain of hops in `GuardedLocations`, computed once at construction, and have `contains()` return the covering declarations with the distance at which each matched rather than a boolean.
- [x] Delete the `location_only` parameter and every use of it.
- [x] Fix `fragment()` to keep a glob component as a pattern in the trailing fragment, so `instructions/*.md` yields a fragment that matches `instructions/x.md` and not `.md`.
- [x] Resolve a relative path against the payload's `cwd` where one is supplied, and report it unresolvable where none is.
- [x] Add to `tests/test_guarded_paths.py`: a declared link reached by its target, an intermediate hop reached, a resolved word carrying a declaration's written form that resolves elsewhere, an unresolvable word holding a declaration, a relative path with and without a supplied `cwd` — evidence for `SpellingIndependence` and `TextMatchingIsForTextThatMayHoldNoPath`.
- [x] Add a glob case set: `*` in a directory component, `*` in the last component matching directly within and not one level deeper, and `*` failing to span a separator — evidence for `OneGlobForm`.
- [x] Record the four stated limits in the module docstring of `guarded_paths.py`, with the directory-change limit marked deferred and the absolute-path instruction beside it — evidence for `StatedLimits`, read by the docstring test that already checks the limits are described.

## guarded-path-declarations

- [x] Rewrite `hooks/guarded-paths.toml` to the five tables, `[guarded]`, `[block]`, `[exec-through]`, `[write-through]`, `[[exceptions]]`, with the content the `guarded-surface` delta declares and a comment per table stating what the class does.
- [x] Read the five tables in `build_guarded` and in the sensitive-path hook's credential alternation, which becomes the block alternation; treat a missing table as a load failure.
- [x] Route a load failure in the tamper hook through `internal_error`, so a call to a covered mutating tool asks under Claude and refuses where no prompt is honored, a `Read` proceeds with the failure reported, and the reason names the failure; leave the sensitive-path hook proceeding with its report.
- [x] Update `TestManifestLoadFailure` in `tests/test_guarded_paths_manifest.py`: the tamper hook asks on a `Write` and a `Bash` call and proceeds on a `Read` for an absent manifest, an unparsable one, and one missing a table; refuses on Codex; and the sensitive-path hook still proceeds with its report — evidence for `LoadFailureIsReported`.
- [x] Implement `guarded_paths.verdict(path, operation)` as the design's per-hop rule: block absolute, closest declaration otherwise, delta class on a tie, strictest across hops.
- [x] Derive the enforcement floor independently of grants and enforce it at verdict time, retaining grants outside the floor and naming the paths they cannot permit.
- [x] Implement `guarded_paths.validate(manifest)`: floor restrictions, a hop under block and a carve-out, and a link held directly inside a carve-out directory whose target lands under a stricter declaration with no same-class carve-out.
- [x] Update `tests/test_guarded_paths_manifest.py`: the required-section list and `_all_path_entries` cover the five tables and nothing else — evidence for `SingleDeclarationSource` `OnlyPolicyTablesExist`; the two existing manifest-shape scenarios stay.
- [x] Add the precedence cases to `tests/test_path_class_policy.py` over the substituted manifest, one per scenario: block beneath write-through, write-through beneath guarded, guarded beneath write-through, exec-through beneath guarded, a link from a write-through directory into a guarded location, a link from an exec-through directory into undeclared space, and the same declarations in two orders — evidence for `PrecedenceIsOneRule`, in `test_block_overrides_write_through`, `test_closest_declaration_decides_with_delta_on_tie`, `test_exec_through_supplies_a_guarded_default`, `test_link_into_guarded_space_keeps_stricter_target`, `test_link_into_undeclared_space_keeps_exec_through`, and `test_declaration_order_does_not_change_verdict`.
- [x] Add `tests/test_path_class_policy.py::test_equivalent_policies_reach_equal_verdicts`: a base-with-carve-outs manifest and an enumerated manifest judged over the same calls — evidence for `EquivalentPoliciesReachEqualVerdicts`.
- [x] Add `tests/test_class_hook_integration.py::test_class_outcomes`: a read, a write, and a run under a guarded declaration; a read and a write under block; a write under exec-through; a run under write-through — evidence for `TheGuardedClassIsTheBase` and `ADeltaClassChangesOneOutcome`, with `tests/test_path_class_policy.py::test_guarded_base_outcomes` over the policy alone.
- [x] Cover the run rule in `tests/test_path_class_policy.py`: a run under guarded alone asks, under exec-through proceeds, and a read under exec-through proceeds — evidence for `RunRequiresAnExecThroughDeclaration`, in `test_exec_through_supplies_a_guarded_default` and `test_write_through_does_not_make_runnable`, with `tests/test_tamper_gate.py::TestExecThroughIsItsOwnClass` over the hook.
- [x] Add the enforcement cases to `tests/test_path_class_policy.py`: a substituted manifest carving out its own manifest, a hook, and a hook's repository source, each asserted to ask and to be reported — evidence for `EnforcementIsNeverCarvedOut`, in `test_enforcement_members_cannot_be_carved_out`, `test_each_declared_hook_tree_is_enforcement`, and `test_carve_out_covering_enforcement_is_limited_and_reported`.
- [x] Add the validator cases to `tests/test_path_class_policy.py`: the two conflict shapes reported with their names, the two no-conflict link cases silent, and the real manifest exercised — evidence for `ConflictingDeclarationsAreReported`, in `test_block_overlap_is_reported_with_both_declarations`, `test_overlap_reports_only_the_matching_pair`, `test_link_with_matching_target_carve_out_is_silent`, and `test_real_manifest_validation_returns_diagnostics`.
- [x] Move the sops representatives from the manifest into `tests/conformance.py` as `SECRET_FLOOR_REPRESENTATIVES`, and have `test_secret_floor_declarations.py` read `[block]` plus that tuple — evidence for `ConfigurationSurfacesCoverTheDeclarations` `AgentPermissionFloor` and `SandboxFloor`.
- [x] Delete from `test_guardrail_declarations.py` the guarded-source and deployed-declaration coverage tests and the VS Code exception class; add one test that a guarded declaration with no floor entry passes — evidence for `GuardedDeclarationWithNoFloorEntry`.
- [x] Remove the `vscode-edit-approvals` and `codex-guarded-workspace` exceptions from the manifest, and the Codex read-grant conformance helper they excused.
- [x] Update `test_pi_guarded_declarations.py`: drop the location-only behavioral-coverage test, and point the instruction-layer one at write-through.

## hook-tampering-blocking

- [x] Replace the tamper hook's lexing with `shell_words.lex`, and build `_paths_in`, the read classifier, and the run classifier over word kinds.
- [x] Judge each named path with `guarded_paths.verdict`, and apply the text check to unresolvable words and interpreter program text as specified below.
- [x] Delete `READ_THROUGH`, `only_carved_out`, `_carved_out`, `INSTRUCTION_BASES`, `is_instruction_markdown`, and `_only_instruction_markdown`; a write proceeds where `verdict` returns write-through for every written path.
- [x] Rewrite `_unrecognized_read_reason` and `_unrecognized_read_refusal` to name the syntax that stopped recognition, the accepted read utilities and interpreters, and the instruction to name paths absolutely.
- [x] Update `tests/test_tamper_gate.py` and `tests/test_tamper_protected_classes.py` to the class vocabulary: every read case proceeds on every agent; a block read refuses; the existing write cases ask — evidence for `ReadsAreAllowed` and `MutationIsBlocked`, scenario by scenario.
- [x] Add the write-through cases to `tests/test_class_hook_integration.py::test_class_outcomes` over the hermetic fixture: a write-through directory beneath a guarded base proceeds, a nested path asks, a link named under write-through leading to a guarded file asks, and a shell command mixing write-through and guarded paths asks — evidence for `WriteThroughLocationsAreWritable`, with `tests/test_path_class_policy.py::test_write_through_does_not_make_runnable` over the policy alone.
- [x] Text-check the word after an interpreter's inline-code option with `mentioned_in`, so the guarded paths inside an inline program are among the paths the command names.
- [x] Refuse recognition for any command with a builder segment: `xargs`, `eval`, an interpreter with inline code, or a shell reading standard input, whatever the other segments do.
- [x] Add the unrecognized-command cases to `tests/test_class_hook_integration.py`: a recognized read, a recognized run, each hidden-effect form, `bash -c 'rm <guarded>'`, `echo <guarded> | xargs rm`, a relative path after `cd`, a run mixed with a guarded path, and a read mixed with a block path in `test_class_outcomes`, with the reason-text assertions for the accepted forms, the stopping syntax, and the absolute-path instruction in `test_unrecognized_reason_names_syntax` — evidence for `UnrecognizedCommandsAreGated`.
  The two probe forms exit 0 under Codex against the worktree hook as of 2026-09-15 and must gate.
- [x] Keep `RUNS` and `NOT_RUNS` and re-point them at the fixture — evidence for `ARunTargetsAnExistingScript`.
- [x] Add `test_a_write_to_another_agents_guarded_location_asks` over the substituted manifest, run under each agent — evidence for `ProtectedSurface`.
- [x] Update the Claude, Codex, and Copilot tamper suites, each of which asserts instruction markdown is writable; each now asks.

## sensitive-path-blocking

- [x] Replace `_lex_tokens`, `_decode_ansi_c`, `_candidate_paths`, and `expand_glob_candidates` in `block-sensitive-paths.py` with `shell_words.lex`; judge every word of a read segment by the strong rules, an unresolvable word by the paths it holds, and an input-redirection target regardless of the command word.
- [x] Apply `NAME_PATTERN_RE` to path candidates and redirection targets, as the updated sensitive-path spec requires.
- [x] Add to `sensitive-path-cases.json`: a search pattern carrying a heuristic word that names no entry proceeds; the same bare word refuses once an entry exists; a word with a separator refuses whether or not the file exists; a quoted and an ANSI-C quoted zero-access path refuse; a zero-access path inside an unresolvable word refuses; a bare `id_rsa` refuses with no such file — evidence for `BlockBashReadFromZeroAccessPath`.
- [x] Run the verdict tables against the Pi port to confirm the added cases are inert to it or match.
  Superseded: `security-posture-alignment` deleted the port, and the tables now judge Pi's hook runner.

## session-tool-checks

- [x] Add the shell check to `session-tool-checks.sh`: under Claude, identified as `hook_response.invoking_agent` identifies it, warn when `CLAUDE_CODE_SHELL` is unset or names no executable whose name contains `bash`, naming the variable and the value to set; silent otherwise; no check under another agent.
- [x] Add the manifest check: call `guarded_paths.validate` through `uv run` and print each finding as a warning with exit 0; on an absent, unparsable, or table-less manifest print an error stating that mutating calls will ask until it is repaired, and exit 2.
- [x] Add `tests/test_session_tool_checks.py` running the script with a substituted environment and manifest: pin present, pin absent, pin naming zsh, another agent, a valid manifest, a grant restricted by the floor, an inert carve-out, and an unloadable manifest asserting exit 2 — evidence for `ClaudeToolShellIsPinnedToBash` and `ManifestIsValidatedAtSessionStart`.

## guarded-surface

- [x] Add `tests/test_guarded_surface.py`, running the real manifest through the hooks over a representative path per declaration: a write and a read in each agent home, the editor settings on the running platform, a repository source in the checkout and in a temporary worktree, an ordinary module file, a profile layer that does not exist, a block path read and written, a skill script run through the per-agent link and directly, a skill file written, a memory file written, an instruction markdown file written, and the renderer read — evidence for every `guarded-surface` requirement.

## Pi reader

Paused by user direction on 2026-09-15: no further Pi implementation or tests.
Existing edits remain unverified until the replacement.

Pi's new class and lexer behavior is temporarily excepted until the shared-hook migration, as recorded in `design.md` under Verification Overrides.
Report affected shared-table cases as divergences; do not silently exclude them or claim parity.

- [x] Update `pi/security/manifest.ts` to read `guarded`, `block`, `exec-through`, and `write-through`, and derive `GUARDED_FILES`, `CREDENTIAL_FILES`, and the instruction-layer shape `guarded-paths.ts` consumes from them, with `LOCATION_ONLY` empty.
  Superseded: `manifest.ts` was deleted with the port, and Pi reads the manifest through the shared hooks.
- [x] Unhook the Pi suite until the migration lands: remove `pi-security-validator-tests` from `outputs.checks` in `flake.nix` and `_test-pi` from `_test-all` in `justfiles/apps.just`, leaving `just apps test pi` runnable by name.
  The suite cannot run in this tree: the Pi migration WIP imports `shell-quote`, which neither the check derivation nor the test layout supplies, so the reader update is committed unverified and is judged when the migration replaces the port.

## Documentation and settings

- [x] The user adds `CLAUDE_CODE_SHELL` to the `env` block of `users/mithras/home-manager/claude/settings.darwin.json` and commits it, because the sandbox denies the agent that file.
- [x] Add a "Tool shell" section to `modules/home/ai/claude/README.md`: the hooks assume bash, the pin, the value, and what the session-start warning means.
- [x] Add to `modules/home/ai/shared/AGENTS.md`: the lexer's bash assumption, the zsh divergence set from the one-off measurement, and the instruction to name paths absolutely in Bash commands.
- [x] Add the absolute-path instruction to the session instructions the hooks load, in the response-style or tool-use file, so every agent reads it at session start.
- [x] Run the differential property once under zsh, with `ShellProbe` given the zsh binary, and record in `AGENTS.md` the forms where the words differed.
  The recorder comparison and differential run are complete.
  The differential property failed under zsh on ANSI-C control escapes, as recorded in `AGENTS.md`; Bash remains the supported shell.

## Verification

### Red-team follow-up

- [x] Preserve unresolvable home notation in `GuardedLocations._expand()` when `expanduser()` raises `ValueError`.
  The explicit Hypothesis example `~\x00` failed before the fix; path property and matcher tests now pass (43 passed, one filesystem-dependent skip).
- [x] Rerun the non-Pi shared suite after the null-byte expansion fix.
  Shared: 1,304 passed and one skipped, excluding `test_pi_guarded_declarations.py` by user direction.
  Scoped pre-commit checks and `git diff --check` passed.
- [x] State that option-kind classification takes precedence over the existing-entry path rule, without changing lexer behavior.
  Shared suite: 1,245 passed and one skipped on 2026-09-17, excluding `test_pi_guarded_declarations.py` because Pi tests remain paused by user direction.
- [x] Recognize the approved execution wrappers and gate pipe-fed programs not recognized as read utilities.
- [x] Review the concrete derived enforcement locations with the user, then implement the independent floor and its tests.
  Broad grants remain effective outside the floor, as confirmed by the user on 2026-09-17.
  At verdict time, block wins first; the floor then requires approval for writes and runs regardless of grant distance, ties, or order.
  Reads are unchanged.
  Diagnostics must name the floor paths where a grant does not apply rather than claim the whole grant is ignored.
  The user approved the location list, including project-local permission settings.
- [x] Run all non-Pi suites and scoped pre-commit checks after the floor and wrapper fixes.
  On 2026-09-17: shared 1,304 passed and one skipped, excluding `test_pi_guarded_declarations.py` by user direction; Claude 562 passed and two expected failures; Codex 49 passed; Copilot 34 passed.
  Scoped pre-commit checks and `git diff --check` passed.
  Logs are in `.verify/redteam-*-tests.log`.
  All five entries in `tests/redteam.md` are resolved.
  No Pi port changes, merge, activation, or new `sdd-verify` run were performed.

### Code review follow-up

- [x] Fix embedded operands (`dd of=`, attached options, assignment tilde expansion, and unmatched patterns) with location checks and regression tests.
- [x] Fix attached inline programs, wrapped interpreters, executable Git configuration, and text piped to a shell, with targeted program-text checks.
- [x] Extend enforcement carve-out rejection to all declared hook trees and test construction failures through the tool-specific error response.
- [x] Expand Hypothesis strategies to generate attached operands, inline programs, and assignments.
- [x] Correct the Bash pin advice to `/run/current-system/sw/bin/bash`.
- [x] Preserve a valid block list when other manifest validation fails, and correct the degraded-mode rationale without changing the approved failure outcomes.
- [x] Rerun affected suites and scoped pre-commit checks after the review fixes.
- [x] Move conflict directory walks to session validation, validate exception surfaces, and test the real manifest validation path.
- [x] Preserve read recognition for descriptor duplication and closure without exempting file redirects.
- [x] Report floor restrictions on grants through hook responses without weakening Ask or Block.
- [x] Add the stated-limits docstring check.
- [x] Correct the evidence references: every task above now names the test that carries it, because the delivered suites state these cases as functions rather than as the classes first planned.
- [x] Remove unused matcher code: `_within_home`, `_within_repository`, `_patterns`, `_home_location`, and the `_locations`, `_home_patterns`, and `_repo_patterns` sets only they read, all stranded when `contains()` moved to `matches_hop`.
- [x] Correct the stale vocabulary in `tests/test_tamper_gate.py`: rename the three classes named for the deleted read-through class to `TestGuardedLocationReads`, `TestAgentHomeReadsProceed`, and `TestAgentModuleTreeReadsProceed`, and restate the comments and docstrings that described the split manifest in terms of a read-through list.

Copilot floor changes and `NotebookEdit` coverage require separate scope decisions.

`sdd-verify` is deferred to a new session by user direction.

### Verification report follow-up

- [x] Guard per-user VS Code settings sources and test the repository spelling.
- [x] Name only missing manifest tables in the failure diagnostic.
- [x] Reproduce deployed hook carve-outs with regular files for Claude, Codex, and Copilot.
  All remain guarded and are reported; their grants remain effective outside the floor.
- [x] Call validation in the three silent-policy assertions, require a clean real manifest, and assert empty stderr for a valid session check.
- [x] Remove unused command classifiers and update the posture-alignment task to name the active classifier.
- [x] Add direct coverage for nested exec-through, subshell boundaries, syntax reasons, and every credential under each agent.
- [x] Generate equivalent policies, test unsupported glob forms, and run floor conformance with a guarded declaration absent from the floor.
- [x] Pass payload directories into ancestor checks and avoid process-directory resolution in both hooks when no directory is supplied.
- [x] Report bare words after directory changes as unresolvable and preserve ancestor candidates when newlines prevent lexing.
- [x] Correct contradictory test names and add mixed-operation, substitution, partly quoted glob, and surrogate cases.
- [x] Run affected suites and scoped formatting checks.
  On 2026-09-17: shared 1,241 passed and one skipped, excluding the paused Pi declaration tests; Claude 562 passed and two expected failures; Codex 49 passed; Copilot 34 passed.
  Scoped pre-commit checks and `git diff --check` passed.
  The equivalent-policy fixture adjustment also passed all 50 policy tests after the full run started.

Finding dispositions are in `.verify/feedback-resolution.md`; the original verification report remains unchanged.

### Validation results

- [x] Run `pytest -q modules/home/ai/shared/tests` and each agent suite separately, `modules/home/ai/{claude,codex,copilot}/tests`.
  Final run on 2026-09-16, after the code review fixes: shared 1,187 passed, one skipped, including `test_pi_guarded_declarations.py`.
  Codex: 49 passed.
  Copilot: 34 passed.
  Claude: 562 passed, two expected failures.
- [x] Run `nix build .#checks.<system>.shared-hook-tests` and `just nix check`.
  `shared-hook-tests` and `pi-hook-tests` built on 2026-10-03; `just nix check` was not run.
  The Pi check is no longer in `outputs.checks`, so `just nix check` covers the shared hooks and the repository contracts alone until the migration lands.
- [x] Run `prek run --files` over every changed path.
  Scoped checks passed on 2026-09-16, excluding paused Pi files and unrelated user changes.
- [x] Run `sdd-verify` for this change and for `security-posture-alignment`.
  Run on 2026-10-01 and 2026-10-03; each finding was fixed.
  Both MODIFIED completeness checks pass.
  The failure-mode specs agree with the implementation after the user's 2026-09-16 edits.
  Contract and coverage review remain pending.

## Pay down the structure this change introduced

The lexer, the word kinds, the class model, and the enforcement floor all arrived here, and each of these items is conformance to a requirement this change wrote, or internal structure no requirement names.
None changes a contract.

Measured 2026-09-19, before any of it: `PathPolicy` construction costs 77.5 ms and builds 176 floor declarations from 39 manifest entries, on every tool call, in a fresh process.
`verdict("write")` costs 3.42 ms against `verdict("read")` at 0.03 ms, which is `_project_floor` rebuilding per call.
With two to four hooks registered per tool call, construction alone is 250 to 500 ms of latency on every tool use.

Measured 2026-09-20, after: construction costs 1.38 ms, `verdict("read")` 0.01 ms, and `verdict("write")` 0.37 ms once the floor is built.
Building the floor still costs 51 ms, on the first query that consults it rather than on every call.

Which calls consult it does not follow from the operation alone, so the end-to-end cost splits by the route a path takes rather than by read against write.
A path that resolves to an absolute location reaches `_hop_verdict`, which returns before the floor for a read.
A path that stays relative because the tool call supplied no working directory falls through to the text check over `guarded`, which is built from the floor's declarations, as does an unresolvable word or an unlexable command in `block-hook-tampering.py`.
Warm, best of five on the same machine:

| Call                                    | End to end |
| --------------------------------------- | ---------- |
| `Read` of an absolute path              | 34 ms      |
| Bash read whose words all resolve       | 34 ms      |
| `Read` with no working directory        | 78 ms      |
| Bash read carrying an unresolvable word | 83 ms      |
| `Write` of an absolute path             | 82 ms      |

A Bash read holding `$pattern` costs what a write costs.
That is the common spelling of the second group, so the saving is real for file reads and for fully resolved commands, and absent for the rest.

- [x] Annotate `shell_words.lex` and `_lex` as returning `list[Segment] | None` rather than `list[list[Word]] | None`.
  `_lex` already constructs `Segment`, and the four `getattr(segment, "separator", None)` calls in `block-hook-tampering.py` exist only because the annotation hides it.
- [x] Judge words by their kind in `_read_only_segment` and `_destroyed_operands`, which take `list[str]` and re-derive `command`, `assignment`, and `option` from string prefixes.
  `_ASSIGNMENT_RE` in the hook is a copy of `_ASSIGNMENT` in `shell_words.py` — evidence for `EveryWordHasAKind`, which the lexer satisfies and these two consumers discard.
  The copy is now `shell_words.is_assignment`, for the two callers that ask about a word's shape rather than its kind.
  Two guards went with it: `_read_segment` checked the opaque kinds twice around a call that only drops leading words, and `_read_only_segment` refused an option holding `$`, which the lexer had already marked unresolvable.
- [x] Collapse the three glob translations in `guarded_paths.py` into one helper: `[^/\s]*` for fragments, `[^/]*` for distance, and `fnmatchcase` for ancestors — evidence for `OneGlobForm`.
  The component splitting in `_proper_ancestor_of` makes them equivalent today, so this is latent rather than live, and nothing holds them equal.
  `_glob_expression` is now the one translation, taking the character class as a named argument, because free text has no component boundary to rely on and must stop at whitespace as well.
  Replacing `fnmatchcase` corrects a live divergence rather than a latent one: it gave `?` and `[` glob meaning in the ancestor check, against the clause of `OneGlobForm` that recognizes no other glob form.
  `test_the_ancestor_check_reads_the_same_glob_form_as_the_distance_check` holds the two equal.
- [x] Publish `GuardedLocations.chains` as a read-only property and give `guarded_paths.py` a module-level path expander.
  `PathPolicy` reaches into `_chains` at six sites, and `verdict` borrows the guarded class's `_expand` as a general utility, so a differently configured class would change how every path expands.
  `expand_user(path, home)` is the module-level expander; `GuardedLocations._expand` is gone rather than left as a second name for it.
- [x] Return findings from `PathPolicy.validate` and `verdict` rather than accumulating them on the instance.
  Deduplication substring-matches the accumulated message text, so rewording a message breaks it, and a query that mutates its object makes two identical calls differ in effect.
  Done in part, and the part left undone is deliberate.
  A `Restriction` record replaces the message text, so deduplication is set membership and two identical calls now have equal effect.
  `verdict` still records rather than returns: it returns a class string at more than fifty call sites, and threading a second return value through all of them costs more than the mutation does.
  `validate` computes its grant restrictions rather than reading what earlier queries left behind, which is what moved the construction-time check out of `__init__`.
- [x] Resolve enforcement-floor membership per query instead of enumerating at construction, and cache `_project_floor` on `cwd`.
  Both results are pure functions of the filesystem and of `cwd`, neither of which changes within a process.
  The floor is a `cached_property` built on first use instead of per query, which is the same saving with none of the matching rewritten.
  A write builds it once; a read builds it only where the path does not resolve and the verdict falls through to the text check over `guarded`, which carries the floor's declarations.
  The measurement above gives the cost of each route.
  This moves when a scan failure surfaces, from import to the first call that needs the floor.
  A mutating call still asks or refuses through `internal_error`; a read proceeds either way, silently where it never reached the floor and with the failure reported where it did.
  `test_a_failing_floor_scan_does_not_gate_a_read` states that over both routes.
- [x] Collapse `POLICY`, `GUARDED`, `CREDENTIALS`, and `MANIFEST_ERROR` into one binding once construction is lazy.
  `tests/hermetic.py` carries a comment warning that a test setting some of the four judges against the deployed manifest for the rest and still passes; that warning is the workaround for this shape.
  `guarded_paths.load_policy` returns a `PathPolicy` either way, carrying the load failure as `.error`, so `install_policy` sets one name and the warning is gone.
- [x] Extract the Bash command classifier from `block-hook-tampering.py` into its own module, and have it return the stopping reason with the class.
  `_stopping_syntax` re-runs `_defines_function`, `_program_text`, and `_builder_segment` over segments the classifier already processed, so a drift between the two orderings names a reason that was not the reason.
  This is the shape `OneLexerForEveryHook` gave the lexer, applied to the classifier above it.
  `hooks/bash_commands.py` holds the reading; `block-hook-tampering.py` holds the policy and dropped from 772 to 406 lines.
  `read()` classifies once and `Reading.stopping_syntax()` reports from that pass, so the hook lexes a Bash command once where it lexed three times.
  `_builder_segment` and `_piped_programs` now share `_reads_stdin_program` instead of one re-deriving the other through the pipe-fed rule, which they disagreed about.
- [x] Parse `apply_patch` headers in one module rather than three.
  The regex and extractor are duplicated verbatim across `block-hook-tampering.py`, `block-sensitive-paths.py`, and `block-secrets.py`.
  `hooks/apply_patch.py` holds it.

Do not merge `block-sensitive-paths.py`'s `READ_CMDS` into `bash_commands.READ_ONLY_UTILITIES`.
They answer opposite questions: `READ_CMDS` asks which words a command reads, and includes `cp` so a credential named as a source operand blocks; `READ_ONLY_UTILITIES` asks whether a segment is provably read-only, and excludes `cp` because it writes.

`_word_candidates` and `bash_commands.word_paths` were listed here as duplicates, and they are not.
`word_paths` returns the paths a word names, filtered by kind and resolved against `cwd`, because the tamper hook judges each one against a declaration.
`_word_candidates` yields every spelling a word could carry, unfiltered and unresolved, because the sensitive-path hook matches name patterns and would rather test a string that is not a path than miss one that is.
Merging them would make one of the two hooks wrong.

## Deferred and closing

- [x] Deferred: a generic rule for discovering hook directories that joins the enforcement floor without a code-held list or a repository-specific glob, so onboarding an agent does not mean editing `HOOK_DIRECTORIES`.
  Closed as deferred on 2026-10-06: no rule is known that finds hook directories without depending on this repository's layout.
  The configuration assessment reports a registered hook whose directory the list leaves out (`security-posture-alignment` `RegisteredHooksLieInTheEnforcementFloor`), so a forgotten entry is found.

- [x] Deferred: directory-change tracking in the lexer, as `DirectoryChangeTrackingIsDeferred` designs it.
  Taken up in `security-posture-alignment` on 2026-10-04; `shell-lexing` `EachSegmentCarriesTheDirectoriesItMayRunIn` states the rule, and `DirectoryChangeTrackingIsDeferred` records where it differs from the design.
  Reactivate when the absolute-path instruction proves to cost more prompts than the rule would cost to hold.

- [x] Closing: reevaluate whether floor conformance should broaden back over the guarded class.
  Expected to be hard: the harness sandboxes differ in what they can express, the harness hooks differ in whether they can ask, and the shared hooks differ in what they support, so a single floor statement has no single surface to check.
  Closed as no on 2026-10-06, after a read-only measurement of each agent's own layer; `design.md` `FloorConformanceCoversTheBlockClass` records the findings and the reason.

- [x] Closing: evaluate adopting `shell_words` in `block-destructive-ops.py` and `block-secrets.py`, each of which matches patterns over the command text and would gain the same brace and ANSI-C resolution.
  Evaluated on 2026-10-05.
  `block-destructive-ops.py` allows `\r\m -r <dir>` and `$'\x72m' -r <dir>`, which the lexer resolves, so it adopts the lexer in `single-command-rule-engine`.
  `block-secrets.py` does not: its checks are about network destinations, credential stores, and literal secrets in the text, which the lexer does not judge.
  The lexer leaves brace expansions unresolved, so that gain does not exist.

- [x] Closing: evaluate splitting the manifest into a global policy file and a user file, `guarded-paths.policy.toml` and `guarded-paths.local.toml`, so the default stance ships with the module and a user file carries only their additions and grants.
  Raised by the user on 2026-09-17 while deciding how the enforcement floor is known.
  The floor question is settled separately: the floor is derived, not declared, so this split is about authoring ergonomics and upgrade behavior rather than about protection.
  Decided 2026-10-09: the manifest stays one file, recorded in `design.md` as `TheManifestStaysOneFile`.

- [x] Closing: the Pi migration in `security-posture-alignment` replaces the Pi reader updated here; note there that `manifest.ts` is deleted with the rest of the port.
  Recorded there: its tool-vocabulary task states that `manifest.ts` is deleted with the port.

- [x] Closing: spike a Rust port of the hooks as one binary, and decide it from a measurement taken then rather than from this one.
  Out of scope: the user deferred the Rust port on 2026-10-05, so this change does not spike it.
  The measurement below stays as the starting point for a later change.
  Measured here, warm, best of five: `block-dangerous-bash.sh` 150 ms, `block-sensitive-paths.py` 120 ms, `block-hook-tampering.py` 110 ms, `bash-command-validator.sh` 90 ms, `block-destructive-ops.py` 40 ms. Seven hooks run for one Bash tool call, so the roughly 50 ms of interpreter and import startup inside each Python hook is paid five to seven times, and the two shell hooks are the most expensive of the set.
  One binary removes that startup and subsumes the shell hooks, which a Python rewrite would not.
  `brush-parser` and `brush-core` supply word expansion, which `TheLexerIsWrittenRatherThanTakenFromAPackage` records as having no Python supplier.

  What the spike has to establish:

  - A command substitution can be refused from the `brush-parser` AST before anything is expanded.
    The crate expands one by default, so the refusal that `_resolve` gets from recognizing nothing has to be written out explicitly.
  - `_fragment_pattern` can drop `(?<=:-)`, because the `regex` crate has no lookaround.
    It gives linear-time matching in exchange, which the current patterns do not have.
  - An out-of-store symlink to the build output keeps the present edit loop, with a session-start warning where the binary is older than its source.
    A compile error leaves the previous binary in place, where a Python syntax error is live on save; a forgotten build is silently stale, which is the new failure to guard.
  - The suites regenerate from the scenarios, `shellprobe` shells out to bash and carries over, and `hegeltest` or `proptest` replaces `hypothesis`.
