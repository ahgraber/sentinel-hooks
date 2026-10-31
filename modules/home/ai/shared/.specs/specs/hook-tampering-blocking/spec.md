# Spec: hook-tampering-blocking

## Purpose

Every other guardrail depends on the files that enforce it, so an agent that can change those files without the user can remove any guardrail.
These requirements cover the locations treated as enforcement, which actions on them proceed, ask, or are refused, and how the gate reads shell commands and patches to find them.

## Requirements

### Requirement: Purpose

The system SHALL ensure that the files constraining an agent's behavior — its own or any other agent's — change only with the user's approval.

Every other guardrail in this repository depends on this one.
A hook script, a permission rule, or a hook registration file is enforcement.
An edit to enforcement is not a routine edit: it removes or reshapes a constraint, and whether that happens is the user's decision alone.

The system SHALL put that decision to the user in the moment, where the invoking agent can prompt, and SHALL refuse the edit where it cannot.
A guard that can only refuse is a guard that gets disabled instead of consulted; maintenance that can be approved in-session stays inside the guardrails while it happens.

Agent credentials are the exception and SHALL be refused without a prompt.
No legitimate flow maintains a credential in-session, so a prompt there gains nothing and trains approval of the one request that should never come.

### Requirement: ProtectedSurface

The system SHALL protect every location the manifest declares, in the classes `guarded-path-declarations` defines, and SHALL protect the same surface regardless of which agent is running.

Which locations are declared, and why, is posture, recorded in `guarded-surface`.
This capability consults the manifest and names no location of its own.

Every agent SHALL enforce every agent's protected set.
An agent that enforces only its own set leaves the others writable from a session it controls, and those others constrain it the moment they run.

#### Scenario: AgentEditsOtherAgentGuardrail

- **GIVEN** any agent is running
- **WHEN** a tool call would modify a different agent's protected path
- **THEN** the gate applies exactly as it would to the agent's own guardrail

### Requirement: ReadsAreAllowed

The system SHALL allow a read of every guarded location, by the Read tool and by a shell command recognized as a read, and SHALL refuse a read of a block location.

This is a deliberate concession, not an oversight.
A guarded location holds enforcement an agent may inspect, instructions it is meant to load, and skills it is meant to use.
Refusing a read there withholds review of the guardrails without concealing them, because `git log -p` prints the sources without reaching any gate.
On Linux the sandbox cannot express a read-deny over a symlink into the store at all: it attempts to mount over the link, fails, and aborts every sandboxed command rather than the one read.

The consequence is accepted: an agent can read the rules that constrain it, and could use them to look for a gap.
Write protection is the boundary; concealment is not.
Material an agent must not see is declared in the block class, where `sensitive-path-blocking` and this hook both refuse it.

#### Scenario: ReadProtectedHook

- **GIVEN** a Read tool call is intercepted
- **WHEN** the target is a guarded location
- **THEN** the hook exits 0

#### Scenario: RecognizedShellRead

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is recognized as a read and names guarded locations alone
- **THEN** the hook exits 0 on every agent

#### Scenario: ReadOfABlockLocation

- **GIVEN** any tool call is intercepted
- **WHEN** it would read a block location
- **THEN** the call is refused on every agent

### Requirement: MutationIsBlocked

The system SHALL intercept any tool call that would create, modify, delete, or rename a location the manifest covers, and SHALL NOT let it proceed on the agent's judgment alone.

The outcome is the one `guarded-path-declarations` `PrecedenceIsOneRule` assigns to the path:

- **Guarded** — the decision is `Ask`.
  The mutation proceeds only with the user's approval, and is refused where the invoking agent honors no prompt for that tool, per `hook-interface` `ExitCodes`.
- **Block** — the decision is `Block`, on every agent.
- **Write-through** — the mutation proceeds, per `WriteThroughLocationsAreWritable`.

This covers direct file writes, patch application, and shell commands.
A shell command SHALL be judged by the paths it names, because a command can make every change a file tool can.
The paths a command names are:

- each path its words resolve to when bash expands them
- each path written inside a word whose expansion cannot be determined
- each path written inside program text that a segment's program runs: an interpreter's inline code, an argument of `eval`, executable Git configuration such as `core.pager` or an `alias` that begins with `!`, and text piped from `echo` or `printf` into a shell

