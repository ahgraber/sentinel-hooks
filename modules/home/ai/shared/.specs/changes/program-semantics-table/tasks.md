# Tasks: program-semantics-table

## 1. Record the verdicts before anything moves

- [ ] 1.1 Write `tests/program-reading-cases.json`: every probe form in `proposal.md` and the review findings, each with the program, effects, completeness, and per-hook verdict expected after the change; mark each case that fails today as expected-to-fail.
- [ ] 1.2 Add `tests/test_program_reading_cases.py`, which runs every case against today's hooks and fails if an expected-to-fail case passes or any other case fails.
- [ ] 1.3 Capture today's verdict for every case in `guarded-path-cases.json`, `sensitive-path-cases.json`, and `program-reading-cases.json` on every hook into `tests/pre-catalog-verdicts.json`, with a script that regenerates it from a named commit.
- [ ] 1.4 List the approved loosenings in `tests/approved-loosenings.json`, one case each: a read under `nice`, `caffeinate`, and `env`, and an admitted utility spelled with a trusted-directory path.
  List spec corrections apart in `tests/spec-corrections.json`, each with the baseline requirement it restores, starting with `bash -e <existing exec-through script>`.
  Add no loosening without a dated approval in the proposal's Resolved Questions; a looser verdict found later that no baseline requirement supports goes to the user first.
- [ ] 1.4a Add `bash -e <existing exec-through script>` and `python3 -e <code>` to `tests/program-reading-cases.json` with today's verdicts, so the effect of correcting their parse is visible.
- [ ] 1.5 Benchmark the full hook path of the four Bash-reading hooks over the verdict cases on today's code and record the timings in `tests/benchmarks/pre-catalog.json`.

## 2. Inventory the programs agents run

- [ ] 2.1 Move `._scratch/program-semantics-pilot/inventory.py` to `scripts/program-inventory.py` under the repository's script conventions, with a `just` recipe, extended to record shell functions and aliases the agent's shell defines.
- [ ] 2.2 Run the inventory for each agent on each host the hooks run on and commit the results under `modules/home/ai/shared/.specs/changes/program-semantics-table/inventory/`.
- [ ] 2.3 Write the declared coverage list `hooks/programs/_coverage.toml`: today's recognized programs (destroyers, writers, store commands, privilege tools, admitted readers, wrappers, interpreters, launchers) and the privilege tools, wrappers, launchers, interpreters, and shells this change names, adding each wrapper, launcher, and shell in Tracekit's tables that the list lacks (`draft-table.md`, Prior art).

## 3. Catalog schema and loader

- [ ] 3.1 Write `hooks/programs/SCHEMA.md` from `draft-table.md`, with the changes from the pilot and the review, as the reference audit workers and reviewers read.
- [ ] 3.2 Implement `hooks/program_catalog.py`: `entry(name)` returning an entry, an `InvalidEntry`, or `None`, reading from disk per call, following `_aliases.toml` and shared grammars with a cycle check; and `validate_all()`.
- [ ] 3.3 Test the loader: a valid entry; a file that does not parse; an undefined field or effect; a duplicate name across entries; a duplicate option spelling for one implementation; an alias to a missing entry; a shared-grammar cycle; a missing verification record; a `long-prefixes` field, which the validator rejects; an entry repaired between two calls (`AnInvalidEntryDisablesOnlyItsProgram`, `TheCatalogIsCheckedAgainstItsUsers`).
- [ ] 3.4 Test that an invalid `tar` entry leaves `cat` readable and makes `gtar` invalid (`OneEntryIsInvalid`, `AnAliasReachesAnInvalidEntry`).

## 4. First audit batch

- [ ] 4.1 Write the second audit brief from `._scratch/program-semantics-pilot/BRIEF.md` with the verifiers' recommended changes: ask what each subcommand does with no operands, name the operand positions a retype affects, check `-h` against the option string, build the environment-variable list line by line, record per-implementation parser probes, run `--version` first, and record sources and the verification result in each entry.
- [ ] 4.2 Audit every program in `_coverage.toml` that today's hooks recognize, with haiku workers and one sonnet verification pass per batch; correct every `effect-under` finding before the entry is committed.
- [ ] 4.3 Audit `uv`, `uvx`, `ruff`, `pre-commit`, `git`, `op`, `kubectl`, and the privilege tools `sudo`, `su`, `doas`, `pkexec`, `run0`, `runuser`, `setpriv`, `chroot`, `systemd-run`, and macOS `osascript`.
- [ ] 4.4 Add `tests/test_catalog_coverage.py`: every program in `_coverage.toml` has a valid entry, and every program and refused option in `tests/pre-catalog-verdicts.json` sources is stated (`NoRecognitionIsLostInTheMove`, `AProgramRecognizedBeforeTheMove`).

