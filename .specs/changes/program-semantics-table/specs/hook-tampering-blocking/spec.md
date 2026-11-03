# Delta for Hook Tampering Blocking

## MODIFIED Requirements

### Requirement: UnrecognizedCommandsAreGated

> Previously: the classifier identified the program through a fixed set of wrappers, and any wrapper outside that set stopped recognition; which wrappers kept a read a read was a separate set; a segment that changed the shell's state did not keep a later segment from being recognized, so `source <file>; cat <guarded>` proceeded.

Where a Bash command names guarded locations, the system SHALL classify the command before gating it: a command recognized as a read SHALL proceed, a command recognized as a run of a program held in an exec-through location SHALL proceed, and any other command SHALL be gated with a reason that names the syntax that stopped recognition and, per `GateResponse`, the rewrite that would proceed where one exists: the admitted commands for a stop on the program, and absolute paths for a stop on relative paths.

One path in a block location SHALL refuse the whole command, whatever the rest of it does.
One path outside every exec-through location SHALL gate a run, whatever the rest of it does.

Recognition SHALL rest on the command text alone, read as `shell-lexing` requires every path hook to read it, and read through the program catalog as `program-catalog` requires.
A command whose effect that text does not show SHALL NOT be recognized, because the classifier cannot judge what it cannot see: an unresolvable word, an assignment that picks which binary runs or loads code into it, program text handed to an interpreter, a relative path after a change of directory, or a reading that `program-catalog` `AnIncompleteReadingEndsRecognition` ends.

A redirection SHALL NOT keep a command from being recognized; its target SHALL be judged by its direction.
An input target is judged as a read, and an output or read-write target as a write, so a recognized read that writes its output into a guarded location meets the write gate for that location.
A redirection that duplicates or closes a descriptor names no file and is not judged.
A segment that does nothing but redirect, such as `> file`, `: > file`, or `exec 3> file`, is judged by its targets alone, so it meets the write gate as the write it is.
The command text names every target, so a redirection hides nothing the classifier needs.

A command with any segment whose program executes text it receives SHALL NOT be recognized, whatever its other segments do: `xargs`, `eval`, an interpreter given inline code, or a shell reading its standard input.
The classifier SHALL identify the program through every wrapper the catalog reads through, in any order and nesting.
A pipe-fed program outside the recognized read utilities SHALL be treated as a builder, including an interpreter or an unknown wrapper.
A wrapper around a recognized read SHALL preserve read recognition only when the admitted list names it as transparent, its own words carry no effect but plain values, and it is spelled as `ReadClassifierAdmitsOnlySelfDescribingUtilities` requires an admitted utility to be spelled.
The transparent wrappers are `time`, `timeout`, `stdbuf`, `setsid`, `nice`, and `caffeinate`.
`env` is transparent only when it carries no option and no assignment it receives, or that precedes it, names a hidden input of the program it runs.
`nohup` is not transparent, because it writes `nohup.out`.
A read segment that names a guarded path and pipes into such a program hands that path to a command the classifier never sees, so the read is not the whole of what the command does.

A segment that changes the shell's state for the segments after it SHALL keep every later segment in the same shell from being recognized as a read or a run: a segment that is only an assignment, and a builtin that sets, exports, or unsets a variable, sets a shell option, loads a builtin, binds a name to a program path, defines an alias, or runs a file or text in the current shell.
The classifier does not judge which variable or name changed, because each change can redirect what a later admitted name runs or how it behaves, and a list of names misses the one it does not hold.
A change of directory is judged by the paths it moves, as `shell-lexing` `EachSegmentCarriesTheDirectoriesItMayRunIn` requires, and is not such a change.

The reason is what tells an agent what to rewrite.
A refusal that names neither the syntax that stopped recognition nor a rewrite that proceeds, where one exists, leaves an agent whose gate is a refusal with nothing to do but try another route, which is the behavior every refusal in this module instructs against.
A command whose every segment is recognized, stopped only by a write to a guarded location, is gated as that write, and its reason names the write rather than a syntax.
A command with any unrecognized segment keeps the recognition reason, because it may do more than that write.

