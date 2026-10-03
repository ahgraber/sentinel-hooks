# Delta for cross-agent-capability-parity

## ADDED Requirements

### Requirement: EveryAgentImplementsEveryCapability

Serves: every-agent-carries-the-policy

Every capability declared in this specs root SHALL have a recorded kind, and every agent this repository configures SHALL carry every capability of the enforcement kind.

A capability is one of five kinds, and what it means to carry it differs by kind:

- **Enforcement**: a hook the package runs on a harness event.
  The package SHALL hold the hook, and every agent SHALL register it.
- **Mechanism**: a module the hooks import, such as the lexer or the path matcher.
  The package SHALL hold the module; an agent carries it by running the hooks that import it.
- **Posture**: what the manifest declares.
  The manifest SHALL hold the declarations; an agent carries them by running the hooks that read the manifest.
- **Configuration**: what an agent's own configuration must say.
  No package artifact implements it; each agent's configuration is judged against it.
- **Conformance**: a check the package's test suite carries over the package itself, such as this capability.
  The suite SHALL hold the test; no agent carries it, because it judges the package rather than a tool call.

An agent that registers a smaller set of hooks is a session in which the missing guardrails do not apply, and the agent is chosen for reasons that have nothing to do with which guardrails should hold.
A hook an agent does not register is drift, not a decision, unless it is declared as an exception with its reason.

An agent MAY satisfy a capability by invoking the shared implementation rather than carrying its own.

An extension MAY give an agent a mechanism another harness provides natively, such as running registered hooks on its events, confining commands in an OS sandbox, or showing the user a prompt.
Such an extension is part of that agent's harness, and its requirements live with that agent's specs rather than here.
It SHALL NOT decide what a tool call may do: every such decision comes from a shared hook, the manifest, or a configuration this repository declares.

An extension that holds its own pattern, path list, or rule for which tool calls proceed is a reimplementation, a second copy of the policy, and SHALL NOT be written.

The test is removal: take away the shared hooks and their registration, and a harness extension refuses nothing for what a call does.
It may still refuse a call because a hook it runs failed to answer, since that refusal is how it carries the hook's failure direction, not a rule of its own.

The package side of this requirement is checked by test: every capability has a kind and, for every kind but configuration, an artifact that exists, in `hooks/` for the first three kinds and in `tests/` for conformance, and every hook in the package is claimed by a capability.
A hook that enforces nothing, deployed beside the others for an agent's convenience, is listed as tooling and is outside every capability; the check accepts what that list names and nothing else.
The agent side is judged by the assessment, because it reads each agent's registration, which is that agent's configuration.

#### Scenario: CapabilityHasAPackageArtifact

- **GIVEN** a capability of the enforcement, mechanism, posture, or conformance kind
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
- **WHEN** each agent's registration is assessed
- **THEN** every agent registers its hook, directly or through an adapter

#### Scenario: CapabilityMissingFromOneAgent

- **GIVEN** an enforcement capability no exception covers
- **WHEN** one agent's registration does not run its hook
- **THEN** the assessment reports it

#### Scenario: HarnessExtensionWithTheHooksRemoved

- **GIVEN** an extension that runs the shared hooks for an agent
- **WHEN** the shared hooks and their registration are removed
- **THEN** the extension refuses no tool call for what the call does, and refuses only where a hook it runs failed to answer

#### Scenario: ExtensionCarriesItsOwnRule

- **GIVEN** an extension holding a pattern, path list, or rule of its own for which tool calls proceed
- **WHEN** the agent's surfaces are assessed
- **THEN** the extension is reported as a reimplementation

### Requirement: VerdictSurfacesAgree

Serves: every-agent-carries-the-policy

Every surface that turns a tool call into a verdict SHALL reach the outcome the shared verdict tables declare for that input, whether it reimplements a capability or adapts onto the shared implementation.

A reimplementation can diverge because it is a second copy of the policy.
An adapter can diverge without holding any policy at all, because the payload it builds decides which gate the shared implementation applies.
Both failures look the same from the agent's side — the call proceeds — and neither is visible in the source of the surface that caused it.
What can be checked is the verdict, so every such surface SHALL be judged against a shared table of inputs and expected outcomes rather than by reading its source.

#### Scenario: SharedTableAgrees

- **GIVEN** an input in the shared verdict table
- **WHEN** each verdict-reaching surface judges it
- **THEN** every one of them reaches the outcome the table declares

#### Scenario: ReimplementationDiverges

- **GIVEN** an input in the shared verdict table
- **WHEN** a surface that reimplements a capability reaches a different outcome from the shared implementation
- **THEN** conformance fails

