# Delta for sensitive-path-blocking

## MODIFIED Requirements

### Requirement: ToolScope

The system SHALL evaluate tool calls when `tool_name` is `Bash`, `Read`, `Write`, or
`Edit`. (Previously: `Bash`, `Write`, or `Edit` only. `Read` was not evaluated, leaving
zero-access paths readable via the dedicated Read tool despite sandbox `denyRead` rules.)

Because the hook now handles a mix of sensitive tools (`Bash`, `Write`, `Edit`) and a read-only tool (`Read`), it cannot determine the tool type on a JSON parse failure.
The system SHALL exit 0 on parse failure (fail-open), per `hook-interface` `ErrorHandlingByDamagePotential`. (Previously: exit 2 on parse failure, since all handled tools were sensitive.)

## ADDED Requirements

### Requirement: BlockReadFromZeroAccessPath

The system SHALL block `Read` tool calls whose `file_path` matches any zero-access path
pattern defined in `ZeroAccessPaths`.

Reading zero-access paths exposes secret material to Claude's context window.
A subsequent operation — network call, file write, or command — could then transmit that material without a further confirmation opportunity.
Hard-blocking the read prevents the secret from entering context at all.

#### Scenario: ReadSshKey

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` is within `~/.ssh/`
- **THEN** the hook exits 2

#### Scenario: ReadEnvFile

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` matches a dot-env pattern (`.env`, `.env.*`, `.envrc`)
- **THEN** the hook exits 2

#### Scenario: ReadPemFile

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` has a zero-access extension (`.pem`, `.key`, `.p12`, etc.)
- **THEN** the hook exits 2

#### Scenario: ReadCredentialNamedFile

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` basename matches `credentials` or `secret` (case-insensitive)
  and the path is not within a package directory
- **THEN** the hook exits 2

#### Scenario: ReadCredentialNamedFileInVenv

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` basename matches `credentials` or `secret` but the path
  contains `.venv/` or `site-packages/`
- **THEN** the hook exits 0 (package-dir exemption applies)
