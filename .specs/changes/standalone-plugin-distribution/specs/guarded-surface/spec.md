# Delta for guarded-surface

## ADDED Requirements

### Requirement: PluginSwitchesAreInTheFloor

The enforcement floor SHALL cover every settings file in which a supported harness reads whether a plugin or its hooks are enabled.

A harness switches Sentinel off from these files, through settings such as `enabledPlugins` and `disableAllHooks`, so a write to one of them is a write to enforcement.
For Copilot CLI these are `~/.copilot/settings.json`, `~/.copilot/config.json`, which records its installed plugins, and a project's `.github/copilot/settings.json`, `.github/copilot/settings.local.json`, and `.claude/settings*.json`.
The files of the other harnesses are in the floor already as their permission and settings files.

Serves: protect-installed-copy

#### Scenario: CopilotSettingsDisableTheHooks

- **GIVEN** a broad grant over `~/.copilot/`
- **WHEN** a tool call writes `~/.copilot/settings.json`
- **THEN** the decision is `Ask`

#### Scenario: ProjectCopilotSettingsAreWritten

- **GIVEN** a broad project grant
- **WHEN** a tool call writes the project's `.github/copilot/settings.local.json`
- **THEN** the decision is `Ask`

### Requirement: InstalledEnforcementIsInTheFloor

The enforcement floor SHALL cover every installed copy of Sentinel in the locations where a supported harness installs plugins, and every copy a supported harness's user-level records name as loaded in place, whichever harness installed it, and MAY cover other installed enforcement there.

The plugin directory the guard runs from covers the copy of Sentinel that is running, wherever the harness loaded it.
A copy another harness loads in place is outside every install location, and that harness records where it is.
A copy that another harness runs is enforcement for that harness, and an agent that can change it has weakened another agent's guardrails.
Other plugins in those locations can register hooks too, and a hook can allow, refuse, or reshape a tool call.

Serves: protect-installed-copy

#### Scenario: AnotherHarnessesCopyIsWritten

- **GIVEN** Sentinel installed in two harnesses
- **WHEN** a tool call in a session of one harness writes a file in the copy the other harness installed
- **THEN** the decision is `Ask`

#### Scenario: AnotherHarnessesInPlaceCopyIsWritten

- **GIVEN** a checkout of Sentinel that one harness loads in place, and a session of another harness
- **WHEN** a tool call in that session writes a file in the checkout's plugin directory
- **THEN** the decision is `Ask`

#### Scenario: CheckoutOutsideThePluginDirectory

- **GIVEN** a checkout of Sentinel that a harness loads in place
- **WHEN** a tool call writes a file in the checkout outside its plugin directory, where no declaration covers it
- **THEN** the call proceeds

#### Scenario: AnotherPluginsFileIsWritten

- **GIVEN** a plugin other than Sentinel installed in a plugin install location
- **WHEN** a tool call writes any file in that plugin
- **THEN** the decision is `Ask`

#### Scenario: PluginSkillScriptRuns

- **GIVEN** a plugin that ships a skill with a helper script, installed in a plugin install location
- **WHEN** a shell command runs that script by path
- **THEN** the call proceeds

#### Scenario: InstalledCopyIsRead

- **GIVEN** a file in an installed copy of Sentinel that no block declaration covers
- **WHEN** a tool call reads it
- **THEN** the call proceeds

## MODIFIED Requirements

### Requirement: SkillsRootsAreRunnable

> Previously: the declaration covered a skills source in a configuration checkout, `<repo>/modules/home/ai/shared/skills/`, and no plugin's skill directories.

The manifest SHALL declare exec-through each skills root an agent loads: `~/.claude/skills/`, `~/.codex/skills/`, `~/.pi/agent/skills/`, `~/.agents/skills/`, and the skill directories of every plugin in a plugin install location.

A skill ships helper scripts and tells the agent to run them by path.
The skill was installed by the user, writes to it still ask, and the sandbox and permission layers still gate what the script touches, so the run itself carries no risk a prompt would address.
`~/.agents/skills/` is declared because the per-agent roots hold links into it, and a declaration does not follow the links inside the directory it names.

Serves: one-tree

#### Scenario: SkillScriptRun

- **GIVEN** an existing program under a declared skills root, reached through the per-agent link or directly
- **WHEN** a shell command runs it
- **THEN** the call proceeds

#### Scenario: SkillContentWrite

- **GIVEN** a file under a declared skills root
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

## REMOVED Requirements

### Requirement: RepositorySourcesAreGuarded

Removed because: each harness runs its installed copy of the plugin, not a link into a checkout, so no repository source is a live guardrail.
`InstalledEnforcementIsInTheFloor` covers the installed copies the harnesses run.
