# Delta Spec: hook-tampering-blocking (shared-hook-contracts)

> Source files: modules/home/ai/shared/.specs/specs/hook-tampering-blocking/spec.md

---

## MODIFIED Requirement: PathSpellingIndependence

The system SHALL determine whether a path denotes a protected location according to `path-matching`.

The limits recorded there apply here unchanged: a working-directory change within a single shell command, hard links, and any route that does not present a path.

A spelling that differs only in letter case is no longer a limit where the filesystem treats such spellings as the same file.

### Scenario: CaseVariantSpelling

- **GIVEN** a Write, Edit, or Bash tool call is intercepted on a case-insensitive filesystem
- **WHEN** the target names a protected path under a differing letter case
- **THEN** the hook exits 2

---

## MODIFIED Requirement: FailureMode

The system SHALL let a tool call proceed when it cannot judge it.

Where the tool is one this hook does not cover, the decision is `Allow`.

Where the payload does not parse, the decision is `Warn`.
The tool call still proceeds, but a hook that silently checks nothing is how a change to the agent harness goes unnoticed.
The encoding of `Warn` is agent-specific, per `hook-interface` `ExitCodes`; exiting 0 is its degraded form, not the contract.

Neither SHALL apply to a path that cannot be resolved.
Such a path is judged from the path as written, per `path-matching` `UnresolvablePathIsGuarded`.

### Scenario: UnresolvableProtectedPath

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** the target cannot be resolved but as written denotes a protected path
- **THEN** the hook exits 2

---

## MODIFIED Requirement: ProtectedSurface

The system SHALL protect the same surface regardless of which agent is running.

Every agent SHALL enforce every agent's protected set.
An agent that enforces only its own set leaves the others writable from a session it controls, and those others constrain it the moment they run.

Consolidating enforcement removes the prior condition where a correction reached one agent's implementation and not the others.

### Scenario: AgentEditsOtherAgentGuardrail

- **GIVEN** any agent is running
- **WHEN** a tool call would modify a different agent's protected path
- **THEN** the hook exits 2

---

## MODIFIED Requirement: BlockResponse

A block SHALL exit 2 and write an explanation to stderr that satisfies the `hook-interface` `ExplanationContract`.

The explanation SHALL name the specific path or command that was refused.
It SHALL NOT be required to name which agent owns the refused path, because enforcement no longer varies by agent.

---

## MODIFIED Requirement: MutationIsBlocked

The system SHALL block any tool call that would create, modify, delete, or rename a protected path.

This covers direct file writes, patch application, and shell commands.
A shell command SHALL be judged by the paths it names, because a command is capable of every mutation a file tool is.

A path a command supplies as the operand of shell syntax SHALL count as a path the command names, whether or not a space separates the two.
Shell syntax written against its operand is the same instruction as the spaced form, so a difference in verdict between the two is a difference the writer chooses.

### Scenario: OperandAttachedToShellSyntax

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command carries a protected path as an operand written against a redirection or an option
- **THEN** the hook exits 2

---

## MODIFIED Requirement: InstructionTextIsWritable

The system SHALL permit writes to instruction markdown files held directly in an agent's instructions directory.

These files are prompt text supplied to the agent, not enforcement.
Blocking them would prevent ordinary authoring for no security gain.

The exemption SHALL be narrow.
It SHALL apply only to markdown files, and only to files directly in an instructions directory — not to a nested path, and not to any other file type held there.
A shell command SHALL qualify for the exemption only when every protected path it names qualifies.

The exemption SHALL be decided by the location the write lands on, not by the name the target is given.
A write to a link is a write to what the link leads to, so a name that qualifies for the exemption does not make the write qualify.

### Scenario: ExemptNameLeadingToEnforcement

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** the target is named as markdown directly in an instructions directory but leads to an enforcement file
- **THEN** the hook exits 2
