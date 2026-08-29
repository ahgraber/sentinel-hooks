# Spec: hook-interface

## Requirement: StdinContract

The system SHALL read a JSON object from stdin containing at minimum `tool_name` (string) and `tool_input` (object).

### Scenario: WellFormedInput

- **GIVEN** a hook is invoked by Claude Code
- **WHEN** the hook reads stdin
- **THEN** it receives a JSON object with `tool_name` and `tool_input` fields

#### Scenario: MalformedInput

- **GIVEN** a hook is invoked with missing or unparsable JSON on stdin
- **WHEN** the hook attempts to parse input
- **THEN** the hook applies `ErrorHandlingByDamagePotential`: if the hook only handles sensitive tools (`Bash`, `Write`, `Edit`), it exits 2 (fail-closed); if the hook handles read-only tools or all tools, it exits 0 (fail-open)

Note: a hook that handles multiple tool types (e.g., `Bash|Write|Edit` or all tools) cannot determine the tool name from malformed input.
Such hooks SHALL exit 0 on parse failure, since failing closed would block read-only tools.
Hooks that exclusively handle sensitive tools (e.g., `dangerous-bash-blocking` which only handles `Bash`) SHALL exit 2 on parse failure.

### Requirement: ExitCodes

The system SHALL express its outcome as one of four decisions:

- **Allow** — the tool call proceeds, with nothing reported.
- **Warn** — the tool call proceeds, and the reason is made visible.
- **Block** — the tool call is refused.
- **Ask** — the user is prompted to decide.

A decision is the shared vocabulary.
Its encoding is not.

Every hook SHALL reach its outcome through this vocabulary rather than by writing an exit code of its own.
A hook that encodes its own outcome carries its own copy of the explanation contract and its own view of what each agent understands, and those copies drift.

The system SHALL encode a decision according to the agent that invoked the hook.
The same exit code does not mean the same thing across the agents these hooks serve: one agent treats a non-zero, non-blocking code as "proceed, and show this to the user", and another refuses the tool call on any non-zero exit.
A hook that emits one code for all agents is therefore limited to the codes on which every agent already agrees, which is why `Warn` cannot be expressed today.

Where an agent cannot express `Warn`, the system SHALL degrade it to `Allow`, never to `Block`.
Degrading upward would convert a diagnostic into a refusal, and would refuse every tool call for as long as the condition persisted.

Under Claude Code the encoding is:

**Allow** — exit 0, no stdout output.
The tool proceeds normally.

**Warn** — exit 1, reason written to stderr.
The tool proceeds and the reason is shown to the user.

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

#### Scenario: WarnOnAgentThatSupportsIt

- **GIVEN** a hook reaches a `Warn` decision
- **WHEN** the invoking agent can report a reason without refusing the tool call
- **THEN** the tool call proceeds and the reason is shown to the user

#### Scenario: WarnOnAgentThatDoesNot

- **GIVEN** a hook reaches a `Warn` decision
- **WHEN** the invoking agent has no encoding that both proceeds and reports
- **THEN** the tool call proceeds and nothing is reported

### Requirement: AgentIdentification

The system SHALL determine which agent invoked it, and SHALL do so in one place.

Identification SHALL NOT require an addition to each agent's hook registration.
A registration is enforcement configuration, so every entry added to it is another place a rename can silently drop protection.

Hooks are deployed into a directory belonging to the invoking agent, so the invocation path is sufficient wherever it applies.
Two cases it does not cover, and which the same answer SHALL account for:

- **A hook reached through an adapter.**
  One agent dispatches to these scripts from outside its own hook directory.
  It SHALL name itself instead.
- **A payload that identifies its sender.**
  One agent sends a field no other sends.
  Hooks relied on this before identification was shared, and it remains the more direct evidence where it is present.

Where these disagree, the invocation path SHALL decide, because it reflects how the hook was deployed rather than what the caller claimed.

Where the agent cannot be established, the system SHALL treat it as one that supports neither warning nor prompting.
Both degrade safely: a warning becomes silence, and a prompt becomes a refusal.

#### Scenario: AgentCannotBeEstablished

- **GIVEN** a hook reaches a decision that needs a prompt
- **WHEN** the invoking agent cannot be identified
- **THEN** the tool call is refused rather than allowed unprompted

### Requirement: ExplanationContract

Every block or ask response SHALL include an explanation that contains:

1. **What the operation does** — a plain-language description of the matched command's or path's purpose and effect (e.g., "reads your SSH private key into Claude's context", "pipes your AWS credentials to a remote host")
2. **Why it is dangerous or suspicious** — the specific security risk this operation poses (e.g., "a private key in context can be incorporated into a subsequent command or network call without further confirmation", "credential files piped to remote hosts expose authentication material to third parties")

