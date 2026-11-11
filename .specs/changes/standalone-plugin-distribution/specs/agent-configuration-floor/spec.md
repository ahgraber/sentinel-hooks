# Delta for agent-configuration-floor

## MODIFIED Purpose

> Previously: the requirements judged the configuration a repository deployed for each agent.

Each harness's own settings can stop Sentinel's hooks from running, or let a model answer a question a hook put to the user, with no change to the hooks themselves.
Sentinel reads those settings and reports what defeats its hooks; it never writes them.
These requirements cover the values the session-start check reports, which calls each registration routes to a hook, and how a refused guardrail edit reaches the user.

## ADDED Requirements

### Requirement: SettingsThatDefeatTheHooksAreReported

At session start, Sentinel SHALL report every value, in the settings any supported harness reads, that stops Sentinel's hooks from running or that lets a hook's `ask` be answered without the user.
Each report SHALL name the harness, the settings file, and the setting.
Sentinel SHALL NOT write a settings file.

Sentinel reports only what defeats Sentinel.
A harness's permission mode, sandbox, and network settings are the user's choices about their own work, and Sentinel does not own them.
A report that appears in every session is ignored, so the report is kept for the values that leave a guardrail edit with no route to the user.
Each session reports every supported harness's values, not only its own, because a harness whose hooks are off runs no check of its own.

The settings a harness reads are its user, project, and managed settings files, as that harness merges them for a session in the working directory.
A setting left unset takes the harness's current default, and where that default is a reported value the check reports the setting as unset.
A setting whose default is safe today is not reported while it is unset, so a vendor change to the default is reported only once Sentinel records the new default.

A value is reported only when a probe, the harness's source, or the harness's documentation shows its effect.
The record of each value names that evidence, the harness version, and the date.
A mode's name or description is not evidence.

A value is reported for one of two effects.
It stops Sentinel's hooks from running: it turns off the harness's hooks, switches the Sentinel plugin off, or switches off one hook Sentinel registered.
Or it lets a hook's `ask` be answered without the user, as a permission mode does whose reviewer approves a call a hook asked about.
`configuration-floor.toml` names each value.

A mode in which a hook's `ask` reaches the user, or is refused because no user is present, is not reported.

Serves: install-per-agent

#### Scenario: HooksSwitchedOff

- **GIVEN** settings of any supported harness that turn off all hooks
- **WHEN** a session starts in another supported harness
- **THEN** the session-start report names the harness, the file, and the setting

#### Scenario: SentinelSwitchedOffInSettings

- **GIVEN** settings of any supported harness that switch the Sentinel plugin off, by its own entry or by a default for every plugin
- **WHEN** a session starts in another supported harness
- **THEN** the session-start report names the harness, the file, and the setting

#### Scenario: OneSentinelHookSwitchedOff

- **GIVEN** a harness configuration that switches off one hook Sentinel registered
- **WHEN** a session starts in any supported harness
- **THEN** the session-start report names the harness, the file, and the hook

#### Scenario: AskAnsweredByAModel

- **GIVEN** settings of a supported harness that select a permission mode whose reviewer answers a hook's `ask`
- **WHEN** a session starts in any supported harness
- **THEN** the session-start report names the harness, the file, and the setting

#### Scenario: UnsetSettingWithAnUnsafeDefault

- **GIVEN** a setting whose current default is a reported value, left unset in every settings file
- **WHEN** a session starts
- **THEN** the session-start report names the setting as unset

#### Scenario: UnsetSettingWithASafeDefault

- **GIVEN** a setting whose current default is safe, left unset in every settings file
- **WHEN** a session starts
- **THEN** the session-start report does not name it

#### Scenario: ModeThatKeepsTheAsk

- **GIVEN** settings that select a mode in which a hook's `ask` reaches the user or is refused
- **WHEN** a session starts
- **THEN** the session-start report does not name the mode

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

## REMOVED Requirements

### Requirement: BypassModesAreRefused

Removed because: no repository deploys each agent's configuration now, so no conformance run can refuse a value in it.
`SettingsThatDefeatTheHooksAreReported` reports the values that defeat Sentinel's hooks, and a user's permission mode and sandbox are the user's own settings.

### Requirement: ExperimentControlledDefaultsAreDeclared

Removed because: `SettingsThatDefeatTheHooksAreReported` reports an unset setting whose current default is a reported value, and a setting whose default is safe today is not reported while unset.

### Requirement: NetworkReachIsUniformPerUser

Removed because: the hosts each harness reaches without asking are the user's own settings, and a difference between them does not defeat Sentinel's hooks.
A comparison across harnesses belongs to a configuration audit the user runs on request, which is a later change.

### Requirement: RegisteredHooksLieInTheEnforcementFloor

Removed because: the plugin ships every registration, and the hooks they name are inside the plugin directory.
`guarded-surface` `InstalledEnforcementIsInTheFloor` and `guarded-path-declarations` `EnforcementIsNeverCarvedOut` put every installed copy, every in-place copy, and every other location a harness loads hooks from in the floor.
