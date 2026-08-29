# Delta Spec: hook-interface (shared-hook-contracts)

> Source files: modules/home/ai/shared/.specs/specs/hook-interface/spec.md

---

## MODIFIED Requirement: ExitCodes

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

### Scenario: WarnOnAgentThatSupportsIt

- **GIVEN** a hook reaches a `Warn` decision
- **WHEN** the invoking agent can report a reason without refusing the tool call
- **THEN** the tool call proceeds and the reason is shown to the user

#### Scenario: WarnOnAgentThatDoesNot

- **GIVEN** a hook reaches a `Warn` decision
- **WHEN** the invoking agent has no encoding that both proceeds and reports
- **THEN** the tool call proceeds and nothing is reported

---

## ADDED Requirement: AgentIdentification

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

### Scenario: AgentCannotBeEstablished

- **GIVEN** a hook reaches a decision that needs a prompt
- **WHEN** the invoking agent cannot be identified
- **THEN** the tool call is refused rather than allowed unprompted

---

## MODIFIED Requirement: ErrorHandlingByDamagePotential

The system SHALL handle internal errors differently based on the damage potential of the tool being evaluated, as previously specified.

That guarantee SHALL be stated as conditional.
It holds only for errors the hook reaches and handles.

A failure that prevents the hook from running at all — an interpreter that cannot start, a script that is absent or unreadable — produces an outcome the agent encodes, not the hook.
At least one agent refuses the tool call on any such failure.
The stated fail-open posture therefore does not hold uniformly for startup failures, and SHALL NOT be represented as if it did.

### Scenario: HookCannotStart

- **GIVEN** a hook is registered but cannot be executed
- **WHEN** a tool call is intercepted
- **THEN** the outcome is determined by the invoking agent, and may be either allow or deny depending on the agent
