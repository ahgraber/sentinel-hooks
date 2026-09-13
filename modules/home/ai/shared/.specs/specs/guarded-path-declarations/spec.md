# Spec: guarded-path-declarations

## Requirements

### Requirement: SingleDeclarationSource

The system SHALL declare the guarded surface in one manifest: the gated protected classes, the agent credential class, the instruction layers, the location-only roots, and the secret-floor representatives.

Every enforcement implementation SHALL take these declarations from the manifest rather than carrying a copy.
A copy is a second authoring surface, and a second authoring surface is where one platform or one implementation gets left behind.

#### Scenario: TwoImplementationsOneSource

- **GIVEN** two implementations of the tamper policy in different languages
- **WHEN** each judges the same path
- **THEN** they reach the same verdict, because both read the same declarations

#### Scenario: AddedPathReachesEveryConsumer

- **GIVEN** a path is added to a manifest class
- **WHEN** any enforcement implementation next judges that path
- **THEN** the path is treated as a member of that class, with no edit to the implementation

### Requirement: ManifestIsEnforcement

The manifest SHALL belong to the protected surface it declares.

An edit to the manifest changes what every implementation guards, which is the definition of an enforcement change.

#### Scenario: MutateTheManifest

- **GIVEN** any mutating tool call is intercepted
- **WHEN** the target is the manifest
- **THEN** the gate applies, exactly as it does to a hook script

### Requirement: LoadFailureIsReported

Where an implementation cannot load the manifest, the tool call SHALL proceed and the failure SHALL be reported where the invoking agent can report it.
It SHALL NOT be silent: a guard that quietly checks nothing is how the guarded surface disappears without anyone noticing.

Proceeding is deliberate, for the same reason the tamper hook's `FailureMode` proceeds: the hook covers a mix of sensitive and read-only tools, and the operating system sandbox and permission layers do not read the manifest, so they keep enforcing regardless.

#### Scenario: MissingManifest

- **GIVEN** the manifest file is absent
- **WHEN** a tool call is intercepted
- **THEN** the call proceeds, and the failure is reported where the agent can show it

#### Scenario: UnparsableManifest

- **GIVEN** the manifest file cannot be parsed
- **WHEN** a tool call is intercepted
- **THEN** the call proceeds, and the failure is reported where the agent can show it

### Requirement: ConfigurationSurfacesCoverTheDeclarations

Every configuration surface that gates access by path SHALL cover the manifest's declarations as a floor: the per-user agent permission lists, the per-user OS sandbox lists, and the editor's edit-approval globs.

A surface MAY gate more than the manifest declares.
What must not happen is the reverse, where the manifest names something no surface entry covers, because then a hook is the only thing standing between an agent and that path.

Coverage SHALL be judged against concrete representative paths, not by comparing pattern text.
A pattern that looks right and does not match is the failure this requirement exists to catch.

#### Scenario: AgentPermissionFloor

- **GIVEN** a per-user agent permission list
- **WHEN** it is checked against the manifest's representatives
- **THEN** every representative is covered by a rule in that list

#### Scenario: SandboxFloor

- **GIVEN** a per-user OS sandbox configuration
- **WHEN** it is checked against the manifest's representatives
- **THEN** every representative is covered by an entry in that configuration

#### Scenario: EditApprovalFloor

- **GIVEN** an editor edit-approval configuration
- **WHEN** it is checked against the manifest's declared repository sources
- **THEN** every source is covered by an entry requiring approval

### Requirement: ExceptionsAreDeclared

A deliberate loosening of a configuration surface relative to the manifest's declarations SHALL itself be declared in the manifest, with the surface it applies to.

Conformance SHALL accept a declared exception and SHALL treat an undeclared loosening as drift.
The difference between the two is the difference between a decision and an accident, and only the manifest can carry the decision.

#### Scenario: DeclaredException

- **GIVEN** a surface entry loosens coverage for a location the manifest declares as an exception for that surface
- **WHEN** conformance is checked
- **THEN** the surface passes

#### Scenario: UndeclaredLoosening

- **GIVEN** a surface entry loosens coverage for a location the manifest does not declare as an exception
- **WHEN** conformance is checked
- **THEN** the surface fails
