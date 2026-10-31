# end-of-turn-precommit Specification

## Purpose

An agent can end a turn with files that fail the project's formatting and lint checks, and the user then meets the failures later, away from the turn that caused them.
These requirements cover when the end-of-turn check runs, which files it checks, when it does nothing, and how a failure stops the turn once.

## Requirements

### Requirement: RunsAtEndOfTurn

The system SHALL run the repository's pre-commit configuration over the files a turn changed, once the agent has finished the turn.
The run needs `prek` or `pre-commit` on the path; where neither is installed, the turn ends with no run and no message.

Running per edit fires autofixers mid-sequence, which removes an import or a binding before the first use of it lands, and never sees a file written by a shell command rather than by a file tool.

#### Scenario: PassingRunIsSilent

- **GIVEN** a turn ends with changed files in a repository configured for pre-commit
- **WHEN** the run succeeds
- **THEN** the turn ends with no output

### Requirement: ChangedFileSelection

The system SHALL select the files the turn changed: each file whose content differs between the working tree at the turn's start and at its end, whatever its tracking state.
It SHALL exclude files the run cannot act on.
Where no snapshot of the turn's start exists, it SHALL select every file the working tree presents as changed.
A file changed before the turn is not the turn's to fix, and checking it can block a turn on work the agent did not do.

A file's tracking state does not determine whether a linter should see it; whether the file exists and is not ignored does.

#### Scenario: FileChangedBeforeTheTurn

- **GIVEN** a file was modified before the turn started and the turn did not change it
- **WHEN** the turn ends
- **THEN** the file does not reach the runner

#### Scenario: TurnThatChangesNothing

- **GIVEN** the working tree holds uncommitted changes from before the turn, and the turn changes no file
- **WHEN** the turn ends
- **THEN** the runner does not run

#### Scenario: ModifiedTrackedFile

- **GIVEN** a tracked file has uncommitted modifications
- **WHEN** the turn ends
- **THEN** the file is passed to the runner

#### Scenario: UntrackedFile

- **GIVEN** a file is new and untracked
- **WHEN** the turn ends
- **THEN** the file is passed to the runner

#### Scenario: StagedFile

- **GIVEN** a file is staged
- **WHEN** the turn ends
- **THEN** the file is passed to the runner

#### Scenario: IgnoredFile

- **GIVEN** a changed file matches the repository's ignore rules
- **WHEN** the turn ends
- **THEN** the file is not passed to the runner

#### Scenario: DeletedFile

- **GIVEN** a file was deleted during the turn
- **WHEN** the turn ends
- **THEN** the path is not passed to the runner

#### Scenario: RepositoryWithNoCommits

- **GIVEN** a repository with no `HEAD`
- **WHEN** the turn ends
- **THEN** the staged files and the untracked files are the changed set

### Requirement: NoWorkMeansNoRun

Where there is nothing to check, the system SHALL do nothing and SHALL NOT report.

The hook fires on every turn of every session, so any output it produces where no check was possible is noise the agent must read and discard.

#### Scenario: OutsideARepository

- **GIVEN** the turn ended outside a git repository
- **WHEN** the hook runs
- **THEN** it does nothing

#### Scenario: NoPreCommitConfiguration

- **GIVEN** a repository with no pre-commit configuration
- **WHEN** the turn ends
- **THEN** the hook does nothing

#### Scenario: NoChangedFiles

- **GIVEN** a repository whose working tree is clean
- **WHEN** the turn ends
- **THEN** the hook does nothing

#### Scenario: UnresolvableWorkingDirectory

- **GIVEN** the payload names a working directory that cannot be resolved
- **WHEN** the hook runs
- **THEN** it judges the directory the process is in rather than reporting a failure

### Requirement: FailureBlocksTheTurnOnce

A failing run SHALL block the end of the turn and SHALL return its output to the agent, and the block SHALL happen at most once per turn.

An agent that can be blocked repeatedly on the same run cannot end the turn, so the second block is a loop rather than a correction.

#### Scenario: FailingRunBlocks

- **GIVEN** a turn ends with changed files that fail the run
- **WHEN** the hook evaluates the result
- **THEN** the turn is blocked and the run's output reaches the agent

#### Scenario: SecondPassAfterABlock

- **GIVEN** the turn was already blocked once by this hook
- **WHEN** the turn ends again
- **THEN** the hook does not run and the turn proceeds
