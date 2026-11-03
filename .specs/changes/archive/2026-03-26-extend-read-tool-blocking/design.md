# Design: extend-read-tool-blocking

## Context

The hook chain in `settings.json` runs in this order for `Read` calls:

1. `block-sensitive-paths.py` (matcher: `Bash|Write|Edit` — currently skips Read)
2. `block-secrets.py` (no matcher — runs for all tools, produces `ask` for credential dirs)

The sandbox `denyRead` is supposed to hard-block reads to `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gcloud` — but it only enforces against the Bash tool.
The Read tool bypasses it and falls through to a user permission prompt.

The fix is to extend `block-sensitive-paths.py` (which already has all zero-access path logic) to also intercept Read calls, and to update the matcher so Claude Code routes Read events to it.

## Decisions

### Decision: ExtendBlockSensitivePaths

**Chosen:** Add `Read` handling to `block-sensitive-paths.py` using the existing `should_block()` predicate — no new path patterns needed.

**Rationale:** All zero-access path patterns are already defined and tested in `block-sensitive-paths.py`.
Reusing `should_block()` for Read calls avoids duplication and keeps the zero-access definition in one place.
The Read input field is `file_path`, which is the same field used by Write and Edit — the branch is a one-liner.

**Alternatives considered:**

- Add Read blocking to `block-secrets.py`: that hook's job is secret detection, not path policy.
  Mixing concerns would make both hooks harder to reason about.
  Rejected.
- New dedicated hook for Read: unnecessary complexity for what is a single new branch in an existing hook.
  Rejected.

### Decision: ParseFailureExitCode

**Chosen:** Change parse-failure exit from 2 → 0 in `block-sensitive-paths.py`.

**Rationale:** The `hook-interface` spec requires exit 0 on parse failure for hooks that handle a mix of sensitive and read-only tools — because on parse failure the hook cannot determine whether it would be blocking a Read (acceptable to allow) or a Bash write (should be blocked).
Exit 2 on unknown tool type would deny all reads on a hook crash, which is unnecessarily disruptive.
The risk of a parse failure silently allowing a malicious Bash command is low: malformed JSON means Claude Code itself had an error, not an attacker.

**Alternatives considered:**

- Keep exit 2: causes read-blocking if the hook crashes, breaking normal Read operations.
  Rejected.

### Decision: AskExplanationStandard

**Chosen:** Require all `ask` messages to state (1) what is being read/done, naming the specific file or command, and (2) what harm could result if approved — particularly that secrets in context can be used in subsequent operations without further confirmation.

**Rationale:** The confused-deputy threat model requires users to understand the downstream risk, not just the immediate action.
A prompt that says "this file may contain credentials — confirm?" does not convey that approving it lets Claude incorporate those credentials into a later network call.
Naming the file and the risk makes the dialog actionable.

**Alternatives considered:**

- Generic messages per category: easier to write but users cannot make an informed decision without knowing which file and what risk.
  Rejected.

## Architecture

```text
Read tool call
      │
      ▼
block-sensitive-paths.py  (matcher: Bash|Read|Write|Edit)
      │
      ├── file_path in zero-access list? ──YES──► exit 2 (block)
      │
      NO
      │
      ▼
block-secrets.py  (no matcher — all tools)
      │
      ├── credential dir prefix?  ──YES──► exit 0 + ask (w/ danger explanation)
      ├── credential file name?   ──YES──► exit 0 + ask (w/ danger explanation)
      ├── secret pattern in args? ──YES──► exit 0 + ask
      │
      NO
      │
      ▼
   exit 0 (allow)
```

Zero-access paths (hard block for Read, Write, Edit, Bash):

- `~/.ssh/` `~/.aws/` `~/.kube/` `~/.gnupg/`
- `.env` `.env.*` `.envrc`
- `*.pem` `*.key` `*.p12` `*.pfx` `*.crt` `*.cer`
- `*.tfstate` `*.tfstate.backup`
- Shell history files
- Files with `credentials` or `secret` in name (outside package dirs)

Credential paths (ask for Read, Write, Edit — not in zero-access list):

- Files matching key/cert/token/password/secret name patterns outside zero-access dirs (e.g., `./project-token.txt`, `.npmrc`, `.netrc`, `.git-credentials`)

Note: `~/.kube/` is already in `ZERO_ACCESS_DIRS`, so `~/.kube/config` is hard-blocked (not asked) once Read is added to the hook scope.

## Risks

- **Parse-failure exit 0 weakens defence for Bash**: If `block-sensitive-paths.py` receives malformed JSON it now exits 0 instead of 2, allowing the Bash call to proceed to the next hook.
  `block-dangerous-bash.sh` and `bash-command-validator.sh` still run; the risk is low.
- **Test coverage gap**: New Read scenarios must be added to the pytest suite; otherwise a regression in `should_block()` could silently allow reads.
  Mitigated by including test tasks explicitly.
