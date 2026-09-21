# Delta for agent-configuration-floor

## ADDED Requirements

### Requirement: BypassModesAreRefused

Serves: posture-floor-is-enforced

No agent configuration in this repository SHALL declare a value that disables the permission layer, the sandbox, or the hooks wholesale, or that lets the agent proceed past one of them on its own.

The hooks are defense in depth and say so; the permission layer and the sandbox are the boundary they depend on.
A single configuration value can remove that boundary for a whole session, and the hooks cannot detect that it has happened.

The forbidden values are configuration identifiers the agents publish, so they are named here rather than described: a Claude `defaultMode` of `bypassPermissions`, a Codex `sandbox_mode` of `danger-full-access`, the Codex `danger-full-access` permission profile, and `features.hooks = false`.

A sandbox also carries values that keep it enabled while letting the agent past it, and those are forbidden on the same grounds: a sandbox the agent can decline is not a boundary.
In the editor surface these are `chat.agent.sandbox.allowAutoApprove`, which drops the approval prompt for any command the sandbox accepts; `chat.agent.sandbox.allowUnsandboxedCommands`, which lets a command the sandbox refused run outside it; and `chat.agent.sandbox.retryWithAllowNetworkRequests`, which retries a refused command with wider network reach.
Each defaults to permissive, so the floor is expressed against the default rather than against a value somebody chose.

The editor also carries approval bypasses of its own, apart from the sandbox: `chat.tools.global.autoApprove`, which its documentation says "disables critical security protections"; a `chat.permissions.default` of `autoApprove` or `autopilot`, which starts every new session without approval prompts; `chat.tools.terminal.enableAutoApprove`, which lets the rule table approve terminal commands and defaults to permissive; `chat.assistedPermissions.enabled`, which lets a model approve calls in the user's place; a `chat.tools.edits.autoApprove` entry that approves every path; and a `chat.hookFilesLocations` that does not load the hooks directory this repository deploys.
The last is the editor's `features.hooks = false`: the hooks directory is not among the editor's defaults, so only the declaration loads it.

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
- **WHEN** it permits auto-approval inside the sandbox, permits commands to run outside it, or permits a refused command to be retried with wider network reach
- **THEN** conformance fails

#### Scenario: EditorApprovalBypassed

- **GIVEN** an editor configuration in this repository
- **WHEN** it enables global auto-approval, starts sessions at an auto-approving permission level, enables terminal auto-approval, delegates approval to a model, auto-approves edits to every path, or does not load the deployed hooks directory
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
`chat.tools.terminal.enableAutoApprove` defaults to permissive, and `chat.assistedPermissions.enabled` defaults one way on the stable channel and the other on the insiders channel, so each is declared rather than inherited.
A declared setting also carries its reason beside it where the format allows a comment, so a reader of the configuration learns the posture from the file rather than from this specification.

#### Scenario: ExperimentControlledSettingLeftUnset

- **GIVEN** a setting whose default the vendor may change and which governs a boundary this posture depends on
- **WHEN** the repository declares no value for it
- **THEN** conformance fails

#### Scenario: ExperimentControlledSettingDeclared

- **GIVEN** the same setting
- **WHEN** the repository declares a value for it
- **THEN** conformance passes, whichever permitted value it declares

### Requirement: GuardrailEditsRouteToTheUser

Serves: degradation-still-reaches-the-user

Where an agent cannot honor a hook's `Ask`, that agent's own review or escalation surface SHALL route a guardrail modification to explicit user authorization, and SHALL refuse a wholesale bypass outright.

`Ask` degrades to `Block` on an agent with no honored prompt encoding, per `hook-interface`.
A refusal with no route to the user is where a guardrail gets disabled instead of consulted, which is the failure the ask gate was introduced to end.
The agent's own escalation surface is the remaining route, so it carries that decision rather than deciding for the user.

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

### Requirement: NetworkReachIsUniformPerUser

Serves: every-agent-carries-the-policy

For any user this repository configures for more than one agent, the set of hosts those agents reach without asking SHALL be the same across them.

The allowlists live in different files in different notation, so drift is invisible from either side alone.
For the editor, the host set is `chat.agent.allowedNetworkDomains`, which its sandbox applies to terminal commands; an empty list under an enabled sandbox reaches no host at all.
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
