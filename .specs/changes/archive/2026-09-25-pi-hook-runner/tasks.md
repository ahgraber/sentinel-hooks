# Tasks: pi-hook-runner

Source lives in `modules/home/ai/pi/hooks/`.
Each module below except the entry point `index.ts` imports nothing from Pi at run time, so its cases run under `node --test` with no Pi process.
The event handlers live in `extension.ts`, which takes Pi's API and the agent directory as arguments; `index.ts` passes Pi's `getAgentDir`.
The event handlers are driven through a stand-in for Pi's extension API that records what each handler returns and calls.
Intra-module imports name the `.ts` extension, because `node --test` strips types natively and does not resolve an extensionless specifier.

## Read the registration

- [x] Add `registration.ts`: read `hooks.json` from a given directory and return the command handlers per event, or a description of why the file is unusable.
  A missing file is no registrations and no error.
- [x] Add cases: a declared `PreToolUse` command is returned; a missing file returns none and no error — evidence for `DeclaredHookRuns` and `NoFile`.
- [x] Add cases: text that is not JSON, and JSON whose `hooks` is not an object of event names, each return an unusable result naming the file and the problem — evidence for `FileDoesNotParse` and `FileHasTheWrongShape`.
- [x] Add a case: a handler whose type is not `command` is reported and dropped, and the command handler beside it is returned; an event this extension does not raise is reported and skipped; an event name that differs from a raised event only in case makes the file unusable — evidence for `UnknownHandlerType`, `EventPiDoesNotRaise`, and `EventNameDiffersOnlyInCase`.

## Match tool names

- [x] Add `matcher.ts`: decide whether a group's matcher matches a tool name, without regard to case; an empty matcher or `*` matches everything, a matcher of letters, digits, `_`, `-`, spaces, `,`, and `|` is a list of exact names separated by `|` or `,`, and anything else is an unanchored regular expression.
  An invalid regular expression matches nothing and is reported.
- [x] Add cases for `Bash` against `bash`, `write|edit` against `edit` and `read`, an empty matcher, `mcp.*` against `mcp`, and `Edit, Write` against `write` — evidence for `CaseDiffers`, `ListOfNames`, `EmptyMatcher`, `RegularExpression`, and `CommaSeparatedNames`.

## Run a command and decode its outcome

- [x] Add `runner.ts`: run one command as `/bin/sh -c` in a new process group, in a given directory, with the payload on standard input, a timeout defaulting to 60 seconds, and standard output and standard error each capped at 1 MiB.
  On timeout send `SIGTERM` to the group, then `SIGKILL` after two seconds.
  Return the exit status, the signal, whether it timed out, whether it failed to start, and both outputs.
- [x] Add a case: a hook that writes its standard input and working directory to a file receives the payload it was given and runs in the given directory — evidence for `PayloadCarriesTheCommonFields` and `WorkingDirectory` at the runner.
- [x] Add a case: a hook that starts a child and sleeps past its timeout is reported as timed out, and neither it nor its child is still running afterward.
- [x] Add `decode.ts`: turn a run result into allow, ask, block, or failure, with its reason and context.
  Output whose first non-space character is `{` is parsed as the JSON reply on any exit status.
  Exit 2 is a block, with the reply's blocking reason if it has one and standard error otherwise.
  On any other status the reply decides; without a reply, exit 0 with output is plain text and any other status is a non-blocking error.
  A timeout, a failure to start, a signal or a status of 129 through 159, and a `{` reply that does not parse are failures.
- [x] Add decode cases: exit 2; exit 0 with `permissionDecision` `ask`, `deny`, and `allow`; exit 0 with plain text; exit 1 — evidence for `ExitTwo`, `AskOnExitZero`, and `ExitOne`.
- [x] Add decode cases: exit 2 with a JSON reason and other standard error; exit 1 with `permissionDecision` `deny`; exit 2 with a `{` reply that does not parse — evidence for `ReasonFromJSONOnExitTwo` and `JSONOnAnotherExitStatus`.
- [x] Add decode cases for each failure: timed out, not started, command not found (exit 127), not executable (exit 126), ended by a signal, a malformed `{` reply, and an unknown `permissionDecision`.
- [x] Add a decode case for exit 137, and a combiner case for a hook `sh -c 'kill -KILL $$' && true` refusing the call — evidence for `CommandInsideTheHookEndedBySignal`.