Bash passes program text as one word, and that word names no real file.
So the hook searches the program text for paths and judges them by their text, as `path-matching` `TextMatchingIsForTextThatMayHoldNoPath` permits for a word a program will run.
A command naming paths in more than one class SHALL receive the most restrictive outcome among them.

A shell command recognized as a read, or as a run of a program held in an exec-through location, is the exception, and SHALL be judged by `UnrecognizedCommandsAreGated` instead.
That requirement decides from the command text what the command does; a command it does not recognize returns here.

A path a command supplies as the operand of shell syntax SHALL count as a path the command names, whether or not a space separates the two.
Shell syntax written against its operand is the same instruction as the spaced form, so a difference in verdict between the two is a difference the writer chooses.

#### Scenario: OperandAttachedToShellSyntax

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command carries a guarded path as an operand written against a redirection or an option
- **THEN** the gate applies

#### Scenario: EditProtectedHookScript

- **GIVEN** an Edit tool call is intercepted
- **WHEN** the target is a guarded location
- **THEN** the decision is `Ask`, and the mutation proceeds only on the user's approval

#### Scenario: ShellCommandNamingProtectedPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command writes a guarded location in this repository
- **THEN** the decision is `Ask`, and the mutation proceeds only on the user's approval

#### Scenario: EditPerUserConfiguration

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** the target is a guarded location belonging to a user other than the one the agent runs as
- **THEN** the decision is `Ask`, and the mutation proceeds only on the user's approval

#### Scenario: WriteAgentCredential

- **GIVEN** any mutating tool call is intercepted
- **WHEN** the target is a block location
- **THEN** the decision is `Block`, whatever the invoking agent's prompting ability

#### Scenario: GatedMutationOnAgentThatCannotPrompt

- **GIVEN** a mutating tool call reaches an `Ask` decision
- **WHEN** the invoking agent has no honored prompt encoding for that tool
- **THEN** the tool call is refused with an explanation

#### Scenario: MixedClassCommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command names both a guarded location and a block location
- **THEN** the decision is `Block`

#### Scenario: WriteBeneathAGuardedBase

- **GIVEN** a guarded declaration for a directory
- **WHEN** a Write tool call targets a file beneath it that no write-through declaration covers
- **THEN** the decision is `Ask`

### Requirement: PathSpellingIndependence

The system SHALL determine whether a path denotes a protected location according to `path-matching`.

The limits recorded there apply here unchanged: a working-directory change within a single shell command, hard links, a tree that is not a repository, and any route that does not present a path.

A spelling that differs only in letter case is not a limit where the filesystem treats such spellings as the same file.

These limits are why this requirement is defense in depth.
The operating system sandbox and the agent permission layer are the boundary.

#### Scenario: CaseVariantSpelling

- **GIVEN** a Write, Edit, or Bash tool call is intercepted on a case-insensitive filesystem
- **WHEN** the target names a protected path under a differing letter case
- **THEN** the path is treated as protected and the gate applies

### Requirement: GateResponse

Every outcome the gate reaches SHALL carry an explanation that satisfies the `hook-interface` `ExplanationContract`.

A refusal SHALL name the specific path or command that was refused, and SHALL state that enforcement is the reason.
It SHALL end with the instruction `hook-interface` `BlockAIGuidance` defines for it, and SHALL direct the agent to report the refusal to the user.

The gate SHALL list the admitted commands in a refusal only when the classifier stopped on the program the command runs.
The classifier stops on one of two things: the program, or the shape of the command.
Substituting a program changes the first and leaves the second unchanged, so a refusal that stopped on shape lists commands the agent cannot use.

The gate SHALL end a refusal that lists the admitted commands with the retry instruction.
Listing them is safe only while each one reads.
An admitted utility that writes a file named as an operand would make the retry instruction a route to the write the gate just refused.

A refusal whose classifier stopped only on relative paths in a directory the gate cannot determine SHALL tell the agent to name every path absolutely, and SHALL end with the absolute-path instruction.
That shape stop has one rewrite that resolves it, and the restated command is judged in full.
Every other refusal SHALL end with the stop instruction.

A refusal SHALL state what the gate refused, rather than which category the command failed to match.
The gate matches the command; it does not receive the agent's intent.
A refusal that reports "not a recognized read" therefore sends an agent that was writing to look for a read.

