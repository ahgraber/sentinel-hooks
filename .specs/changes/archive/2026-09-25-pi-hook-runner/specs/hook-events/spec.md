# Delta for hook-events

## ADDED Requirements

### Requirement: PreToolUseDecidesWhetherTheCallRuns

Before Pi runs a tool call, the extension SHALL run the matching `PreToolUse` hooks with `tool_name`, `tool_input`, and `tool_use_id`, and the tool SHALL run only if the combined decision is an allow, or an ask the user approved.

A block refuses the call.
The model receives the reason, and the turn continues so the model can respond to it.
`permissionDecision` `deny` is a block and `allow` is an allow; `permissionDecisionReason` is the reason.
A hook's `additionalContext` reaches the model when the call proceeds.

Serves: hooks-decide-tool-calls, hooks-guide-the-agent

#### Scenario: Allowed

- **GIVEN** a `PreToolUse` hook that exits 0 with no output
- **WHEN** the agent makes a matching tool call
- **THEN** the tool runs

#### Scenario: DeniedByJSON

- **GIVEN** a `PreToolUse` hook that returns `permissionDecision` `deny` with a reason
- **WHEN** the agent makes a matching tool call
- **THEN** the tool does not run, the model receives the reason, and the model's turn continues

#### Scenario: ContextOnAnAllowedCall

- **GIVEN** a `PreToolUse` hook that allows the call and returns `additionalContext`
- **WHEN** the agent makes a matching tool call
- **THEN** the tool runs, and the context reaches the model before its next response

### Requirement: AnAskIsTheUsersDecision

A combined `PreToolUse` decision of ask SHALL be put to the user as a prompt showing the reason when Pi can show one, and SHALL refuse the call when it cannot.

An ask never lets a call run without the user approving it.
A declined or dismissed prompt refuses the call.

Serves: asks-reach-the-user

#### Scenario: Approved

- **GIVEN** a session with a user interface and a hook that reaches ask
- **WHEN** the user approves the prompt
- **THEN** the tool runs

#### Scenario: Declined

- **GIVEN** a session with a user interface and a hook that reaches ask
- **WHEN** the user declines or dismisses the prompt
- **THEN** the tool does not run, and the model is told the user declined

#### Scenario: NoInterface

- **GIVEN** a session running without a user interface and a hook that reaches ask
- **WHEN** the agent makes a matching tool call
- **THEN** the tool does not run, and the model receives the hook's reason

### Requirement: PostToolUseReportsBackOnTheResult

After a tool call finishes, the extension SHALL run the matching `PostToolUse` hooks when the call succeeded, and the matching `PostToolUseFailure` hooks when it failed, with `tool_name`, `tool_input`, `tool_use_id`, and the tool's result, and a hook's feedback SHALL reach the model beside that result.

Feedback is the reason of an exit 2 or of `decision` `block`, and any `additionalContext`.
The tool has already run, so no outcome undoes it.

Serves: hooks-guide-the-agent

#### Scenario: ContextAfterSuccess

- **GIVEN** a `PostToolUse` hook that returns `additionalContext`
- **WHEN** a matching tool call succeeds
- **THEN** the model receives the tool result and the context together

#### Scenario: FeedbackAfterFailure

- **GIVEN** a `PostToolUseFailure` hook that exits 2 with a reason
- **WHEN** a matching tool call fails
- **THEN** the model receives the failed result and the reason, and no `PostToolUse` hook runs

### Requirement: UserPromptSubmitSeesThePrompt

Before the agent responds to a prompt the user submits, the extension SHALL run the `UserPromptSubmit` hooks with the prompt, and a block SHALL stop the prompt from reaching the agent.

An exit 2 or `decision` `block` stops the prompt and shows the user the reason.
Standard output on exit 0, or `additionalContext`, reaches the model with the prompt.

Serves: hooks-run-on-lifecycle-events, hooks-guide-the-agent

#### Scenario: PromptBlocked

- **GIVEN** a `UserPromptSubmit` hook that exits 2 with a reason
- **WHEN** the user submits a prompt
- **THEN** the agent does not respond to it, and the user sees the reason

#### Scenario: ContextWithThePrompt

- **GIVEN** a `UserPromptSubmit` hook that prints text and exits 0
- **WHEN** the user submits a prompt
- **THEN** the model receives the text with the prompt

### Requirement: StopCanContinueTheTurnOnce

When Pi will not continue on its own, the extension SHALL run the `Stop` hooks with `stop_hook_active`, and a block SHALL send its reason to the agent as a new turn.

`stop_hook_active` is true when the turn now ending was started by a `Stop` hook's block, and false otherwise.
A hook uses it to avoid continuing the agent forever.
A turn the user starts resets it to false.
A turn that ends because the user interrupted it, or because the model call failed, runs no `Stop` hooks: the agent stopped for a reason a hook cannot overrule, and a continuation would undo the interruption or repeat the failing call.

Serves: hooks-guide-the-agent

#### Scenario: BlockContinues

- **GIVEN** a `Stop` hook that exits 2 with a reason
- **WHEN** the agent finishes a turn the user started
- **THEN** the agent starts a new turn with the reason, and the hook saw `stop_hook_active` false

#### Scenario: SecondStop

- **GIVEN** the agent finishes the turn a `Stop` hook's block started
- **WHEN** the `Stop` hooks run again
- **THEN** they see `stop_hook_active` true

#### Scenario: InterruptedOrFailedTurn

- **GIVEN** a `Stop` hook that exits 2 with a reason
- **WHEN** the user interrupts the agent, or the agent's turn ends in a model error
- **THEN** the hook does not run, and the agent stays stopped

#### Scenario: NoBlock

- **GIVEN** a `Stop` hook that exits 0
- **WHEN** the agent finishes a turn
- **THEN** the agent stays stopped

### Requirement: SessionHooksBracketTheSession

The extension SHALL run the `SessionStart` hooks when a session starts, resumes, or is replaced, with `source` naming which, and SHALL run the `SessionEnd` hooks when the session ends.

A `SessionStart` hook's standard output on exit 0, or its `additionalContext`, reaches the model before its first response.
A `SessionEnd` hook's outcome changes nothing, because the session is already ending.
The `SessionStart` hooks run once for each start, even when Pi reports the same start more than once.

Serves: hooks-run-on-lifecycle-events, hooks-guide-the-agent

#### Scenario: StartupContext

- **GIVEN** a `SessionStart` hook that prints text and exits 0
- **WHEN** a new session starts
- **THEN** the hook saw `source` `startup`, and the model receives the text before its first response

#### Scenario: Resumed

- **GIVEN** a `SessionStart` hook
- **WHEN** the user resumes an earlier session
- **THEN** the hook runs with `source` `resume`

#### Scenario: Replaced

- **GIVEN** a `SessionStart` hook
- **WHEN** the user starts a new session in place of the current one, or forks it
- **THEN** the hook runs with `source` `clear` for the new session and `fork` for the fork

#### Scenario: SessionEnds

- **GIVEN** a `SessionEnd` hook that records that it ran
- **WHEN** the user exits Pi
- **THEN** the hook runs

#### Scenario: StartReportedTwice

- **GIVEN** a `SessionStart` hook
- **WHEN** Pi reports the start of the same session twice, with no end between
- **THEN** the hook runs once

#### Scenario: SessionReplaced

- **GIVEN** a `SessionEnd` hook
- **WHEN** the user starts a new session in place of the current one, resumes another, or forks it
- **THEN** the hook runs for the session being left, with `reason` `clear`, `resume`, or `other`
