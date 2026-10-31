# Delta Spec: bash-command-validator — pytest-uv-run-rule

## ADDED Requirements

### Requirement: RedirectPytestToUv

The system SHALL redirect bare `pytest` and `py.test` invocations to `uv run pytest`.

A bare invocation is one where `pytest` or `py.test` is not preceded by `uv run`.

#### Scenario: BarePytestRedirected

- **GIVEN** a Bash tool call invokes `pytest` directly (not preceded by `uv run`)
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `uv run pytest` instead

#### Scenario: BarePyTestAliasRedirected

- **GIVEN** a Bash tool call invokes `py.test` directly (not preceded by `uv run`)
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `uv run pytest` instead

#### Scenario: UvRunPytestAllowed

- **GIVEN** a Bash tool call invokes `uv run pytest`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0 (uv-prefixed invocation is not redirected)

#### Scenario: UvRunPyTestAliasAllowed

- **GIVEN** a Bash tool call invokes `uv run py.test`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0 (uv-prefixed invocation is not redirected)
