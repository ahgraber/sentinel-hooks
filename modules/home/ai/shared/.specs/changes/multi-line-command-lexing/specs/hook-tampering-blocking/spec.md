# Delta for hook-tampering-blocking

## MODIFIED Requirements

### Requirement: UnrecognizedCommandsAreGated

> Previously: a command written across lines was never recognized, because the hook treated it as unresolvable as a whole.

Where a Bash command names guarded locations, the system SHALL classify the command before gating it: a command recognized as a read SHALL proceed, a command recognized as a run of a program held in an exec-through location SHALL proceed, and any other command SHALL be gated with a reason that names the syntax that stopped recognition, the forms that would have proceeded, and the instruction to name paths absolutely.

Serves: a-multi-line-command-is-read-line-by-line

One path in a block location SHALL refuse the whole command, whatever the rest of it does.
One path outside every exec-through location SHALL gate a run, whatever the rest of it does.

Recognition SHALL rest on the command text alone, read as `shell-lexing` requires every path hook to read it.
A command whose effect that text does not show SHALL NOT be recognized, because the classifier cannot judge what it cannot see: an unresolvable word, an assignment that picks which binary runs, program text handed to an interpreter, or a relative path after a change of directory.

A redirection SHALL NOT keep a command from being recognized; its target SHALL be judged by its direction.
An input target is judged as a read, and an output or read-write target as a write, so a recognized read that writes its output into a guarded location meets the write gate for that location.
A redirection that duplicates or closes a descriptor names no file and is not judged.
A segment that does nothing but redirect, such as `> file`, `: > file`, or `exec 3> file`, is judged by its targets alone, so it meets the write gate as the write it is.
The command text names every target, so a redirection hides nothing the classifier needs.
Refusing recognition for one refused a guarded read for writing its errors to `/dev/null`, a form agents write by habit, while a write the target class permits gained nothing from the refusal.

A command with any segment whose program executes text it receives SHALL NOT be recognized, whatever its other segments do: `xargs`, `eval`, an interpreter given inline code, or a shell reading its standard input.
The classifier SHALL identify the program through `time`, `timeout`, `stdbuf`, and `setsid`.
A pipe-fed program outside the recognized read utilities SHALL be treated as a builder, including an interpreter or an unknown wrapper.
Supported wrappers around recognized reads SHALL preserve read recognition unless their options permit writing output.
A read segment that names a guarded path and pipes into such a program hands that path to a command the classifier never sees, so the read is not the whole of what the command does.

A command written across lines SHALL be classified the same way as the same command written on one line.

A here-document SHALL be data only where the command that reads it is a recognized read, or a sink that keeps its input as a record rather than acting on it: `git commit` and `git tag` given `-F -` or `--file=-`, `gh` given `--body-file -`, and `tee`, whose targets are judged as the writes they are.
A path inside a data body is text, names no file, and is not judged; the command's own words and redirections are judged as they are on one line.
A here-document read by any other program SHALL be judged as program text handed to it, as text `echo` pipes into a shell is: the command is not recognized, and a guarded or block path inside the body is found.

The default is program text because the hazard is not limited to shells and interpreters.
`xargs`, `sudo sh`, `source /dev/stdin`, `awk -f -`, `sed -f -`, `sqlite3`, `git apply`, `patch`, `crontab -`, and a remote shell each act on input whose effects are named only inside the body, and a list of such programs would refuse only the ones it remembered.
This is the rule `ReadClassifierAdmitsOnlySelfDescribingUtilities` applies to a utility: a command is admitted when its command line states what it does.
If bash would expand any part of a body, the body is an unresolvable word, like any other.

The reason is what tells an agent what to rewrite.
A refusal that names neither the syntax that stopped recognition nor the forms that proceed leaves an agent whose gate is a refusal with nothing to do but try another route, which is the behavior every refusal in this module instructs against.
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
- **WHEN** the command is neither a recognized read nor a recognized run
- **THEN** the decision is `Ask`, and the reason names the read utilities and the interpreters that would have proceeded

#### Scenario: ReasonNamesTheSyntaxThatStoppedRecognition

- **GIVEN** a Bash tool call that would be a recognized read but for a substitution or a brace expansion
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

#### Scenario: AMultiLineReadIsRecognized

- **GIVEN** a Bash tool call whose lines are each a recognized read of a guarded location
- **WHEN** the command is judged
- **THEN** the hook exits 0, as it does for the same reads joined by `;`

#### Scenario: AMultiLineCommandReachesItsOneLineVerdict

- **GIVEN** a Bash tool call written across lines, by newlines between commands, a backslash continuation, or a newline after an operator or an opening reserved word
- **WHEN** the command is judged
- **THEN** the decision and its reason are the ones the same command on one line reaches

#### Scenario: AHereDocumentReadAsDataIsNotJudged

- **GIVEN** a command whose here-document is read by a recognized read such as `cat`, or by `git commit -F -`, `git tag -F -`, `gh --body-file -`, or `tee`
- **WHEN** the body names a guarded path as text
- **THEN** the body is not judged, and the command reaches the verdict its own words and redirections reach

#### Scenario: AHereDocumentReadByAnyOtherProgramIsProgramText

- **GIVEN** a here-document read by a shell, an interpreter, `xargs`, `sudo sh`, `source /dev/stdin`, `sed -f -`, `git apply`, or any program not named as a data reader
- **WHEN** the body names a guarded path
- **THEN** the gate applies, as it does for `bash -c` with the same text, and a block path in the body refuses the command
