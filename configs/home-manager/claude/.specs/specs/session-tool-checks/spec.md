# Spec: session-tool-checks

## Requirement: SessionStartHook

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
`jq` is required by bash-based hooks (`block-dangerous-bash.sh`, `bash-command-validator.sh`) for JSON input parsing.

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
`perl` is required by `block-dangerous-bash.sh` for PCRE pattern matching.

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
Gitleaks is the primary secret detection engine for `secret-access-blocking`.

#### Scenario: GitleaksPresent

- **GIVEN** a new session starts
- **WHEN** `gitleaks` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: GitleaksMissing

- **GIVEN** a new session starts
- **WHEN** `gitleaks` is not found on `PATH`
- **THEN** the hook prints a warning to stderr and exits 0 (session proceeds; secret detection falls back to built-in patterns with reduced coverage)

### Requirement: ChecksAreIndependent

Each tool check SHALL be evaluated independently.
A missing optional tool SHALL NOT prevent the session from starting if no hook requires it.
A missing required tool SHALL block the session with a clear message identifying the tool and install instructions.
