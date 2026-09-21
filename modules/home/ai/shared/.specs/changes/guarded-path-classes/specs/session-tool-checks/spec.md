# Delta for session-tool-checks

## ADDED Requirements

### Requirement: ClaudeToolShellIsPinnedToBash

At session start under Claude, the system SHALL warn where the tool shell is not pinned to bash, and SHALL stay silent where it is.

Serves: one-lexer

`shell-lexing` reads a command the way bash does, and its evidence is a differential property against a real bash.
A session whose tool shell is another shell runs commands the lexer never modelled.
Claude selects its tool shell from the login shell unless `CLAUDE_CODE_SHELL` names another, so the pin is that variable naming a bash, delivered by the settings file every launcher reads.

The check warns rather than blocks.
The lexer refuses what it cannot resolve, so a divergent shell costs prompts rather than misses, and blocking every session on a settings edit would stop the session in which the operator makes it.

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

Serves: one-list-then-deltas

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