## Combine the outcomes of one event

- [x] Add `combine.ts`: run every matching hook for one event together, wait for all of them, and return the strictest decision with the reasons and context of every hook that reached it.
  For `PreToolUse` a failure is a block whose reason names the hook and what went wrong; for every other event a failure is a report and the event proceeds.
- [x] Add cases: ask and block combine to block in either registration order; allow and ask combine to ask; a hook after an ask still runs — evidence for `BlockAfterAsk`, `AllowAndAsk`, and `HookAfterAnAskStillRuns`.
- [x] Add cases through the combiner for `PreToolUse`: a timeout, a missing command, a signal, and a malformed reply each refuse with the hook named — evidence for `TimeoutBeforeAToolCall`, `CommandNotFound`, `EndedBySignal`, and `MalformedJSON`.
- [x] Add a case: a `PostToolUse` hook that times out is reported, and the event's outcome carries no feedback from it — evidence for `FailureOnAnotherEvent`.

## Handle Pi's events

- [x] Add `extension.ts` and the entry point `index.ts`: on `session_start`, read the registration from `getAgentDir()`; on an unusable file, notify at error level and set a status indicator that stays for the session, or write to standard error when Pi has no UI.
  Report each skipped handler, skipped event, and invalid matcher the same way at warning level.
- [x] Add cases through the stand-in: a file that does not parse and a file with the wrong shape each notify an error naming the file and set the indicator; without a UI the error reaches standard error; a skipped handler is reported as a warning; a tool call then proceeds and no hook runs — evidence for `UnknownHandlerType` reported, `FileDoesNotParse`, `FileHasTheWrongShape`, `NoInterface`, and `ToolCallsProceed` under `UnusableRegistrationIsReportedForTheWholeSession`.
- [x] Add a case: a `.pi/hooks.json` and a `.claude/settings.json` in the working directory each declaring hooks run none of them — evidence for `ProjectFileIsIgnored`.
- [x] Handle `tool_call` for `PreToolUse`: build the payload from `ctx.sessionManager.getSessionId()`, `ctx.cwd`, `event.toolName`, `event.input`, and `event.toolCallId`; return `{ block: true, reason }` on a block, without `terminate`; hold any `additionalContext` for that call's result.
- [x] Add cases: an allowing hook lets the tool run; a `deny` returns a block carrying the reason with no `terminate`; an allowing hook's context appears in that call's result — evidence for `Allowed`, `DeniedByJSON`, and `ContextOnAnAllowedCall`.
- [x] Add a case: the payload a `PreToolUse` hook receives holds `hook_event_name`, `session_id`, `cwd`, `tool_name` `bash`, `tool_input`, and `tool_use_id`, and no `transcript_path` — evidence for `PayloadCarriesTheCommonFields`.
- [x] Handle an ask: with `ctx.hasUI`, call `ctx.ui.confirm` with the reason and run the tool only on approval; without a UI, return a block with the reason.
- [x] Add cases: approved runs the tool; declined and dismissed each return a block saying the user declined; no UI returns a block carrying the hook's reason — evidence for `Approved`, `Declined`, and `NoInterface` under `AnAskIsTheUsersDecision`.
- [x] Handle `tool_result` for `PostToolUse` and `PostToolUseFailure`, split on `isError`, passing the result; append the combined feedback and any held `PreToolUse` context to the result's content.
- [x] Add cases: context after a success reaches the result; a reason after a failure reaches the result and no `PostToolUse` hook runs — evidence for `ContextAfterSuccess` and `FeedbackAfterFailure`.
- [x] Handle `input` for `UserPromptSubmit` when `event.source` is not `extension`: on a block return `{ action: "handled" }` and notify the reason; hold plain output and `additionalContext` for the next `before_agent_start`.
- [x] Handle `before_agent_start`: return the held `SessionStart` and `UserPromptSubmit` context as one message, then clear it.
- [x] Add cases: a blocked prompt is handled and the reason is shown; printed text reaches the model through `before_agent_start`; a prompt with `source` `extension` runs no `UserPromptSubmit` hook — evidence for `PromptBlocked` and `ContextWithThePrompt`.
- [x] Handle `agent_settled` for `Stop`: pass `stop_hook_active`; on a block send the reason with `pi.sendMessage` and `triggerTurn`, and set the flag; clear the flag on `input` from the user.
- [x] Add cases: a block starts a new turn and the hook saw `stop_hook_active` false; the next `Stop` sees it true; an allowing hook starts no turn — evidence for `BlockContinues`, `SecondStop`, and `NoBlock`.
- [x] Record the last assistant `stopReason` on `agent_end`, and skip `Stop` on `agent_settled` when it is `aborted` or `error`; add cases for each, and for a normal end still running `Stop` — evidence for `InterruptedOrFailedTurn`.
- [x] Handle `session_start` for `SessionStart` with `source` mapped from the reason, skipping `reload`, and hold its context; handle `session_shutdown` for `SessionEnd` with `reason` mapped, skipping `reload`.
- [x] Add cases: startup context reaches the model before its first response with `source` `startup`; a resumed session runs with `source` `resume`; a quit runs `SessionEnd` — evidence for `StartupContext`, `Resumed`, and `SessionEnds`.
- [x] Report an invalid matcher at error level and set the indicator, and keep the file's other hooks running; add a case — evidence for `InvalidMatcher`.
- [x] Set `stop_hook_active` from the outcome of each `Stop` run, and clear it when `Stop` is skipped; add a case for a turn another extension starts after an allowing `Stop` — evidence for `StopCanContinueTheTurnOnce`.
- [x] Add cases through the stand-in: a `PreToolUse` hook that exits 1 and a `PostToolUse` hook that times out each reach the user as a warning naming the hook — evidence for `ExitOne` and `FailureOnAnotherEvent`.
- [x] Add cases: the `UserPromptSubmit` payload carries `prompt`, the `PostToolUse` payload `tool_response`, and the `PostToolUseFailure` payload `error`, each with the common fields; a hook runs in the session's working directory — evidence for `PayloadCarriesTheCommonFields` and `WorkingDirectory`.
- [x] Add cases: a new session runs `SessionStart` with `source` `clear` and a fork with `fork`; a reload from a usable file to an unusable one reports it and sets the indicator; a failing `UserPromptSubmit` hook is reported and the prompt proceeds — evidence for `Replaced` and `FailureOnAnotherEvent`.

