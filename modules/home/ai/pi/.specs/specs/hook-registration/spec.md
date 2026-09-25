# Hook Registration Specification

## Purpose

The Pi hooks extension reads command-hook registrations from one file, `hooks.json` in Pi's agent directory, in the shape of Claude Code's `hooks` setting.
These requirements define which file is read, how a group's matcher selects tools, and how a file or matcher that cannot be used is reported.

## Requirements

### Requirement: RegistrationsAreReadFromOneFile

The extension SHALL run the command hooks declared in `hooks.json` in Pi's agent directory, and no others.

The file has the shape of Claude Code's `hooks` setting: a top-level `hooks` object whose keys are event names, each holding a list of matcher groups, each group holding a `matcher` and a list of handlers.
A handler of type `command` names a `command` to run and MAY name a `timeout` in seconds.

The extension reads no other file for hooks: not Claude Code's settings, not Pi's `settings.json`, and not any file in the project.

#### Scenario: DeclaredHookRuns

- **GIVEN** `hooks.json` declares a command handler under `PreToolUse`
- **WHEN** Pi is about to run a tool call the group's matcher matches
- **THEN** the command runs

#### Scenario: ProjectFileIsIgnored

- **GIVEN** the project holds a `.pi/hooks.json` and a `.claude/settings.json` that each declare hooks
- **WHEN** Pi raises any event
- **THEN** none of those hooks runs

#### Scenario: NoFile

- **GIVEN** Pi's agent directory holds no `hooks.json`
- **WHEN** Pi raises any event
- **THEN** no hook runs, and nothing is reported

### Requirement: UnusableRegistrationIsReportedForTheWholeSession

A `hooks.json` that exists but cannot be read, does not parse, or does not have the registration shape SHALL be reported to the user as an error when the session starts, and SHALL stay visibly reported for as long as the session runs without it.

While the file is unusable no hook runs, and every event proceeds.
A file that is present was meant to register hooks, so running none of them is reported as an error and stays in view, rather than appearing once and scrolling away.
Where Pi shows no user interface, the report is written to standard error.

A group whose `matcher` is not a valid regular expression selects no tool.
It is reported and kept in view the same way, and the file's other hooks run, because the problem is confined to that group.

#### Scenario: FileDoesNotParse

- **GIVEN** `hooks.json` holds text that is not JSON
- **WHEN** the session starts
- **THEN** the user sees an error naming the file and the parse error, and an indicator stays in view for the rest of the session

#### Scenario: ToolCallsProceed

- **GIVEN** a session whose `hooks.json` is unusable
- **WHEN** the agent makes a tool call
- **THEN** the tool runs, and no hook runs

#### Scenario: FileHasTheWrongShape

- **GIVEN** `hooks.json` parses but its `hooks` value is not an object of event names
- **WHEN** the session starts
- **THEN** the user sees an error naming the file and saying its shape is wrong

#### Scenario: NoInterface

- **GIVEN** a session running without a user interface and an unusable `hooks.json`
- **WHEN** the session starts
- **THEN** the error is written to standard error

#### Scenario: InvalidMatcher

- **GIVEN** `hooks.json` declares one `PreToolUse` group whose matcher is `bash(` and another whose matcher is valid
- **WHEN** the session starts and the agent makes a tool call the valid group matches
- **THEN** the user sees an error naming the invalid matcher, an indicator stays in view, and the valid group's hooks run

#### Scenario: UnknownHandlerType

- **GIVEN** `hooks.json` declares a handler whose type is not `command`
- **WHEN** the file is read
- **THEN** that handler is reported and skipped, and the command handlers beside it run

#### Scenario: EventPiDoesNotRaise

- **GIVEN** `hooks.json` declares hooks under an event this extension does not raise, such as `Notification`
- **WHEN** the file is read
- **THEN** those hooks are reported and skipped, and the hooks under other events run

#### Scenario: EventNameDiffersOnlyInCase

- **GIVEN** `hooks.json` declares hooks under `pretooluse`
- **WHEN** the session starts
- **THEN** the file is reported as unusable, because the name differs from `PreToolUse` only in case and was meant as that event

### Requirement: MatchersSelectByToolName

For the tool events, a group's hooks SHALL run for a tool call exactly when the group's `matcher` matches the tool's name, compared without regard to case.

An empty matcher or `*` matches every tool.
A matcher of letters, digits, `_`, `-`, spaces, `,`, and `|` is a list of exact names separated by `|` or `,`.
Any other matcher is a regular expression that matches if it is found anywhere in the name.
For every other event the matcher is ignored and the group's hooks always run.

#### Scenario: CaseDiffers

- **GIVEN** a `PreToolUse` group whose matcher is `Bash`
- **WHEN** the agent calls Pi's `bash` tool
- **THEN** the group's hooks run

#### Scenario: ListOfNames

- **GIVEN** a group whose matcher is `write|edit`
- **WHEN** the agent calls `edit`, and later calls `read`
- **THEN** the group's hooks run for `edit` and not for `read`

#### Scenario: CommaSeparatedNames

- **GIVEN** a group whose matcher is `Edit, Write`
- **WHEN** the agent calls `write`
- **THEN** the group's hooks run

#### Scenario: EmptyMatcher

- **GIVEN** a group whose matcher is empty
- **WHEN** the agent calls any tool
- **THEN** the group's hooks run

#### Scenario: RegularExpression

- **GIVEN** a group whose matcher is `mcp.*`
- **WHEN** the agent calls a tool named `mcp`
- **THEN** the group's hooks run
