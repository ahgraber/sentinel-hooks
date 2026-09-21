# Delta for hook-tampering-blocking

## MODIFIED Requirements

### Requirement: GateResponse

> Previously: every refusal had to instruct the agent not to look for another route, which is one of the two instruction forms `hook-interface` `BlockAIGuidance` now defines.

Serves: a-refusal-says-what-would-work

Every outcome the gate reaches SHALL carry an explanation that satisfies the `hook-interface` `ExplanationContract`.

A refusal SHALL name the specific path or command that was refused, and SHALL state that enforcement is the reason.
It SHALL end with the instruction `hook-interface` `BlockAIGuidance` defines for it, and SHALL direct the agent to report the refusal to the user.

The gate SHALL list the admitted commands in a refusal only when the classifier stopped on the program the command runs.
The classifier stops on one of two things: the program, or the shape of the command.
Substituting a program changes the first and leaves the second unchanged, so a refusal that stopped on shape lists commands the agent cannot use.

The gate SHALL end a refusal that lists the admitted commands with the retry instruction, and every other refusal with the stop instruction.
Listing them is safe only while each one reads.
An admitted utility that writes a file named as an operand would make the retry instruction a route to the write the gate just refused.

A refusal SHALL state what the gate refused, rather than which category the command failed to match.
The gate matches the command; it does not receive the agent's intent.
A refusal that reports "not a recognized read" therefore sends an agent that was writing to look for a read.

An ask SHALL address the user alone.
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

- **GIVEN** the gate refuses because the classifier stopped on the shape of the command
- **WHEN** the gate writes the refusal
- **THEN** the refusal names what stopped the classifier, omits the admitted commands, and ends with the stop instruction

### Requirement: FailureMode

> Previously: an unexpected error let every call proceed, on the grounds that the hook covered a mix of sensitive and read-only tools and could not infer damage potential from the failure.

Serves: degradation-still-reaches-the-user

The system SHALL choose what to do about a call it cannot judge by the tool the call names.

Where the tool is one this hook does not cover, the decision is `Allow`.

Where evaluation raises an unexpected error and the payload names a tool this hook gates, `Bash`, `Write`, `Edit`, or `apply_patch`, the decision is `Ask`, degrading to `Block` where the agent cannot show a prompt.
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

- **GIVEN** a `Bash`, `Write`, `Edit`, or `apply_patch` call is intercepted
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

## ADDED Requirements

### Requirement: ReadClassifierAdmitsOnlySelfDescribingUtilities

Serves: existing-guarantees-are-recorded, a-refusal-says-what-would-work

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

Ripgrep meets both routes and is admitted.
`--pre` and `--hostname-bin` name a program to run.
`-z` and `--search-zip` run a decompressor that the command does not name and that is found on `PATH`.
All four are refused.
`RIPGREP_CONFIG_PATH` supplies options from a file, and one of those options can be `--pre`, so `rg pattern file` can run whatever that file names.
`--no-config` turns that file off, so the command must supply `--no-config` first.
This was tested against ripgrep 15.1.0, which does not match an abbreviated option name, or a differently-cased one.

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

Serves: the-declared-surface-is-what-is-protected

A command that installs code for the shell to run later SHALL be judged as a whole, and no part of it SHALL be recognized as a read.

The classifier judges one segment at a time.
A segment that does not name a guarded location is not judged, so the command around it keeps its read carve-out.
That rule holds only while each segment runs on its own.

Installed code does not run on its own.
It runs beside every later command in the same shell, including the recognized read that follows it.
The segment that installs it does not name a guarded location, so nothing judges it, and the installed code then runs without a prompt.

The classifier SHALL read an installed body as program text.
A body written as one quoted word reaches the word-level checks as a single word, so no path rule matches the guarded location inside it.
Reading the body as program text judges the locations it names, and withdraws the read carve-out from the rest of the command.

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

Serves: the-declared-surface-is-what-is-protected

The system SHALL gate an operation that removes, renames, or replaces a directory holding a declared location.

A declaration names a directory and protects what is inside it.
It does not protect the path to it, so `rm -rf modules/home/ai/pi` takes away the declared `modules/home/ai/pi/security/` while no word equals or falls inside any declaration.
No other layer closes this: guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, which means the permission layer permits the write by design.

The gate covers removal, renaming, and replacement alone.
Reading, searching, and creating files beneath an ancestor are ordinary work and SHALL stay unprompted.
Gating every command naming a prefix of a declaration reaches `modules/`, the home directory, and the repository root.

A removal, a rename, or a replacement is a write under `guarded-path-declarations` `PrecedenceIsOneRule`; this gate reaches the ancestor that rule finds no declaration for.

An ancestor carries no declaration fragment, so it is found by resolving the path rather than by matching text.
A relative spelling resolves against the working directory the tool call supplies, and where none is supplied the word is unresolvable and gates, per `path-matching` `TextMatchingIsForTextThatMayHoldNoPath`.

#### Scenario: AnAncestorIsRemoved

- **GIVEN** a command that removes a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies, though the command names no declaration

#### Scenario: AnAncestorIsReplaced

- **GIVEN** a command that renames a directory over such a directory, or copies over it
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

### Requirement: APatchIsJudgedByTheFilesItNames

Serves: degradation-still-reaches-the-user

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