## 5. The walker

- [ ] 5.1 Implement the `Reading`, `Effect`, and context types in `bash_commands.py`.
- [ ] 5.1a Make `bash_commands.read` contain its own faults: an exception raised while loading an entry or walking a segment ends that segment's recognition and is recorded as its reason; test `AnEntryOfTheWrongShape`, `AFaultWhileWalking` with an injected fault, and `ArbitraryCommandText` as a property test over random command text (`ReadingACommandNeverFails`).
- [ ] 5.2 Implement option parsing over an entry: clusters, value letters, attached values, `--`, numeric options, single-dash long options, dashless clusters, and `options-before-operands` per implementation.
- [ ] 5.3 Test option parsing against the catalog scenarios: `AValueLetterInsideACluster`, `AWordAfterTheEndOfOptions`, `AnUnlistedOption`, `AnAbbreviatedLongOption`.
- [ ] 5.4 Implement per-implementation reading with documented rejection and the union of accepting implementations; test `TwoImplementationsReadOneCommand`, `OneImplementationRejectsTheCommand`, and `OneImplementationIsUnsettled`.
- [ ] 5.5 Implement modes, subcommands, retypes, implicit effects, and effect sets; test `CodeAndAWriteInOneSegment`, `AModeSelectsTheFileDirection`, `AnEffectNoWordNames`, `AnInterpreterGivenNoScript`, and `RepositoryStateIsNotADirectoryChange`.
- [ ] 5.6 Implement nested reading through `command`, `shell-text`, and launchers with context (directory, expanding shell, environment) and the nesting bound; test `WrappersInAnyOrder`, `APathSpelledProgram`, `ShellTextInsideAWrapper`, `NestingBeyondTheBound`, `AGlobExpandedBeforeADirectoryChange`, `AGlobExpandedInsideANestedShell`, `AnOuterRedirectionBesideAChildOperand`, `ALauncherOfACommand`, `AnUncatalogedChildOfAnInstaller`, and `ProgramTextWithoutAFile`.
- [ ] 5.7 Implement launchers that generate arguments; test `ALauncherBuildsItsArguments`, `AKnownChildBeforeGeneratedWords`, `AReplacementInsideAnArgument` with a replacement holding `..`, `AChildRunInTheDirectoryItFinds`, and `AFixedTargetBesideGeneratedWords`.
- [ ] 5.8 Seed the table of pre-catalog effects in `bash_commands.py`, held apart from the catalog, from `_OPERAND_EXTRACTORS`, the sensitive-path write forms, the privilege tools, and the store commands; test `AnInvalidEntryForAProgramRecognizedToday`.
- [ ] 5.8a Implement the `env -S` split-string decoder from the GNU and FreeBSD manuals (quotes, `\_`, the other escapes, `${NAME}` as unknown), and test it against a harmless argument recorder (`/usr/bin/env -S '/bin/echo …'`) for each escape, never running a privilege tool.
- [ ] 5.8b Implement the stop rule with `possible` effects for the stopped program, later named programs, and names split out of command strings as the union of the wrapper's own grammar, Bash lexing, and program-name runs; test `AnExpansionInTheOperands`, `AnUnsplitCommandLine`, `EffectsFoundBeforeTheEnd`, `TheStoppedProgramItself`, `AQuotedNameInAnUnsplitCommandLine`, `ADangerousProgramAfterTheStop`, and `AProgramWithNoEntry`.
- [ ] 5.9 Mark each segment that changes the shell's state for later segments: a segment that is only an assignment, and the builtins `export`, `declare`, `typeset`, `local`, `readonly`, `unset`, `set`, `shopt`, `enable`, `hash`, `alias`, `source`, `.`, `eval`, `read`, `printf -v`, `mapfile`, `readarray`, and a function definition; test each form, and test that `cd` is not marked.
- [ ] 5.10 Test that the `option` kind no longer decides a removed file (`shell-lexing` `AnOperandSpelledLikeAnOption`).
- [ ] 5.11 Benchmark the walker over the verdict cases and compare with `tests/benchmarks/pre-catalog.json`.

## 6. Read admission

