# Delta for hook-execution

## ADDED Requirements

### Requirement: PackageHooksAreGivenThePackageDirectory

Every hook the package's registration file declares SHALL run with the environment variable `PLUGIN_ROOT` set to the absolute path of the installed plugin directory that holds the extension.
A hook the agent directory's registration file declares SHALL run without `PLUGIN_ROOT` set by the extension.

A hook command runs in the session's working directory, so a package hook cannot name its script by a path relative to the package.
The value is wherever Pi installed the package, so no registration names a fixed install path.
A user's own hook belongs to no package, as a hook in a user's settings belongs to no plugin in Claude Code.

Serves: install-per-agent

#### Scenario: PackageHookReadsThePackageDirectory

- **GIVEN** a hook in the package's registration file that prints `PLUGIN_ROOT`
- **WHEN** it runs in a session started in a project directory
- **THEN** it prints the absolute path of the plugin directory inside the package Pi installed

#### Scenario: UserHookHasNoPackageDirectory

- **GIVEN** a hook in the agent directory's registration file that prints `PLUGIN_ROOT`, in a Pi process whose environment does not set it
- **WHEN** it runs
- **THEN** it prints nothing

### Requirement: ASystemMessageReachesTheUser

The extension SHALL show the user the `systemMessage` a hook's JSON reply carries, on every event and whatever the hook decides, and SHALL show it whole.
A hook's error report longer than a set length SHALL be shortened in the middle, keeping its start, which names the hook, and its end, which holds the error, and saying how many characters it left out.
Every other text the extension shortens before the model or the user sees it, such as a hook's name or a refusal built from a hook that gave no answer, SHALL be shortened the same way, so one rule says what a shortened text keeps.

Claude Code and Codex show this field to the user, and a hook uses it for a report the user must see and the model need not act on.
The session-start check reports the settings that defeat the hooks this way, so the same reply reaches the user in Pi.
Where Pi has no UI, the message goes to standard error, as the extension's other reports do.
A failing hook can print a traceback or a whole file, and the last line of a traceback names the error, so an error report keeps its end.

Serves: install-per-agent

#### Scenario: SessionHookReportsThroughASystemMessage

- **GIVEN** a `SessionStart` hook that exits 0 with a `systemMessage` on standard output
- **WHEN** a session starts
- **THEN** the user is shown the message, and the session proceeds

#### Scenario: SystemMessageBesideADecision

- **GIVEN** a `PreToolUse` hook whose JSON reply carries a `permissionDecision` and a `systemMessage`
- **WHEN** the agent makes a matching tool call
- **THEN** the user is shown the message, and the decision stands

## MODIFIED Requirements

### Requirement: AHookThatCannotAnswerBeforeAToolCallRefusesIt

> Previously: a reply did not parse only when its text was not JSON.

A `PreToolUse` hook that does not finish within its timeout, cannot be started, is ended by a signal, or writes standard output that begins as a JSON object but does not parse SHALL refuse the tool call, with an explanation naming the hook and what went wrong.
Text that is not valid UTF-8, or that holds `NaN`, `Infinity`, or a number outside the range of a double, does not parse.

A hook is ended by a signal when its command, or a command inside it whose status the hook returns, is ended by one.

On every other event the same failures SHALL be reported to the user, and the event SHALL proceed as though the hook had allowed it.

This departs from Claude Code, which lets a tool call proceed when a hook fails in these ways.
A `PreToolUse` hook exists to decide whether a call runs, so a hook that gave no answer is not read as a yes.
A timed-out hook's process and its children are ended, so a hook does not outlive its answer.

Serves: install-per-agent

#### Scenario: TimeoutBeforeAToolCall

- **GIVEN** a `PreToolUse` hook that sleeps past its `timeout`
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused with an explanation naming the hook and the timeout, and the hook's process is no longer running

#### Scenario: CommandNotFound

- **GIVEN** a `PreToolUse` hook whose command does not exist
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused with an explanation naming the hook

#### Scenario: EndedBySignal

- **GIVEN** a `PreToolUse` hook that kills itself with a signal
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused

#### Scenario: CommandInsideTheHookEndedBySignal

- **GIVEN** a `PreToolUse` hook whose command runs a program that is killed, and returns that program's status
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused

#### Scenario: MalformedJSON

- **GIVEN** a `PreToolUse` hook that exits 0 and writes `{` followed by text that is not JSON
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused

#### Scenario: FailureOnAnotherEvent

- **GIVEN** a `PostToolUse` hook that sleeps past its `timeout`
- **WHEN** a matching tool call completes
- **THEN** the user sees a report naming the hook, and the tool result reaches the model unchanged

#### Scenario: ReplyWithANumberOutsideTheRangeOfADouble

- **GIVEN** a `PreToolUse` hook that exits 0 and writes a JSON object holding `1e400`
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused
