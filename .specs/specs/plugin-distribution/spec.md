# plugin-distribution Specification

## Purpose

Sentinel is one plugin that each supported harness installs, so every agent a developer runs gets the same guardrails.
These requirements cover how each harness installs the plugin, how the Codex hook installer keeps the user's own hooks, that each harness runs only its own registration, that hooks run from the installed copy, that the plugin holds everything it needs, and that its manifests carry one version.

## Requirements

### Requirement: EachSupportedHarnessInstallsSentinel

The repository SHALL be installable as the Sentinel plugin by Claude Code, Codex, Copilot in VS Code, Copilot CLI, and Pi, each through that harness's own install mechanism, with no step outside it other than installing the programs `session-tool-checks` requires.

A step outside the harness is a step a user can skip, and a skipped step leaves an agent with no guardrails and no sign of it.
A missing required program is reported at session start, so skipping that step has a sign.

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

### Requirement: CodexHookInstallKeepsTheUsersHooks

The Codex hook installer SHALL keep every entry in the user's Codex hook file that is not Sentinel's, when it installs and when it uninstalls, and uninstalling SHALL remove only Sentinel's entries.
A hook file the installer cannot read, or can read only by dropping part of it, SHALL be reported, naming the file, and left unchanged.
Text that is not valid UTF-8, or that holds `NaN`, `Infinity`, or a number outside the range of a double, does not parse.
A registration in the installed copy that cannot be read SHALL be reported, naming that file, and the hook file SHALL be left unchanged.
Where the hook file is a link, the installer SHALL write the file the links end at and keep every link.
A hook file the installer cannot reach or cannot write SHALL be reported, naming the file at fault, and left unchanged.
The installer SHALL keep the permission bits of a file it rewrites, and give a file it creates the permission bits the user's other new files get; the owner, group, access control lists, and extended attributes are not carried over.
A run that would leave the hook file as it is SHALL NOT write it.
An install whose hook definitions already stand in the file SHALL leave the file as it is, in whatever order they stand among the user's hooks and among themselves, so the order the user gave the hooks is kept.

The installer writes into a file the user owns, beside hooks the user wrote.
A dotfile manager can keep that file as a link into the user's own configuration, and replacing the link would take the file out of that configuration.

#### Scenario: InstallKeepsTheUsersHooks

- **GIVEN** a Codex hook file that holds a hook of the user's own
- **WHEN** the user installs Sentinel's hooks and then uninstalls them
- **THEN** the user's hook is in the file after each step, and after uninstalling it is the only entry

#### Scenario: UnreadableHookFileIsLeftUnchanged

- **GIVEN** a Codex hook file that does not parse
- **WHEN** the user installs Sentinel's hooks
- **THEN** the installer fails, names the file, and leaves its content unchanged

#### Scenario: HookFileThatNamesAKeyTwiceIsLeftUnchanged

- **GIVEN** a Codex hook file that names one event twice in its `hooks` object
- **WHEN** the user installs Sentinel's hooks
- **THEN** the installer fails, names the file and the repeated key, and leaves its content unchanged, because a rewrite would keep only one copy

#### Scenario: LinkedHookFileKeepsItsLink

- **GIVEN** a Codex hook file that is a link to a file holding a hook of the user's own
- **WHEN** the user installs Sentinel's hooks
- **THEN** the hook file is still the same link, and the file it links to holds the user's hook and Sentinel's

#### Scenario: LinkChainThatEndsAtNoFileNamesTheMissingFile

- **GIVEN** a Codex hook file that links to a second link, which links to a file that does not exist
- **WHEN** the user installs Sentinel's hooks
- **THEN** the installer fails and names the file that does not exist, not the second link

#### Scenario: RunThatChangesNothingSucceedsOnAReadOnlyFile

- **GIVEN** a read-only Codex hook file that holds only the user's own hooks
- **WHEN** the user uninstalls Sentinel's hooks
- **THEN** the installer succeeds and leaves the file unchanged

#### Scenario: ReinstallKeepsTheOrderOfTheHooks

- **GIVEN** a read-only Codex hook file in which a hook of the user's own follows Sentinel's hooks, and Sentinel's hooks stand in another order than the installer writes them, within an event and within a group
- **WHEN** the user installs Sentinel's hooks again from the same copy
- **THEN** the installer succeeds and leaves the file unchanged

#### Scenario: NewHookFileGetsTheUsersDefaultPermissions

- **GIVEN** no Codex hook file
- **WHEN** the user installs Sentinel's hooks
- **THEN** the file the installer creates has the permissions the user's umask gives a new file

### Requirement: EachHarnessRunsOnlyItsOwnRegistration

A harness that installs Sentinel SHALL run the hooks in the registration written for that harness, and SHALL NOT run a hook from a registration the plugin holds for another harness.

The harnesses name their events and tools differently.
A registration written for one harness matches no tool in another, or matches the wrong tools, and both leave a gap.
Copilot in VS Code and Copilot CLI run one hook runtime with one event vocabulary, so one registration is written for both.

#### Scenario: OwnRegistrationRuns

- **GIVEN** Sentinel installed in any supported harness
- **WHEN** a session in that harness raises an event its registration names
- **THEN** the hooks that registration declares for the event run, and no hook from another harness's registration runs

### Requirement: HooksRunFromTheInstalledPlugin

Every hook a Sentinel registration declares SHALL run from the installed copy of the plugin, whatever directory the session runs in.

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
The one exception is a write to the plugin directory of the running hooks, or to the Pi extensions its repository names.
Each copy gates writes to its own directory, and to another copy only where `guarded-surface` `InstalledEnforcementIsInTheFloor` puts that copy in the floor, which is never for a checkout.

A harness copies only the plugin directory into its install location.
A file the hooks reach outside that directory is missing from every installed copy.

#### Scenario: CopyOutsideACheckout

- **GIVEN** a copy of the plugin directory in a location outside any checkout of this repository
- **WHEN** each hook decides a tool call that writes to neither copy's plugin directory nor to the Pi extensions of either copy's repository
- **THEN** the decision equals the decision the hook in the checkout reaches for the same call

#### Scenario: EachCopyGatesItsOwnDirectory

- **GIVEN** a copy of the plugin directory outside any checkout, and the checkout's own copy
- **WHEN** each decides a write to `plugins/sentinel/hooks/guarded_paths.py` or `extensions/pi/extension.ts` in the checkout
- **THEN** the checkout's copy asks, and the outside copy permits the write

### Requirement: OneVersionAcrossManifests

Every plugin manifest, package manifest, and catalog entry the repository holds for Sentinel SHALL carry the same version, the plugin version.
The Pi extension's own manifest, `extensions/pi/package.json`, SHALL carry the extension's version, and that version SHALL NOT be held to the plugin version.

Codex and Claude Code keep an installed copy for each version.
A harness whose manifest carries an older version keeps its older copy after the others update, and then runs different guardrails.
Pi installs the package that the root `package.json` describes, so the plugin version names what a Pi user runs.
The extension is the runner inside that package, and it is released on its own.

#### Scenario: VersionsAgree

- **GIVEN** the repository's manifests and catalogs
- **WHEN** the package is checked
- **THEN** every version they carry for Sentinel is the same

#### Scenario: VersionsDisagree

- **GIVEN** one manifest that carries a different version from the others
- **WHEN** the package is checked
- **THEN** conformance fails

#### Scenario: ExtensionVersionIsItsOwn

- **GIVEN** the Pi extension's manifest carries a version that differs from the plugin version
- **WHEN** the package is checked
- **THEN** conformance passes, and the extension's manifest carries a version
