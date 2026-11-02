# Delta for cross-agent-capability-parity

## MODIFIED Requirements

### Requirement: EveryAgentImplementsEveryCapability

> Previously: the agent set was the agents a configuration repository configured, an assessment of each agent's configuration judged the agent side, a configuration kind had no package artifact, and a harness extension's requirements lived in that agent's own specs root with no recorded kind.

Every capability declared in this specs root SHALL have a recorded kind, and every harness Sentinel supports SHALL carry every capability of the enforcement kind.

A capability is one of five kinds, and what it means to carry it differs by kind:

- **Enforcement**: a hook the package runs on a harness event.
  The package SHALL hold the hook, and every agent SHALL register it.
- **Mechanism**: a module the hooks import, such as the lexer or the path matcher.
  The package SHALL hold the module; an agent carries it by running the hooks that import it.
- **Posture**: what the manifest declares.
  The manifest SHALL hold the declarations; an agent carries them by running the hooks that read the manifest.
- **Conformance**: a check the package's test suite carries over the package itself, such as this capability.
  The suite SHALL hold the test; no agent carries it, because it judges the package rather than a tool call.
- **Harness**: an extension that gives one harness a mechanism another harness provides natively, such as Pi's hook runner.
  The package SHALL hold the extension in that harness's directory; only that harness carries it.

An agent that registers a smaller set of hooks is a session in which the missing guardrails do not apply, and the agent is chosen for reasons that have nothing to do with which guardrails should hold.
A hook an agent does not register is drift, not a decision, unless it is declared as an exception with its reason.

An agent MAY satisfy a capability by invoking the shared implementation rather than carrying its own.

An extension MAY give an agent a mechanism another harness provides natively, such as running registered hooks on its events, confining commands in an OS sandbox, or showing the user a prompt.
Such an extension is part of that agent's harness, and its requirements are capabilities of the harness kind.
It SHALL NOT decide what a tool call may do: every such decision comes from a shared hook, the manifest, or the agent's own configuration.

An extension that holds its own pattern, path list, or rule for which tool calls proceed is a reimplementation, a second copy of the policy, and SHALL NOT be written.

The test is removal: take away the shared hooks and their registration, and a harness extension refuses nothing for what a call does.
It may still refuse a call because a hook it runs failed to answer, since that refusal is how it carries the hook's failure direction, not a rule of its own.

A test checks the package side of this requirement.
Every capability has a kind.
Every capability has an artifact that exists in the package: a hook, module, or declaration for the first three kinds; a test for the conformance kind; an extension file for the harness kind.
Every hook in the package belongs to a capability.
A hook that enforces nothing, deployed beside the others for an agent's convenience, is listed as tooling and is outside every capability; the check accepts what that list names and nothing else.
The plugin ships a registration for each harness, so the same check covers the agent side: each registration runs every hook of the enforcement kind, directly or through an adapter.

Serves: install-per-agent

#### Scenario: CapabilityHasAPackageArtifact

- **GIVEN** a capability of the enforcement, mechanism, posture, conformance, or harness kind
- **WHEN** the package is checked
- **THEN** every artifact recorded for it exists in the package

#### Scenario: CapabilityWithNoRecordedKind

- **GIVEN** a capability directory in this specs root that no record assigns a kind
- **WHEN** the package is checked
- **THEN** conformance fails, so adding a capability means saying how it is implemented

#### Scenario: HookClaimedByNoCapability

- **GIVEN** a hook in the package that no capability names and the tooling list does not name
- **WHEN** the package is checked
- **THEN** conformance fails, because a hook with no requirement is behavior the record does not cover

#### Scenario: CapabilityCarriedByEveryAgent

- **GIVEN** a capability of the enforcement kind
- **WHEN** the package is checked
- **THEN** the registration for every harness runs its hook, directly or through an adapter

#### Scenario: CapabilityMissingFromOneAgent

- **GIVEN** an enforcement capability no exception covers
- **WHEN** the registration for one harness does not run its hook
- **THEN** conformance fails

#### Scenario: HarnessExtensionWithTheHooksRemoved

- **GIVEN** an extension that runs the shared hooks for an agent
- **WHEN** the shared hooks and their registration are removed
- **THEN** the extension refuses no tool call for what the call does, and refuses only where a hook it runs failed to answer

#### Scenario: ExtensionCarriesItsOwnRule

- **GIVEN** an extension holding a pattern, path list, or rule of its own for which tool calls proceed
- **WHEN** the agent's surfaces are assessed
- **THEN** the extension is reported as a reimplementation
