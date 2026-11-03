# Delta for agent-configuration-floor

## ADDED Requirements

### Requirement: BypassModesAreRefused

Serves: posture-floor-is-enforced

No agent configuration in this repository SHALL declare a value that disables the permission layer, the sandbox, or the hooks wholesale, or that lets the agent proceed past one of them on its own.

The hooks are defense in depth and say so; the permission layer and the sandbox are the boundary they depend on.
A single configuration value can remove that boundary for a whole session, and the hooks cannot detect that it has happened.

The forbidden values are configuration identifiers the agents publish, so they are named here rather than described: a Claude `defaultMode` of `bypassPermissions`, a Codex `sandbox_mode` of `danger-full-access`, the Codex `danger-full-access` permission profile, and `features.hooks = false`.

A sandbox also carries values that keep it enabled while letting the agent past it, and those are forbidden on the same grounds: a sandbox the agent can decline is not a boundary.
In the editor surface these are `chat.agent.sandbox.allowUnsandboxedCommands`, which lets a command the sandbox refused run outside it; `chat.agent.sandbox.retryWithAllowNetworkRequests`, which retries a refused command with wider network reach; and an `enableWeakerNestedSandbox` of `true` in `chat.agent.sandbox.advanced.runtime`.
Most default to permissive, so the floor is expressed against the default rather than against a value somebody chose.
In Pi's sandbox extension the values are an `enabled` of `false`, which turns the sandbox off; an `ignoreViolations` entry, which lets the named violations through; and an `enableWeakerNestedSandbox` of `true`, which weakens the sandbox's isolation.

The editor also carries values, apart from the sandbox, that let a call proceed past the permission layer with no prompt from the user, or stop the deployed hooks from loading or running.
They are forbidden by the first sentence of this requirement whether or not they are listed; the editor carries these today: `chat.tools.global.autoApprove`, which its documentation says "disables critical security protections"; a `chat.permissions.default` of `autoApprove` or `autopilot`, which starts every new session without approval prompts; `chat.tools.terminal.enableAutoApprove`, which lets the rule table approve terminal commands and defaults to permissive; a `chat.defaultConfiguration` whose `approvals` is `assisted`, which lets a model approve calls in the user's place, or `allowAll`, or whose `mode` is `autopilot`; a `chat.tools.edits.autoApprove` entry this repository declares that approves every path; a `chat.hookFilesLocations` that does not load the hooks directory this repository deploys; and a `chat.useHooks` of `false`, which stops the editor running any hook.
The editor's own default for `chat.tools.edits.autoApprove` approves every path in the workspace, and that default is not a bypass.
An edit in the workspace is ordinary recoverable work, and the hooks put a guardrail edit to the user; the `false` entries this repository declares for guardrail paths add a second prompt, not a floor.
The last two are the editor's `features.hooks = false`: `chat.hookFilesLocations` decides which hook files load, and `chat.useHooks` decides whether what is loaded runs.

Which non-bypass mode a profile selects is not constrained.
A profile that prompts more than another is a judgment about that profile's work, not a weakening of the floor.

#### Scenario: ClaudeSettingsDeclaresBypass

- **GIVEN** a Claude settings file in this repository
- **WHEN** it declares a `defaultMode` of `bypassPermissions`
- **THEN** conformance fails

#### Scenario: CodexConfigDeclaresFullAccess

- **GIVEN** a Codex configuration in this repository
- **WHEN** it declares a `sandbox_mode` of `danger-full-access`, selects the `danger-full-access` permission profile, or disables hooks
- **THEN** conformance fails

#### Scenario: EditorSandboxLetsTheAgentPastIt

- **GIVEN** an editor configuration in this repository with the agent sandbox enabled
- **WHEN** it permits auto-approval inside the sandbox, permits commands to run outside it, permits a refused command to be retried with wider network reach, weakens the sandbox's isolation, or offers a per-session switch that turns the sandbox off
- **THEN** conformance fails

#### Scenario: PiSandboxLetsTheAgentPastIt

- **GIVEN** a Pi sandbox configuration in this repository
- **WHEN** it disables the sandbox, ignores a class of violations, or enables the weaker nested sandbox
- **THEN** conformance fails

#### Scenario: EditorApprovalBypassed

