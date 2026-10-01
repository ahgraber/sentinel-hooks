# Delta for git-baseline-drift

## MODIFIED Requirements

### Requirement: DriftWarning

Serves: every-agent-carries-the-policy

Before any call to a tool in the declared `mutating` group, the hook SHALL inject model-visible context describing the HEAD displacement when and only when the current HEAD commit differs from the session baseline.

> Previously: the qualifying tools were listed here as {Bash, Write, Edit, apply_patch}, and an agent that registers hooks without a matcher ran the check stage before every call, reads included.

#### Scenario: NoDrift

- **GIVEN** a qualifying tool call is about to execute
- **WHEN** the check stage runs and the current HEAD matches the session baseline
- **THEN** the hook exits 0 with no output

#### Scenario: DriftDetected

- **GIVEN** a qualifying tool call is about to execute
- **WHEN** the check stage runs and the current HEAD differs from the session baseline
- **THEN** the hook exits 0 and writes JSON to stdout injecting model context that includes the abbreviated SHA before and after the move and the current branch name

#### Scenario: ReadDoesNotQualify

- **GIVEN** the current HEAD differs from the session baseline
- **WHEN** the agent makes a call to a tool outside the `mutating` group, such as a read
- **THEN** no drift warning is injected before that call