Serves: a-wrapper-read-once-holds-everywhere, unknown-reads-as-dangerous

#### Scenario: RecognizedRead

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command is a recognized read
- **THEN** the hook exits 0

#### Scenario: RecognizedRun

- **GIVEN** a Bash tool call names exec-through locations alone
- **WHEN** the command runs a program held there
- **THEN** the hook exits 0

#### Scenario: EffectHiddenFromTheCommandText

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command carries an unresolvable word or an assignment that picks which binary runs or program text handed to an interpreter
- **THEN** the gate applies

#### Scenario: RedirectionElsewhereLeavesAReadRecognized

- **GIVEN** a Bash tool call is a recognized read of a guarded location
- **WHEN** it redirects its output to a location the policy permits writing, or a descriptor, or reads the guarded location as an input redirection target
- **THEN** the hook exits 0

#### Scenario: RedirectionIntoAGuardedLocationIsAWrite

- **GIVEN** a Bash tool call is a recognized read or run
- **WHEN** an output or read-write redirection target is a guarded location
- **THEN** the gate applies, with the reason for a write to that location

#### Scenario: GitConfigurationNamingAGuardedPath

- **GIVEN** a Bash tool call sets an executable Git configuration value that names a guarded path, such as `git -c core.pager='cat ~/base/private' log`
- **WHEN** the command is judged
- **THEN** the path inside the value is found and the gate applies

#### Scenario: TextPipedIntoAShellNamingAGuardedPath

- **GIVEN** a Bash tool call pipes text that names a guarded path into a shell, such as `echo 'rm ~/.claude/settings.json' | sh`
- **WHEN** the command is judged
- **THEN** the path inside the text is found and the gate applies

#### Scenario: InlineProgramNamingAGuardedPath

- **GIVEN** a Bash tool call gives an interpreter inline code that names a guarded path, such as `bash -c 'rm ~/.claude/settings.json'`
- **WHEN** the command is judged
- **THEN** the gate applies, because the path inside the program text is found and the command is not recognized

#### Scenario: GuardedPathPipedIntoACommandBuilder

- **GIVEN** a Bash tool call whose read segment names a guarded path and pipes into `xargs`, such as `echo ~/.claude/settings.json | xargs rm`
- **WHEN** the command is judged
- **THEN** the gate applies, though the builder segment names nothing guarded

#### Scenario: RelativePathAfterADirectoryChange

- **GIVEN** a Bash tool call changes directory and then reads a guarded location by a relative path
- **WHEN** the command is judged
- **THEN** the gate applies, and the reason instructs the agent to name the path absolutely

#### Scenario: ReasonNamesTheAcceptedForms

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command is neither a recognized read nor a recognized run, because of the program it runs
- **THEN** the decision is `Ask`, and the reason names the read utilities and the interpreters that would have proceeded

#### Scenario: ReasonNamesTheSyntaxThatStoppedRecognition

- **GIVEN** a Bash tool call that would be a recognized read but for a newline or a substitution or a brace expansion
- **WHEN** the command is gated
- **THEN** the reason names that syntax

#### Scenario: RunMixedWithAGuardedPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs a program in an exec-through location and names a guarded path outside every exec-through location
- **THEN** the gate applies to the whole command

#### Scenario: ReadMixedWithABlockPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is a recognized read naming a guarded path and a block path
- **THEN** the decision is `Block`

#### Scenario: ATransparentWrapperKeepsAReadARead

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command is a recognized read under `nice -n 5` or `caffeinate -i`
- **THEN** the hook exits 0

#### Scenario: AWrapperThatWritesEndsTheRead

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command is a recognized read under `nohup`
- **THEN** the gate applies

#### Scenario: AnAssignmentNamesAHiddenInput

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** an admitted read runs under `env`, or after a leading assignment, that sets a hidden input of that utility
- **THEN** the gate applies

