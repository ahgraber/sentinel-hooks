# Delta for hook-tampering-blocking

## ADDED Requirements

### Requirement: CarvedOutLocationsAreClassified

Serves: skill-scripts-run, carve-outs-are-specified

Where a Bash command names carved-out locations alone, the system SHALL classify the command before gating it, and the command SHALL proceed where it is recognized as a read of those locations or as a run of a script held in an exec-through location.
A command recognized as neither SHALL be gated, and the reason SHALL name the forms that would have proceeded.

One protected path outside the carved-out locations SHALL gate the whole command, whatever the rest of it does.

Some protected locations hold material an agent is meant to use rather than change.
An agent's skills directory holds the instructions it reads and the helper scripts those instructions name by path, so gating either form gates ordinary use of an installed skill.

Recognition SHALL rest on the command text alone.
A command whose effect that text does not show SHALL NOT be recognized, because the classifier cannot judge what it cannot see.

#### Scenario: RecognizedReadUnderReadThrough

- **GIVEN** a Bash tool call names read-through locations alone
- **WHEN** the command is a recognized read
- **THEN** the hook exits 0

#### Scenario: RecognizedRunUnderExecThrough

- **GIVEN** a Bash tool call names exec-through locations alone
- **WHEN** the command runs a script held there
- **THEN** the hook exits 0

#### Scenario: EffectHiddenFromTheCommandText

- **GIVEN** a Bash tool call names carved-out locations alone
- **WHEN** the command carries a redirection a substitution an assignment that picks which binary runs or program text handed to an interpreter
- **THEN** the gate applies

#### Scenario: UnrecognizedCommandNamesTheAcceptedForms

- **GIVEN** a Bash tool call names carved-out locations alone
- **WHEN** the command is neither a recognized read nor a recognized run
- **THEN** the decision is `Ask`, and the reason names the read commands and the interpreters that would have proceeded

#### Scenario: CarveOutMixedWithProtectedPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command names a carved-out path and a protected path outside those locations
- **THEN** the gate applies to the whole command

### Requirement: ARunTargetsAnExistingScript

Serves: skill-scripts-run

The system SHALL recognize a run only where the file it names already exists and is a program.

A path the run would create is a write, and a file the interpreter would not execute is not the thing this carve-out permits.

#### Scenario: ScriptAlreadyHeldThere

- **GIVEN** a Bash tool call names a file in an exec-through location
- **WHEN** the file exists and is a program
- **THEN** the hook exits 0

#### Scenario: TargetIsNotAProgram

- **GIVEN** a Bash tool call names a file in an exec-through location
- **WHEN** the file exists and is not a program
- **THEN** the gate applies

#### Scenario: TargetDoesNotExist

- **GIVEN** a Bash tool call names a path in an exec-through location
- **WHEN** no file exists at that path
- **THEN** the gate applies
