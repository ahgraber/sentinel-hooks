# guarded-surface Specification

## Purpose

The path policy protects only the locations it names: an agent home, an editor setting, or a credential file left out of it is open to any agent.
These requirements cover which locations are guarded, blocked, runnable, or writable, and the declared exceptions to the name rules.

## Requirements

### Requirement: AgentHomesAreGuarded

The manifest SHALL declare each agent's home directory guarded: `~/.claude/`, `~/.codex/`, `~/.copilot/`, and `~/.pi/agent/`.

An agent home holds the enforcement the agent loads at run time, its settings, its skills, and its instructions, and little else.
One base declaration with the carve-outs beneath it is the shortest true statement of the posture, and a directory kind a harness adds later is guarded the day it appears.
`~/.pi/` is declared at `agent/`, the directory Pi reads its settings, extensions, packages, and skills from.

#### Scenario: WriteInAnAgentHome

- **GIVEN** a path directly within any declared agent home
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

#### Scenario: ReadInAnAgentHome

- **GIVEN** a path within any declared agent home that no block declaration covers
- **WHEN** a tool call reads it
- **THEN** the call proceeds

### Requirement: EditorAgentSettingsAreGuarded

The manifest SHALL declare the editor's user settings and its agent instruction files guarded, on each platform's path.

The editor's settings hold the agent sandbox and approval configuration `agent-configuration-floor` requires, and its instruction files are prompt text an agent loads.
Both are enforcement for the agent that runs inside the editor.

#### Scenario: EditorSettingsWrite

- **GIVEN** the editor's user settings file on the running platform
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

### Requirement: ProfileLayersAreGuarded

The manifest SHALL declare guarded any file that can layer additional permissions over an agent's base configuration, whether or not it exists yet.

An agent that loads a named configuration layer can widen any permission the base configuration narrows.
Such a layer is enforcement wherever it is stored, and a layer that does not exist yet is guarded by its shape so that creating it asks.

#### Scenario: CreateAProfileLayer

- **GIVEN** a path matching a declared profile-layer shape, where no file exists yet
- **WHEN** a tool call creates it
- **THEN** the decision is `Ask`

### Requirement: AgentCredentialsAreBlocked

The manifest SHALL declare blocked each agent's stored authentication material, the Claude state file `~/.claude.json`, and the rendered MCP environment file.

No legitimate flow maintains a credential in-session, so a prompt there gains nothing and trains approval of the one request that should never come.
The Claude state file holds account state and OAuth material beside MCP configuration, and the sandbox already denies reading it.
The MCP environment file holds the API keys the MCP servers start with, and its suffix reaches no strong rule in `sensitive-path-blocking`.

#### Scenario: CredentialRead

- **GIVEN** a declared block path
- **WHEN** a tool call reads it
- **THEN** the call is refused on every agent

#### Scenario: CredentialWrite

- **GIVEN** a declared block path
- **WHEN** a tool call writes it
- **THEN** the call is refused on every agent, with no prompt

### Requirement: SkillsRootsAreRunnable

The manifest SHALL declare exec-through each skills root an agent loads: `~/.claude/skills/`, `~/.codex/skills/`, `~/.pi/agent/skills/`, `~/.agents/skills/`, and the skill directories of every plugin in a plugin install location.

A skill ships helper scripts and tells the agent to run them by path.
The skill was installed by the user, writes to it still ask, and the sandbox and permission layers still gate what the script touches, so the run itself carries no risk a prompt would address.

#### Scenario: SkillScriptRun

- **GIVEN** an existing program under a declared skills root, reached through the per-agent link or directly
- **WHEN** a shell command runs it
- **THEN** the call proceeds

#### Scenario: SkillContentWrite

- **GIVEN** a file under a declared skills root
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

### Requirement: AgentMemoryIsWritable

The manifest SHALL declare write-through the directory where an agent keeps its own memory across sessions, `~/.claude/projects/`.

Memory is written in ordinary sessions and changes no enforcement.
Gating it prompts on every note an agent keeps for itself, for no security gain.

#### Scenario: MemoryWrite

- **GIVEN** a file under the declared memory directory
- **WHEN** a tool call writes it
- **THEN** the call proceeds

### Requirement: InstructionTextIsGuarded

The manifest SHALL NOT declare any instructions directory write-through.

