# Delta Spec: hook-interface (guardrail-ask-gate)

> Source files: modules/home/ai/shared/.specs/specs/hook-interface/spec.md

---

## MODIFIED Requirements

### Requirement: ExitCodes

Serves: safe-degradation

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

Where an agent cannot express `Ask`, the system SHALL degrade it to `Block`, never to `Allow`.
An ask records that the call must not proceed on the agent's judgement alone; refusing keeps that property where no prompt can be shown.

An agent that accepts the prompt encoding without honouring it SHALL be treated as unable to express `Ask`.
One agent parses the prompt JSON, marks the hook run failed, and lets the tool call proceed.
Emitting the prompt encoding to such an agent converts a gate into an allow, which is the one degradation direction this requirement forbids.

Honouring MAY differ by tool within one agent, so the judgement SHALL be made per tool surface, not per agent alone.
One agent holds a file edit on the prompt and lets a shell command proceed past the same JSON; the encoding is emitted for the first and withheld for the second.

> Previously: `Ask` had a single encoding, defined for Claude Code alone, and no degradation was specified because no other agent was asked to express it.

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

Under Copilot, `Ask` is honoured for file-mutation tools only, as exit 0 with the same `hookSpecificOutput` JSON Claude Code uses; the surface shows the reason and holds the call.
For the shell tool the same output is ignored and the call proceeds, so `Ask` degrades to `Block` there.
Where the surface has no interactive user, the platform itself treats the prompt as a denial, which is the degradation direction this requirement requires.
Established empirically on 2026-08-27; the probe record in the change's `.verify/` directory is the evidence.

#### Scenario: WarnOnAgentThatSupportsIt

- **GIVEN** a hook reaches a `Warn` decision
- **WHEN** the invoking agent can report a reason without refusing the tool call
- **THEN** the tool call proceeds and the reason is shown to the user

#### Scenario: WarnOnAgentThatDoesNot

- **GIVEN** a hook reaches a `Warn` decision
- **WHEN** the invoking agent has no encoding that both proceeds and reports
- **THEN** the tool call proceeds and nothing is reported

#### Scenario: AskOnAgentThatPrompts

- **GIVEN** a hook reaches an `Ask` decision
- **WHEN** the invoking agent can put a per-call decision to the user
- **THEN** the prompt encoding is emitted, and the tool call proceeds only on the user's approval

#### Scenario: AskOnAgentThatCannotPrompt

- **GIVEN** a hook reaches an `Ask` decision
- **WHEN** the invoking agent has no honoured prompt encoding
- **THEN** the tool call is refused with an explanation, exactly as a `Block` would be

#### Scenario: AskEncodingWithheldWhereUnhonoured

- **GIVEN** a hook reaches an `Ask` decision
- **WHEN** the invoking agent parses the prompt encoding but lets the tool call proceed on it
- **THEN** the refusal encoding is emitted instead, and the prompt JSON is never written

---

### Requirement: NoSideEffects

Serves: contract-states-its-property

A hook SHALL NOT, while judging a tool call, modify the state it is judging, spawn background processes, or make network calls.

Reading is unrestricted.
A hook that cannot read its own declarations cannot judge anything, and concealment is not the boundary these hooks defend.

Interpreter-managed derived data, such as a bytecode cache, is not a modification of that state and SHALL NOT be treated as one.
Suppressing it does not defend the guarded surface: the interpreter loads an existing cache entry whether or not the current process is permitted to write one, so a planted entry executes either way, and what prevents that is the directory's write protection at the permission, sandbox, and tamper layers.

This binds a hook at invocation.
It does not bind test or tooling code that imports the same modules outside the tool-call path.
Read as a blanket prohibition on writing to disk, the requirement is applied wherever the mechanism appears rather than where the boundary is at stake, and cost is spent where no protection is bought.

#### Scenario: HookDoesNotAlterWhatItJudges

- **GIVEN** a hook is judging a tool call
- **WHEN** it reaches its decision
- **THEN** the paths and payload it judged are unchanged, and no process or connection outlives it

#### Scenario: InterpreterDerivedData

- **GIVEN** a hook or a test imports a hook module
- **WHEN** the interpreter caches bytecode beside that module
- **THEN** this requirement is not violated

> Previously: the requirement prohibited writing to disk outright. Applied to
> bytecode caching, that bought no protection — a planted cache entry is loaded
> regardless of the setting — while making ordinary imports look like breaches.
