# Proposal: pi-hook-runner

## Intent

Claude Code runs commands that its configuration registers as hooks on its lifecycle events, and a hook can allow, refuse, or ask about a tool call, add context for the model, or continue a turn.
Pi has no equivalent: an extension can do each of these things, but only in TypeScript written for that purpose.
This change adds a Pi extension that runs registered command hooks with Claude Code's registration shape, input, and output contract, so a hook is configured for Pi the way it is configured for Claude Code.

## User Stories

### Story: hooks-run-on-lifecycle-events

As a Pi user, I want to register commands that Pi runs on its lifecycle events, the way Claude Code runs hooks, so that behavior configured for Claude Code can be configured for Pi the same way.

### Story: hooks-decide-tool-calls

As a hook author, I want a hook to allow, refuse, or ask about a tool call through Claude Code's output contract, so that a hook written for Claude Code runs under Pi without rewriting its output.

### Story: asks-reach-the-user

As a Pi user, I want a hook's ask shown to me as a prompt, and refused when no prompt can be shown, so that a decision a hook leaves to me is never made without me.

### Story: hooks-guide-the-agent

As a hook author, I want a hook's context to reach the model and a Stop hook to continue the turn, so that a hook can guide the agent under Pi as it does under Claude Code.

### Story: a-hook-failure-is-not-silent

As a hook author, I want a hook that cannot answer to be reported, and a tool call its check depends on to be refused, so that a registered check is never skipped without anyone seeing it.

## Scope

**In scope:**

- A Pi extension that reads hook registrations from its own file, `hooks.json` in Pi's agent directory, and runs the command handlers they list.
- The registration shape of Claude Code's `hooks` setting: event name, matcher groups, and command handlers with a `timeout`.
- The events Pi can source with Claude Code's meaning: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Stop`, and `SessionEnd`.
- The input each event's hooks receive on stdin, and the environment they run in.
- Claude Code's output contract: exit 0, exit 2, other exit codes, and the JSON fields `permissionDecision`, `permissionDecisionReason`, `additionalContext`, `decision`, and `reason`.
- How the outcomes of several hooks on one event combine.
- The runner's behavior when a hook times out, cannot start, dies on a signal, or writes output that does not parse.
- A test suite that runs command hooks through the extension.

**Out of scope:**

- Any particular hook, and what any hook decides.
- Handler types other than `command`: `http`, `prompt`, `agent`, and `mcp_tool`.
- Claude Code events Pi has no source for, such as `SubagentStart`, `TaskCreated`, `PermissionRequest`, and `Notification`.
- Reading Claude Code's own settings files, or Pi's `settings.json`.
- How `hooks.json` is produced or placed.
- Project-level registrations, and `disableAllHooks`.
  No story asks for hooks a repository ships; a later change can read a project file behind Pi's project trust, adding hooks without removing the user's.
- Commands the user runs directly with `!`, which Pi raises as `user_bash`.
  They are the user's decision rather than a tool call the agent makes, and the stories are about hooks judging the agent.

## Approach

The extension is written here rather than adopted.
Four published Claude-hooks extensions for Pi were assessed.
Three turn an ask or a refusal into an allow.
The closest, `pi-code`, reads only Claude Code's settings files, treats a malformed reply or a signal death as an allow, and depends on a large package.
Its MIT-licensed design for running hooks in parallel, killing a process group on timeout, capping output, and combining decisions is reused.

Candidate event mapping: `session_start` for `SessionStart`, `input` or `before_agent_start` for `UserPromptSubmit`, `tool_call` for `PreToolUse`, `tool_result` for `PostToolUse` and `PostToolUseFailure`, `agent_settled` for `Stop`, and `session_shutdown` for `SessionEnd`.
`Stop` runs on `agent_settled` because Pi raises it only once it will not continue on its own; `agent_end` can fire before an automatic retry or compaction.
The extension is native to Pi: a hook receives Pi's tool name and tool input unchanged, with no table translating them to Claude Code's.
A matcher compares tool names without regard to case, so `Bash` and `bash` both match Pi's `bash`, and a matcher written for Claude Code matches wherever Pi's name differs from Claude Code's only in case.
Input field names are not translated: a hook reads Pi's `path` where Claude Code sends `file_path`.

Every matching hook runs, and a refusal outranks an ask, which outranks an allow.
An ask becomes `ctx.ui.confirm` when a UI is attached, and a refusal otherwise.
A refusal does not set Pi's `terminate`, so the model reads the refusal and continues, as it does under Claude Code.

A `PreToolUse` hook that times out, cannot start, dies on a signal, or writes JSON that does not parse refuses the tool call, with an explanation naming the hook.
This departs from Claude Code, which lets the call proceed, and the spec states the difference.
On every other event the same failures are reported as warnings, and the event proceeds.
`UserPromptSubmit` also decides whether something runs, but a failure there that refused would block every prompt until the hook is fixed, including the prompt asking the agent to fix it.
