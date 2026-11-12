# Sentinel

Sentinel checks each action a coding agent takes before the action runs.
It adds a layer of oversight on top of each agent's own sandbox, permissions, and approval settings.
It supports Claude Code, Codex, GitHub Copilot CLI, GitHub Copilot in VS Code, and Pi, and it applies the same policy in each.

The documentation is at <https://ahgraber.github.io/sentinel-hooks/>.

## What Sentinel does with an action

Sentinel matches its response to the risk of the action.

Sentinel refuses these actions:

| Category                                            | Examples                                                                                     |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Reading credentials or sending them off the machine | read `~/.ssh/id_ed25519` or a `.env` file; send a token with `curl`; read a secret with `op` |
| Gaining privileges, persistence, or remote control  | `sudo`; add a cron job; pipe a downloaded script to `sh`                                     |
| Destroying work that cannot be recovered            | `git push --force` without `--force-with-lease`; `rm -rf ~`; `git filter-branch`             |
| Using a tool Sentinel does not know                 | a tool that a new agent release adds before Sentinel lists it                                |

Sentinel asks you before these actions:

| Category                                     | Examples                                                                 |
| -------------------------------------------- | ------------------------------------------------------------------------ |
| Changing Sentinel or its settings            | edit a file in the installed plugin; `claude plugin disable sentinel`    |
| Destructive operations with a legitimate use | `git reset --hard`; `rm -r build/`; `git push --force-with-lease`        |
| Reading what may be a credential             | read a file named `api_token.txt`; read an entry from the macOS Keychain |

Ordinary work proceeds without a prompt from Sentinel: reading and editing project files, running tests, and committing.
Your agent's own approval settings still apply.

## When Sentinel refuses an action

The action does not run.
The agent is told what was refused and why.
In most cases it is also told to stop, not to try the action another way, and to give you what you need to decide whether to run the action yourself.
Sentinel offers the agent no way to approve an action it refused.
If an agent cannot show you a question, Sentinel refuses the action rather than let it proceed without you.

[Answer a question or a refusal](https://ahgraber.github.io/sentinel-hooks/user-guide/asks-and-refusals.html) says what you see in each agent and what to do next.

## Prerequisites

Sentinel's hooks run with these programs, which must be on your `PATH`:

| Program | Used for                                      | Install                                                                             |
| ------- | --------------------------------------------- | ----------------------------------------------------------------------------------- |
| `uv`    | runs the Python hooks                         | `brew install uv`, or see <https://docs.astral.sh/uv/getting-started/installation/> |
| `jq`    | reads the agent's tool call in the Bash hooks | `brew install jq`, or see <https://jqlang.github.io/jq/download/>                   |
| `perl`  | matches dangerous shell commands              | included with macOS; on Linux, use your package manager                             |

`gitleaks` is optional.
Without it, Sentinel detects secrets with its own patterns, which cover fewer formats.
Sentinel reports a missing program when a session starts.

## Install

| Agent                     | Install                                                                                                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claude Code               | `claude plugin marketplace add ahgraber/sentinel-hooks`, then `claude plugin install sentinel@sentinel-hooks`                                                                                                                 |
| Codex                     | `codex plugin marketplace add ahgraber/sentinel-hooks`, install Sentinel from `/plugins`, then run the hook installer that the [install guide](https://ahgraber.github.io/sentinel-hooks/user-guide/install.html#codex) names |
| GitHub Copilot CLI        | `copilot plugin marketplace add ahgraber/sentinel-hooks`, then `copilot plugin install sentinel@sentinel-hooks`                                                                                                               |
| GitHub Copilot in VS Code | In the Agent Customizations editor, select **Browse**, then **Configure Marketplaces**, add `ahgraber/sentinel-hooks`, and install Sentinel                                                                                   |
| Pi                        | `pi install git:github.com/ahgraber/sentinel-hooks`                                                                                                                                                                           |

[Install, update, and remove Sentinel](https://ahgraber.github.io/sentinel-hooks/user-guide/install.html) has the update and remove steps for each agent, and a test that Sentinel runs.

## The session-start report

When a session starts, Sentinel checks two things.
It checks that the programs it needs are installed.
It also checks your agent's settings for any setting that turns Sentinel's hooks off, or that lets something other than you answer Sentinel's questions.
Sentinel reports what it finds and never changes a setting.

[Read the session-start report](https://ahgraber.github.io/sentinel-hooks/user-guide/session-start-report.html) says where the report appears in each agent and how to clear each finding.

## More

- [Install, update, and remove Sentinel](https://ahgraber.github.io/sentinel-hooks/user-guide/install.html)
- [Answer a question or a refusal](https://ahgraber.github.io/sentinel-hooks/user-guide/asks-and-refusals.html)
- [Read the session-start report](https://ahgraber.github.io/sentinel-hooks/user-guide/session-start-report.html)
- [Limits](https://ahgraber.github.io/sentinel-hooks/user-guide/limits.html)