An ask SHALL address the user alone, except where an adapter may refuse it: there it also carries the instruction section, per `hook-interface` `ExplanationContract`.
It SHALL name the specific file, state that the file is enforcement, and state what approving the mutation would permit.
It SHALL NOT present the mutation as routine: the user is deciding whether a guardrail changes, and the explanation is what makes that decision an informed one.

Neither explanation is required to name which agent owns the path, because enforcement does not vary by agent.

#### Scenario: AskNamesTheEnforcementFile

- **GIVEN** the gate reaches an `Ask` decision
- **WHEN** the user reads the prompt
- **THEN** they see which file would change, that it is enforcement, and what approving the change would permit

#### Scenario: ADeclarationCoversThePath

- **GIVEN** the gate refuses because a declaration covers the path
- **WHEN** the gate writes the refusal
- **THEN** the refusal names the path, states that enforcement is the reason, and ends with the stop instruction

#### Scenario: TheClassifierStoppedOnTheProgram

- **GIVEN** the gate refuses because the classifier stopped on the program the command runs
- **WHEN** the gate writes the refusal
- **THEN** the refusal lists the admitted commands and ends with the retry instruction

#### Scenario: TheClassifierStoppedOnTheShape

- **GIVEN** the gate refuses because the classifier stopped on the shape of the command, such as a substitution or program text
- **WHEN** the gate writes the refusal
- **THEN** the refusal names what stopped the classifier, omits the admitted commands, and ends with the stop instruction

#### Scenario: TheClassifierStoppedOnARelativePath

- **GIVEN** the gate refuses because the classifier stopped only on relative paths after a directory change
- **WHEN** the gate writes the refusal
- **THEN** the refusal names that stop, omits the admitted commands, tells the agent to name every path absolutely, and ends with the absolute-path instruction

### Requirement: FailureMode

The system SHALL choose what to do about a call it cannot judge by the tool the call names.

Where the tool is one this hook does not cover, the decision is `Allow`.

Where evaluation raises an unexpected error and the payload names a tool this hook gates, a tool in the declared `mutating` group, the decision is `Ask`, degrading to `Block` where the agent cannot show a prompt.
Every tool this hook gates can modify state, so a call it failed to judge is a mutation nothing checked.
`Read` is registered so that a read of a block location is refused, and it cannot modify state: a failure while judging a `Read` lets the call proceed with the failure reported, as `hook-interface` requires of a read-only tool.
`Ask` rather than `Block` because this hook runs on every such call and most of them reach nothing it guards: a fault that recurs would otherwise refuse every mutation the agent attempts, with no route left for the user to say otherwise.
This follows `hook-interface` `ErrorHandlingByDamagePotential`.

Where the payload does not parse, or where naming the tool is itself the step that failed, the decision is `Warn`.
The tool call still proceeds, because this hook is registered for `Read` as well and an unnamed tool cannot be assumed to be a mutation.
A hook that silently checks nothing is how a change to the agent harness goes unnoticed, so the failure is reported rather than swallowed.
The encoding of `Warn` is agent-specific, per `hook-interface` `ExitCodes`; exiting 0 is its degraded form, not the contract.

The operating system sandbox and the permission layer remain in force regardless, and neither is a reason to allow.
Guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, so the permission layer permits the write this hook exists to ask about.

Neither SHALL apply to a path that cannot be resolved.
Such a path is judged from the path as written, per `path-matching` `UnresolvablePathIsGuarded`.

#### Scenario: UnparsablePayload

- **GIVEN** a tool call is intercepted
- **WHEN** the payload cannot be parsed
- **THEN** the tool call proceeds, and the reason is reported where the agent can report it

#### Scenario: EvaluationRaisesOnAMutatingTool

- **GIVEN** a call to a tool in the declared `mutating` group is intercepted
- **WHEN** evaluation raises an unexpected error
- **THEN** the gate applies, and the reason names the failure

#### Scenario: EvaluationRaisesOnARead

- **GIVEN** a `Read` call is intercepted
- **WHEN** evaluation raises an unexpected error
- **THEN** the tool call proceeds, and the reason is reported where the agent can report it

#### Scenario: UnresolvableProtectedPath

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** the target cannot be resolved but as written denotes a protected path
- **THEN** the gate applies

