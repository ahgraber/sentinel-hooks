# Delta for agent-configuration-floor

## MODIFIED Purpose

> Previously: the requirements judged the configuration a repository deployed for each agent.

Each harness's own settings can switch off its permission layer, sandbox, or hooks, and that removes a layer of enforcement with no change to the hooks themselves.
Sentinel reads those settings and reports what weakens a layer; it never writes them.
These requirements cover the values the session-start check reports, which calls each registration routes to a hook, how a refused guardrail edit reaches the user, and which network hosts each harness reaches without asking.

## ADDED Requirements

### Requirement: BypassModesAreReported

At session start, Sentinel SHALL report every value, in the settings any supported harness reads, that disables the permission layer, the sandbox, or the hooks wholesale, or that lets the agent proceed past one of them on its own.
Each report SHALL name the harness, the settings file, and the setting.
Sentinel SHALL NOT write a settings file.

The hooks are defense in depth and say so; the permission layer and the sandbox are the boundary they depend on.
A single settings value can remove that boundary for a whole session, and the hooks cannot detect that it has happened during a tool call.
Each session reports every supported harness's values, not only its own, because a harness whose hooks are off runs no check of its own.

The settings a harness reads are its user, project, and managed settings files, as that harness merges them for a session in the working directory.
A setting left unset takes the harness's current default, and where that default is a forbidden value the check reports the setting as unset.
A setting whose default is safe today is not reported while it is unset, so a vendor change to the default is reported only once Sentinel records the new default.

The forbidden values are configuration identifiers the agents publish, so they are named here rather than described: a Claude `defaultMode` of `bypassPermissions`, a Codex `sandbox_mode` of `danger-full-access`, the Codex `danger-full-access` permission profile, `features.hooks = false`, and `features.plugins = false`; a `disableAllHooks` of `true` in Claude Code or Copilot CLI settings; an `enabledPlugins` entry, a Codex `[plugins]` entry, or a VS Code `chat.plugins.enabled` that switches Sentinel off; and the Copilot CLI values that approve every tool call without a prompt.

A sandbox also carries values that keep it enabled while letting the agent past it, and those are forbidden on the same grounds: a sandbox the agent can decline is not a boundary.
In the editor surface these are `chat.agent.sandbox.allowUnsandboxedCommands`, which lets a command the sandbox refused run outside it; `chat.agent.sandbox.retryWithAllowNetworkRequests`, which retries a refused command with wider network reach; and an `enableWeakerNestedSandbox` of `true` in `chat.agent.sandbox.advanced.runtime`.
In Pi's sandbox extension the values are an `enabled` of `false`, which turns the sandbox off; an `ignoreViolations` entry, which lets the named violations through; and an `enableWeakerNestedSandbox` of `true`, which weakens the sandbox's isolation.

The editor also carries values, apart from the sandbox, that let a call proceed past the permission layer with no prompt from the user, or stop the plugin's hooks from loading or running.
They are forbidden by the first sentence of this requirement whether or not they are listed; the editor carries these today: `chat.tools.global.autoApprove`, which its documentation says "disables critical security protections"; a `chat.permissions.default` of `autoApprove` or `autopilot`, which starts every new session without approval prompts; `chat.tools.terminal.enableAutoApprove`, which lets the rule table approve terminal commands and defaults to permissive; a `chat.defaultConfiguration` whose `approvals` is `assisted`, which lets a model approve calls in the user's place, or `allowAll`, or whose `mode` is `autopilot`; a `chat.tools.edits.autoApprove` entry that approves every path; and a `chat.useHooks` of `false`, which stops the editor's Local harness running any hook.
The editor's own default for `chat.tools.edits.autoApprove` approves every path in the workspace, and that default is not a bypass.
An edit in the workspace is ordinary recoverable work, and the hooks put a guardrail edit to the user.

Which non-bypass mode a settings file selects is not constrained.
A mode that prompts more than another is a judgment about that work, not a weakening of the floor.

