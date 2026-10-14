# Spec: session-tool-checks

## Requirements

### Requirement: SessionStartHook

The system SHALL provide a SessionStart hook that verifies required security tools are available before a session proceeds.

### Requirement: UvAvailability

The system SHALL check that `uv` is available on `PATH` at session start.

#### Scenario: UvPresent

- **GIVEN** a new session starts
- **WHEN** `uv` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: UvMissing

- **GIVEN** a new session starts
- **WHEN** `uv` is not found on `PATH`
- **THEN** the hook exits 2 with a message explaining how to install `uv`

### Requirement: JqAvailability

The system SHALL check that `jq` is available on `PATH` at session start.
The security hooks require `jq`.

#### Scenario: JqPresent

- **GIVEN** a new session starts
- **WHEN** `jq` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: JqMissing

- **GIVEN** a new session starts
- **WHEN** `jq` is not found on `PATH`
- **THEN** the hook exits 2 with a message explaining that `jq` is required for security hooks

### Requirement: PerlAvailability

The system SHALL check that `perl` is available on `PATH` at session start.
The security hooks require `perl`.

#### Scenario: PerlPresent

- **GIVEN** a new session starts
- **WHEN** `perl` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: PerlMissing

- **GIVEN** a new session starts
- **WHEN** `perl` is not found on `PATH`
- **THEN** the hook exits 2 with a message explaining that `perl` is required for security hooks

### Requirement: GitleaksAvailability

The system SHALL check that `gitleaks` is available on `PATH` at session start.
Without gitleaks, `secret-access-blocking` detects fewer secret formats in network sends.

#### Scenario: GitleaksPresent

- **GIVEN** a new session starts
- **WHEN** `gitleaks` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: GitleaksMissing

- **GIVEN** a new session starts
- **WHEN** `gitleaks` is not found on `PATH`
- **THEN** the hook prints a warning to stderr and exits 0 (session proceeds)

### Requirement: ChecksAreIndependent

Each tool check SHALL be evaluated independently.
A missing optional tool SHALL NOT prevent the session from starting if no hook requires it.
A missing required tool SHALL block the session with a clear message identifying the tool and install instructions.
