# Proposal: credential-store-handoff

## Intent

`AskOnCredentialStoreRead` asks the user before an agent reads any credential store.
For 1Password and Kubernetes secrets, approval cannot succeed on most agents: the Claude, Codex, and editor sandboxes deny `~/.config/op` and `~/.kube`, so an approved read fails with an unexplained filesystem error, and the agent is left looking for another route.
On Pi, whose sandbox denies neither path, the same approval grants the read, so one store answers differently by agent.
The user has decided that 1Password stays out of every agent's reach; a refusal that tells the agent to hand the command to the user matches that decision on every agent.

## User Stories

### Story: hand-off-not-dead-end

As the maintainer, I want an agent that needs a 1Password or Kubernetes secret to stop and ask me to run the command, so that I am not asked to approve a read that then fails, and the agent does not search for a workaround.

### Story: one-answer-per-store

As the maintainer, I want each credential store to get the same answer on every agent, so that whether an agent can read a secret does not depend on which agent I am using.

## Scope

**In scope:**

- `secret-access-blocking`: a refusal for Bash commands that read from the 1Password CLI or Kubernetes secrets, with a reason that directs the agent to the user.
- `secret-access-blocking`: `AskOnCredentialStoreRead` narrowed to the stores this change does not refuse.

**Out of scope:**

- The macOS keychain (`security find-*-password`).
  `security` reaches the keychain over IPC from inside the sandbox (a lookup of a missing item returned exit 44 on 2026-10-15), so an approved read succeeds and the ask is meaningful.
- `vault` and `aws secretsmanager`.
  The maintainer does not use them, and whether an approved read succeeds was not checked.
- Adding `~/.config/op` and `~/.kube` to Pi's `sandbox.json`.
  The hook refusal covers Pi; the sandbox entry is a separate surface decision.
- 1Password service accounts or any route that gives agents scoped secret access.

## Approach

`block-leaks.py` already matches `op read`, `op item get`, and `op run` in one credential-store pattern and asks.
Split that pattern: 1Password and `kubectl get secret` move to a refusal, and the remaining stores keep the ask.
Widen the 1Password match to the subcommands that print a secret: `op inject` and `op document get`, in addition to the three already matched.
The shared refusal instructions already tell the agent to stop and give the user the exact command to run, so the refusal reason only states that the store is for the user alone.
The network-send refusal in `BlockSecretExfiltration` is unchanged and still takes precedence when the read is piped to a network command.

## Resolved Questions

- 2026-10-15 Keep 1Password blocked for every agent, rather than allowing it for the editor or through a service account: keep it blocked.
  Decided with the user.
- 2026-10-15 Which credential stores move from ask to refuse: 1Password and Kubernetes secrets only; other stores stay ask unless shown to be unreachable.
  Decided with the user.
- 2026-10-15 Whether the loopback exemption covers a user-only store read: no; the read places the secret in the agent's context, which reaches the model provider, so the read is exfiltration whatever its destination.
  Decided with the user.
- 2026-10-15 How the refusal finds a store read, after a text pattern refused a `grep` that only mentioned the subcommands: judge the program the shared lexer finds in command position.
  Decided with the user.
