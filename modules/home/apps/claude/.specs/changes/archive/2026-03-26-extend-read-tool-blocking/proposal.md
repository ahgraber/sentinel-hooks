# Proposal: extend-read-tool-blocking

## Intent

The sandbox `denyRead` rules (`.ssh`, `.aws`, `.gnupg`, `.config/gcloud`) only enforce against the Bash tool.
The dedicated `Read` tool bypasses them and falls back to a user permission prompt.
This means zero-access paths — paths Claude should never be able to read — can currently be read via `Read` with only a dialog standing in the way.

A confused-deputy attack (e.g., prompt injection in a file or webpage) could trick Claude
into reading an SSH private key or AWS credentials and then incorporating them into a
subsequent command or network call before the user realises what happened.

Additionally, `ask` mode prompts across all hooks currently lack consistent explanation
quality: they state what is happening but not why it matters or what the downstream risk is.

## Scope

**In:**

- Extend `block-sensitive-paths.py` to cover the `Read` tool: hard-block reads to all
  zero-access paths (`.ssh/`, `.aws/`, `.kube/`, `.gnupg/`, `.env`, `*.pem`, `*.key`,
  terraform state, shell history, and credential/secret-named files outside package dirs).
- Update the `block-sensitive-paths.py` matcher in `settings.json` from `Bash|Write|Edit`
  to `Bash|Read|Write|Edit`.
- Update the `sensitive-path-blocking` spec to add `Read` to `ToolScope` and introduce a
  `BlockReadFromZeroAccessPath` requirement.
- Update the error-handling exit code for `block-sensitive-paths.py` on parse failure from
  exit 2 to exit 0, per the `hook-interface` spec rule for hooks that handle mixed
  sensitive/read-only tools.
- Strengthen the `ExplanationContract` in `hook-interface` to require that every `ask`
  response explain both the potential danger and why Claude is requesting the operation.
- Update `block-secrets.py` ask-mode messages to conform to the strengthened explanation
  contract.
- Update the `secret-access-blocking` spec `AskOnSecretFileAccess` requirement and its
  scenarios to reflect the strengthened explanation requirement and the new layering
  (zero-access path reads are now hard-blocked by `block-sensitive-paths.py` before
  `block-secrets.py` runs).

**Out:**

- No changes to `block-secrets.py` tool scope or detection modes (it already covers all
  tools; credential-dir reads remain `ask` for paths outside the zero-access list).
- No changes to `block-dangerous-bash.sh`, `block-destructive-ops.py`, or
  `bash-command-validator.sh`.
- No changes to gitleaks integration or secret pattern sets.
- No new zero-access paths beyond those already defined in `block-sensitive-paths.py`.

## Approach

Extend `block-sensitive-paths.py` with a `Read` branch: extract `tool_input.file_path`, run it through the existing `should_block()` predicate (already handles all zero-access patterns), and exit 2 if matched.
No new path logic is needed.

Update the `settings.json` PreToolUse matcher to include `Read`.

Adjust the parse-failure exit from 2 → 0 (mixed-tool-type hook rule in `hook-interface`).

Strengthen ask-mode explanation text across all hooks: every `ask` message must state
(1) what the operation would do and (2) why it is dangerous or suspicious.

## Open Questions

None.
