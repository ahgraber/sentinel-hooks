# Delta Spec: bash-command-validator

## ADDED Requirement: ToolScope

The system SHALL only evaluate commands when `tool_name` is `Bash`.

## ADDED Requirement: RedirectGrepToRipgrep

The system SHALL redirect bare `grep` invocations to `rg` (ripgrep).

A bare `grep` invocation is one that is not part of a pipeline (i.e., not preceded by `|`).

### Scenario: BareGrepRedirected

- **GIVEN** a Bash tool call contains `grep` at the start of a command not preceded by a pipe
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `rg` instead

### Scenario: PipedGrepAllowed

- **GIVEN** a Bash tool call contains `grep` as part of a pipeline (e.g., `cat file | grep foo`)
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0 (piped grep is not redirected)

## ADDED Requirement: RedirectFindToRipgrep

The system SHALL redirect `find <dir> -name` invocations to `rg`.

### Scenario: FindNameRedirected

- **GIVEN** a Bash tool call contains `find <path> -name`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `rg --files` instead

## ADDED Requirement: RedirectPythonToUv

The system SHALL redirect direct `python` or `python3` invocations to `uv run`.

A direct invocation is one that appears at the start of a command or after a command separator
(`; | & ( )`), optionally preceded by environment variable assignments.

### Scenario: DirectPythonRedirected

- **GIVEN** a Bash tool call invokes `python` or `python3` directly
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `uv run` instead

## ADDED Requirement: RedirectPipToUv

The system SHALL redirect `pip install`, `pip uninstall`, `pip download`, and their `pip3`
equivalents to `uv add` or `uv run --with`.

### Scenario: PipInstallRedirected

- **GIVEN** a Bash tool call invokes `pip install` or `pip3 install`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `uv add` instead

## ADDED Requirement: RedirectPreCommitToPrek

The system SHALL redirect `pre-commit run` invocations to `prek run`.

`prek` is the sandbox-compatible wrapper for `pre-commit` available in PATH.

### Scenario: PreCommitRedirected

- **GIVEN** a Bash tool call invokes `pre-commit run`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `prek run` instead

## ADDED Requirement: RequireSignedCommits

The system SHALL block `git commit` invocations that do not include a signing flag.

A signing flag is one of:

- `-S` (standalone or combined with other short flags, e.g. `-aS`, `-Sa`)
- `--gpg-sign`

### Scenario: UnsignedCommitBlocked

- **GIVEN** a Bash tool call contains `git commit` without a signing flag
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `git commit -S`

### Scenario: SignedCommitAllowed

- **GIVEN** a Bash tool call contains `git commit -S` or `git commit --gpg-sign`
  or a combined flag such as `-aS`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0

## ADDED Requirement: RuleRegistrationPattern

The system SHALL define rules using a `rule` registration function that co-locates
each pattern with its corresponding message as a single declaration.

```bash
rule() {
  patterns+=("$1")
  messages+=("$2")
}
```

Each rule SHALL be declared as a single `rule 'pattern' 'message'` call.
Parallel arrays populated by index are NOT permitted.

This ensures that adding, removing, or reordering a rule is an atomic edit
with no risk of index desynchronisation between patterns and messages.
