# Spec: hook-tampering-blocking

## Requirement: Purpose

The system SHALL prevent an agent from modifying the files that constrain that agent's own behaviour, or any other agent's.

Every other guardrail in this repository depends on this one.
A hook script, a permission rule, or a hook registration file is enforcement.
An edit to enforcement is not a routine edit: it removes the constraint rather than changing a program.
The system therefore SHALL block such an edit unconditionally, and SHALL NOT offer the user an approval dialog for it.

Deliberate maintenance of a guardrail is a separate, out-of-band act.
It is the user's to perform, not the agent's to request.

### Requirement: ProtectedSurface

The system SHALL protect four classes of file:

- **Deployed enforcement** — the hook scripts, permission rules, and hook registrations that each agent loads at run time.
- **Repository sources** — the tracked files those deployed paths resolve to.
  The deployed paths are symlinks into this repository, so a write to a source is a write to the live guardrail.
  Protecting only the deployed path would be trivially sidestepped.
- **Per-user agent configuration** — every user's agent settings under `users/`, not only the user the agent is running as.
- **Agent credentials** — stored authentication material for any agent.

The system SHALL protect the same surface regardless of which agent is running.

Every agent SHALL enforce every agent's protected set.
An agent that enforces only its own set leaves the others writable from a session it controls, and those others constrain it the moment they run.

#### Scenario: AgentEditsOtherAgentGuardrail

- **GIVEN** any agent is running
- **WHEN** a tool call would modify a different agent's protected path
- **THEN** the hook exits 2

### Requirement: ReadsAreAllowed

The system SHALL allow reads of every protected path.

This is a deliberate concession, not an oversight.
The protected paths are symlinks into an immutable store.
On Linux the sandbox cannot express a read-deny over such a path: it attempts to mount over the link, fails, and aborts every sandboxed command rather than the one read.
The failure names the mount, never the rule that caused it.

The consequence is accepted: an agent can read the rules that constrain it, and could use them to look for a gap.
Write protection is the boundary; concealment is not.

#### Scenario: ReadProtectedHook

- **GIVEN** a Read tool call is intercepted
- **WHEN** the target is a protected path
- **THEN** the hook exits 0

### Requirement: MutationIsBlocked

The system SHALL block any tool call that would create, modify, delete, or rename a protected path.

This covers direct file writes, patch application, and shell commands.
A shell command SHALL be judged by the paths it names, because a command is capable of every mutation a file tool is.

A path a command supplies as the operand of shell syntax SHALL count as a path the command names, whether or not a space separates the two.
Shell syntax written against its operand is the same instruction as the spaced form, so a difference in verdict between the two is a difference the writer chooses.

#### Scenario: OperandAttachedToShellSyntax

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command carries a protected path as an operand written against a redirection or an option
- **THEN** the hook exits 2

#### Scenario: EditProtectedHookScript

- **GIVEN** an Edit tool call is intercepted
- **WHEN** the target is a protected path
- **THEN** the hook exits 2

#### Scenario: ShellCommandNamingProtectedPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command names a protected path
- **THEN** the hook exits 2

### Requirement: PathSpellingIndependence

The system SHALL determine whether a path denotes a protected location according to `path-matching`.

The limits recorded there apply here unchanged: a working-directory change within a single shell command, hard links, a tree that is not a repository, and any route that does not present a path.

A spelling that differs only in letter case is not a limit where the filesystem treats such spellings as the same file.

These limits are why this requirement is defence in depth.
The operating system sandbox and the agent permission layer are the boundary.

#### Scenario: CaseVariantSpelling

- **GIVEN** a Write, Edit, or Bash tool call is intercepted on a case-insensitive filesystem
- **WHEN** the target names a protected path under a differing letter case
- **THEN** the hook exits 2

### Requirement: InstructionTextIsWritable

The system SHALL permit writes to instruction markdown files held directly in an agent's instructions directory.

These files are prompt text supplied to the agent, not enforcement.
Blocking them would prevent ordinary authoring for no security gain.

The exemption SHALL be narrow.
It SHALL apply only to markdown files, and only to files directly in an instructions directory — not to a nested path, and not to any other file type held there.
A shell command SHALL qualify for the exemption only when every protected path it names qualifies.

The exemption SHALL be decided by the location the write lands on, not by the name the target is given.
A write to a link is a write to what the link leads to, so a name that qualifies for the exemption does not make the write qualify.

#### Scenario: ExemptNameLeadingToEnforcement

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** the target is named as markdown directly in an instructions directory but leads to an enforcement file
- **THEN** the hook exits 2

#### Scenario: InstructionMarkdown

- **GIVEN** a Write tool call is intercepted
- **WHEN** the target is a markdown file directly within an agent's instructions directory
- **THEN** the hook exits 0

#### Scenario: NestedPathUnderInstructions

- **GIVEN** a Write tool call is intercepted
- **WHEN** the target is below a subdirectory of an instructions directory
- **THEN** the hook exits 2

#### Scenario: NonMarkdownInInstructions

- **GIVEN** a Write tool call is intercepted
- **WHEN** the target is a non-markdown file in an instructions directory
- **THEN** the hook exits 2

### Requirement: ProfileLayerConfiguration

The system SHALL protect any file that can layer additional permissions over an agent's base configuration.

An agent that loads a named configuration layer can widen any permission the base configuration narrows.
Such a layer is enforcement, and is protected as enforcement, wherever it is stored.

### Requirement: BlockResponse

A block SHALL exit 2 and write an explanation to stderr that satisfies the `hook-interface` `ExplanationContract`.

The explanation SHALL name the specific path or command that was refused, and SHALL state that enforcement is the reason.
It SHALL instruct the agent not to look for another route to the same result, and to report the refusal to the user.

It SHALL NOT be required to name which agent owns the refused path, because enforcement does not vary by agent.

### Requirement: FailureMode

The system SHALL let a tool call proceed when it cannot judge it.

Where the tool is one this hook does not cover, the decision is `Allow`.
Where evaluation raises an unexpected error, the decision is `Allow`.

Where the payload does not parse, the decision is `Warn`.
The tool call still proceeds, but a hook that silently checks nothing is how a change to the agent harness goes unnoticed.
The encoding of `Warn` is agent-specific, per `hook-interface` `ExitCodes`; exiting 0 is its degraded form, not the contract.

Letting the call proceed is the correct choice here and is chosen deliberately.
This hook covers a mix of sensitive and read-only tools, so it cannot infer damage potential from an unparsable payload.
Refusing would block ordinary read-only work whenever anything unexpected occurred, and the operating system sandbox and permission layer remain in force regardless.

Neither SHALL apply to a path that cannot be resolved.
Such a path is judged from the path as written, per `path-matching` `UnresolvablePathIsGuarded`.

#### Scenario: UnparsablePayload

- **GIVEN** a tool call is intercepted
- **WHEN** the payload cannot be parsed
- **THEN** the tool call proceeds, and the reason is reported where the agent can report it

#### Scenario: UnresolvableProtectedPath

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** the target cannot be resolved but as written denotes a protected path
- **THEN** the hook exits 2