### Requirement: WriteThroughLocationsAreWritable

The system SHALL permit a write whose target a write-through declaration covers, and the permission SHALL hold only where every hop of the target's link chain is covered by a write-through declaration or by no declaration at all.

A write to a link is a write to what the link leads to.
A name a write-through declaration covers does not make the write qualify when the link leads to a guarded or block location, because `PrecedenceIsOneRule` takes the strictest hop.
A shell command SHALL qualify only when every path it writes qualifies.

The declaration is as narrow as its glob makes it.
A declaration ending in a glob with a suffix covers files of that suffix directly within the directory, not a nested path and not another file type.

#### Scenario: ExemptNameLeadingToEnforcement

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** the target is named under a write-through declaration but is a link leading to a guarded file
- **THEN** the gate applies

#### Scenario: FileMatchingTheGlob

- **GIVEN** a write-through declaration with a glob in its last component
- **WHEN** a Write tool call targets a file directly within the directory that matches the glob
- **THEN** the hook exits 0

#### Scenario: NestedPathBeneathTheGlob

- **GIVEN** a write-through declaration with a glob in its last component
- **WHEN** a Write tool call targets a file below a subdirectory of that directory
- **THEN** the gate applies

#### Scenario: FileNotMatchingTheGlob

- **GIVEN** a write-through declaration with a glob in its last component
- **WHEN** a Write tool call targets a file directly within the directory that does not match the glob
- **THEN** the gate applies

#### Scenario: WriteThroughDirectoryBeneathAGuardedBase

- **GIVEN** a write-through declaration for a directory beneath a guarded one
- **WHEN** a Write tool call targets a file in that directory
- **THEN** the hook exits 0

#### Scenario: ShellCommandMixingWriteThroughAndGuarded

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command writes one path a write-through declaration covers and one it does not
- **THEN** the gate applies to the whole command

### Requirement: UnrecognizedCommandsAreGated

Where a Bash command names guarded locations, the system SHALL classify the command before gating it: a command recognized as a read SHALL proceed, a command recognized as a run of a program held in an exec-through location SHALL proceed, and any other command SHALL be gated with a reason that names the syntax that stopped recognition and, per `GateResponse`, the rewrite that would proceed where one exists: the admitted commands for a stop on the program, and absolute paths for a stop on relative paths.

One path in a block location SHALL refuse the whole command, whatever the rest of it does.
One path outside every exec-through location SHALL gate a run, whatever the rest of it does.

Recognition SHALL rest on the command text alone, read as `shell-lexing` requires every path hook to read it.
A command whose effect that text does not show SHALL NOT be recognized, because the classifier cannot judge what it cannot see: an unresolvable word, an assignment that picks which binary runs, program text handed to an interpreter, or a relative path after a change of directory.

A redirection SHALL NOT keep a command from being recognized; its target SHALL be judged by its direction.
An input target is judged as a read, and an output or read-write target as a write, so a recognized read that writes its output into a guarded location meets the write gate for that location.
A redirection that duplicates or closes a descriptor names no file and is not judged.
A segment that does nothing but redirect, such as `> file`, `: > file`, or `exec 3> file`, is judged by its targets alone, so it meets the write gate as the write it is.
The command text names every target, so a redirection hides nothing the classifier needs.

A command with any segment whose program executes text it receives SHALL NOT be recognized, whatever its other segments do: `xargs`, `eval`, an interpreter given inline code, or a shell reading its standard input.
The classifier SHALL identify the program through a wrapper known to run its operands unchanged, such as `time` or `timeout`; a command under any other wrapper is not recognized.
A pipe-fed program outside the recognized read utilities SHALL be treated as a builder, including an interpreter or an unknown wrapper.
A known wrapper around a recognized read SHALL preserve read recognition unless its options permit writing output.
A read segment that names a guarded path and pipes into such a program hands that path to a command the classifier never sees, so the read is not the whole of what the command does.

The reason is what tells an agent what to rewrite.
A refusal that names neither the syntax that stopped recognition nor a rewrite that proceeds, where one exists, leaves an agent whose gate is a refusal with nothing to do but try another route, which is the behavior every refusal in this module instructs against.
A command whose every segment is recognized, stopped only by a write to a guarded location, is gated as that write, and its reason names the write rather than a syntax.
A command with any unrecognized segment keeps the recognition reason, because it may do more than that write.

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

