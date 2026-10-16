# Design: credential-store-handoff

## Context

`block-leaks.py` judges credential-store reads with one pattern, `CREDENTIAL_STORE_RE`.
It covers the keychain, `vault`, three `op` subcommands, `aws secretsmanager`, and `kubectl get secret`.
A match piped to a non-local network command is blocked; any other match asks.

Every agent runs this hook: Claude Code and Codex natively, Copilot through its adapter, and Pi through its hook runner.
Codex cannot show a hook prompt, so an ask already reaches Codex as a block.

`hook_response.py` appends the shared refusal instructions to every block.
They tell the agent to stop, report what was blocked, and give the user the exact command to run.
The refusal reason therefore needs to state only why the store is closed to the agent.

## Decisions

### Decision: SplitThePattern

**Chosen:** Move 1Password and Kubernetes secrets into a second pattern, `USER_ONLY_STORE_RE`, and leave the remaining stores in `CREDENTIAL_STORE_RE`.
The new check blocks on any match.
It runs after the network-send check on `CREDENTIAL_STORE_RE` and before the ask, so a store read piped to a remote host still gets the exfiltration reason.
A user-only read with a loopback destination or no network at all reaches the new check.

**Rationale:** Two patterns keep each outcome in one place.
The exfiltration check keeps matching all stores, including the user-only ones, so its behavior is unchanged.

**Alternatives considered:**

- A rule table entry in `block-destructive-ops-patterns.toml`: that table covers destructive operations, not credential access, and `secret-access-blocking` owns this requirement.
- A per-store mode field on one pattern list: more structure than two stores need.

### Decision: ContextIsExfiltration

**Chosen:** Treat a user-only store read as an exfiltration vector, so it is a `block` under the existing definition in `RuleModes`, and exclude it from the loopback exemption in `BlockSecretExfiltration`.

**Rationale:** The agents run on models served over an API, so a secret read into an agent's context leaves the machine before any later command sends it anywhere.
A local destination therefore does not make the read safe.

**Alternatives considered:**

- Widen the definition of `block` beyond exfiltration: unnecessary, because the read already is one.
- Leave the loopback scenario unchanged: the synced baseline would allow and refuse the same command.

### Decision: JudgeTheInvokedProgram

**Chosen:** Judge the words the shared lexer (`shell_words.lex`) produces, not the command text.
For each segment, `bash_commands.invoked` returns the program past `sudo`, `env`, and the other execution wrappers, and the check reads that program's subcommand.
Inline code (`bash -c`, `eval`) is judged recursively through `bash_commands.program_text`.
`USER_ONLY_STORE_RE` judges the raw text only where the lexer cannot: a command it does not lex, such as a multi-line command, and a segment with a command substitution (`$(…)`, backticks, process substitution).

**Rationale:** A pattern over the whole text refused a `grep` for these subcommands, a commit message that quotes them, and an `echo` argument.
The old ask had the same false positive, but an ask can be approved; a block cannot.
The lexer's quoting rules place a quoted argument outside command position.
Falling back to the text where the lexer cannot read keeps the check fail-closed.

**Alternatives considered:**

- Anchor the pattern to the start of the command or a separator: misses `sudo` and `env` wrappers and still matches inside `bash -c` strings.
- Keep the text pattern: refuses commands that only mention the subcommands.

### Decision: SubcommandsThatReadASecret

**Chosen:** The check refuses `op read`, `op run`, `op inject`, `op item get`, and `op document get`, and `kubectl get` with a `secret` or `secrets` resource in any operand.
The resource comparison ignores case, a `/<name>` suffix, a `.<version>` suffix, and comma-separated lists, so `Secret`, `secret.v1`, and `pod/x,secret/y` all match.
Programs that run another program from their arguments (`xargs`, `find`, `watch`, `parallel`) are judged by the text fallback over their arguments.
Global options such as `op --account <name>` and `kubectl -n <namespace>` may come before the subcommand; the value options of each program are listed so their values are not read as the subcommand.

**Rationale:** These subcommands print a secret value or place one in a child process's environment.
`op whoami`, `op account list`, `op vault list`, and `op item list` read no secret value, so they stay outside the pattern, as the spec requires.
Options before the subcommand are common in real use; a pattern that requires the subcommand to follow the program name directly misses `kubectl -n prod get secret`.

**Alternatives considered:**

- Match any `op` invocation: refuses `op whoami`, which reads no secret and is useful for checking the CLI's sign-in state.

### Decision: ReasonText

**Chosen:** The reason names the matched command (`op read`, `kubectl get secret`, or "a 1Password or Kubernetes secret read" where only the text fallback matched), states that the secret is for the user alone, states the exposure risk, and tells the agent to ask the user to run the command.

**Rationale:** `hook-interface ExplanationContract` requires every reason to convey exposure, the credential, and the risk, and to name the specific command where possible.
The shared refusal instructions tell the agent to report how the user can help; the reason supplies the specific help, which is running this command.

## Architecture

```text
Bash command
  │
  ├─ DNS exfil, credential-file pipe, egress, env dump ──► block (unchanged)
  ├─ CREDENTIAL_STORE_RE + non-local network ──────────► block (unchanged, exfiltration reason)
  ├─ lexed program reads 1Password or a Kubernetes secret ► block (new, user-only reason)
  ├─ CREDENTIAL_STORE_RE ──────────────────────────────► ask (keychain, vault, aws)
  └─ universal secret scan ────────────────────────────► unchanged
```

## Risks

- **A form that reads a secret is not matched** (a new `op` subcommand, an unlisted launcher, an unlisted option that takes a value): the hook allows it with no prompt.
  Every agent's sandbox denies `~/.config/op` and `~/.kube`, Pi's included, so the read fails there.
  Add the form to the check when found.
- **A kubeconfig outside `~/.kube`** (set through `KUBECONFIG` or kept in a project): the refusal blocks these reads too, which matches the user's decision that agents do not read Kubernetes secrets.
