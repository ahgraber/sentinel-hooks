# Delta for hook-interface

## ADDED Requirements

### Requirement: StdinContract

The system SHALL read a JSON object from stdin containing at minimum `tool_name` (string) and `tool_input` (object).

#### Scenario: WellFormedInput

- **GIVEN** a hook is invoked by Claude Code
- **WHEN** the hook reads stdin
- **THEN** it receives a JSON object with `tool_name` and `tool_input` fields

#### Scenario: MalformedInput

- **GIVEN** a hook is invoked with missing or unparsable JSON on stdin
- **WHEN** the hook attempts to parse input
- **THEN** the hook applies `ErrorHandlingByDamagePotential`: if the hook only handles sensitive tools (`Bash`, `Write`, `Edit`), it exits 2 (fail-closed); if the hook handles read-only tools or all tools, it exits 0 (fail-open)

Note: a hook that handles multiple tool types (e.g., `Bash|Write|Edit` or all tools) cannot determine the tool name from malformed input. Such hooks SHALL exit 0 on parse failure, since failing closed would block read-only tools. Hooks that exclusively handle sensitive tools (e.g., `dangerous-bash-blocking` which only handles `Bash`) SHALL exit 2 on parse failure.

### Requirement: ExitCodes

The system SHALL communicate its decision to Claude Code via exit code and, where applicable, JSON written to stdout.

Three outcomes are defined:

**Allow** — exit 0, no stdout output.
The tool proceeds normally.

**Block** — exit 2, explanation written to stderr.
The tool is hard-blocked with no path to proceeding in the current invocation.

**Ask** — exit 0, JSON written to stdout with `permissionDecision: "ask"`.
Claude Code shows the user a permission dialog (approve once / always allow / deny).
This is the correct mechanism for potentially-dangerous operations where user confirmation is sufficient.

The `ask` JSON output format:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "<explanation \u2014 see ExplanationContract>"
  }
}
```

### Requirement: ExplanationContract

Every block or ask response SHALL include an explanation that contains:

1. **What the operation does** — a plain-language description of the matched command's purpose and effect
2. **Why it was blocked or flagged** — the security or safety reason (e.g., "irreversibly rewrites git history", "may expose credentials over the network")

The explanation SHALL be written for the user, not for the hook implementer.
It SHALL NOT be a raw regex pattern or an internal rule identifier.

#### Scenario: BlockExplanation

- **GIVEN** a hook exits 2
- **WHEN** the user reads the stderr output
- **THEN** they understand both what the command would have done and why it was stopped

#### Scenario: AskExplanation

- **GIVEN** a hook exits 0 with `permissionDecision: "ask"`
- **WHEN** the user reads the dialog reason
- **THEN** they understand both what the command will do and why confirmation is required

#### Scenario: Allow

- **GIVEN** no blocking or ask condition is matched
- **WHEN** the hook finishes evaluation
- **THEN** the hook exits 0 with no stdout output

#### Scenario: Block

- **GIVEN** a hard-block condition is matched
- **WHEN** the hook finishes evaluation
- **THEN** the hook exits 2 and writes a human-readable reason to stderr

#### Scenario: Ask

- **GIVEN** a confirmation-required condition is matched
- **WHEN** the hook finishes evaluation
- **THEN** the hook exits 0 and writes the ask JSON to stdout; Claude Code presents a permission dialog to the user

### Requirement: ErrorHandlingByDamagePotential

The system SHALL handle internal errors differently based on the damage potential of the tool being evaluated.

**Sensitive tools** (`Bash`, `Write`, `Edit`) — tools that can modify state, destroy data, or transmit information.
On internal error, the hook SHALL exit 2 (fail-closed).
An unhandled crash in a hook guarding a destructive tool must not silently allow the operation.

**Read-only tools** (`Read`, `Glob`, `Grep`) — tools that cannot modify state.
On internal error, the hook SHALL exit 1 (error logged, tool proceeds).
Blocking a read on a hook crash is unnecessarily disruptive.

#### Scenario: InternalErrorOnSensitiveTool

- **GIVEN** an unhandled error occurs inside the hook
- **WHEN** the tool being evaluated is `Bash`, `Write`, or `Edit`
- **THEN** the hook exits 2 (fail-closed — block rather than risk allowing a destructive operation)

#### Scenario: InternalErrorOnReadOnlyTool

- **GIVEN** an unhandled error occurs inside the hook
- **WHEN** the tool being evaluated is `Read`, `Glob`, or `Grep`
- **THEN** the hook exits 1 (fail-open — allow with error logged, since reads cannot cause damage)

### Requirement: NoSideEffects

The system SHALL NOT write to disk, spawn background processes, or make network calls during hook execution.

### Requirement: ToolNameFiltering

The system SHALL exit 0 immediately when invoked for a tool name the hook does not handle.
