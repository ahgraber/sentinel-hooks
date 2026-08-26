# Delta for git-baseline-drift

## ADDED Requirements

### Requirement: BaselineCapture

At the start of each agent turn, the hook SHALL record the current HEAD commit as the session baseline when the working directory is within a git repository.

Serves: drift-awareness

#### Scenario: GitRepository

- **GIVEN** a UserPromptSubmit event fires and the session working directory is within a git repository
- **WHEN** the init stage runs
- **THEN** a baseline file is written to the per-worktree git directory containing the current HEAD SHA

#### Scenario: NonGitDirectory

- **GIVEN** a UserPromptSubmit event fires and the session working directory is not within a git repository
- **WHEN** the init stage runs
- **THEN** no file is written and the hook exits 0 with no output

### Requirement: DriftWarning

Before any tool call in {Bash, Write, Edit, apply_patch}, the hook SHALL inject model-visible context describing the HEAD displacement when and only when the current HEAD commit differs from the session baseline.

Serves: drift-awareness

#### Scenario: NoDrift

- **GIVEN** a qualifying tool call is about to execute
- **WHEN** the check stage runs and the current HEAD matches the session baseline
- **THEN** the hook exits 0 with no output

#### Scenario: DriftDetected

- **GIVEN** a qualifying tool call is about to execute
- **WHEN** the check stage runs and the current HEAD differs from the session baseline
- **THEN** the hook exits 0 and writes JSON to stdout injecting model context that includes the abbreviated SHA before and after the move and the current branch name

### Requirement: DriftWarningPersistence

The hook SHALL inject a drift warning before each qualifying tool call for as long as the current HEAD differs from the session baseline; the warning SHALL NOT be suppressed after its first occurrence.

Serves: drift-awareness

#### Scenario: RepeatedWarning

- **GIVEN** the session baseline records HEAD=A and the current HEAD has moved to HEAD=B by an external actor
- **WHEN** two consecutive qualifying tool calls execute without an intervening Bash command
- **THEN** the drift warning is injected before both tool calls

#### Scenario: WarningClearedAfterBash

- **GIVEN** the session baseline records HEAD=A and the current HEAD is HEAD=B
- **WHEN** a Bash command executes (advancing the baseline to B) and a qualifying tool call then executes
- **THEN** no drift warning is injected before the subsequent qualifying tool call

### Requirement: BaselineAdvancement

After any agent-run Bash command completes, the session baseline SHALL reflect the current HEAD commit.

Serves: drift-awareness

#### Scenario: BashAdvancesBaseline

- **GIVEN** a Bash tool call completes in a session whose working directory is within a git repository
- **WHEN** the update stage runs
- **THEN** the baseline file is overwritten with the current HEAD SHA

### Requirement: BaselineScoping

The session baseline SHALL be scoped to a single session within a single worktree; baseline state SHALL NOT be shared across different sessions or across different worktrees of the same repository.

Serves: drift-awareness

#### Scenario: SameSession

- **GIVEN** a single agent session is active
- **WHEN** the init, check, and update stages run within that session
- **THEN** all stages read and write the same baseline file

#### Scenario: ConcurrentSessions

- **GIVEN** two agent sessions with different session IDs are active in the same worktree simultaneously
- **WHEN** each session's init stage writes its baseline
- **THEN** each session writes to a distinct file and neither session's baseline read is affected by the other's write

#### Scenario: ConcurrentWorktrees

- **GIVEN** two git worktrees of the same repository each have an active agent session
- **WHEN** each session's init stage writes its baseline
- **THEN** each session writes to a path within its own worktree's git directory, and the two files are at distinct paths

### Requirement: SessionIdSafety

The baseline filename SHALL be safe for use as a filesystem path component regardless of the characters present in the session ID.

Serves: drift-awareness

#### Scenario: AlphanumericId

- **GIVEN** a session ID consisting only of alphanumeric characters and dashes
- **WHEN** the baseline file path is constructed
- **THEN** the session ID is used as-is in the filename

#### Scenario: SpecialCharId

- **GIVEN** a session ID containing characters outside the alphanumeric-and-dash set
- **WHEN** the baseline file path is constructed
- **THEN** each such character is replaced with a dash before the filename is constructed

### Requirement: FailSilent

The hook SHALL exit 0 and emit no output when the working directory is not a git repository, when no session baseline file exists, or when any internal error occurs.

Serves: drift-awareness

#### Scenario: NonGitDirectory

- **GIVEN** the hook runs and the working directory is not within a git repository
- **WHEN** any stage executes
- **THEN** the hook exits 0 with no stdout or stderr output

#### Scenario: NoBaseline

- **GIVEN** the check or update stage runs and no baseline file exists for the current session
- **WHEN** the stage executes
- **THEN** the hook exits 0 with no stdout or stderr output

#### Scenario: InternalError

- **GIVEN** an unhandled exception occurs during hook execution
- **WHEN** the exception propagates to the outermost handler
- **THEN** the hook exits 0 with no stdout or stderr output