#### Scenario: AnAssignmentLoadsCode

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** an admitted read runs after an assignment that loads code into the program it runs, such as `LD_PRELOAD` or `DYLD_INSERT_LIBRARIES`
- **THEN** the gate applies

#### Scenario: AReadThroughNestedWrappers

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command is a recognized read under `time` inside `timeout 5`
- **THEN** the hook exits 0

#### Scenario: AStateChangeBeforeARead

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** a recognized read follows, in the same command, `export NAME=value`, `PATH=/tmp/p`, `source <file>`, `hash -p <path> <name>`, `enable -f <file> <name>`, or `alias <name>=<text>`
- **THEN** the gate applies

#### Scenario: AStateChangeAfterARead

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** `export NAME=value` follows a recognized read in the same command
- **THEN** the hook exits 0

#### Scenario: AWrapperAtAnUntrustedPath

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** a recognized read runs under `/project/bin/timeout 5`
- **THEN** the gate applies

### Requirement: ReadClassifierAdmitsOnlySelfDescribingUtilities

> Previously: the admitted set listed utilities by name, with refused options and required options held beside it, and was not checked against a catalog; a utility or wrapper spelled with any path was not recognized, `/usr/bin/cat` included; outside sources were judged per utility, not stated in a catalog.

The read classifier SHALL admit a utility only when the command line decides what that utility does.

`UnrecognizedCommandsAreGated` gates every command the classifier does not recognize as a read.
This requirement says which utilities the classifier may recognize.

Some utilities take options from a configuration file or an environment variable.
Some run a helper program that the command does not name.
The classifier reads the command text and nothing else, and neither one appears there.
It reports the command as a read, and the command runs with no prompt.

This rule keeps the admitted set small.
It is also why each utility missing from the set is a decision and not an oversight.
A utility does not qualify because it only reads files.
It qualifies when its command line says so.

The admitted set SHALL list each utility with the options it refuses and the options that turn off its outside sources.
The utility's `program-catalog` entry SHALL show that those cover it: every effect the entry states beyond reading a file and a plain value SHALL belong to a refused option, and every hidden input that can supply options, run a program, or name a file the utility opens SHALL be turned off by a listed option or reachable only through a refused option.
A hidden input that changes only how the utility interprets or presents its data, such as the locale, does not bar admission.
A utility whose entry shows an effect or a hidden input the list does not cover SHALL NOT be admitted.
This holds the admitted set to the catalog without letting a catalog entry admit a utility on its own.

An admitted utility SHALL NOT write a file named as an operand.
An option that writes can be refused by name; an operand cannot, because the paths a command reads appear in the same position.
`uniq in out` and `xxd in out` each replace `out`, which is why neither is admitted.
This property SHALL be checked against the real utility rather than assumed, because it is what `hook-interface` `BlockAIGuidance` rests on when it offers the admitted set to a refused agent.

A utility MAY be admitted with named options refused.
This applies when those options are the only way the utility acts outside its command line, and when each one can be refused as a whole token.
A refused option SHALL also be refused with an attached value and as a letter inside a cluster.

A utility MAY also be admitted when one of its own options turns off the outside source.
The command SHALL then supply that option, and the command line decides what the utility does because the outside source is off.

The required option SHALL be the first argument.
An option that takes a value can come first and take the required option as its value.
The outside source stays on, and the required token is still in the command, so a check for the token alone would pass the command wrongly.

Both routes need the utility to match each option name exactly.
A utility that accepts an abbreviation, or the same name in another case, gives a refused option more than one spelling.
A check over whole tokens misses the spellings it does not list.

A utility SHALL be recognized as admitted only under its bare name or under a path in a trusted system directory: a directory only root can change, `/usr/bin`, `/bin`, `/run/current-system/sw/bin`, and `/etc/profiles/per-user/<user>/bin`.
A program at any other path need not be the utility its name suggests.
A directory the user owns, such as `~/.nix-profile/bin`, `~/.cargo/bin`, or `~/.local/bin`, is not trusted, because the agent runs as the user and can place a program there.
A path directly in the nix store is not trusted, because any build can place a program of any name there.

