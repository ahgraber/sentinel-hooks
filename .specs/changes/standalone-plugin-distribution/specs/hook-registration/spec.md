# Delta for hook-registration

## ADDED Requirements

### Requirement: RegistrationsAreReadFromThePackageAndTheAgentDirectory

The extension SHALL run the command hooks declared in two registration files, the `hooks.json` its own package ships and the `hooks.json` in Pi's agent directory, and no others.

The package's file registers Sentinel's hooks.
The agent directory's file registers the user's own hooks, as a user's settings do beside a plugin's hooks in Claude Code.
Hooks from both files run on the events they name, and `hook-execution` `EveryMatchingHookRunsAndTheStrictestDecides` combines their outcomes.

Each file has the shape of Claude Code's `hooks` setting: a top-level `hooks` object whose keys are event names, each holding a list of matcher groups, each group holding a `matcher` and a list of handlers.
A handler of type `command` names a `command` to run and MAY name a `timeout` in seconds.

The extension reads no other file for hooks: not Claude Code's settings, not Pi's `settings.json`, and not any file in the project.

Serves: install-per-agent

#### Scenario: PackageHookRuns

- **GIVEN** the package's `hooks.json` declares a command handler under `PreToolUse`
- **WHEN** Pi is about to run a tool call the group's matcher matches
- **THEN** the command runs

#### Scenario: UserHookRuns

- **GIVEN** the agent directory's `hooks.json` declares a command handler under `PreToolUse`
- **WHEN** Pi is about to run a tool call the group's matcher matches
- **THEN** the command runs

#### Scenario: BothFilesMatchOneCall

- **GIVEN** each file declares a `PreToolUse` handler whose matcher matches the same tool
- **WHEN** Pi is about to run a call to that tool
- **THEN** both commands run

#### Scenario: ProjectFileIsIgnored

- **GIVEN** the project holds a `.pi/hooks.json` and a `.claude/settings.json` that each declare hooks
- **WHEN** Pi raises any event
- **THEN** none of those hooks runs

#### Scenario: NoUserFile

- **GIVEN** Pi's agent directory holds no `hooks.json`
- **WHEN** Pi raises an event the package's file names
- **THEN** the package's hooks run, and nothing is reported

## MODIFIED Requirements

### Requirement: UnusableRegistrationIsReportedForTheWholeSession

> Previously: the extension read one registration file, and an unusable file stopped every hook.

A registration file that exists but cannot be read, does not parse, or does not have the registration shape SHALL be reported to the user as an error when the session starts, and SHALL stay visibly reported for as long as the session runs without it.

While a file is unusable none of its hooks run, and the other file's hooks run as declared.
An event that no usable file's hooks match proceeds.
A file that is present was meant to register hooks, so running none of them is reported as an error and stays in view, rather than appearing once and scrolling away.
Where Pi shows no user interface, the report is written to standard error.

A group whose `matcher` is not a valid regular expression selects no tool.
It is reported and kept in view the same way, and the file's other hooks run, because the problem is confined to that group.

Serves: install-per-agent

<!-- modified-removes: ToolCallsProceed -->

#### Scenario: FileDoesNotParse

- **GIVEN** `hooks.json` holds text that is not JSON
- **WHEN** the session starts
- **THEN** the user sees an error naming the file and the parse error, and an indicator stays in view for the rest of the session

#### Scenario: UnusableUserFileLeavesThePackageHooks

- **GIVEN** a session whose agent directory `hooks.json` is unusable
- **WHEN** the agent makes a tool call the package's file matches
- **THEN** the package's hooks run, and no hook from the unusable file runs

#### Scenario: UnusablePackageFileLeavesTheUserHooks

- **GIVEN** a session whose package `hooks.json` is unusable
- **WHEN** the agent makes a tool call
- **THEN** the hooks in the agent directory's file run as declared, no hook from the package's file runs, and the tool runs if no hook refuses it

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

## REMOVED Requirements

### Requirement: RegistrationsAreReadFromOneFile

Removed because: the extension reads a second registration file, the one its package ships, so a single-file contract does not hold.
`RegistrationsAreReadFromThePackageAndTheAgentDirectory` replaces it.
