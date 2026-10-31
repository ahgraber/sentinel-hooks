# Delta for hook-tampering-blocking

## MODIFIED Requirements

### Requirement: ProtectedSurface

> Previously: the surface was stated here as four kinds of location, which is posture, beside the rule that every agent enforces every agent's set, and the read-through and exec-through carve-outs were in force with no requirement here recording them.

The system SHALL protect every location the manifest declares, in the classes `guarded-path-declarations` defines, and SHALL protect the same surface regardless of which agent is running.

Serves: posture-and-mechanism-are-separate

Which locations are declared, and why, is posture, recorded in `guarded-surface`.
This capability consults the manifest and names no location of its own.

Every agent SHALL enforce every agent's protected set.
An agent that enforces only its own set leaves the others writable from a session it controls, and those others constrain it the moment they run.

#### Scenario: AgentEditsOtherAgentGuardrail

- **GIVEN** any agent is running
- **WHEN** a tool call would modify a different agent's protected path
- **THEN** the gate applies exactly as it would to the agent's own guardrail

### Requirement: ReadsAreAllowed

> Previously: reads were allowed for the Read tool alone, justified by a sandbox limit on Linux, and a shell command reading a protected path was gated unless a read-through table listed the location.

The system SHALL allow a read of every guarded location, by the Read tool and by a shell command recognized as a read, and SHALL refuse a read of a block location.

Serves: reads-are-frictionless

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

> Previously: the outcome was decided by four protected classes, a shell command was judged by the paths it named with the read-through carve-out contradicting rather than qualifying the rule, and a command naming several classes took the most restrictive outcome among them.

The system SHALL intercept any tool call that would create, modify, delete, or rename a location the manifest covers, and SHALL NOT let it proceed on the agent's judgment alone.

Serves: one-list-then-deltas

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

## REMOVED Requirements

### Requirement: InstructionTextIsWritable

Removed because: whether instruction text is writable is posture, not mechanism, and the posture decision recorded in `guarded-surface` `InstructionTextIsGuarded` is that it asks like any other guardrail.
The mechanism that requirement described, a write permitted by the location it lands on and narrowed to one file shape, is now `WriteThroughLocationsAreWritable`, with no location named.

### Requirement: ProfileLayerConfiguration

Removed because: which files can layer permissions over an agent's base configuration is posture, and `guarded-surface` `ProfileLayersAreGuarded` records it with the declaration that enforces it.

## ADDED Requirements

### Requirement: WriteThroughLocationsAreWritable

The system SHALL permit a write whose target a write-through declaration covers, and the permission SHALL hold only where every hop of the target's link chain is covered by a write-through declaration or by no declaration at all.

Serves: one-list-then-deltas, reads-are-frictionless

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

Where a Bash command names guarded locations, the system SHALL classify the command before gating it: a command recognized as a read SHALL proceed, a command recognized as a run of a program held in an exec-through location SHALL proceed, and any other command SHALL be gated with a reason that names the syntax that stopped recognition, the forms that would have proceeded, and the instruction to name paths absolutely.

Serves: reads-are-frictionless, skill-scripts-run

One path in a block location SHALL refuse the whole command, whatever the rest of it does.
One path outside every exec-through location SHALL gate a run, whatever the rest of it does.

Recognition SHALL rest on the command text alone, read as `shell-lexing` requires every path hook to read it.
A command whose effect that text does not show SHALL NOT be recognized, because the classifier cannot judge what it cannot see: a redirection, an unresolvable word, an assignment that picks which binary runs, program text handed to an interpreter, or a relative path after a change of directory.

A command with any segment whose program executes text it receives SHALL NOT be recognized, whatever its other segments do: `xargs`, `eval`, an interpreter given inline code, or a shell reading its standard input.
The classifier SHALL identify the program through `time`, `timeout`, `stdbuf`, and `setsid`.
A pipe-fed program outside the recognized read utilities SHALL be treated as a builder, including an interpreter or an unknown wrapper.
Supported wrappers around recognized reads SHALL preserve read recognition unless their options permit writing output.
A read segment that names a guarded path and pipes into such a program hands that path to a command the classifier never sees, so the read is not the whole of what the command does.

The reason is what tells an agent what to rewrite.
A refusal that names neither the syntax that stopped recognition nor the forms that proceed leaves an agent whose gate is a refusal with nothing to do but try another route, which is the behavior every refusal in this module instructs against.

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
- **WHEN** the command carries a redirection or an unresolvable word or an assignment that picks which binary runs or program text handed to an interpreter
- **THEN** the gate applies

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
- **WHEN** the command is neither a recognized read nor a recognized run
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

Serves: skill-scripts-run

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