## Wire and check

- [x] Load the extension from `pi/default.nix` and list it in Pi's `extensions` setting, beside the ones already loaded.
- [x] Run the extension's suite from `scripts/apps-test.sh pi`, and update `scripts/tests/test-apps-test.sh` for the new suite path.
- [x] Run the suite with no exclusions, and run the shared, claude, codex, and copilot suites to show nothing else changed.
- [x] Exercise a live `pi` session over RPC with a test `hooks.json` covering each event: a refusal the model reads and responds to, an ask answered both ways, context on an allowed call, a `Stop` block that starts one new turn, and an unusable file reported with the indicator in view.
- [x] Add cases: a `Stop` block whose continuation is interrupted leaves the next `Stop` seeing `stop_hook_active` false; an invalid matcher's error names the file; a bad matcher on `Stop` is not reported and its hook runs; a replaced session runs `SessionEnd` with `clear`, `resume`, and `other`; hooks in Pi's `settings.json` do not run; with no `hooks.json` nothing is reported — evidence for `InterruptedOrFailedTurn`, `InvalidMatcher`, `SessionReplaced`, `RegistrationsAreReadFromOneFile`, and `NoFile`.
- [x] Skip a `session_start` whose session ID and reason match the last one handled, cleared on `session_shutdown`, because Pi 0.86.1 raises it twice when a session is replaced; add a case for the repeat and for a start after a shutdown — evidence for `StartReportedTwice`.
- [x] Record the live RPC session in `design.md` under Verification Waivers, since Pi's `getAgentDir` and event dispatch run only inside Pi.