### Requirement: ARunTargetsAnExistingScript

The system SHALL recognize a run only where the file it names already exists and is a program.

A path the run would create is a write, and a file the interpreter would not execute is not the thing this carve-out permits.

#### Scenario: ScriptAlreadyHeldThere

- **GIVEN** a Bash tool call names a file in an exec-through location
- **WHEN** the file exists and is a program
- **THEN** the hook exits 0

#### Scenario: TargetIsNotAProgram

- **GIVEN** a Bash tool call names a file in an exec-through location
- **WHEN** the file exists and is not a program
- **THEN** the gate applies

#### Scenario: TargetDoesNotExist

- **GIVEN** a Bash tool call names a path in an exec-through location
- **WHEN** no file exists at that path
- **THEN** the gate applies

### Requirement: ReadClassifierAdmitsOnlySelfDescribingUtilities

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

An admitted utility SHALL NOT write a file named as an operand.
An option that writes can be refused by name; an operand cannot, because the paths a command reads appear in the same position.
`uniq in out` and `xxd in out` each replace `out`, which is why neither is admitted.
This property SHALL be checked against the real utility rather than assumed, because it is what `hook-interface` `BlockAIGuidance` rests on when it offers the admitted set to a refused agent.

A utility MAY be admitted with named options refused.
This applies when those options are the only way the utility acts outside its command line, and when each one can be refused as a whole token.

A utility MAY also be admitted when one of its own options turns off the outside source.
The command SHALL then supply that option, and the command line decides what the utility does because the outside source is off.

The required option SHALL be the first argument.
An option that takes a value can come first and take the required option as its value.
The outside source stays on, and the required token is still in the command, so a check for the token alone would pass the command wrongly.

Both routes need the utility to match each option name exactly.
A utility that accepts an abbreviation, or the same name in another case, gives a refused option more than one spelling.
A check over whole tokens misses the spellings it does not list.

Ripgrep is admitted under both routes: its options that run a program are refused, and `--no-config` must come first.

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

### Requirement: InstalledCodeIsJudgedWithTheCommandThatInstallsIt

A command that installs code for the shell to run later SHALL be judged as a whole, and no part of it SHALL be recognized as a read.

The classifier judges one segment at a time.
A segment that does not name a guarded location is not judged, so the command around it keeps its read carve-out.
That rule holds only while each segment runs on its own.

Installed code does not run on its own.
It runs beside every later command in the same shell, including the recognized read that follows it.
The segment that installs it does not name a guarded location, so nothing judges it, and the installed code then runs without a prompt.

The hook SHALL find and judge a guarded location named inside an installed body, however the body is quoted.
The read carve-out SHALL NOT apply to the rest of a command that installs a body.
A body quoted as one word is one word to the shell, so a check of whole words misses the location inside it.

A command that does not install a body SHALL keep the read carve-out.
Listing the installed handlers, or resetting them, does not install anything and does not put code beside the read.

A prefix that only chooses how the shell dispatches a command SHALL NOT change what the classifier reads.
Such a prefix leaves the command and its arguments as they were, so treating the prefixed form differently would gate one spelling of a command and pass another.

Binding a command name to a body is installing code, and SHALL be judged the same way.
The admitted set records which program each name runs.
A definition rebinds that name for every command after it, so an admitted name in the same command reaches the body instead of the program the set records.
The body can also drop a required option before passing the rest to the real program.

#### Scenario: CodeIsInstalledBesideARecognizedRead

- **GIVEN** a command whose first segment installs code for the shell to run later
- **WHEN** a later segment would be recognized as a read of a guarded location
- **THEN** the command is judged as a whole and the read carve-out does not apply

#### Scenario: AnInstalledBodyNamesAGuardedLocation

- **GIVEN** an installed body that names a guarded location inside one quoted word
- **WHEN** the command is judged
- **THEN** the location is found, and the command reaches the class that location carries

#### Scenario: AnInstalledBodyNamesACredential

- **GIVEN** an installed body that names a location in the block class
- **WHEN** the command is judged
- **THEN** the command is refused on every agent

#### Scenario: NoCodeIsInstalled