Instruction markdown is prompt text an agent loads, and prompt text shapes what the agent does with every other guardrail.
An edit to it is an edit to the agent's behavior, and whether that happens is the user's decision, as for a hook.
The cost is one prompt per instruction edit, which is authoring the operator does rarely and deliberately.

#### Scenario: InstructionMarkdownWrite

- **GIVEN** a markdown file directly within an agent's instructions directory
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

### Requirement: NameHeuristicExceptionIsDeclared

The manifest SHALL declare, as an exception for the name-heuristic surface, the tracked program that renders the MCP environment file and holds no secret itself.

The program is named for the file it renders, and `sensitive-path-blocking` `TheNameHeuristicIsExcusedOnlyByDeclaration` excuses a name only where the manifest says so.

#### Scenario: RendererIsReadable

- **GIVEN** the declared renderer program
- **WHEN** a tool call reads it
- **THEN** the call proceeds

### Requirement: DotenvPlaceholdersAreDeclared

The manifest SHALL declare `.env.example`, `.env.sample`, `.env.template`, and `.env.op` as exceptions for the dotenv surface, each matching its file name in any directory.

These are the names projects commit to list the variables they expect, with placeholder values.
The values in `.env.op` are 1Password secret references, which name a vault, an item, and a field but hold no secret.
`.env.dist` is not declared.
`sensitive-path-blocking` `DotenvPlaceholderReadIsExcusedOnlyByDeclaration` excuses a read of a declared name and nothing else.

An agent's configuration MAY refuse a declared name more strictly than the declaration allows.
Codex has no way to reopen a file inside a deny glob, so its `**/.env.*` deny still refuses these names.

#### Scenario: EachPlaceholderNameIsDeclared

- **GIVEN** the shipped manifest
- **WHEN** its dotenv exceptions are read
- **THEN** they name exactly `.env.example`, `.env.sample`, `.env.template`, and `.env.op`

#### Scenario: ADotenvExceptionIsAFileName

- **GIVEN** a dotenv exception whose pattern is not `.env.` followed by a suffix, or holds a directory separator, home notation, whitespace, or a glob character
- **WHEN** the manifest is validated
- **THEN** validation fails, because the pattern is compared as one literal file name, and `.env` itself is the file the dotenv rule exists to refuse

### Requirement: PluginSwitchesAreInTheFloor

The enforcement floor SHALL cover every settings file in which a supported harness reads whether a plugin or its hooks are enabled.

A harness switches Sentinel off from these files, through settings such as `enabledPlugins` and `disableAllHooks`, so a write to one of them is a write to enforcement.
For Copilot CLI these are `~/.copilot/settings.json`, `~/.copilot/config.json`, which records its installed plugins, and a project's `.github/copilot/settings.json`, `.github/copilot/settings.local.json`, and `.claude/settings*.json`.
The files of the other harnesses are in the floor already as their permission and settings files.

#### Scenario: CopilotSettingsDisableTheHooks

- **GIVEN** a broad grant over `~/.copilot/`
- **WHEN** a tool call writes `~/.copilot/settings.json`
- **THEN** the decision is `Ask`

#### Scenario: ProjectCopilotSettingsAreWritten

- **GIVEN** a broad project grant
- **WHEN** a tool call writes the project's `.github/copilot/settings.local.json`
- **THEN** the decision is `Ask`

### Requirement: InstalledEnforcementIsInTheFloor

The enforcement floor SHALL cover every installed copy of Sentinel in the locations where a supported harness installs plugins, whichever harness installed it, and MAY cover other installed enforcement there.

The plugin directory the guard runs from covers the copy of Sentinel that is running, wherever the harness loaded it.
A checkout that a harness loads in place is a development setup, and the floor covers it only as the running copy.
A copy that another harness runs is enforcement for that harness, and an agent that can change it has weakened another agent's guardrails.
Other plugins in those locations can register hooks too, and a hook can allow, refuse, or reshape a tool call.

#### Scenario: AnotherHarnessesCopyIsWritten

- **GIVEN** Sentinel installed in two harnesses
- **WHEN** a tool call in a session of one harness writes a file in the copy the other harness installed
- **THEN** the decision is `Ask`

#### Scenario: AnotherHarnessesCheckoutIsNotCovered

- **GIVEN** a checkout of Sentinel that one harness loads in place, and a session of another harness
- **WHEN** a tool call in that session writes a file in the checkout's plugin directory, where no declaration covers it
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