For `ask` responses, the explanation addresses the user only.

For `block` responses (exit 2), the stderr message SHALL contain two sections:

**Section 1 — Human explanation** (as above): addressed to the user, states what the operation would have done and why it was stopped.

**Section 2 — AI instruction block**: a delimited section that instructs the AI not to seek workarounds and directs it to surface a four-point report to the user (see `BlockAIGuidance`).

The AI instruction block SHALL begin with the exact delimiter `---` on its own line, followed by `AI INSTRUCTIONS:` on the next line.

The explanation SHALL be written for the user, not for the hook implementer.
It SHALL NOT be a raw regex pattern or an internal rule identifier.
It SHALL name the specific file or command where possible, not a generic category.

#### Scenario: AskExplanation

- **GIVEN** a hook exits 0 with `permissionDecision: "ask"`
- **WHEN** the user reads the dialog reason
- **THEN** they understand (a) what operation Claude is attempting, (b) what specific file or command is involved, and (c) what harm could result if the operation proceeds unchecked (e.g., credentials entering context, data reaching a remote host)

#### Scenario: BlockExplanation

- **GIVEN** a hook exits 2
- **WHEN** the user reads the stderr output
- **THEN** they understand both what the command would have done and why it was stopped, including the specific downstream risk; additionally, the AI receives explicit instruction not to seek workarounds and to surface the block context to the user

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

### Requirement: BlockAIGuidance

Every block response (exit 2) SHALL include a structured AI instruction section appended after the human explanation.

The purpose of this section is to prevent the AI from silently pivoting to a workaround after receiving a block, and to ensure the user is given enough context to make an informed decision about completing the action themselves.

The AI instruction section SHALL use this exact format:

```text
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
```

#### Scenario: BlockMessageFormat

- **GIVEN** a hook exits 2
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation section followed by a `---` delimiter, `AI INSTRUCTIONS:` header, a prohibition on workaround-seeking, and the four-point reporting directive

#### Scenario: AIDoesNotSeekWorkaround

- **GIVEN** the AI receives a block response with an AI instruction section
- **WHEN** the AI processes the tool result
- **THEN** it does NOT attempt alternative commands, equivalent operations, or any other substitutes for the blocked action

#### Scenario: AIReportsToUser

- **GIVEN** the AI receives a block response with an AI instruction section
- **WHEN** the AI presents the block to the user
- **THEN** its response includes: (1) what ongoing task it was performing, (2) what step it intended to take, (3) what was blocked and why, and (4) what the user could do manually and why they might want to

### Requirement: ErrorHandlingByDamagePotential

The system SHALL handle internal errors differently based on the damage potential of the tool being evaluated.

**Sensitive tools** (`Bash`, `Write`, `Edit`) — tools that can modify state, destroy data, or transmit information.
On internal error, the hook SHALL exit 2 (fail-closed).
An unhandled crash in a hook guarding a destructive tool must not silently allow the operation.

**Read-only tools** (`Read`, `Glob`, `Grep`) — tools that cannot modify state.
On internal error, the hook SHALL reach a `Warn` decision: the tool proceeds and the reason is reported where the agent can report it.
Blocking a read on a hook crash is unnecessarily disruptive.

This guarantee is conditional.
It holds only for errors the hook reaches and handles.

A failure that prevents the hook from running at all — an interpreter that cannot start, a script that is absent or unreadable — produces an outcome the agent encodes, not the hook.
At least one agent refuses the tool call on any such failure.
The stated fail-open posture therefore does not hold uniformly for startup failures, and SHALL NOT be represented as if it did.

#### Scenario: InternalErrorOnSensitiveTool

- **GIVEN** an unhandled error occurs inside the hook
- **WHEN** the tool being evaluated is `Bash`, `Write`, or `Edit`
- **THEN** the hook reaches `Block` (fail-closed — refuse rather than risk allowing a destructive operation)

#### Scenario: InternalErrorOnReadOnlyTool

- **GIVEN** an unhandled error occurs inside the hook
- **WHEN** the tool being evaluated is `Read`, `Glob`, or `Grep`
- **THEN** the hook reaches `Warn` (fail-open — the tool proceeds, and the reason is reported where the agent can report it)

#### Scenario: HookCannotStart

- **GIVEN** a hook is registered but cannot be executed
- **WHEN** a tool call is intercepted
- **THEN** the outcome is determined by the invoking agent, and may be either allow or deny depending on the agent

### Requirement: NoSideEffects

The system SHALL NOT write to disk, spawn background processes, or make network calls during hook execution.

### Requirement: ToolNameFiltering

The system SHALL exit 0 immediately when invoked for a tool name the hook does not handle.