A bare name resolves through `PATH` when the command runs, and `PATH` can hold a directory the agent can write ahead of the trusted ones.
The classifier does not resolve a bare name, because the hook cannot see the shell's `PATH`, functions, or a program an earlier segment of the same command places.
A program the agent places and runs does what the command text does not show, under any name; the operating-system sandbox, not this classifier, bounds it.

Ripgrep is admitted under both routes: its options that run a program are refused, and `--no-config` must come first.

Serves: every-argument-has-a-stated-effect, unknown-reads-as-dangerous

#### Scenario: UtilityDeterminedByItsCommandLine

- **GIVEN** a utility whose behavior follows from its command line alone
- **WHEN** admission to the read classifier is considered
- **THEN** it may be admitted, with any option that writes or executes refused

#### Scenario: UtilityWritesAFileNamedAsAnOperand

- **GIVEN** a utility that writes a file named as an operand
- **WHEN** it is run against the admitted set with a second file operand
- **THEN** the operand is unchanged for every admitted utility, and the one that changes it is refused admission

#### Scenario: UtilityTakesDirectionFromTheEnvironment

- **GIVEN** a utility that reads options from a configuration file or an environment variable
- **WHEN** the utility has no option that turns that source off
- **THEN** it is refused, because refusing an option cannot turn the source off

#### Scenario: ExternalConfigurationIsDisabledByTheCommand

- **GIVEN** an admitted utility whose external configuration one of its own options disables
- **WHEN** a command supplies that option in the first argument position and does not name a refused option
- **THEN** the command is recognized as a read

#### Scenario: TheDisablingOptionIsAbsent

- **GIVEN** such a utility
- **WHEN** a command omits the required option
- **THEN** the command is not recognized as a read

#### Scenario: TheDisablingOptionIsNotFirst

- **GIVEN** such a utility
- **WHEN** a command supplies the required option in any position but the first
- **THEN** the command is not recognized as a read

#### Scenario: ARefusedOptionAccompaniesTheDisablingOption

- **GIVEN** such a utility
- **WHEN** a command supplies the required option first and also names an option that writes or executes
- **THEN** the command is not recognized as a read

#### Scenario: TheCatalogShowsAnUncoveredEffect

- **GIVEN** an admitted utility whose catalog entry states an option that runs a program
- **WHEN** the admitted list does not refuse that option
- **THEN** the checks fail and name the utility and the option

#### Scenario: ARefusedOptionUnderAnotherSpelling

- **GIVEN** an admitted utility with a refused option
- **WHEN** a command gives that option as an abbreviation, with an attached value, or inside a cluster
- **THEN** the command is not recognized as a read

#### Scenario: AUtilityAtAnUntrustedPath

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command runs an admitted utility's name at a path outside the trusted system directories, such as `/project/bin/cat`
- **THEN** the command is not recognized as a read

#### Scenario: AUtilityAtATrustedPath

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command runs an admitted utility as `/usr/bin/cat`
- **THEN** the command is recognized as a read

#### Scenario: AUtilityDirectlyInTheStore

- **GIVEN** a Bash tool call names guarded locations alone
- **WHEN** the command runs a program named `cat` by a path directly in the nix store
- **THEN** the command is not recognized as a read

#### Scenario: AHiddenInputThatChangesOnlyPresentation

- **GIVEN** an admitted utility whose catalog entry states a locale variable as a hidden input that changes only presentation
- **WHEN** admission is checked
- **THEN** the locale variable does not bar admission

### Requirement: ADestructiveOperationOnAnAncestorReachesTheUser

> Previously: the gate knew the operation from a fixed list of programs read through one privilege wrapper and one execution wrapper, so a deeper or reordered wrapper, or an operand after `--`, passed; every ancestor, the enforcement floor's included, was asked about; a command `xargs` built passed even for a target its text shows.

