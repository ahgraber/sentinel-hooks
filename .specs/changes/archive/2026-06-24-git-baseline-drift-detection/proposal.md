# Proposal: git-baseline-drift-detection

## Intent

Coding agents working in git repositories execute tool calls across multiple steps within a single turn.
When the repository HEAD moves outside of changes the agent itself made — a concurrent commit, branch switch, or rebase — the agent continues with a stale mental model: reading files that have changed, writing over concurrent edits, or building on a history that has since been rewritten.
No existing hook in this repo detects or surfaces that condition.

This change introduces a three-stage hook that records a HEAD baseline at turn start, warns the agent before file-modifying and Bash operations when HEAD has drifted externally, and advances the baseline after agent-run Bash commands so only external drift generates warnings.

> **Note:** No `NORTH-STAR.md` exists in this specs root.
> The story below is anchored to the operational goal of the hook system: agents should operate on accurate repo state.
> A candidate north star should be ratified before the next change that adds new hook capabilities.

## User Stories

### Story: drift-awareness

As a coding agent, I want to be warned when git HEAD moves outside of changes I made during my turn, so that I can avoid overwriting concurrent changes or making decisions based on a stale view of the codebase.

## Scope

**In scope:**

- A single-script Codex hook (`git-baseline.sh`) with three stages dispatched by argv: `init`, `check`, `update`
- `UserPromptSubmit` (`init`): records HEAD SHA as session baseline at turn start
- `PreToolUse` for `Bash`, `Write`, `Edit`, `apply_patch` (`check`): injects model-visible warning when HEAD ≠ baseline; does not advance the baseline
- `PostToolUse` for `Bash` (`update`): advances baseline to current HEAD after every agent-run Bash command
- Session isolation: baseline scoped by sanitized session ID within the per-worktree `$GIT_DIR`
- Worktree isolation: `$GIT_DIR` resolves to the per-worktree git directory automatically
- Fail-open behavior throughout: the hook exits 0 silently on any error, non-git directory, or missing baseline
- Hook registration in `users/mithras/home-manager/codex/hooks.json`

**Out of scope:**

- Detecting uncommitted worktree or index changes (file-level drift without a commit)
- Blocking tool calls based on drift state (the hook warns; it does not enforce)
- Detecting remote ref changes without a HEAD move (`git fetch` alone)
- Cleanup of stale baseline files in `.git/` across sessions
- Claude Code hook support (implementation targets Codex hook protocol only)

## Approach

Storage: a plain file at `$GIT_DIR/agent-baseline-<sanitized-session-id>`.
`$GIT_DIR` is per-worktree in git worktrees, providing automatic worktree isolation without extra logic.
Session isolation comes from the session ID suffix.
Git refs and tmpfiles were rejected: git refs risk remote contamination on `git push --all`; tmpfiles have `$TMPDIR` inheritance issues across hook subprocess invocations.

Session ID sanitization: non-alphanumeric, non-dash characters are replaced with `-` before use in the filename.

Single script with argv dispatch: `init`, `check`, `update` share the baseline file path construction, which includes the `$GIT_DIR` resolution and sanitization logic — the code most likely to diverge silently if duplicated.

Baseline advancement only in `update()`, never in `check()`: `check()` detects and reports; `update()` advances.
This means drift warnings persist before every qualifying tool call until the agent runs any Bash command — the proxy for "operating in the current tree."
Advancing in `check()` was rejected because it normalizes drift silently even if the agent ignores the warning.

Fail-open everywhere: this hook is informational, not a security gate.
Silent failure degrades to "hook does not exist" rather than blocking work.
