# When Codex can ask

Codex runs a hook's `ask` response as a failure, so `supports_ask` in `hooks/hook_response.py` returns false for it and every `Ask` reaches Codex as a refusal.
Copilot shows a prompt only for the tools `[ask]` in `hooks/tool-vocabulary.toml` lists for it, `Bash`, `Write`, `Edit`, and `apply_patch`, and takes every other `Ask` as a refusal.
A Pi session with no UI attached takes the refusal path too.

The decisions below were made around that limit.
When an agent gains a working hook `ask`, add it to `supports_ask`, then revisit each item for that agent.
Upstream issues to watch: openai/codex#28437 and openai/codex#20702.

## Widen into a prompt

Each of these was narrowed, or left a refusal, because a prompt would have reached Codex as a refusal of ordinary work.

| Decision                                          | Where                               | Today, on an agent with no prompt                                                         | With a prompt                                                                                                   |
| ------------------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `AnInternalErrorAsksRatherThanBlocks`             | `security-posture-alignment` design | A recurring fault in the tamper hook refuses every mutation                               | The user decides each call                                                                                      |
| `AnUnloadableManifestAsksOnMutatingTools`         | `guarded-path-classes` design       | An unreadable manifest refuses every mutation                                             | The user decides each call                                                                                      |
| Instruction text is guarded                       | `guarded-path-classes` design       | Every edit under `hooks/instructions/` is refused                                         | The edit asks                                                                                                   |
| `ADestructiveOperationOnAnAncestorReachesTheUser` | `hook-tampering-blocking`           | Gates remove, rename, replace, and mode or owner changes on an ancestor, and nothing else | May widen to every mutation naming an ancestor. Prompt volume on Claude is also a reason for the current scope. |
| `ReadIsTheDefault`                                | `guarded-path-classes` design       | A read of a guarded path is never gated                                                   | Narrow asks become possible. Habituation is the main reason for the current rule.                               |
| `BashIsTheReferenceShell`                         | `guarded-path-classes` design       | zsh divergence is not checked, in part because Copilot's terminal ask is a refusal        | Revisit if Copilot's terminal gains a prompt: a zsh divergence could then reach the user as a permissive prompt |

## Fallbacks that exist because no prompt can be shown

With a prompt, each of these becomes a secondary route or can be removed.

| Mechanism                                                                | Where                                                                    | Purpose                                                                                                                                                              |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The retry instruction for an unrecognized command                        | `TheRefusalInstructionFollowsTheReason`, `BlockAIGuidance`               | Tells a refused agent to rerun in an accepted form, since it cannot ask                                                                                              |
| Growth of the admitted read-utility set, such as `rg` with `--no-config` | `RipgrepIsAdmittedWithItsConfigurationRefused`                           | Admits more reads because an unrecognized read is refused rather than asked                                                                                          |
| The Codex reviewer's `USER_APPROVAL_REQUIRED` route                      | `GuardrailEditsRouteToTheUser`, the Codex `config*.toml` reviewer policy | Judges sandbox escalations no hook refused; a hook's refusal of a guardrail edit reaches Codex first and ends with the user (`ARefusalNoSurfaceSeesEndsWithTheUser`) |
| The editor prompt as Copilot's escalation surface                        | `TheEditorPromptIsCopilotsEscalationSurface`                             | Same, for Copilot                                                                                                                                                    |
| The degraded message in `block-leaks.py`                                 | `block-leaks.py`                                                         | Tells the agent to have the user act outside the session                                                                                                             |
| The degraded refusal in `block-destructive-ops.py`                       | `block-destructive-ops.py`                                               | Turns an `ask` rule into a refusal with a note                                                                                                                       |
| The two-form block contract in the test helpers                          | each agent's `tests/conftest.py`                                         | Asserts the exit-2 forms an agent with no prompt receives                                                                                                            |

## Related defect

`block-leaks.py` and `block-destructive-ops.py` call `supports_ask(agent)` with no tool name.
For Copilot that returns false, so those two hooks refuse Copilot even on the tools where it can show a prompt.
The archived `guardrail-ask-gate` change records this as an open, undecided task.