The system SHALL gate an operation that removes, renames, or replaces a directory holding a declared location, or changes its permissions, owner, or attributes.

A declaration names a directory and protects what is inside it.
It does not protect the path to it, so `rm -rf ~/.pi` takes away the declared `~/.pi/agent/` while no word equals or falls inside any declaration.
No other layer closes this: guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, which means the permission layer permits the write by design.

The gate covers those operations alone.
Reading, searching, and creating files beneath an ancestor are ordinary work and SHALL stay unprompted.
Gating every command naming a prefix of a declaration reaches the home directory and the repository root.

A removal, a rename, or a replacement is a write under `guarded-path-declarations` `PrecedenceIsOneRule`; this gate reaches the ancestor that rule finds no declaration for.

An ancestor carries no declaration fragment, so it is found by resolving the path rather than by matching text.
A relative spelling resolves against the working directory the tool call supplies, moved by any earlier `cd` in the command and by any directory change a wrapper makes.
Where no directory is supplied, or a `cd` names one the hook cannot resolve, the word is unresolvable, per `path-matching` `TextMatchingIsForTextThatMayHoldNoPath`.
The system SHALL refuse a removal, rename, or replacement of such a word on every agent, with the absolute-path instruction of `hook-interface` `BlockAIGuidance`.
It cannot be judged by its text: a `*` in a declaration matches almost any word, so judging its shape would refuse ordinary commands.
It is not put to the user either, because the user has no more to place it by than the hook.
The same command with the path written absolutely can be judged.

The gate SHALL know the operation from the delete, write, and permission effects of the reading `program-catalog` gives, through every wrapper and for every cataloged program.
Where a segment's reading ends, the gate SHALL judge every path the segment names as a possible target of each program the segment may run, as `program-catalog` `AnIncompleteReadingEndsRecognition` counts them, whose entry is invalid or states a delete, write, or permission effect anywhere in its grammar, so a stale or broken entry, or a wrapper the reading stopped at, produces a gate and never a pass.
A program the catalog does not list passes on an ancestor, and is reported as `program-catalog` `UncatalogedProgramsAreReported` requires.
So does a branch switch, which changes every tracked file.
A command assembled at run time, such as one `xargs` builds, passes only for the targets that come from its input; a program and a target the command text shows, such as `xargs -a <file> rm -rf <dir>`, SHALL be judged as any other.

Where the directory holds an enforcement-floor location, the system SHALL refuse the operation on every agent, with a reason that tells the user to run the command in their own terminal, instead of asking.
Every agent runs its hooks through links into the repository, so removing the hook sources turns the guardrails off for every agent at once, and an ask is what a fatigued user approves.
A directory that holds only guarded locations is asked about, with a reason that names the declared locations the operation would remove; editing a single file on the floor stays an ask.

The floor refusal SHALL NOT depend on the program catalog alone.
A segment that invokes `rm`, `rmdir`, `mv`, `shred`, `trash`, `unlink`, or `find` with `-delete` or an execution action, by base name and through any wrapper the text shows, and that names a path enclosing an enforcement-floor location, SHALL be refused whatever the catalog reading holds, so a valid but wrong entry cannot remove the refusal.
An operand of such a segment that cannot be resolved to a definite path, where the floor location could lie beneath it, SHALL be refused on every agent rather than asked about.

The floor refusal closes the direct removal of the hook sources.
It does not cover a branch switch or a reset to a commit without them, which the command text cannot show.

Serves: a-wrapper-read-once-holds-everywhere, every-argument-has-a-stated-effect

#### Scenario: AnAncestorIsRemoved

- **GIVEN** a command that removes a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies, though the command names no declaration

#### Scenario: AnAncestorIsReplaced

- **GIVEN** a command that renames a directory over such a directory, or copies over it
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: AnAncestorsPermissionsChange

