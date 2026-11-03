# Delta for guarded-path-declarations

## MODIFIED Requirements

### Requirement: EnforcementIsNeverCarvedOut

> Previously: the declared floor covered the repository sources that deployed hooks resolved to, every location a harness loads hooks from without exception for plugin install locations, and no grant applied to a run inside the floor.

An exec-through or write-through declaration SHALL have no effect on writes and runs where it covers the enforcement floor, at any distance, including an exact tie, with one exception.
An exec-through declaration that names the skill directories inside a plugin install location SHALL apply to runs there.
No declaration SHALL apply to a write inside the floor.

A skill tells the agent to run its helper scripts by path, so a skill installed as a plugin cannot work without a prompt on every run unless its runs are open.
Opening runs and not writes keeps every plugin file from changing without the user, while the scripts the user installed run as they do in a skills root.

Block SHALL outrank the floor, and the floor SHALL NOT restrict reads.
The grant SHALL remain effective outside the floor.
Every implementation SHALL report the floor paths to which a grant does not apply where the invoking agent can show the report; it SHALL NOT describe the entire grant as ignored.
At session start, only a grant lying at or inside the floor SHALL be reported, because such a grant has no effect at all; a broader grant keeps its effect outside the floor and is reported at gate time, on the call it does not reach.
An exec-through declaration of plugin skill directories keeps its effect on runs, so it is not reported at session start.

The floor SHALL be the locations the manifest declares in its enforcement floor, together with the manifest itself, the guard's own implementation and launch locations, and the plugin directory that holds them, which no manifest edit removes.
A harness can load a plugin in place from a directory outside every install location, and that copy's registrations and adapters are enforcement while it runs.
A guarded, exec-through, or write-through declaration SHALL NOT extend or reduce the floor.
A floor declaration MAY be anchored at the working directory and every directory above it, for the settings a project carries; no other class uses that anchor.
The declared floor covers hook implementations and dependencies, harness permission and settings files and their profile layers, project-local permission settings and hook files, every location outside a plugin install location that a harness loads hooks from, and the installed enforcement `guarded-surface` `InstalledEnforcementIsInTheFloor` names; the floor covers every hop of their link chains.
Inside a plugin install location, the floor covers every link at any depth, every hop of its chain, and every path under a link whose target is a directory, including a file created there later.
Instruction text is outside the floor; where no declaration covers it, it SHALL be guarded.
A broad home or project grant permits content changes without permitting the permission rules themselves to be rewritten without approval.

Serves: protect-installed-copy

<!-- modified-removes: CarveOutOverAHookSource -->

#### Scenario: WriteThroughOverTheManifest

- **GIVEN** a write-through declaration covering the manifest
- **WHEN** a tool call writes the manifest
- **THEN** the decision is `Ask`, and the report names the manifest as a floor path to which the grant does not apply

#### Scenario: ExecThroughOverAHook

- **GIVEN** an exec-through declaration covering a hook implementation
- **WHEN** a shell command runs that hook
- **THEN** the decision is `Ask`, and the report names the hook as a floor path to which the grant does not apply

#### Scenario: PluginSkillScriptRunsInsideTheFloor

- **GIVEN** an exec-through declaration naming the skill directories inside a plugin install location that the floor covers
- **WHEN** a shell command runs a script already held in an installed plugin's skill directory
- **THEN** the call proceeds

#### Scenario: PluginSkillScriptWriteInsideTheFloor

- **GIVEN** exec-through and write-through declarations covering an installed plugin's skill directory that the floor covers
- **WHEN** a tool call writes a script there
- **THEN** the decision is `Ask`

#### Scenario: CarveOutOverAnInstalledCopy

- **GIVEN** a write-through declaration covering a location a harness installs plugins into
- **WHEN** a tool call writes a hook in an installed copy of Sentinel there
- **THEN** the decision is `Ask`, and the report names the hook as a floor path to which the grant does not apply

#### Scenario: NewFileBehindALinkInAnInstallLocation

- **GIVEN** a plugin in a plugin install location that holds, below its top level, a link to a directory outside every install location
- **WHEN** a tool call creates a new file in that directory
- **THEN** the decision is `Ask`

#### Scenario: RunningCopyLoadedInPlace

- **GIVEN** Sentinel loaded in place from a checkout outside every plugin install location, and a write-through declaration covering that checkout
- **WHEN** a tool call writes a registration file in the plugin directory the running hooks belong to
- **THEN** the decision is `Ask`

#### Scenario: BroadGrantPreservesContentPermission

- **GIVEN** a write-through grant over an agent home or project
- **WHEN** a tool writes ordinary content or instruction text outside the floor
- **THEN** the grant remains effective

#### Scenario: BroadGrantIsSilentAtSessionStart

- **GIVEN** a write-through grant over an agent home that contains floor paths
- **WHEN** the manifest is validated at session start
- **THEN** no finding is reported for that grant

#### Scenario: GrantInsideTheFloorIsReportedAtSessionStart

- **GIVEN** a write-through grant naming a hook directory or a file inside one
- **WHEN** the manifest is validated at session start
- **THEN** the grant is reported with the floor paths it does not apply to

#### Scenario: ExactGrantCannotOverrideTheFloor

- **GIVEN** a grant naming a floor file exactly
- **WHEN** a tool writes or runs that file
- **THEN** the decision is `Ask`, regardless of declaration order

#### Scenario: ProjectPermissionSettingsAreEnforcement

- **GIVEN** a broad project grant and project-local permission settings
- **WHEN** a tool writes those settings
- **THEN** the decision is `Ask`, even if the manifest declares no guarded paths

#### Scenario: AFloorDeclarationHoldsAgainstAGrant

- **GIVEN** a location declared in the enforcement floor, and a grant covering it
- **WHEN** a tool writes or runs a file there
- **THEN** the decision is `Ask`, and without the floor declaration the grant decides

#### Scenario: AnEmptyFloorKeepsTheGuard

- **GIVEN** a manifest whose enforcement floor declares nothing, and a grant covering the manifest and the running hook
- **WHEN** a tool writes either
- **THEN** the decision is `Ask`

#### Scenario: ProjectAnchorOutsideTheFloorDoesNotLoad

- **GIVEN** a guarded, block, exec-through, or write-through declaration anchored at the working directory
- **WHEN** the manifest is loaded
- **THEN** loading fails

#### Scenario: UncoveredInstructionTextIsGuarded

- **GIVEN** instruction text inside a floor directory, with no declaration covering it
- **WHEN** a tool writes it
- **THEN** the decision is `Ask`, and a grant covering it permits the write

#### Scenario: ProjectHookFilesAreEnforcement

- **GIVEN** a broad project grant
- **WHEN** a tool writes a file in a directory a harness loads project hooks from, such as `.github/hooks/`
- **THEN** the decision is `Ask`, even if the manifest declares no guarded paths
