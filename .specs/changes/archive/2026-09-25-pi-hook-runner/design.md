# Design: pi-hook-runner

## Context

Pi 0.86.1 exposes lifecycle events to extensions, and an extension's handler can block a tool call, show a confirm dialog, patch a tool result, inject a message before the agent runs, and start a new turn.
Those are the effects Claude Code's hooks produce, so the extension is a translation from Claude Code's hook contract onto Pi's extension API, with no behavior of its own beyond carrying outcomes.

Four published Pi extensions already run Claude Code hooks.
An assessment of their source (bridge 0.3.1, `pi-code` 1.0.77, `@hsingjui/pi-hooks` 0.0.2, `@fyeeme/pi-hooks` 1.0.5) found that none meets the contract in these specs.
Three turn an ask or a refusal into an allow.
`pi-code` comes closest, and it reads only Claude Code's settings files, treats a malformed reply or a signal death as an allow, and is about 20,000 lines with the MCP SDK as a dependency.

## Decisions

### Decision: WrittenHereWithNoRuntimeDependencies

**Chosen:** write the extension in this module, in TypeScript Pi loads directly, using Node's standard library alone.

**Rationale:** the contract is small: read one JSON file, spawn commands, decode their output, and call Pi's API.
Node's `child_process`, `fs`, and `path` cover it, so a dependency would add install and update work with nothing it alone provides.
`pi-code`'s design for running hooks in parallel, ending a process group on timeout, capping output, and combining decisions is reused under its MIT license; its code is not vendored.

**Alternatives considered:**

- Adopt `pi-code`, loading only its hooks module through Pi's package filter: still installs its full dependency tree, and keeps the fail-open cases and the Claude-settings-only registration.
- Vendor a patched copy of `pi-code`'s hooks module: carries its internal imports and its assumption that registrations come from Claude Code's settings chain.
- Adopt one of the other three: each fails the ask or refusal contract.

### Decision: EventsMapOntoPiEvents

**Chosen:**

| Claude Code event                   | Pi event                                                    | Carried to Pi by                                                          |
| ----------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------- |
| `SessionStart`                      | `session_start`, reasons `startup`, `new`, `resume`, `fork` | context held for `before_agent_start`                                     |
| `UserPromptSubmit`                  | `input` from a typed or RPC prompt                          | `{ action: "handled" }` to stop it; context held for `before_agent_start` |
| `PreToolUse`                        | `tool_call`                                                 | `{ block, reason }`, `ctx.ui.confirm`, context held for `tool_result`     |
| `PostToolUse`, `PostToolUseFailure` | `tool_result`, split on `isError`                           | content appended to the result                                            |
| `Stop`                              | `agent_settled`                                             | `pi.sendMessage` with `triggerTurn`                                       |
| `SessionEnd`                        | `session_shutdown`, except `reload`                         | nothing                                                                   |

`source` maps `startup` to `startup`, `new` to `clear`, `resume` to `resume`, and `fork` to `fork`.
A `reload` raises neither `SessionStart` nor `SessionEnd`, because it rebinds the runtime rather than starting or ending a session.
Pi 0.86.1 raises `session_start` twice when a session is replaced, to the same extension instance with the same session ID and reason, so the extension skips a `session_start` whose session ID and reason match the last one it handled; a `session_shutdown` clears that record.
A flag that allowed one start per instance would instead depend on Pi creating an instance for every session, which the extension cannot check.
`SessionEnd`'s `reason` maps `quit` to `prompt_input_exit`, `new` to `clear`, `resume` to `resume`, and anything else to `other`.

**Rationale:** each row is the Pi event whose timing matches Claude Code's.
`input` is used for `UserPromptSubmit` because it is the event that can stop a prompt, and it sees the text as typed.
It cannot add context, so context from `SessionStart` and `UserPromptSubmit` is held and returned as a message from the next `before_agent_start`.
A prompt from `pi.sendMessage` or `sendUserMessage` has `source` `extension` and raises no `UserPromptSubmit`, so a `Stop` continuation is not mistaken for the user.
`PreToolUse` context is returned with the same call's result in `tool_result`, keyed by `toolCallId`, because that places it beside the call it concerns.
`Stop` runs on `agent_settled`, which Pi raises only once it will not continue on its own; `agent_end` can fire before an automatic retry or compaction.
Pi also raises `agent_settled` after an interrupted or failed run, so the extension records the last assistant message's `stopReason` on each `agent_end` and skips `Stop` when it is `aborted` or `error`.

**Alternatives considered:**

- `before_agent_start` for `UserPromptSubmit`: can add context but cannot stop the prompt.
- `agent_end` for `Stop`: fires promptly when another extension holds a dialog open, and can fire on a turn Pi then retries.
- Inject `PreToolUse` context through the `context` event before the next model call: detaches it from the call it concerns.

### Decision: CommandsRunInTheirOwnProcessGroup

**Chosen:** each command runs as `/bin/sh -c <command>` in a new process group, in the session's working directory, with the payload on standard input.
All matching hooks for one event start together.
A hook with no `timeout` gets 60 seconds.
On timeout the extension sends `SIGTERM` to the group, then `SIGKILL` after two seconds.
Standard output and standard error are each capped at 1 MiB; output past the cap is dropped.
Output is read for 250 milliseconds after the hook exits, and the run then ends whether or not the pipes have closed; a background child that a hook started and left running is not ended.

**Rationale:** Claude Code runs a hook's command through a shell, so a registration written for it may use pipes, variables, and `&&`.
A process group lets the extension end a hook's children as well as the hook, which `AHookThatCannotAnswerBeforeAToolCallRefusesIt` requires.
Running hooks together keeps one slow hook from adding its time to every other hook's.
The cap bounds memory for a hook that writes without end; a capped JSON reply no longer parses, so on `PreToolUse` it refuses.
Waiting for the pipes to close instead would hold a hook that answered and left a background job running until its timeout, and then refuse the call.