- **GIVEN** an editor configuration in this repository
- **WHEN** it enables global auto-approval, starts sessions at an auto-approving permission level, enables terminal auto-approval, delegates approval to a model, declares auto-approval of edits to every path, does not load the deployed hooks directory, or turns hook execution off
- **THEN** conformance fails

#### Scenario: ProfilesDifferWithoutBypass

- **GIVEN** two users' configurations declare different non-bypass modes
- **WHEN** conformance is checked
- **THEN** both pass

### Requirement: ExperimentControlledDefaultsAreDeclared

Serves: posture-floor-is-enforced

Where a setting that governs a boundary this posture depends on has a default its vendor may change without a configuration edit, the repository SHALL declare that setting explicitly rather than rely on the default.

A floor expressed only as a prohibition assumes the unset value is safe.
That assumption fails for a setting the vendor can move: the editor marks its agent sandbox switch as experiment-controlled, so whether a session is sandboxed — and therefore which of that sandbox's permissive companions apply — is not decided by this repository at all.
Declaring the value makes the posture a statement about the configuration rather than a bet on a default, and makes a vendor change visible as a conflict instead of a silent shift.

The sandbox switch is not the only such setting.
`chat.tools.terminal.enableAutoApprove` defaults to permissive, `chat.useHooks` is a preview setting an organization policy can turn off, and the editor's approval settings are renamed and re-defaulted between releases, so each is declared rather than inherited.
A declared setting also carries its reason beside it where the format allows a comment, so a reader of the configuration learns the posture from the file rather than from this specification.

#### Scenario: ExperimentControlledSettingLeftUnset

- **GIVEN** a setting whose default the vendor may change and which governs a boundary this posture depends on
- **WHEN** the repository declares no value for it
- **THEN** conformance fails

#### Scenario: ExperimentControlledSettingDeclared

- **GIVEN** the same setting
- **WHEN** the repository declares a value for it
- **THEN** conformance passes, whichever permitted value it declares

### Requirement: RegisteredHooksLieInTheEnforcementFloor

Serves: posture-floor-is-enforced

Every directory that holds a hook an agent's configuration registers SHALL lie inside the enforcement floor that `guarded-path-declarations` defines, both where the agent runs the hook and where a deployed link to it resolves in the repository.

The manifest names the hook directories of the floor rather than the hooks discovering them, because no rule is known that finds hook directories without depending on one repository's layout.
A directory missing from the floor is outside it, so a grant that covers it lets an agent edit a hook it runs without a prompt.
The registrations are the one record of which hooks an agent runs, and they are vendor configuration, so the assessment compares them with the floor rather than a hook reading them.

#### Scenario: RegisteredHookInsideTheFloor

- **GIVEN** an agent registers a hook whose script lies in a directory the floor names, and its deployed link resolves to a repository directory the floor names
- **WHEN** the configuration is assessed
- **THEN** the assessment passes

#### Scenario: RegisteredHookOutsideTheFloor

- **GIVEN** an agent registers a hook whose script lies in a directory the floor does not name
- **WHEN** the configuration is assessed
- **THEN** the assessment fails, naming the registration and the directory

#### Scenario: DeployedHookResolvesOutsideTheFloor

- **GIVEN** a registered hook under a directory the floor names, whose deployed link resolves to a repository directory the floor does not name
- **WHEN** the configuration is assessed
- **THEN** the assessment fails, naming the link and the directory it resolves to

#### Scenario: HookRunThroughAnAdapter

- **GIVEN** an agent that runs the shared hooks through an adapter or a dispatcher
- **WHEN** the configuration is assessed
- **THEN** the adapter or dispatcher and every hook it runs are judged as registered hooks

### Requirement: RegistrationsRouteTheVocabulary

Serves: every-agent-carries-the-policy

Each hook an agent's configuration registers SHALL receive every call whose tool name the tool vocabulary maps onto a tool that hook judges.

A registration selects calls by the agent's own tool names before any hook runs.
A spelling the vocabulary gains reaches a hook only if the registration routes it there, so a hook can be correct about a tool it never sees.
The registrations are vendor configuration, so the assessment compares them with the vocabulary rather than a test reading them.

#### Scenario: RegistrationRoutesEveryMappedSpelling

- **GIVEN** a hook that judges a tool, and an agent whose vocabulary maps several spellings onto that tool
- **WHEN** the configuration is assessed
- **THEN** the assessment passes only if the agent's registration sends a call under each spelling to that hook