- [ ] 6.1 Write `hooks/read-admission.toml` from `READ_ONLY_UTILITIES`, `WRITE_OPTIONS`, `REQUIRED_FIRST_OPTION`, and `READ_WRAPPERS`, adding `nice`, `caffeinate`, and `env` with its condition, and the trusted directories.
- [ ] 6.2 Add `tests/test_read_admission_against_catalog.py`: every effect beyond a read and a plain value belongs to a refused option, and every hidden input that supplies options, runs a program, or names files is neutralized (`TheCatalogShowsAnUncoveredEffect`, `AHiddenInputThatChangesOnlyPresentation`, `ARefusedOptionRecognizedBeforeTheMove`).
- [ ] 6.3 Keep the test that runs each admitted utility against a second file operand (`UtilityWritesAFileNamedAsAnOperand`).

## 7. Tamper hook

- [ ] 7.1 Move read recognition in `block-hook-tampering.py` onto the reading and `read-admission.toml`, including the spelling rule for utilities and wrappers and the rule that a shell-state change ends read and run recognition for every later segment.
- [ ] 7.2 Test the `UnrecognizedCommandsAreGated` scenarios, old and new: `ATransparentWrapperKeepsAReadARead`, `AWrapperThatWritesEndsTheRead`, `AnAssignmentNamesAHiddenInput`, `AnAssignmentLoadsCode`, `AReadThroughNestedWrappers`, `AStateChangeBeforeARead`, `AStateChangeAfterARead`, and `AWrapperAtAnUntrustedPath`.
- [ ] 7.3 Test the `ReadClassifierAdmitsOnlySelfDescribingUtilities` scenarios, old and new: `ARefusedOptionUnderAnotherSpelling`, `AUtilityAtAnUntrustedPath`, `AUtilityAtATrustedPath`, and `AUtilityDirectlyInTheStore`.
- [ ] 7.4 Move the ancestor gate onto delete, write, and permission effects, `known` and `possible`, and refuse on every agent where the ancestor holds an enforcement-floor location.
- [ ] 7.4a Add the floor backstop that does not read the catalog: `rm`, `rmdir`, `mv`, `shred`, `trash`, `unlink`, and `find` with `-delete` or an execution action, by base name through any wrapper the text shows, naming a path that encloses a floor location, are refused; an unresolved operand that could enclose one is refused.
- [ ] 7.5 Test the `ADestructiveOperationOnAnAncestorReachesTheUser` scenarios, old and new: `AnAncestorRemovedThroughWrappers`, `AnAncestorAfterTheEndOfOptions`, `AnAncestorWithAnInvalidEntry`, `AnAncestorWithAnUnlistedOption`, `AnAncestorBehindAWrapperTheReadingStoppedAt`, `AnAncestorRemovedByAnUncatalogedProgram`, `AnAncestorOfTheFloorIsRemoved` on each agent's encoding, `AnAncestorOfOnlyGuardedLocations`, `TheFloorWithAWrongCatalogEntry`, `AnUnresolvedOperandThatMayHoldTheFloor`, `AFileOnTheFloorIsEdited`, `AnAncestorWithAnInvalidPermissionEntry`, `AShownTargetOfAGeneratedCommand`, and `ATargetOnlyInTheInput`.

## 8. Sensitive-path hook

- [ ] 8.1 Move `_write_words` in `block-sensitive-paths.py` onto the reading's write, delete, and permission effects, keeping the by-name forms beside them.
- [ ] 8.2 Test `CopyWithATargetDirectoryOption`, `InPlaceEditUnderAWrapper`, the baseline scenarios, and a write target after a stopped reading.
- [ ] 8.3 Test that `BlockBashReadFromZeroAccessPath` verdicts are unchanged over `sensitive-path-cases.json`.

## 9. Leak hook

- [ ] 9.0 Copy the helpers the leak hook's store recognizer calls (`invoked`, `program_text`, `watch_script`, `launched_arguments`, and their dependencies) into `block-leaks.py` as its fallback recognizer, importing neither the walker nor the catalog; test the copy against today's store cases with the catalog absent.
- [ ] 9.1 Move store-command detection in `block-leaks.py` onto the reading, keeping the lexer-based recognizer as the fallback for an incomplete reading or an invalid `op` or `kubectl` entry.
- [ ] 9.2 Test the `RefuseUserOnlyCredentialStores` scenarios, old and new: `StoreReadUnderAWrapper`, `GlobalOptionsBeforeTheSubcommand`, `StoreCommandWithAnInvalidEntry`, `ResourceListWithAnInvalidEntry`, `DecodedSpellingWithAnInvalidEntry`, and `StoreReadBuiltByALauncher`.