**Alternatives considered:**

- Run hooks one after another: every hook's time adds up on every tool call.
- Spawn without a shell: breaks registrations that use shell syntax.

### Decision: OutputIsJSONOnlyWhenItLooksLikeJSON

**Chosen:** on any exit status, standard output whose first non-space character is `{` is parsed as the hook's JSON reply; any other output is plain text.
A reply that starts with `{` and does not parse is a failure.
So is a `permissionDecision` other than `allow`, `deny`, or `ask`, which includes Claude Code's `defer`: Pi has no way to suspend a session for a later resume.
Exit 126 and 127 are failures to start, because `/bin/sh` returns them for a command it cannot execute or cannot find.
Exit 129 through 159 is a hook ended by a signal, because `/bin/sh` returns 128 plus the signal number for a command a signal ended; a hook that deliberately exits with one of those statuses refuses a `PreToolUse` call.
The JSON reply is read on every exit status, as Claude Code reads it: on exit 2 it supplies the blocking reason, and on any status other than 2 it decides the outcome.
On exit 2 a `{` reply that does not parse still blocks, with standard error as the reason.

**Rationale:** Claude Code treats plain standard output on exit 0 as text, which `SessionStart` and `UserPromptSubmit` use as context.
Reading everything as JSON would refuse a `PreToolUse` hook that prints a message.
Reading a broken `{` reply as plain text would turn a hook that meant to refuse into an allow, which is the failure the assessment found in two of the published extensions.

### Decision: TheRegistrationIsReadOncePerSession

**Chosen:** `hooks.json` is read from `getAgentDir()` when a session starts or reloads, and the result holds for that session.
An unusable file is reported with `ctx.ui.notify` at error level and with a `ctx.ui.setStatus` indicator that stays until the session ends; without a UI it goes to standard error.

**Rationale:** reading once makes every event in a session run the same registrations, and `/reload` picks up an edit.
`getAgentDir()` honors `PI_CODING_AGENT_DIR`, so the file follows Pi's agent directory wherever it is.

**Alternatives considered:**

- Re-read on every event: an edit mid-session changes which checks run between one tool call and the next.
- Refuse every tool call while the file is unusable: keeps checks from being skipped, and makes one typo stop all work; the loud, persistent report was chosen instead.

### Decision: ThePayloadCarriesNoTranscriptPath

**Chosen:** the payload carries `session_id`, `cwd`, `hook_event_name`, and the event's fields, and omits Claude Code's `transcript_path` and `permission_mode`.

A `PostToolUse` payload carries Pi's result as `tool_response`, with its `content` and `details`; a `PostToolUseFailure` payload carries the result's text as `error`, the field names Claude Code uses for each.

**Rationale:** Pi's session file is not Claude Code's transcript format, so a hook reading it as one would misparse it.
Some hooks also take `transcript_path` as a sign that Claude Code invoked them.
Leaving a field out is safer than filling it with something that means something else.

## Architecture

```text
hooks.json ──read at session start──▶ registrations
                                            │
Pi event ──▶ handler ──match──▶ commands ──spawn (group, timeout, cap)──▶ outcomes
                                                                           │
                                                   decode (exit, JSON) ◀───┘
                                                           │
                                          combine (block > ask > allow)
                                                           │
                         Pi effect: block / confirm / result patch / message / new turn
```

Source lives in `modules/home/ai/pi/hooks/`: `extension.ts` holds the event handlers and takes Pi's API and agent directory as arguments, `index.ts` passes Pi's `getAgentDir` to it, and the reading, matching, running, and decoding sit in modules beside it, each testable without Pi.

## Risks

- **A `Stop` hook that always blocks continues the agent without end.**
  Claude Code leaves the guard to the hook through `stop_hook_active`, and so does this extension.
  Mitigation: the flag is provided and tested; no cap is added, because no story asks for one.
- **Pi's event contract moves.**
  The extension depends on the timing and return values of seven Pi events.
  Mitigation: the suite drives the handlers through a stand-in for Pi's API, and a live session over RPC exercises each event against the installed build.
- **The 60-second default and the 1 MiB cap are this extension's, not Claude Code's.**
  A hook tuned against Claude Code's limits may behave differently.
  Mitigation: both are stated here, and a registration sets `timeout` per hook.

## Verification Waivers

- **Requirement:** the parts of these requirements that only a Pi process performs: `RegistrationsAreReadFromOneFile` (the file is found through Pi's `getAgentDir`); `PreToolUseDecidesWhetherTheCallRuns` (Pi runs, refuses, and patches the result of a real call); `AnAskIsTheUsersDecision` (Pi's confirm dialog, approved and declined); `StopCanContinueTheTurnOnce` (`agent_settled` and a continuation turn); `SessionHooksBracketTheSession` (`session_start` at startup, and `session_shutdown` then `session_start` when the session is replaced with `new`); and `UnusableRegistrationIsReportedForTheWholeSession` (the error, the indicator, and a tool call that still runs).
  Resume, fork, and quit are covered only by the stand-in tests.
  **Reason:** `index.ts` passes Pi's `getAgentDir`, and Pi alone raises its events and applies what the handlers return; both exist only inside a Pi process with a model that calls tools, which the test suite does not run.
  The handlers themselves are covered by `extension.test.mjs` through a stand-in for Pi's API.
  **Manual evidence:** `evidence/live-rpc-output.txt`, produced by `evidence/live-rpc-driver.mjs` against Pi 0.86.1 with the extension loaded from this checkout and `PI_CODING_AGENT_DIR` set to a temporary directory.
  **Recorded:** 2026-09-25
