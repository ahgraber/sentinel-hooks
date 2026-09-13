# Spec: bash-command-validator

## Requirements

### Requirement: ToolScope

The system SHALL only evaluate commands when `tool_name` is `Bash`.

### Requirement: ReviewHeredocsForBangHistory

The system SHALL block heredoc syntax (`<<`) so the agent can verify that zsh `BANG_HIST` will not alter the body.

#### Scenario: HeredocBlocked

- **GIVEN** a Bash tool call contains heredoc syntax
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with guidance about zsh `BANG_HIST`

#### Scenario: HereStringAllowed

- **GIVEN** a Bash tool call contains a here-string (`<<<`)
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0

### Requirement: RejectZshExpansionHazards

The system SHALL block command text that is vulnerable to zsh history expansion,
extended globbing, or unsafe wildcard expansion.

#### Scenario: BangHistoryHazardBlocked

- **GIVEN** a Bash tool call contains an unsafe bang in a double-quoted string or an
  unquoted history reference
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with quoting guidance

#### Scenario: UnquotedFlakeReferenceBlocked

- **GIVEN** a Bash tool call contains an unquoted Nix flake reference such as `.#host`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with guidance to quote the reference

#### Scenario: GitParentCaretBlocked

- **GIVEN** a Bash tool call places `^` after a hexadecimal Git object ID
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a safe alternative

#### Scenario: UnquotedFlagGlobBlocked

- **GIVEN** a Bash tool call contains an unquoted wildcard value such as `--glob=*.py`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with guidance to quote the value

#### Scenario: NixStoreGlobBlocked

- **GIVEN** a Bash tool call contains `/nix/store/*`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with guidance to use a deterministic path

### Requirement: RejectRipgrepRecursiveFlag

The system SHALL reject `r` in a ripgrep short-option bundle because ripgrep is recursive
by default and interprets `-r` as `--replace`.

#### Scenario: RecursiveFlagBlockedInAnyBundlePosition

- **GIVEN** a Bash tool call invokes `rg` with `r` anywhere in a short-option bundle
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with guidance to remove `r`

### Requirement: RedirectPythonToUv

The system SHALL redirect direct `python` or `python3` invocations to `uv run`.

A direct invocation is one that appears at the start of a command or after a command separator
(`; | & ( )`), optionally preceded by environment variable assignments.

#### Scenario: DirectPythonRedirected

- **GIVEN** a Bash tool call invokes `python` or `python3` directly
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `uv run` instead

### Requirement: RedirectPipToUv

The system SHALL redirect `pip install`, `pip uninstall`, `pip download`, and their `pip3`
equivalents to `uv add` or `uv run --with`.

#### Scenario: PipInstallRedirected

- **GIVEN** a Bash tool call invokes `pip install` or `pip3 install`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `uv add` instead

### Requirement: RedirectPytestToUv

The system SHALL redirect bare `pytest` and `py.test` invocations to `uv run pytest`.

A bare invocation is one where `pytest` or `py.test` is not preceded by `uv run` and
not embedded inside a longer word token.

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

### Requirement: RedirectPreCommitToPrek

The system SHALL redirect `pre-commit run` invocations to `prek run`.

`prek` is the sandbox-compatible wrapper for `pre-commit` available in PATH.

#### Scenario: PreCommitRedirected

- **GIVEN** a Bash tool call invokes `pre-commit run`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `prek run` instead

### Requirement: RequireAgentCommitAlias

The system SHALL block `commit` when it is the Git subcommand and require use of the `git agent-commit` alias.

`git agent-commit` is the designated alias for AI agents; it signs with the dedicated agent key
(`~/.local/share/git-signing/agent-signing`) without requiring additional flags.

#### Scenario: DirectGitCommitBlocked

- **GIVEN** a Bash tool call contains `git commit` in any form (with or without flags)
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 with a message directing the AI to use `git agent-commit`

#### Scenario: AgentCommitAliasAllowed

- **GIVEN** a Bash tool call invokes `git agent-commit`
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0

#### Scenario: CommitConfigKeyAllowed

- **GIVEN** a Bash tool call contains `commit` in a Git configuration key but uses another
  Git subcommand
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0

#### Scenario: CommitTextInArgumentAllowed

- **GIVEN** a Bash tool call contains `git commit` as an argument to another command
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 0

### Requirement: ReportAllIssues

The system SHALL report every matching validation issue in one response.

#### Scenario: MultipleIssuesReported

- **GIVEN** a Bash tool call violates more than one registered rule
- **WHEN** the hook evaluates the command
- **THEN** the hook exits 2 and emits guidance for every matching rule

### Requirement: RuleRegistrationPattern

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