## 10. Privilege refusal

- [ ] 10.1 Add the privilege check to `block-destructive-ops.py` over the reading, `known` and `possible`, separate from its pattern table.
- [ ] 10.2 Test the `BlockPrivilegeEscalation` scenarios: `SudoCommand`, `PrivilegeUnderAWrapper`, `PrivilegeByPath`, `AnotherPrivilegeTool`, `PrivilegeInsideShellText`, `PrivilegeInAnUnsplitCommandLine`, `PrivilegeQuotedInAnUnsplitCommandLine`, `PrivilegeSplitByTheWrappersOwnEscape`, `PrivilegeBehindAnInvalidWrapperEntry`, `PrivilegeBeyondTheNestingBound`, and `ALookup`.
- [ ] 10.3 Test that every command `block-dangerous-bash.sh` refuses today is still refused.

## 10a. Retire the old helpers

- [ ] 10a.1 Confirm that no hook, and no landed form of `single-command-rule-engine`, calls `invocation`, `invoked`, `_strip_privilege`, `_su_code`, `_privileged_shell`, `_inline_code`, `launched_arguments`, `watch_script`, `_after_options`, `_operands`, `_option_value`, or `_OPERAND_EXTRACTORS` in `bash_commands.py`; where the rule engine landed first and still calls one, move that call onto the reading first.
- [ ] 10a.2 Delete the helpers listed in 10a.1 from `bash_commands.py`, and run the shared and Pi suites.

## 11. Reports

- [ ] 11.1 Add catalog validation and the uncataloged count and list file to `session-policy-checks.py`; test `ValidCatalog`, `InvalidCatalogEntry`, `InvalidAliasIndex`, and `UncatalogedProgramsOnThePath`.
- [ ] 11.2 Emit the at-use warning for an uncataloged program or an invalid entry on an allowed call; test `AnUncatalogedProgramOnAWarningAgent`, `AnUncatalogedProgramOnAnAgentWithoutWarnings`, and `AnEntryCorruptedDuringASession` on each agent's encoding.
- [ ] 11.3 Test `AnInvalidEntryInARefusal` on each agent's encoding: the reason of an ask and of a refusal names the invalid entry and its defect, for an invalid wrapper entry and for an invalid child entry, kept apart from the allowed-call warning test.

## 12. Checks and parity

- [ ] 12.1 Add the catalog validation and coverage tests to the flake checks (`AnEntryWithAnUndefinedEffect`, `AnAdmittedProgramWithoutAnEntry`, `SharedGrammarsThatFormACycle`, `AnEntryWithoutAVerificationRecord`).
- [ ] 12.2 Add a cross-validation test, marked `crossvalidation`, that compares each entry's option spellings with the installed binary's `--help` per implementation present on the host.
- [ ] 12.3 Run every verdict table through each agent's adapter (`cross-agent-capability-parity` `VerdictSurfacesAgree`) and the Pi suite.
- [ ] 12.4 Run `tests/pre-catalog-verdicts.json` against the new hooks and confirm every verdict is the recorded one or stricter, except the cases in `tests/approved-loosenings.json` and `tests/spec-corrections.json` (`AVerdictCaseFromBeforeTheMove`, `ASpecCorrection`).
- [ ] 12.5 Mark the expected-to-fail cases in `program-reading-cases.json` as expected to pass, and run the shared and Pi suites.
- [ ] 12.6 Add a test that builds an agent-style hook directory the way `hooks.nix` does, one symlink per top-level entry into a copy of `hooks/`, leaves out a new data file, and confirms each Bash-reading hook still imports and finds `hooks/programs/` and `read-admission.toml` relative to its module.
- [ ] 12.7 Add a flake check that imports each hook module under the flake's Python, so an import failure in `block-destructive-ops.py` fails the check instead of every Bash call.
- [ ] 12.8 Have the user run the home-manager switch once the new top-level entries exist, and confirm each agent's hook directory lists `program_catalog.py`, `programs/`, and `read-admission.toml`; the agent sandbox cannot run that activation.

## 13. Remaining audit and documentation

- [ ] 13.1 Audit the rest of the declared coverage in batches, each with its verification pass.
- [ ] 13.2 Update the module's `AGENTS.md`: the catalog's place in the layout, the rule that program grammar is declared in `hooks/programs/` and admission in `read-admission.toml`, and the `PATH` limit.
