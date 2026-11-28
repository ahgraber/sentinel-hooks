# Probes

Each probe in `scripts/` builds a throwaway plugin or project that carries its own hook.
None of them needs Sentinel, and none changes a harness's configuration.
The user runs each one: it needs a signed-in harness, and most need a person to watch the screen.

A command-line probe for Copilot CLI installs its plugin into a separate `COPILOT_HOME`.
That home has no sign-in, so the user exports a model provider first, for example `COPILOT_PROVIDER_TYPE`, `COPILOT_PROVIDER_BASE_URL`, and `COPILOT_PROVIDER_API_KEY`, and passes that provider's model ID.

Record every result in the active change's `evidence/` directory, with the harness version and the date.
The "last result" column below is a starting expectation, not evidence for a new build.

## Does a hook's `ask` reach the user in this permission mode?

The probe's `PreToolUse` hook answers `ask`, in the output shape Sentinel's hooks use, to a call that creates one named file.
The user answers No to any prompt.
A file that exists afterward was approved by something other than the user.

| Script                 | Run                                                                                                              | Last result                                                                                                                                                |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `claude-ask-probe.sh`  | `sh claude-ask-probe.sh manual\|auto\|bypassPermissions\|dontAsk`                                                | Claude Code 2.1.318: the prompt reached the user in manual, auto, and bypassPermissions. dontAsk was not run.                                              |
| `copilot-ask-probe.sh` | `sh copilot-ask-probe.sh manual\|assisted\|assisted-prompt\|autopilot\|allow-all\|allow-all-interactive <model>` | Copilot CLI 1.0.108: assisted approved the call in both forms. Manual and interactive allow-all prompted. Autopilot and non-interactive allow-all refused. |
| `vscode-ask-probe.sh`  | `sh vscode-ask-probe.sh`, follow the printed steps, then `sh vscode-ask-probe.sh <dir>`                          | VS Code 1.145.2: the confirmation reached the user under default approvals, allow all, and autopilot. Assisted was not offered.                            |

Read the result this way:

- A prompt appears, or the call is refused with no prompt: the mode is not a floor value.
- No prompt appears and the file is created: the mode answers a hook's `ask`.
  Add it to the floor.
- No prompt appears in the manual run: the harness does not honor the `ask` output shape at all.
  Stop and tell the user; this is a defect in Sentinel's output for that harness, not a floor value.

Codex has no probe here: it does not honor a hook's `ask`, and Sentinel's hooks refuse there instead.

## Which session-start hook output does the harness show the user?

Each probe runs session-start hooks that send one marked line a different way: standard error with exit 0 (`PROBE-A`), a `systemMessage` field (`PROBE-B`), and standard error with exit 1 (`PROBE-C`).
The user says which lines appear on screen, and where.

| Script                   | Run                                                        | Last result                                                                                               |
| ------------------------ | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `claude-ask-probe.sh`    | any mode; the session-start lines are part of the same run | Claude Code 2.1.318: `PROBE-B` only.                                                                      |
| `codex-start-probe.sh`   | `sh codex-start-probe.sh`, follow the printed steps        | Codex 0.167.1: `PROBE-B`, after the first prompt. Exit 1 shows "Hook failed" without the hook's text.     |
| `copilot-start-probe.sh` | `sh copilot-start-probe.sh <model>`                        | Copilot CLI 1.0.109: none of the three.                                                                   |
| `vscode-ask-probe.sh`    | the session-start lines are part of the same run           | VS Code 1.145.2: none in the chat. The "GitHub Copilot Chat Hooks" output channel logs the hook's output. |

Codex runs a project's hooks only after the user trusts them in `/hooks`, and runs session-start hooks when the first prompt is sent.
Pi needs no probe: `extensions/pi/` runs its hooks and shows a reply's `systemMessage`.

`session-policy-checks.py` sends its report by the route these probes show.
A harness that stops showing its route is a decision for the user.

## Does the harness give the model a hook's text?

Each probe gives the model one word in the `additionalContext` field of a JSON reply (`marmalade`) and one as plain output (`tangerine`), then asks the model which words it was given.

| Script                     | Run                                                    | Last result                                                           |
| -------------------------- | ------------------------------------------------------ | --------------------------------------------------------------------- |
| `vscode-context-probe.sh`  | `sh vscode-context-probe.sh`, follow the printed steps | VS Code 1.145.2, at session start: `marmalade`.                       |
| `copilot-context-probe.sh` | `sh copilot-context-probe.sh <model>`                  | Copilot CLI 1.0.109, at session start: `none`.                        |
| `copilot-prompt-probe.sh`  | `sh copilot-prompt-probe.sh <model>`                   | Copilot CLI 1.0.109, when a prompt is sent: `none`, and no `PROBE-F`. |

In VS Code the session-start check hands its report to the model in `additionalContext`, because VS Code shows the user none of a session hook's output.

## What does a harness write when a plugin is switched off?

| Script                        | Run                                                                           | Last result                                                                                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pi-switch-off-probe.sh`      | `sh pi-switch-off-probe.sh`, turn the extension off in `pi config`            | Pi 1.4.0: the package entry becomes an object whose `extensions` list holds the path with a `-` prefix.                                                              |
| `copilot-managed-settings.sh` | `sh copilot-managed-settings.sh`, on a computer with managed Copilot settings | Copilot CLI 1.0.108, on a computer whose organization applies a Copilot policy: no managed file and no managed preferences. That policy comes from GitHub's servers. |

`pi-switch-off-probe.sh` installs the clone in `tmp/homes/src` into a Pi home under `tmp/homes/`.
`copilot-managed-settings.sh` only reads; it prints setting names, and values only for hooks, plugins, and permission modes.
The user reads its output before sharing it, because it describes an employer's policy.

The other switch-off values rest on documentation or source.
A probe for one is a settings file with the value set, a session in that harness, and a check of whether Sentinel's hooks ran.
