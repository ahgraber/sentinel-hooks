# Proposal: security-hooks

## Intent

Claude Code's hook system allows pre-execution interception of tool calls, but the existing hooks in this repo focus on tool-use suggestions and sensitive-read blocking.
There is no coverage for active exploitation vectors: reverse shells, unauthorized credential access or leaking secrets over the network, writes to secret files, or destructive operations against git history and cloud infrastructure.
This change adds a focused, modular set of PreToolUse hooks that close those gaps without introducing external service dependencies or complex cryptographic machinery.

A secondary goal is to consolidate security policy into the hooks and their configuration, replacing the static `permissions.deny` and `permissions.ask` lists in settings.json with context-aware hook logic.
Hooks can make decisions that glob patterns cannot — distinguishing `--force` from `--force-with-lease`, exempting package directories from name-based blocks, escalating from ask to block based on network context.
The settings.json permission lists should thin to broad tool-level rules (`permissions.allow` for noise reduction, `permissions.defaultMode`), with granular deny/ask logic living in the hooks where it can be tested, configured, and reasoned about independently.

## Scope

**In scope:**

- A hook that blocks dangerous shell execution patterns (reverse shells, pipe-to-shell, obfuscated exec, fork bombs)
- A hook that guards secret access — blocking exfiltration vectors (secrets sent over the network) and prompting for confirmation when secrets are accessed locally (debugging, inspecting credentials)
- A hook that blocks writes to zero-access paths (`.env*`, `~/.ssh/`, `*.pem`, `*.tfstate`, etc.)
- A hook that blocks destructive operations against git history, cloud CLIs, infrastructure tools, and databases, driven by an external pattern file
- A SessionStart hook that verifies required security tools (e.g., `uv`, any declared secret scanner) are available before a session proceeds
- Thinning `permissions.deny` and `permissions.ask` in settings.json — rules now covered by hooks are removed; remaining rules are broad tool-level policies only
- Registration of all hooks in `users/mithras/home-manager/claude-settings.json`
- Retirement of `damage_control_check.py` and `damage_control_patterns.yaml` (superseded by destructive-ops-blocking)
- Retirement of `permission-request.py` (auto-deny covered by PreToolUse hooks; auto-approve patterns migrated to `permissions.allow` in settings.json)
- Retirement of `pretooluse-check.py` (dangerous command blocking and secret scanning covered by new hooks)

**Out of scope:**

- Auto-fixing commands (no silent mutation of inputs)
- Audit logging or tamper-proof audit chains
- File integrity manifests or HMAC signing
- Approval token systems
- Quality gates for agent task completion
- Anything requiring a running daemon or network service
- Changes to `block-sensitive-reads.sh` or `bash-command-validator.sh` (preserved as-is)

## Approach

Four independent hooks, each registered as a separate PreToolUse entry so they can be enabled, disabled, or replaced individually.
Each hook is responsible for one concern and one concern only.

Hooks that detect exfiltration vectors exit 2 (hard block).
Hooks that detect potentially-legitimate secret access exit 0 with `permissionDecision: "ask"` to let the user confirm.
This distinction acknowledges that Claude may be used for debugging authentication flows.
Internal errors in the hook itself exit 0 (don't block on our own bug).
No hook writes to disk, spawns background processes, or makes network calls.
