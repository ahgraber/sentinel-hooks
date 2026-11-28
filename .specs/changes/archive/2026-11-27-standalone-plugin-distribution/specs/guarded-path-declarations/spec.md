# Delta for guarded-path-declarations

## MODIFIED Requirements

### Requirement: EnforcementIsNeverCarvedOut

> Previously: the declared floor covered the repository sources that deployed hooks resolved to, every location a harness loads hooks from without exception for plugin install locations, and no grant applied to a run inside the floor.

Runs inside the `skills/` directory of a plugin in a plugin install location SHALL be open, and `PrecedenceIsOneRule` decides them as it decides a run outside the floor; a `skills/` directory in a layout Sentinel does not recognize stays gated.
For every write, and every other run, inside the enforcement floor, an exec-through or write-through declaration that covers it SHALL have no effect, at any distance, including an exact tie.
No declaration SHALL apply to a write inside the floor.

A skill tells the agent to run its helper scripts by path, so a skill installed as a plugin cannot work without a prompt on every run unless its runs are open.
Opening runs and not writes keeps every plugin file from changing without the user, while the scripts the user installed run as they do in a skills root.

Block SHALL outrank the floor, and the floor SHALL NOT restrict reads.
The grant SHALL remain effective outside the floor.
Every implementation SHALL report the floor paths to which a grant does not apply where the invoking agent can show the report; it SHALL NOT describe the entire grant as ignored.
At session start, only a grant lying at or inside the floor SHALL be reported, because such a grant has no effect at all; a broader grant keeps its effect outside the floor and is reported at gate time, on the call it does not reach.
The open runs in plugin `skills/` directories are not reported at session start.

The floor SHALL be the locations the manifest declares in its enforcement floor, together with the manifest itself, the guard's own implementation and launch locations, the plugin directory that holds them, and each directory from which Pi loads an extension of the package two directories above that plugin directory; no manifest edit removes them.
An extension Pi loads only by a fallback, for an `extensions` list that mixes text with other values or for an empty list under a settings filter, is outside the floor.
A harness can load a plugin in place from a directory outside every install location, and that copy's registrations and adapters are enforcement while it runs.
A guarded, exec-through, or write-through declaration SHALL NOT extend or reduce the floor.
A floor declaration MAY be anchored at the working directory and every directory above it, for the settings a project carries; a declaration of any other class anchored there SHALL fail to load.
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

#### Scenario: GuardedDeclarationInsideAPluginSkillDirectory

- **GIVEN** the exec-through declaration of the skill directories inside a plugin install location, and a guarded declaration of one skill inside one of them
- **WHEN** a shell command runs a script of that skill
- **THEN** the decision is `Ask`, because the guarded declaration is closer

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

### Requirement: PrecedenceIsOneRule

> Previously: the enforcement floor decided guarded for every run, which the open runs in a plugin's `skills/` directory contradicted.

For every hop in a supplied path's link chain, the system SHALL find the declarations covering that hop and reach a verdict there: block decides first; for writes, and for runs other than those `EnforcementIsNeverCarvedOut` opens in a plugin's `skills/` directory, the enforcement floor decides guarded next; otherwise the closest declaration decides.
The path's verdict SHALL be the strictest across its hops, and the order of declarations in the manifest SHALL NOT affect any verdict.

A hop is the path as written, each link along the way, and the final target, per `path-matching` `SpellingIndependence`.
The closest declaration is the one whose declared location lies the fewest path segments above the hop, measured in the spelling where it matched; a declaration naming the file itself is closest of all.
Where two declarations lie at the same distance in different classes, the delta class decides, because declaring a carve-out at exactly a guarded location is the intent of writing it.
This tie rule cannot override the enforcement floor.
Strictness runs block over guarded over carve-out over undeclared.

A write consults the write-through and guarded classes.
A run consults the exec-through and guarded classes.
A read consults the block class alone.
The guarded class includes the implicit base supplied by each exec-through and write-through declaration.
A removal, rename, or replacement is a write.

One rule covers restriction and permission alike.
A restriction holds when any hop reaches it, so a write through a link named under a carve-out still asks when the link leads to enforcement.
A permission holds only when every hop allows it, and a hop no declaration covers allows everything, so a link from a carve-out into undeclared space keeps the carve-out.
Fixing precedence this way is what lets a carve-out be written beneath a base and a base be restated beneath a carve-out.

Serves: protect-installed-copy

#### Scenario: BlockBeneathWriteThrough

- **GIVEN** a block declaration for a file beneath a write-through directory
- **WHEN** a tool call writes that file
- **THEN** the call is refused

#### Scenario: WriteThroughBeneathGuarded

- **GIVEN** a write-through declaration for a directory beneath a guarded one
- **WHEN** a tool call writes a file in that directory
- **THEN** the call proceeds

#### Scenario: GuardedBeneathWriteThrough

- **GIVEN** a guarded declaration for a directory beneath a write-through one
- **WHEN** a tool call writes a file in that directory
- **THEN** the decision is `Ask`

#### Scenario: ExecThroughBeneathGuarded

- **GIVEN** an exec-through declaration for a directory beneath a guarded one
- **WHEN** a shell command runs a program held there
- **THEN** the call proceeds

#### Scenario: LinkFromACarveOutIntoAGuardedLocation

- **GIVEN** a link inside a write-through directory whose target lies under a guarded declaration with no write-through declaration of its own
- **WHEN** a tool call writes through the link
- **THEN** the decision is `Ask`, because the strictest hop decides

#### Scenario: LinkFromACarveOutIntoUndeclaredSpace

- **GIVEN** a link inside an exec-through directory whose target lies under no declaration
- **WHEN** a shell command runs a program through the link
- **THEN** the call proceeds, because an undeclared hop allows everything

#### Scenario: DeclarationsReordered

- **GIVEN** two manifests holding the same declarations in different orders
- **WHEN** each judges the same tool calls
- **THEN** every verdict is the same

## REMOVED Requirements

### Requirement: ConfigurationSurfacesCoverTheDeclarations

Removed because: Sentinel neither sets nor reads a user's agent permission lists or OS sandbox, so nothing in this repository can make the requirement hold or check that it does.
The configuration audit, a later change, can judge a user's own configuration against the block class.
