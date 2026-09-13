# Delta for guarded-path-declarations

## MODIFIED Requirements

### Requirement: SingleDeclarationSource

> Previously: the enumeration named the gated classes, the credential class, the instruction layers, the location-only roots, and the secret-floor representatives, and omitted the read-through locations added on 2026-09-02.

Serves: carve-outs-are-specified

The system SHALL declare the guarded surface in one manifest: the gated protected classes, the agent credential class, the instruction layers, the location-only roots, the read-through locations, the exec-through locations, and the secret-floor representatives.

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

## ADDED Requirements

### Requirement: ReadAndRunAreSeparateClasses

Serves: carve-outs-are-specified

The manifest SHALL carry the read-through locations and the exec-through locations as two classes, and a location SHALL be runnable only where it is declared exec-through.

Permission to run a file held in a location is wider than permission to read one: the hook judges the invocation, not what the script then does.
One class carrying both would make every location a later change declares readable also runnable.

#### Scenario: ReadableLocationIsNotRunnable

- **GIVEN** a location declared read-through and not exec-through
- **WHEN** a command runs a script held there
- **THEN** the command is gated
