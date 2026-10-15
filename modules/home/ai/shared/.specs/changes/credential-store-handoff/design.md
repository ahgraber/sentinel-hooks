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

### Decision: SubcommandsThatReadASecret

**Chosen:** `USER_ONLY_STORE_RE` matches `op read`, `op run`, `op inject`, `op item get`, and `op document get`, and `kubectl get secret` or `kubectl get secrets`.
The `op` match allows global options such as `--account <name>` between `op` and the subcommand.
The `kubectl` match allows options such as `-n <namespace>` between `kubectl` and `get`.

**Rationale:** These subcommands print a secret value or place one in a child process's environment.
`op whoami`, `op account list`, `op vault list`, and `op item list` read no secret value, so they stay outside the pattern, as the spec requires.
Options before the subcommand are common in real use; a pattern that requires the subcommand to follow the program name directly misses `kubectl -n prod get secret`.

**Alternatives considered:**

- Match any `op` invocation: refuses `op whoami`, which reads no secret and is useful for checking the CLI's sign-in state.

### Decision: ReasonText

**Chosen:** The reason states that the store holds secrets for the user alone and that no agent reads it, and names the command so the shared instructions can relay it.
Example: "Blocked: 1Password and Kubernetes secrets are for the user alone.
No agent may read them.
Ask the user to run this command in their own terminal."

**Rationale:** `hook-interface ExplanationContract` requires the reason to state what was blocked and why.
The shared instructions already ask for the user-run command, so the reason does not repeat them.

## Architecture

```text
Bash command
  │
  ├─ DNS exfil, credential-file pipe, egress, env dump ──► block (unchanged)
  ├─ CREDENTIAL_STORE_RE + non-local network ──────────► block (unchanged, exfiltration reason)
  ├─ USER_ONLY_STORE_RE ───────────────────────────────► block (new, user-only reason)
  ├─ CREDENTIAL_STORE_RE ──────────────────────────────► ask (keychain, vault, aws)
  └─ universal secret scan ────────────────────────────► unchanged
```

## Risks

- **A new `op` subcommand prints a secret and is not matched**: the agent sandboxes still deny `~/.config/op` on Claude, Codex, and the editor, so the read fails there; Pi would ask.
  Add the subcommand to the pattern when found.
- **A kubeconfig outside `~/.kube`** (set through `KUBECONFIG` or kept in a project): the refusal blocks these reads too, which matches the user's decision that agents do not read Kubernetes secrets.