- **GIVEN** a command that does not install code for the shell to run later
- **WHEN** a segment is recognized as a read of a guarded location
- **THEN** the read proceeds

#### Scenario: TheInstallingCommandOnlyListsOrResetsHandlers

- **GIVEN** a command that lists the installed handlers, or resets them
- **WHEN** a segment beside it is recognized as a read of a guarded location
- **THEN** the read proceeds, because nothing was installed

#### Scenario: TheInstallingCommandCarriesADispatchPrefix

- **GIVEN** a command that installs code, written with a prefix that only chooses how the shell dispatches it
- **WHEN** the command is judged
- **THEN** it reaches the same outcome as the same command without the prefix

#### Scenario: ACommandNameIsBoundToABody

- **GIVEN** a command that binds a command name to a body
- **WHEN** a later segment uses that name to read a guarded location
- **THEN** the command is judged as a whole, because the name now reaches the body rather than the program the admitted set records

### Requirement: ADestructiveOperationOnAnAncestorReachesTheUser

The system SHALL gate an operation that removes, renames, or replaces a directory holding a declared location, or changes its permissions, owner, or attributes.

A declaration names a directory and protects what is inside it.
It does not protect the path to it, so `rm -rf modules/home/ai/pi` takes away the declared `modules/home/ai/pi/security/` while no word equals or falls inside any declaration.
No other layer closes this: guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, which means the permission layer permits the write by design.

The gate covers those operations alone.
Reading, searching, and creating files beneath an ancestor are ordinary work and SHALL stay unprompted.
Gating every command naming a prefix of a declaration reaches `modules/`, the home directory, and the repository root.

A removal, a rename, or a replacement is a write under `guarded-path-declarations` `PrecedenceIsOneRule`; this gate reaches the ancestor that rule finds no declaration for.

An ancestor carries no declaration fragment, so it is found by resolving the path rather than by matching text.
A relative spelling resolves against the working directory the tool call supplies, moved by any earlier `cd` in the command.
Where no directory is supplied, or a `cd` names one the hook cannot resolve, the word is unresolvable, per `path-matching` `TextMatchingIsForTextThatMayHoldNoPath`.
The system SHALL refuse a removal, rename, or replacement of such a word on every agent, with the absolute-path instruction of `hook-interface` `BlockAIGuidance`.
It cannot be judged by its text: a `*` in a declaration matches almost any word, so judging its shape would refuse ordinary commands.
It is not put to the user either, because the user has no more to place it by than the hook.
The same command with the path written absolutely can be judged.

The gate knows the operation from the program, so a program it does not list passes on an ancestor.
So does a command assembled at run time, such as one `xargs` builds, and a branch switch, which changes every tracked file.

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

### Requirement: APatchIsJudgedByTheFilesItNames

Where a patch declares the files it changes, the system SHALL judge those files alone, and SHALL NOT judge the text the patch inserts.

A patch names every file it writes in a header of its own, so the declared set is the whole of what it changes.
The inserted text is content.
Judging it refuses a patch for naming a guarded path in what it writes rather than for changing one, which stops an agent writing a changelog entry, an incident note, or a spec that cites the hook it specifies.

The cost falls on the agent that cannot show a prompt, whose gate is a refusal rather than a question.
That agent cannot write about the guardrail that stopped it, so the record of a refusal is the one thing the refusal reliably prevents.

A patch whose headers yield no file states no target.
The system SHALL then judge its text, because nothing else is left to judge.

The other write routes are unchanged.
The file tools carry the path they write, and a shell command states no intent, so neither gains a target list from this.

#### Scenario: PatchContentNamesAGuardedPath

- **GIVEN** a patch targeting a path no class covers
- **WHEN** the text it inserts names a guarded path
- **THEN** the hook exits 0 on every agent

#### Scenario: PatchTargetsAGuardedPath

- **GIVEN** a patch whose header names a guarded path
- **WHEN** the patch is intercepted
- **THEN** the gate applies, whatever the text it inserts says

#### Scenario: PatchTargetsACredential

- **GIVEN** a patch whose header names a block location
- **WHEN** the patch is intercepted
- **THEN** it is refused on every agent, with no prompt

#### Scenario: PatchDeclaresNoFile

- **GIVEN** a patch no header parses a file out of
- **WHEN** its text names a guarded path
- **THEN** the gate applies
