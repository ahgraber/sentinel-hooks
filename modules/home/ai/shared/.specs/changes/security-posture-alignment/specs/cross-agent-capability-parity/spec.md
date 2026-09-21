# Delta for cross-agent-capability-parity

## ADDED Requirements

### Requirement: EveryAgentImplementsEveryCapability

Serves: every-agent-carries-the-policy

Every agent this repository configures SHALL implement every capability declared in this specs root.

An agent that carries a smaller set is a session in which the missing guardrails do not apply, and the agent is chosen for reasons that have nothing to do with which guardrails should hold.
A capability an agent does not implement is drift, not a decision, unless it is declared as an exception with its reason.

An agent MAY satisfy a capability by invoking the shared implementation rather than carrying its own.

#### Scenario: CapabilityCarriedByEveryAgent

- **GIVEN** a capability declared in this specs root
- **WHEN** each agent's enforcement surface is checked
- **THEN** every agent implements it, directly or by invoking the shared implementation

#### Scenario: CapabilityMissingFromOneAgent

- **GIVEN** a capability no exception covers
- **WHEN** one agent's enforcement surface does not implement it
- **THEN** conformance fails

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

An agent that satisfies a capability by invoking the shared implementation SHALL map every tool its harness can emit onto the declared tool vocabulary, and SHALL refuse a tool name it cannot map rather than forward that name unchanged.

The shared hooks gate on a declared vocabulary and allow any tool outside it, because every agent also emits tools no hook judges.
An unmapped name is therefore indistinguishable at the hook from a tool that was never gated, and the call proceeds with nothing refusing it and nothing reporting it.
Invoking the shared implementation satisfies a capability only where the payload reaches that implementation in a form it recognizes, so the mapping is part of the capability rather than a detail of the adapter.

#### Scenario: MappedToolReachesTheGate

- **GIVEN** a tool the harness emits under its own spelling
- **WHEN** the adapter normalizes the payload
- **THEN** the shared implementation judges it under the declared vocabulary

#### Scenario: UnmappedToolIsRefused

- **GIVEN** a tool name the adapter has no mapping for
- **WHEN** the adapter normalizes the payload
- **THEN** the call is refused, and the unmapped name does not reach the shared implementation

#### Scenario: HarnessGainsATool

- **GIVEN** a harness whose tool set has grown since its mapping was written
- **WHEN** conformance checks that mapping against the harness's declared tool set
- **THEN** conformance fails on the tool with no mapping

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