Serves: install-per-agent

#### Scenario: ClaudeSettingsDeclaresBypass

- **GIVEN** a Claude settings file the session's working directory reaches that declares a `defaultMode` of `bypassPermissions`
- **WHEN** a session starts in any supported harness
- **THEN** the session-start report names Claude, the file, and `defaultMode`

#### Scenario: CodexConfigDeclaresFullAccess

- **GIVEN** a Codex configuration that declares a `sandbox_mode` of `danger-full-access`, selects the `danger-full-access` permission profile, or disables hooks
- **WHEN** a session starts in any supported harness
- **THEN** the session-start report names Codex, the file, and the setting

#### Scenario: SentinelSwitchedOffInSettings

- **GIVEN** settings of any supported harness that disable all hooks or switch the Sentinel plugin off
- **WHEN** a session starts in another supported harness
- **THEN** the session-start report names the harness, the file, and the setting

#### Scenario: EditorSandboxLetsTheAgentPastIt

- **GIVEN** editor settings with the agent sandbox enabled
- **WHEN** they permit commands to run outside it, permit a refused command to be retried with wider network reach, or weaken the sandbox's isolation, and a session starts
- **THEN** the session-start report names each such setting

#### Scenario: PiSandboxLetsTheAgentPastIt

- **GIVEN** a Pi sandbox configuration
- **WHEN** it disables the sandbox, ignores a class of violations, or enables the weaker nested sandbox, and a session starts
- **THEN** the session-start report names each such setting

#### Scenario: EditorApprovalBypassed

- **GIVEN** editor settings
- **WHEN** they enable global auto-approval, start sessions at an auto-approving permission level, enable terminal auto-approval, delegate approval to a model, approve edits to every path, or turn hook execution off, and a session starts
- **THEN** the session-start report names each such setting

#### Scenario: UnsetSettingWithAnUnsafeDefault

- **GIVEN** a boundary setting whose current default is a forbidden value, left unset in every settings file
- **WHEN** a session starts
- **THEN** the session-start report names the setting as unset

#### Scenario: UnsetSettingWithASafeDefault

- **GIVEN** a boundary setting whose current default is safe, left unset in every settings file
- **WHEN** a session starts
- **THEN** the session-start report does not name it

#### Scenario: ProfilesDifferWithoutBypass

- **GIVEN** two harnesses whose settings select different non-bypass modes
- **WHEN** a session starts
- **THEN** the session-start report names neither

#### Scenario: SettingsFileCannotBeRead

- **GIVEN** a settings file a supported harness reads that does not parse
- **WHEN** a session starts
- **THEN** the session-start report names the file as unchecked, and no settings file is written

## MODIFIED Requirements

### Requirement: RegistrationsRouteTheVocabulary

> Previously: an assessment compared the registrations in each agent's configuration with the vocabulary.

Each hook a registration the plugin ships declares SHALL receive every call whose tool name the tool vocabulary maps onto a tool that hook judges.

A registration selects calls by the agent's own tool names before any hook runs.
A spelling the vocabulary gains reaches a hook only if the registration routes it there, so a hook can be correct about a tool it never sees.
The plugin holds every registration, so a test checks them against the vocabulary.

Serves: install-per-agent

#### Scenario: RegistrationRoutesEveryMappedSpelling

- **GIVEN** a hook that judges a tool, and a harness whose vocabulary maps several spellings onto that tool
- **WHEN** the package is checked
- **THEN** conformance passes only if that harness's registration sends a call under each spelling to that hook

#### Scenario: SpellingTheRegistrationMisses

- **GIVEN** a spelling the vocabulary maps onto a tool a hook judges, which a registration does not route to that hook
- **WHEN** the package is checked
- **THEN** conformance fails, naming the spelling, the hook, and the registration

#### Scenario: RoutingThroughAnAdapter

- **GIVEN** a harness whose adapter or dispatcher decides which hooks a call reaches
- **WHEN** the package is checked
- **THEN** the adapter's or dispatcher's routing is judged as the registration

