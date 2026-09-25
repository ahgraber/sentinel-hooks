# Hook Execution Specification

## Purpose

The Pi hooks extension runs each registered command hook as a process, passes it its event as JSON, and reads its outcome with Claude Code's output contract.
These requirements define the input a hook receives, how its exit status and output decode, how several hooks on one event combine, and what happens when a hook gives no answer.

## Requirements

### Requirement: HookReceivesItsEventAsJSON

Every hook SHALL receive one JSON object on standard input carrying `hook_event_name`, `session_id`, and `cwd`, plus the fields its event defines in `hook-events`, and SHALL run with the session's working directory as its own.

`session_id` is the same for every hook of one Pi session.
`cwd` is the directory Pi runs the agent's tools in.
Tool names and tool input are Pi's own, not translated to Claude Code's.

#### Scenario: PayloadCarriesTheCommonFields

- **GIVEN** a hook that writes its standard input to a file
- **WHEN** it runs on `PreToolUse` for a `bash` call
- **THEN** the file holds `hook_event_name` `PreToolUse`, the session's `session_id` and `cwd`, `tool_name` `bash`, and the call's `tool_input`

#### Scenario: WorkingDirectory

- **GIVEN** a hook that prints its working directory
- **WHEN** it runs in a session started in a project directory
- **THEN** it runs in that directory

### Requirement: OutcomesAreDecodedFromExitStatusAndOutput

The extension SHALL read a hook's outcome from its exit status and standard output as Claude Code does, and SHALL NOT read an exit status of 0 as an allow when standard output carries a decision.

Exit 2 is a block whatever standard output carries.
Its reason is the reason of the JSON object's blocking decision when standard output carries one, and the hook's standard error otherwise.
On any other exit status, a JSON object on standard output decides the outcome, and the exit status does not.
Exit 0 with no JSON on standard output is an allow.
Any other exit status with no JSON on standard output is a non-blocking error: the event proceeds and the hook's standard error is reported.
A hook that could not be started or was ended by a signal, as `AHookThatCannotAnswerBeforeAToolCallRefusesIt` defines them, gave no answer, so its standard output is not read.

#### Scenario: ExitTwo

- **GIVEN** a `PreToolUse` hook that writes a reason to standard error and exits 2
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused, and the model receives the reason

#### Scenario: AskOnExitZero

- **GIVEN** a `PreToolUse` hook that exits 0 with `permissionDecision` `ask` on standard output
- **WHEN** the agent makes a matching tool call
- **THEN** the call is treated as an ask, not as an allow

#### Scenario: ReasonFromJSONOnExitTwo

- **GIVEN** a `PreToolUse` hook that exits 2 with `permissionDecision` `deny` and a reason on standard output, and other text on standard error
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused, and the model receives the JSON object's reason

#### Scenario: JSONOnAnotherExitStatus

- **GIVEN** a `PreToolUse` hook that exits 1 with `permissionDecision` `deny` on standard output
- **WHEN** the agent makes a matching tool call
- **THEN** the call is refused

#### Scenario: ExitOne

- **GIVEN** a `PreToolUse` hook that writes to standard error and exits 1
- **WHEN** the agent makes a matching tool call
- **THEN** the call proceeds, and the user sees the hook's standard error

### Requirement: EveryMatchingHookRunsAndTheStrictestDecides

For one event, every matching hook SHALL run, and the combined decision SHALL be the strictest any of them reached: a block outranks an ask, and an ask outranks an allow.

No hook's outcome stops the others from running.
Where the event's outcome carries reasons or context, those of every hook reaching the combined decision are kept.

#### Scenario: BlockAfterAsk

- **GIVEN** two `PreToolUse` hooks, one reaching ask and one reaching block
- **WHEN** the agent makes a tool call both match
- **THEN** the call is refused, whichever hook is registered first

#### Scenario: AllowAndAsk

- **GIVEN** two `PreToolUse` hooks, one allowing and one reaching ask
- **WHEN** the agent makes a tool call both match
- **THEN** the call is treated as an ask

#### Scenario: HookAfterAnAskStillRuns

- **GIVEN** a hook reaching ask followed by a hook that records that it ran
- **WHEN** the agent makes a tool call both match
- **THEN** the second hook runs

### Requirement: AHookThatCannotAnswerBeforeAToolCallRefusesIt

A `PreToolUse` hook that does not finish within its timeout, cannot be started, is ended by a signal, or writes standard output that begins as a JSON object but does not parse SHALL refuse the tool call, with an explanation naming the hook and what went wrong.

A hook is ended by a signal when its command, or a command inside it whose status the hook returns, is ended by one.

On every other event the same failures SHALL be reported to the user, and the event SHALL proceed as though the hook had allowed it.

This departs from Claude Code, which lets a tool call proceed when a hook fails in these ways.
A `PreToolUse` hook exists to decide whether a call runs, so a hook that gave no answer is not read as a yes.
A timed-out hook's process and its children are ended, so a hook does not outlive its answer.

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
