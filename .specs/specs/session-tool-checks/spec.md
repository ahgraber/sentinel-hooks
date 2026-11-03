# Spec: session-tool-checks

## Purpose

The hooks depend on tools that may be missing, and a missing tool makes a hook fail in the middle of a session, where the failure is harder to see than at its start.
These requirements cover the checks a session runs when it starts: the required tools, the shell an agent runs commands in, and the path manifest.

## Requirements

### Requirement: SessionStartHook

The system SHALL provide a SessionStart hook that verifies required security tools are available before a session proceeds.

### Requirement: UvAvailability

The system SHALL check that `uv` is available on `PATH` at session start.

#### Scenario: UvPresent

- **GIVEN** a new session starts
- **WHEN** `uv` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: UvMissing

- **GIVEN** a new session starts
- **WHEN** `uv` is not found on `PATH`
- **THEN** the hook exits 2 with a message explaining how to install `uv`

### Requirement: JqAvailability

The system SHALL check that `jq` is available on `PATH` at session start.
The security hooks require `jq`.

#### Scenario: JqPresent

- **GIVEN** a new session starts
- **WHEN** `jq` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: JqMissing

- **GIVEN** a new session starts
- **WHEN** `jq` is not found on `PATH`
- **THEN** the hook exits 2 with a message explaining that `jq` is required for security hooks

### Requirement: PerlAvailability

The system SHALL check that `perl` is available on `PATH` at session start.
The security hooks require `perl`.

#### Scenario: PerlPresent

- **GIVEN** a new session starts
- **WHEN** `perl` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: PerlMissing

- **GIVEN** a new session starts
- **WHEN** `perl` is not found on `PATH`
- **THEN** the hook exits 2 with a message explaining that `perl` is required for security hooks

### Requirement: GitleaksAvailability

The system SHALL check that `gitleaks` is available on `PATH` at session start.
Without gitleaks, `secret-access-blocking` detects fewer secret formats in network sends.

#### Scenario: GitleaksPresent

- **GIVEN** a new session starts
- **WHEN** `gitleaks` is found on `PATH`
- **THEN** the hook exits 0 silently

#### Scenario: GitleaksMissing

- **GIVEN** a new session starts
- **WHEN** `gitleaks` is not found on `PATH`
- **THEN** the hook prints a warning to stderr and exits 0 (session proceeds)

### Requirement: ChecksAreIndependent

Each tool check SHALL be evaluated independently.
A missing optional tool SHALL NOT prevent the session from starting if no hook requires it.
A missing required tool SHALL block the session with a clear message identifying the tool and install instructions.

### Requirement: ClaudeToolShellIsPinnedToBash

At session start under Claude, the system SHALL warn where the tool shell is not pinned to bash, and SHALL stay silent where it is.

`shell-lexing` requires path hooks to read a command as bash reads it.
The evidence is a differential test against a real bash.
If the agent runs commands in a shell other than bash, the hooks can misread them.
Claude selects its tool shell from the login shell unless `CLAUDE_CODE_SHELL` names another, so the pin is that variable naming a bash, delivered by the settings file every launcher reads.

The check warns rather than blocks.
A path hook treats what it cannot resolve as unresolvable.
So a different shell causes extra prompts, not missed checks.
Blocking every session until the operator edits the setting would also block the session in which the operator makes that edit.

No check applies under another agent.
Codex runs bash by construction, and Copilot's shell follows the editor's terminal profile, which no setting of this module controls; the assumption is recorded as a limit there.

#### Scenario: PinNamesBash

- **GIVEN** a new Claude session starts
- **WHEN** `CLAUDE_CODE_SHELL` names an executable bash
- **THEN** the hook is silent about the shell

#### Scenario: PinAbsent

- **GIVEN** a new Claude session starts
- **WHEN** `CLAUDE_CODE_SHELL` is unset
- **THEN** the hook prints a warning naming the variable and the value to set, and exits 0

#### Scenario: PinNamesAnotherShell

- **GIVEN** a new Claude session starts
- **WHEN** `CLAUDE_CODE_SHELL` names a shell that is not bash
- **THEN** the hook prints a warning naming the variable and the value to set, and exits 0

#### Scenario: AnotherAgent

- **GIVEN** a new session starts under an agent that is not Claude
- **WHEN** the hook runs
- **THEN** it is silent about the shell

### Requirement: ManifestIsValidatedAtSessionStart

At session start, the system SHALL validate the manifest: it SHALL report an error where the manifest cannot be loaded, SHALL warn about the floor restrictions `guarded-path-declarations` `EnforcementIsNeverCarvedOut` reports and every conflict `ConflictingDeclarationsAreReported` names, and SHALL stay silent where there are none.

A PreToolUse hook reports a finding only where an agent can show a warning on a tool call, which Claude alone does.
Session start is the one moment every agent shows output to the user, so it is where a manifest defect reaches the operator whichever agent they opened.

A conflict or a grant restricted by the floor is a warning, exit 0.
The runtime already ignores an invalid carve-out and lets the block class win, so the session is safe to start; what the operator needs is to hear that the manifest does not say what they meant.

A manifest that cannot be loaded is an error, exit 2.
No harness lets a session-start hook stop the session, so the exit code is display rather than enforcement; the enforcement is `guarded-path-declarations` `LoadFailureIsReported`, under which every mutating call asks until the manifest is repaired.
The error tells the operator why the prompts are about to start.

#### Scenario: ValidManifest

- **GIVEN** a new session starts
- **WHEN** the manifest has no grant restricted by the floor and no conflict
- **THEN** the hook is silent about the manifest

#### Scenario: IgnoredCarveOut

- **GIVEN** a new session starts
- **WHEN** the manifest carries a carve-out over enforcement
- **THEN** the hook prints a warning naming the declaration, and exits 0

#### Scenario: InertCarveOut

- **GIVEN** a new session starts
- **WHEN** the manifest carries a carve-out on a link whose target a stricter declaration covers
- **THEN** the hook prints a warning naming the declaration and the target it would need, and exits 0

#### Scenario: UnloadableManifest

- **GIVEN** a new session starts
- **WHEN** the manifest is absent, cannot be parsed, or lacks a required table
- **THEN** the hook prints an error naming the failure and stating that mutating calls will ask until it is repaired, and exits 2