#### Scenario: SpellingTheRegistrationMisses

- **GIVEN** a spelling the vocabulary maps onto a tool a hook judges, which the agent's registration does not route to that hook
- **WHEN** the configuration is assessed
- **THEN** the assessment fails, naming the spelling, the hook, and the registration

#### Scenario: RoutingThroughAnAdapter

- **GIVEN** an agent whose adapter or dispatcher decides which hooks a call reaches
- **WHEN** the configuration is assessed
- **THEN** the adapter's or dispatcher's routing is judged as the registration

### Requirement: GuardrailEditsRouteToTheUser

Serves: degradation-still-reaches-the-user

Where an agent cannot honor a hook's `Ask`, that agent's own review or escalation surface SHALL route a guardrail modification to explicit user authorization, and SHALL refuse a wholesale bypass outright.
Where the hook's refusal reaches no such surface, the refusal SHALL tell the agent to stop and report to the user, and the modification SHALL NOT be made through that agent, authorized or not.

`Ask` degrades to `Block` on an agent with no honored prompt encoding, per `hook-interface`.
A refusal with no route to the user is where a guardrail gets disabled instead of consulted, which is the failure the ask gate was introduced to end.
The agent's own escalation surface is the remaining route, so it carries that decision rather than deciding for the user.
Where no surface sees the refused call, the report to the user is the route: the user makes the change outside that agent, and the guardrail stays closed until then.

The distinction the surface must keep is between an edit and a removal.
An edit to a guardrail is the user's to authorize; disabling enforcement wholesale is not, because no session-scoped approval makes it safe.

#### Scenario: AuthorizedGuardrailEdit

- **GIVEN** an agent whose hook `Ask` degrades to a refusal
- **WHEN** its escalation surface judges a guardrail modification the user authorized in this conversation
- **THEN** the modification is approved for exactly the authorized change

#### Scenario: UnauthorizedGuardrailEdit

- **GIVEN** an agent whose hook `Ask` degrades to a refusal
- **WHEN** its escalation surface judges a guardrail modification with no user authorization
- **THEN** the decision is routed to the user rather than settled by the agent

#### Scenario: WholesaleBypassRequested

- **GIVEN** an agent whose hook `Ask` degrades to a refusal
- **WHEN** the modification would disable enforcement rather than change it
- **THEN** it is refused, authorized or not

#### Scenario: NoSurfaceSeesTheRefusal

- **GIVEN** an agent whose hook refusal reaches no review or escalation surface, such as Codex, whose hooks run before its reviewer, or Pi with no UI attached
- **WHEN** a hook refuses a guardrail modification the user authorized in this conversation
- **THEN** the refusal tells the agent to stop and report to the user, and the modification is not made through that agent

### Requirement: NetworkReachIsUniformPerUser

Serves: every-agent-carries-the-policy

For any user this repository configures for more than one agent, the set of hosts those agents reach without asking SHALL be the same across them.

The allowlists live in different files in different notation, so drift is invisible from either side alone.
For the editor, the host set is `chat.agent.sandbox.network.allowedDomains`, which its sandbox applies to terminal commands, together with every host `chat.tools.urls.autoApprove` lets the fetch tool reach without asking; an empty list under an enabled sandbox reaches no host at all.
Its effect is that the same fetch proceeds under one agent and stops for approval under another, which reads as a broken tool rather than as a policy difference, and the usual repair is to widen whichever list is narrower.

Parity is asserted per user, not across the repository.
One user's profile allows what that profile's work needs, and holding a second profile to the first would assert the wrong thing.

#### Scenario: AgentsAgree

- **GIVEN** a user configured for two agents
- **WHEN** both declare the same host set
- **THEN** conformance passes

#### Scenario: AgentsDisagree

- **GIVEN** a user configured for two agents
- **WHEN** one declares a host the other does not
- **THEN** conformance fails

#### Scenario: OneAgentSplitAcrossFiles

- **GIVEN** a user whose configuration for one agent spans several files
- **WHEN** those files declare different host sets
- **THEN** conformance fails

#### Scenario: UserConfiguredForOneAgent

- **GIVEN** a user configured for one agent only
- **WHEN** conformance is checked
- **THEN** the user is unconstrained by this requirement
