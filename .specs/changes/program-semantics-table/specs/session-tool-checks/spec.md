# Delta for Session Tool Checks

## ADDED Requirements

### Requirement: ProgramCatalogIsValidatedAtSessionStart

At session start, the system SHALL validate every entry of the program catalog and the alias index: it SHALL warn, naming each invalid entry and its defect, and SHALL stay silent about the catalog where every entry is valid.

It SHALL also report how many programs the agent's command path reaches that the catalog does not list, with the location of a file that lists them.

An invalid entry is a warning, exit 0.
Under `program-catalog` `AnInvalidEntryDisablesOnlyItsProgram`, an invalid entry disables only its own program, so the session is safe to start; what the operator needs is to hear which programs the hooks can no longer read.
Session start is the one moment every agent with a session-start hook shows output to the user, so it is where a catalog defect reaches the operator whichever agent they opened.

Serves: unknown-reads-as-dangerous

#### Scenario: ValidCatalog

- **GIVEN** a new session starts
- **WHEN** every catalog entry and the alias index are valid
- **THEN** the hook is silent about invalid entries

#### Scenario: InvalidCatalogEntry

- **GIVEN** a new session starts
- **WHEN** one catalog entry does not parse or uses a field the schema does not define
- **THEN** the hook prints a warning naming the entry and its defect, and exits 0

#### Scenario: InvalidAliasIndex

- **GIVEN** a new session starts
- **WHEN** the alias index does not parse or names an entry that does not exist
- **THEN** the hook prints a warning naming the defect, and exits 0

#### Scenario: UncatalogedProgramsOnThePath

- **GIVEN** a new session starts
- **WHEN** the command path reaches programs the catalog does not list
- **THEN** the hook prints their count and the location of the file that lists them, and exits 0
