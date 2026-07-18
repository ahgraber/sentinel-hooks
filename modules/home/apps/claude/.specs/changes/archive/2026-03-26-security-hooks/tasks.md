# Tasks: security-hooks

## Session tool checks

- [x] Consolidate `check-uv.sh` into a general-purpose session-tool-checks hook that verifies `uv` and `gitleaks`
- [x] Register the session-tool-checks hook under `SessionStart` in `claude-settings.json`

## Block dangerous bash

- [x] Implement the dangerous-bash-blocking hook (reverse shells, pipe-to-shell, obfuscated exec, clipboard reads, fork bombs)
- [x] Implement localhost exemption for reverse shell patterns
- [x] Add missing patterns: mkfifo|nc, telnet reverse shell, cron injection, SSH key manipulation, privilege escalation (sudo/su), macOS interaction (open/osascript/defaults write)
- [x] Register as a PreToolUse hook with matcher `Bash` in `claude-settings.json`
- [x] Verify against the scenario list in the spec (bash reverse shell, netcat, mkfifo|nc, telnet, curl-pipe-sh, base64 exec, pbpaste, fork bomb, cron injection, SSH key injection, sudo, open)

## Block secret access

Note: hook file renamed from `block-exfil.py` to `block-secrets.py`

- [x] Implement universal secret scan: serialize `tool_input` and scan with built-in patterns for all tool calls (ask-mode on match)
- [x] Implement Bash-specific escalation: if universal scan finds a secret AND command contains a network-sending context, escalate to block-mode
- [x] Implement block-mode rules: secret + network transmission, env dump to network, DNS exfil, credential file pipes to network
- [x] Implement ask-mode rules: credential store read without network pipe, file path heuristics for Read/Write/Edit
- [x] Implement localhost exemption for secret + network patterns
- [x] Implement file path heuristics for Read/Write/Edit (`.key`, `.pem`, `id_rsa`, `*token*`, `*password*`, `.npmrc`, `.netrc`, `.git-credentials`) with directory exemption
- [x] Implement `EXEMPT_DIR_RE`: package dirs (.venv, site-packages, node_modules) + tool config dirs (.claude)
- [x] Add missing built-in patterns: Discord tokens, bearer/auth headers, AWS secret key assignments, generic secret assignments, GitHub fine-grained PATs, PGP private keys
- [x] Implement gitleaks integration: gated behind built-in pre-scan (fast path); gitleaks only invoked for Bash+network context (deep path)
- [x] Implement built-in pattern fallback for when gitleaks is not available
- [x] Define overlap boundary with `sensitive-path-blocking`: zero-access paths blocked there take precedence
- [x] Register as a PreToolUse hook with matcher `Bash|Read|Write|Edit` in `claude-settings.json`
- [x] Verify against the scenario list in the spec (API key in curl → block, env dump to network → block, DNS exfil → block, credential file pipe → block, secret in any tool arg → ask, keychain read local → ask, read token file → ask, credentials in venv → allow)

## Block sensitive paths

- [x] Implement the sensitive-path-blocking hook for `Write`, `Edit`, and `Bash` tool calls
- [x] Implement path extraction: `tool_input.path` for Write/Edit, command text scanning for Bash
- [x] Implement zero-access path matching (dot-env, ssh, aws, kube, gnupg, certs, tfstate, credentials/secret name patterns)
- [x] Implement directory exemption for name-based patterns (.venv, site-packages, node_modules, .claude)
- [x] Add shell history files to zero-access list (.bash_history, .zsh_history, .node_repl_history, .python_history)
- [x] Register as a PreToolUse hook with matcher `Bash|Write|Edit` in `claude-settings.json`
- [x] Verify against the scenario list in the spec (write to .env, edit ssh key, redirect to .env, cp to ssh dir, credentials module in venv, write to shell history)

## Block destructive ops

- [x] Choose and document the pattern file format — TOML (`tomllib` is stdlib in Python 3.11+)
- [x] Reorganize TOML from flat `[[rules]]` to `[[category.rules]]` structure (git, filesystem, process, cloud, infra, database, publishing, package, deploy, network)
- [x] Update `block-destructive-ops.py` to parse both flat and nested TOML structures
- [x] Author pattern file with all categories from the spec including description, reason, and mode
- [x] Add missing patterns: cloud (Netlify, Cloudflare, Heroku, Fly.io, DigitalOcean, Supabase), infra (Pulumi, Serverless/sls, SAM, kubectl delete namespace, Docker rm -f/rmi -f/volume prune), database CLIs (redis-cli, mongosh, dropdb, mysqladmin), git (restore ., push --delete, gh repo delete), publishing (npm unpublish), filesystem (history -c), process (killall, pkill, kill -9)
- [x] Implement case-insensitive matching for SQL patterns, case-sensitive for shell patterns
- [x] Implement the `ExplanationContract` output: compose description + reason into the user-facing message
- [x] Handle missing pattern file gracefully (exit 0)
- [x] Register as a PreToolUse hook with matcher `Bash` in `claude-settings.json`
- [x] Verify against the scenario list in the spec (destructive git, terraform destroy, DELETE without WHERE, ask-mode approval flow, new cloud/infra/db patterns)

## Settings and cleanup

- [x] Remove `damage_control_check.py` and `damage_control_patterns.yaml` from `modules/home/apps/claude/hooks/`
- [x] Empty `permissions.deny` (all rules now handled by hooks)
- [x] Reduce `permissions.ask` to `WebSearch` and `WebFetch` only
- [x] Remove any references to retired hooks from `claude-settings.json`
- [x] Reorder hooks for fail-fast: dangerous-bash → sensitive-paths → destructive-ops → secrets → bash-command-validator
- [x] Remove `block-sensitive-reads.sh` from PreToolUse registration (subsumed by sensitive-paths + secrets hooks)
- [x] Remove stale files from `modules/home/apps/claude/hooks/`: `permission-request.py`, `pretooluse-check.py`, `check-uv.sh`, `block-exfil.py`, `block-sensitive-reads.sh`
- [x] Verify `permissions.allow` covers auto-approve patterns from `permission-request.py` (not applicable — file was never registered in this repo's settings; current allow list is correct)
- [x] Document the deny/ask → hook migration mapping for reviewer context (covered in `proposal.md` retirement section)
- [x] Run `home-manager switch` and confirm hooks are symlinked into `~/.claude/hooks/`
- [x] Smoke test: trigger one block and one ask scenario end-to-end to confirm the hooks are wired correctly