### Requirement: GuardrailEditsRouteToTheUser

> Previously: the requirement also bound each agent's own review or escalation surface to route a guardrail modification to the user.

Where a harness cannot honor a hook's `Ask`, the hook's refusal of a guardrail modification SHALL tell the agent to stop and report to the user, and SHALL NOT tell it how to make the modification another way.

`Ask` degrades to `Block` on an agent with no honored prompt encoding, per `hook-interface`.
A refusal with no route to the user is where a guardrail gets disabled instead of consulted, which is the failure the ask gate was introduced to end.
The report to the user is the route Sentinel controls: the user makes the change outside that agent, and the guardrail stays closed until then.
A harness's own review surface is that harness's configuration, which Sentinel neither sets nor can judge.

Serves: protect-installed-copy

<!-- modified-removes: AuthorizedGuardrailEdit, UnauthorizedGuardrailEdit -->

#### Scenario: WholesaleBypassRequested

- **GIVEN** a harness whose hook `Ask` degrades to a refusal
- **WHEN** a hook refuses a modification that would disable enforcement rather than change it
- **THEN** the refusal tells the agent to stop and report to the user

#### Scenario: NoSurfaceSeesTheRefusal

- **GIVEN** a harness whose hook refusal reaches no review or escalation surface, such as Codex, whose hooks run before its reviewer, or Pi with no UI attached
- **WHEN** a hook refuses a guardrail modification the user authorized in this conversation
- **THEN** the refusal tells the agent to stop and report to the user, and the modification is not made through that agent

### Requirement: NetworkReachIsUniformPerUser

> Previously: conformance compared the host sets the repository declared for each user it configured for more than one agent.

At session start, Sentinel SHALL report where the hosts the supported harnesses reach without asking differ, naming each host and the harnesses that allow it.

The allowlists live in different files in different notation, so drift is invisible from either side alone.
For the editor, the host set is `chat.agent.sandbox.network.allowedDomains`, which its sandbox applies to terminal commands, together with every host `chat.tools.urls.autoApprove` lets the fetch tool reach without asking; an empty list under an enabled sandbox reaches no host at all.
Its effect is that the same fetch proceeds under one agent and stops for approval under another, which reads as a broken tool rather than as a policy difference, and the usual repair is to widen whichever list is narrower.

A harness with no settings file declares no host set, and it is left out of the comparison.

Serves: install-per-agent

#### Scenario: AgentsAgree

- **GIVEN** two harnesses whose settings declare the same host set
- **WHEN** a session starts
- **THEN** the session-start report names no host

#### Scenario: AgentsDisagree

- **GIVEN** two harnesses, one of which allows a host the other does not
- **WHEN** a session starts
- **THEN** the session-start report names the host and the harness that allows it

#### Scenario: OneAgentSplitAcrossFiles

- **GIVEN** one harness whose host set spans several settings files
- **WHEN** a session starts
- **THEN** the files' hosts are merged as that harness merges them before the comparison

#### Scenario: UserConfiguredForOneAgent

- **GIVEN** only one harness with a settings file
- **WHEN** a session starts
- **THEN** the session-start report names no host

## REMOVED Requirements

### Requirement: BypassModesAreRefused

Removed because: Sentinel reports a forbidden value in the user's settings at session start instead of failing conformance on a repository's configuration, and `BypassModesAreReported` states that contract.

### Requirement: ExperimentControlledDefaultsAreDeclared

Removed because: `BypassModesAreReported` reports an unset setting whose current default is a forbidden value, and a setting whose default is safe today is not reported while unset.

### Requirement: RegisteredHooksLieInTheEnforcementFloor

Removed because: the plugin ships every registration, and the hooks they name are inside the plugin directory.
`guarded-surface` `InstalledEnforcementIsInTheFloor` and `guarded-path-declarations` `EnforcementIsNeverCarvedOut` put every installed copy, every in-place copy, and every other location a harness loads hooks from in the floor.
