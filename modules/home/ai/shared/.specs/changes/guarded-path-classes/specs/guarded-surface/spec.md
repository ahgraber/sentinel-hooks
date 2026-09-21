# Delta for guarded-surface

## ADDED Requirements

### Requirement: AgentHomesAreGuarded

The manifest SHALL declare each agent's home directory guarded: `~/.claude/`, `~/.codex/`, `~/.copilot/`, and `~/.pi/agent/`.

Serves: posture-and-mechanism-are-separate, one-list-then-deltas

An agent home holds the enforcement the agent loads at run time, its settings, its skills, and its instructions, and little else.
One base declaration with the carve-outs beneath it is the shortest true statement of the posture, and a directory kind a harness adds later is guarded the day it appears.
`~/.pi/` is declared at `agent/` because the parent also holds the module's npm prefix.

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

Serves: posture-and-mechanism-are-separate

The editor's settings hold the agent sandbox and approval configuration `agent-configuration-floor` requires, and its instruction files are prompt text an agent loads.
Both are enforcement for the agent that runs inside the editor.

#### Scenario: EditorSettingsWrite

- **GIVEN** the editor's user settings file on the running platform
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

### Requirement: RepositorySourcesAreGuarded

The manifest SHALL declare guarded, by enumeration, each repository location the deployed enforcement resolves to: every user's agent configuration sources, each agent's hook directory, the Codex rules, the Pi security extension, and the editor settings source.

Serves: posture-and-mechanism-are-separate

The deployed paths are symlinks into this repository, so a write to a source is a write to the live guardrail, and a second working tree holds the same sources with no link pointing at them.
Enumeration rather than a base declaration is the choice here because the module tree is mostly ordinary Nix and tests, and asking on every edit to those is the habituation the north star names.
The cost is that a source added later is unguarded until listed; the shared hook directory is the one place that happens, and its hooks are what an operator changes most.

#### Scenario: SourceWriteInAnyWorkingTree

- **GIVEN** a declared repository source, in the main checkout or in a worktree
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

#### Scenario: OrdinaryModuleFileIsNotGuarded

- **GIVEN** a Nix module or a test file under the agent module tree that no declaration covers
- **WHEN** a tool call writes it
- **THEN** the call proceeds

### Requirement: ProfileLayersAreGuarded

The manifest SHALL declare guarded any file that can layer additional permissions over an agent's base configuration, whether or not it exists yet.

Serves: posture-and-mechanism-are-separate

An agent that loads a named configuration layer can widen any permission the base configuration narrows.
Such a layer is enforcement wherever it is stored, and a layer that does not exist yet is guarded by its shape so that creating it asks.

#### Scenario: CreateAProfileLayer

- **GIVEN** a path matching a declared profile-layer shape, where no file exists yet
- **WHEN** a tool call creates it
- **THEN** the decision is `Ask`

### Requirement: AgentCredentialsAreBlocked

The manifest SHALL declare blocked each agent's stored authentication material, the Claude state file `~/.claude.json`, and the rendered MCP environment file.

Serves: posture-and-mechanism-are-separate

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

The manifest SHALL declare exec-through each skills root an agent loads: `~/.claude/skills/`, `~/.codex/skills/`, `~/.pi/agent/skills/`, and `~/.agents/skills/`.

Serves: skill-scripts-run

A skill ships helper scripts and tells the agent to run them by path.
The skill was installed by the user, writes to it still ask, and the sandbox and permission layers still gate what the script touches, so the run itself carries no risk a prompt would address.
`~/.agents/skills/` is declared because the per-agent roots hold links into it, and a declaration does not follow the links inside the directory it names.

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

Serves: posture-and-mechanism-are-separate, reads-are-frictionless

Memory is written in ordinary sessions and changes no enforcement.
Gating it prompts on every note an agent keeps for itself, for no security gain.

#### Scenario: MemoryWrite

- **GIVEN** a file under the declared memory directory
- **WHEN** a tool call writes it
- **THEN** the call proceeds

### Requirement: InstructionTextIsGuarded

The manifest SHALL NOT declare any instructions directory write-through.

Serves: posture-and-mechanism-are-separate

Instruction markdown is prompt text an agent loads, and prompt text shapes what the agent does with every other guardrail.
An edit to it is an edit to the agent's behavior, and whether that happens is the user's decision, as for a hook.
The cost is one prompt per instruction edit, which is authoring the operator does rarely and deliberately.

#### Scenario: InstructionMarkdownWrite

- **GIVEN** a markdown file directly within an agent's instructions directory
- **WHEN** a tool call writes it
- **THEN** the decision is `Ask`

### Requirement: NameHeuristicExceptionIsDeclared

The manifest SHALL declare, as an exception for the name-heuristic surface, the tracked program that renders the MCP environment file and holds no secret itself.

Serves: posture-and-mechanism-are-separate

The program is named for the file it renders, and `sensitive-path-blocking` `TheNameHeuristicIsExcusedOnlyByDeclaration` excuses a name only where the manifest says so.
The manifest SHALL also declare the hook source whose Home Manager store wrapper needs a name-heuristic exception.
That exception applies only to a symlink directly under `/nix/store`, with a valid store hash and the exact `hm_` name produced by Home Manager's filename sanitization, whose target matches the declared source.
An `hm_` prefix alone does not excuse a path, and strong rules still apply to every hop.

#### Scenario: RendererIsReadable

- **GIVEN** the declared renderer program
- **WHEN** a tool call reads it
- **THEN** the call proceeds

#### Scenario: DeclaredHookWrapperIsReadable

- **GIVEN** a Home Manager store wrapper with the exact sanitized name and a target matching the declared hook source
- **WHEN** a tool call reads it
- **THEN** the name heuristic does not refuse the wrapper

#### Scenario: UnverifiedWrapperIsNotExcused

- **GIVEN** an `hm_` name outside `/nix/store`, a non-link, a mismatched sanitized name, or an undeclared source
- **WHEN** a tool call reads it
- **THEN** the wrapper exception does not apply
