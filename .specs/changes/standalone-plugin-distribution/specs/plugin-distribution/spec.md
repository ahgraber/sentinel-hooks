# Delta for plugin-distribution

## ADDED Requirements

### Requirement: EachSupportedHarnessInstallsSentinel

The repository SHALL be installable as the Sentinel plugin by Claude Code, Codex, Copilot in VS Code, Copilot CLI, and Pi, each through that harness's own install mechanism, with no step outside it other than installing the programs `session-tool-checks` requires.

A step outside the harness is a step a user can skip, and a skipped step leaves an agent with no guardrails and no sign of it.
A missing required program is reported at session start, so skipping that step has a sign.

Serves: install-per-agent

#### Scenario: ClaudeCodeInstall

- **GIVEN** the repository added as a Claude Code marketplace
- **WHEN** the user installs Sentinel from it
- **THEN** Claude Code installs the plugin and lists its hooks

#### Scenario: CodexInstall

- **GIVEN** the repository added as a Codex marketplace
- **WHEN** the user installs Sentinel from it
- **THEN** Codex installs the plugin and lists its hooks

#### Scenario: VSCodeInstall

- **GIVEN** the repository added as a VS Code agent plugin marketplace
- **WHEN** the user installs Sentinel from it
- **THEN** VS Code installs the plugin and lists its hooks

#### Scenario: CopilotCliInstall

- **GIVEN** the repository added as a Copilot CLI marketplace
- **WHEN** the user installs Sentinel from it
- **THEN** Copilot CLI installs the plugin and runs its hooks

#### Scenario: PiInstall

- **GIVEN** the repository's git URL
- **WHEN** the user installs it as a Pi package
- **THEN** Pi loads the Sentinel hook runner extension

### Requirement: EachHarnessRunsOnlyItsOwnRegistration

A harness that installs Sentinel SHALL run the hooks in the registration written for that harness, and SHALL NOT run a hook from a registration the plugin holds for another harness.

The harnesses name their events and tools differently.
A registration written for one harness matches no tool in another, or matches the wrong tools, and both leave a gap.
Copilot in VS Code and Copilot CLI run one hook runtime with one event vocabulary, so one registration is written for both.

Serves: install-per-agent

#### Scenario: OwnRegistrationRuns

- **GIVEN** Sentinel installed in any supported harness
- **WHEN** a session in that harness raises an event its registration names
- **THEN** the hooks that registration declares for the event run, and no hook from another harness's registration runs

### Requirement: HooksRunFromTheInstalledPlugin

Every hook a Sentinel registration declares SHALL run from the installed copy of the plugin, whatever directory the session runs in.

Serves: install-per-agent, one-tree

#### Scenario: SessionInAnUnrelatedProject

- **GIVEN** Sentinel installed in a harness
- **WHEN** a session in a project that holds no copy of Sentinel raises an event
- **THEN** the hooks run from the installed copy

#### Scenario: SessionInACheckoutOfSentinel

- **GIVEN** Sentinel installed in a harness, and a session in a checkout of this repository
- **WHEN** the session raises an event
- **THEN** the hooks run from the installed copy, not from the checkout

### Requirement: ThePluginIsSelfContained

The plugin directory SHALL hold every file its hooks read or run, so that a copy of that directory alone, outside any checkout, decides every tool call as the checkout decides it.

A harness copies only the plugin directory into its install location.
A file the hooks reach outside that directory is missing from every installed copy.

Serves: one-tree

#### Scenario: CopyOutsideACheckout

- **GIVEN** a copy of the plugin directory in a location outside any checkout of this repository
- **WHEN** each hook decides a tool call
- **THEN** the decision equals the decision the hook in the checkout reaches for the same call

### Requirement: OneVersionAcrossManifests

Every plugin manifest, package manifest, and catalog entry the repository holds for Sentinel SHALL carry the same version.

Codex and Claude Code keep an installed copy for each version.
A harness whose manifest carries an older version keeps its older copy after the others update, and then runs different guardrails.

Serves: install-per-agent

#### Scenario: VersionsAgree

- **GIVEN** the repository's manifests and catalogs
- **WHEN** the package is checked
- **THEN** every version they carry for Sentinel is the same

#### Scenario: VersionsDisagree

- **GIVEN** one manifest that carries a different version from the others
- **WHEN** the package is checked
- **THEN** conformance fails