- **GIVEN** a command that changes the mode, owner, or attributes of a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: AnAncestorIsReachedThroughACd

- **GIVEN** a command that changes directory and then removes a relative path that resolves to a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: OrdinaryWorkBeneathAnAncestor

- **GIVEN** a command that reads, searches, or creates a file beneath such a directory
- **WHEN** the command is intercepted
- **THEN** the hook exits 0

#### Scenario: ASiblingNamedLikeAnAncestor

- **GIVEN** a directory whose name begins with an ancestor's name but is not that directory
- **WHEN** a command removes it
- **THEN** the hook exits 0

#### Scenario: ARelativeOperandWithNoWorkingDirectory

- **GIVEN** a tool call that supplies no working directory
- **WHEN** its command removes, renames, or replaces a relative path
- **THEN** the hook refuses it on every agent with the absolute-path instruction

#### Scenario: AnAbsoluteOperandWithNoWorkingDirectory

- **GIVEN** a tool call that supplies no working directory
- **WHEN** its command removes an absolute path
- **THEN** the path is judged as it would be with a working directory

#### Scenario: AnAncestorRemovedThroughWrappers

- **GIVEN** a command that removes a directory holding a declared location under `env sudo`, `sudo env`, or `caffeinate -i`
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: AnAncestorAfterTheEndOfOptions

- **GIVEN** a command that removes a directory holding a declared location, named after `--`
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: AnAncestorWithAnInvalidEntry

- **GIVEN** the catalog entry for `rm` is invalid
- **WHEN** a command runs `rm -rf` on a directory holding a declared location
- **THEN** the gate applies

#### Scenario: AnAncestorWithAnUnlistedOption

- **GIVEN** a command that gives `rm` an option its entry does not list, and names a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: AnAncestorBehindAWrapperTheReadingStoppedAt

- **GIVEN** a command such as `env --chd /tmp rm -rf` naming a directory that holds a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies, because `rm` follows the point where the reading stopped

#### Scenario: AnAncestorOfTheFloorIsRemoved

- **GIVEN** a directory that holds an enforcement-floor location, such as `<repo>/modules`
- **WHEN** a command removes, renames, or replaces it
- **THEN** the hook refuses it on every agent, and the reason tells the user to run it in their own terminal

#### Scenario: AnAncestorOfOnlyGuardedLocations

- **GIVEN** a directory that holds guarded locations and no enforcement-floor location
- **WHEN** a command removes it
- **THEN** the gate applies as an ask, and the reason names the declared locations it would remove

#### Scenario: TheFloorWithAWrongCatalogEntry

- **GIVEN** a catalog entry for `rm` that is valid but types no operand as deleted
- **WHEN** a command runs `rm -rf` on a directory that holds an enforcement-floor location
- **THEN** the hook refuses it on every agent

#### Scenario: AnUnresolvedOperandThatMayHoldTheFloor

- **GIVEN** a tool call whose working directory the hook cannot resolve
- **WHEN** its command removes a relative path
- **THEN** the hook refuses it on every agent

#### Scenario: AFileOnTheFloorIsEdited

- **GIVEN** a single file at an enforcement-floor location
- **WHEN** a command writes it
- **THEN** the gate applies as an ask

#### Scenario: AnAncestorWithAnInvalidPermissionEntry

- **GIVEN** the catalog entry for `chmod` is invalid
- **WHEN** a command runs `chmod 000` on a directory that holds a declared location
- **THEN** the gate applies

#### Scenario: AShownTargetOfAGeneratedCommand

- **GIVEN** a command such as `xargs -a <file> rm -rf` naming a directory that holds a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: ATargetOnlyInTheInput

- **GIVEN** a command such as `xargs rm -rf` whose targets come only from its input
- **WHEN** the command is intercepted
- **THEN** this gate does not apply

#### Scenario: AnAncestorRemovedByAnUncatalogedProgram

- **GIVEN** a command whose program the catalog does not list names a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** this gate does not apply, and the program is reported as uncataloged