#### Scenario: AdapterDiverges

- **GIVEN** an input in the shared verdict table
- **WHEN** a surface that adapts onto the shared implementation reaches a different outcome from a direct invocation of it
- **THEN** conformance fails

#### Scenario: CapabilityAmendedInOnePlace

- **GIVEN** a capability whose contract changes
- **WHEN** only one verdict-reaching surface is amended
- **THEN** conformance fails, because the table is judged against every one of them

### Requirement: AdapterNormalizationIsTotal

Serves: every-agent-carries-the-policy

Every agent SHALL map every tool its harness can emit onto the declared tool vocabulary or find it among the tools the declaration lists as passthrough for that harness, and SHALL refuse a tool name that is neither rather than let it reach the shared implementation unjudged.
An agent whose harness reaches the hooks through an adapter refuses at the adapter.
An agent whose harness sends its tool names to the hooks directly refuses through the hook `unlisted-tool-refusal` specifies.

The shared hooks gate on a declared vocabulary and allow any tool outside it, because every agent also emits tools no hook judges.
An unmapped name is therefore indistinguishable at the hook from a tool that was never gated, and the call proceeds with nothing refusing it and nothing reporting it.
Invoking the shared implementation satisfies a capability only where the payload reaches that implementation in a form it recognizes, so the mapping is part of the capability rather than a detail of the adapter.

The passthrough list is what lets the refusal hold without refusing every read, search, and MCP call a harness makes.
It records that a person decided no hook checks the tool, which an unmapped name does not.
A tool refused on purpose SHALL be declared refused with its reason, so conformance reports only a tool in no table.
A spelling SHALL sit in at most one of the mapped, passthrough, and refused tables, so no reader decides between them.

A passthrough entry MAY be a name pattern, for a harness whose tool names are generated, such as the MCP tools an editor names after the server that provides them.
A pattern admits every later tool its name matches, including one that writes, so it trades the refusal for that family against an edit per new tool.

#### Scenario: DeclaredPassthroughToolProceeds

- **GIVEN** a tool the declaration lists as passthrough for the harness, by name or by pattern
- **WHEN** the adapter normalizes the payload
- **THEN** the call proceeds, and no hook gates it

#### Scenario: SpellingMappedAndPassthrough

- **GIVEN** a declaration that lists a spelling as passthrough and also maps it, directly or through a pattern
- **WHEN** the declaration is read
- **THEN** reading fails, and no adapter runs on it

#### Scenario: MappedToolReachesTheGate

- **GIVEN** a tool the harness emits under its own spelling
- **WHEN** the adapter normalizes the payload
- **THEN** the shared implementation judges it under the declared vocabulary

#### Scenario: UnmappedToolIsRefused

- **GIVEN** a tool name the adapter has no mapping for, and the declaration does not list as passthrough
- **WHEN** the adapter normalizes the payload
- **THEN** the call is refused, and the unmapped name does not reach the shared implementation

#### Scenario: HarnessGainsATool

- **GIVEN** a harness whose tool set has grown since its mapping was written
- **WHEN** conformance checks that mapping against the harness's declared tool set
- **THEN** conformance fails on the tool that is not mapped or listed as passthrough or refused

### Requirement: ToolVocabularyIsDeclared

Serves: every-agent-carries-the-policy

The tool vocabulary the shared implementation gates on SHALL be declared once, in a file beside the manifest that the shared implementation and every adapter read, with each harness's spelling of each tool mapped onto it, and every implementation SHALL read that declaration rather than carry its own copy.

It is not a table of the manifest: `guarded-path-declarations` `OnlyPolicyTablesExist` holds that file to path policy, and a harness spelling is not a path.

A vocabulary spelled in code is one authoring surface per implementation, and each copy drifts on its own.
Undeclared, the vocabulary also has no owner: it becomes whichever harness's spellings the shared code happened to be written against, so every other harness is described by its difference from that one rather than on its own terms.
Declaring it makes each harness's spelling a statement about that harness, and makes the mapping something a test can check.

#### Scenario: VocabularyReadFromTheDeclaration

- **GIVEN** the declared tool vocabulary
- **WHEN** an implementation decides whether it gates a tool
- **THEN** it judges against the declaration rather than against a literal it carries

#### Scenario: SpellingDeclaredOnceReachesEveryConsumer

- **GIVEN** a harness spelling added to the declaration
- **WHEN** each implementation and conformance check runs
- **THEN** every one of them honors it with no further edit

#### Scenario: ImplementationCarriesItsOwnCopy

- **GIVEN** an implementation holding a tool vocabulary of its own
- **WHEN** conformance checks it against the declaration
- **THEN** conformance fails
