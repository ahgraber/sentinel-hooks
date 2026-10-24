# Delta for hook-tampering-blocking

## MODIFIED Requirements

### Requirement: UnrecognizedCommandsAreGated

> Previously: a command written across lines was never recognized, because the hook treated it as unresolvable as a whole.

Where a Bash command names guarded locations, the system SHALL classify the command before gating it: a command recognized as a read SHALL proceed, a command recognized as a run of a program held in an exec-through location SHALL proceed, and any other command SHALL be gated with a reason that names the syntax that stopped recognition and, per `GateResponse`, the rewrite that would proceed where one exists: the admitted commands for a stop on the program, and absolute paths for a stop on relative paths.

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

A command with any segment whose program executes text it receives SHALL NOT be recognized, whatever its other segments do: `xargs`, `eval`, an interpreter given inline code, or a shell reading its standard input.
The classifier SHALL identify the program through a wrapper known to run its operands unchanged, such as `time` or `timeout`; a command under any other wrapper is not recognized.
A pipe-fed program outside the recognized read utilities SHALL be treated as a builder, including an interpreter or an unknown wrapper.
A known wrapper around a recognized read SHALL preserve read recognition unless its options permit writing output.
A read segment that names a guarded path and pipes into such a program hands that path to a command the classifier never sees, so the read is not the whole of what the command does.

A command written across lines SHALL be classified the same way as the same command written on one line.

A here-document SHALL be data only where its reader is a data reader, one of these:

- a recognized read that takes only content from its standard input, never file names, arguments, or a program;
- `git commit` or `git tag` given `-F -`, `--file -`, or `--file=-`, with no option before the subcommand except `-C`, and with neither `-e` nor `--edit`;
- `gh pr` or `gh issue` given `--body-file -` or `--body-file=-`;
- `tee`, whose operands are judged as the writes they are.

The reader SHALL be the first word of its segment, with no assignment and no wrapper before it, and no earlier command in the text that rebinds its name, such as a function definition or `hash -p`.
The reader SHALL NOT pipe its output to another program, whether its own segment pipes, a compound command around it pipes, or it runs as a coprocess.
A path inside a data body is text, names no file, and is not judged; the command's own words and redirections are judged as they are on one line.
A here-document read by any other program SHALL be judged as program text handed to it, as text `echo` pipes into a shell is: the command is not recognized, and a guarded or block path inside the body is found.

Data is the exception because the hazard is not limited to shells and interpreters.
`xargs`, `sudo sh`, `source /dev/stdin`, `awk -f -`, `sed -f -`, `sqlite3`, `git apply`, `patch`, `crontab -`, and a remote shell each act on input whose effects are named only inside the body, and a list of such programs would refuse only the ones it remembered.
This is the rule `ReadClassifierAdmitsOnlySelfDescribingUtilities` applies to a utility: a command is admitted when its command line states what it does.
The conditions on the reader close the routes by which a named reader still runs its input, each confirmed on 2026-10-15:

- A pipe hands the body to the next program, as `cat <<EOF | sh` does.
- `env -S'sh -s' tee` runs a shell that reads the body.
- `GIT_EDITOR=sh`, `git -c core.editor=sh`, and `git commit -e` open the message in a program that may run it.
- An assignment such as `PATH=` in the reader's own segment picks which binary runs.
  An `export PATH=` in an earlier segment is not read here; the same command on one line proceeds too, so the multi-line form adds no route.
- A gh alias or extension may run a shell; gh does not let an alias replace `pr` or `issue`.

If bash would expand any part of a body, the body is an unresolvable word, like any other.

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

- **GIVEN** a Bash tool call pipes text that names a guarded path into a shell, such as `echo 'rm ~/.claude/settings.json' | sh`, or the same through a group, subshell, or loop on either side of the pipe
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

- **GIVEN** a Bash tool call written across lines
- **WHEN** the command is judged
- **THEN** the decision and its reason are the ones the same command on one line reaches

#### Scenario: AHereDocumentReadAsDataIsNotJudged

- **GIVEN** a command whose here-document is read by a recognized read such as `cat`, or by `git commit -F -`, `git tag -F -`, `gh pr` or `gh issue` with `--body-file -`, or `tee`, as the first word of a segment that does not pipe
- **WHEN** the body names a guarded path as text
- **THEN** the body is not judged, and the command reaches the verdict its own words and redirections reach

#### Scenario: AHereDocumentReadByAnyOtherProgramIsProgramText

- **GIVEN** a here-document read by a shell, an interpreter, `xargs`, `sudo sh`, `source /dev/stdin`, `sed -f -`, `git apply`, a read that takes file names, arguments, or a program from its input such as `jq -f /dev/stdin`, `strings @/dev/stdin`, or `file -f -`, or any program not named as a data reader
- **WHEN** the body names a guarded path
- **THEN** the gate applies, as it does for `bash -c` with the same text, and a block path in the body refuses the command

#### Scenario: ANamedReaderThatMayRunItsInputFallsBack

- **GIVEN** a data reader that pipes into another program, directly or from inside a group, subshell, or loop that pipes, runs as a coprocess, follows a wrapper such as `env -S`, follows an assignment such as `GIT_EDITOR=sh`, follows an earlier definition of its name as a function or a `hash -p` of it, or is `git` with `-c` or `-e`
- **WHEN** its here-document names a guarded path
- **THEN** the gate applies, and a block path in the body refuses the command
