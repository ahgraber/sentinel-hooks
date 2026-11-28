# Design: git-baseline-drift-detection

## Context

This hook targets the Codex agent (OpenAI), not Claude Code.
The Codex hook protocol differs from Claude Code's in two ways relevant here:

- Stdin for PreToolUse includes `session_id` and `turn_id` in addition to `tool_name` and `tool_input`.
- Model-visible context injection uses `hookSpecificOutput.additionalContext` in stdout JSON, not plain text.

The existing `hook-interface` spec in this repo describes the Claude Code contract.
This change does not modify that spec; the git-baseline-drift capability is Codex-only.

The hook is informational — it warns but does not block.
This distinguishes it from the security hooks (block-destructive-ops, block-dangerous-bash) which are fail-closed and enforce hard gates.

## Decisions

### Decision: StorageLocation

**Chosen:** Plain file at `$GIT_DIR/agent-baseline-<sanitized-session-id>`

**Rationale:** `$GIT_DIR` is set by git to the per-worktree git directory when git invokes hooks; for non-hook subprocesses (Codex hook scripts), `git rev-parse --git-dir` returns the same path.
In a git worktree, this resolves to `.git/worktrees/<name>/`, providing automatic worktree isolation without extra logic.
The file is repo-local, never pushed, and invisible to all standard git commands (`git status`, `git log`, `git diff`).
No dependency on `$TMPDIR` (inheritance issues across subprocess boundaries) or git refs (contaminate remote on `git push --all`).

**Alternatives considered:**

- Tmpfile (`$TMPDIR/agent-git-<session_id>`): `$TMPDIR` may resolve differently across hook subprocess invocations in some environments (sudo, login shells, certain CI runners); two hooks that should share state end up with different paths.
- Git ref (`refs/agent/<session_id>`): Clean and atomic, but `git push --all` or `git push --mirror` silently pushes agent refs to remotes; requires push-refspec discipline at every call site to avoid contamination.
- Git config (`git config --local`): Single `.git/config` file with no write-lock semantics; concurrent `git config` invocations from two sessions can corrupt it.

### Decision: BaselineAdvancementLocation

**Chosen:** Advance baseline only in `update()` (PostToolUse Bash), never in `check()` (PreToolUse)

**Rationale:** `check()`'s responsibility is detect-and-report; `update()`'s responsibility is advance-after-confirmed-agent-action.
Keeping these separate means drift warnings persist before every qualifying tool call until the agent runs any Bash command — the proxy for "the agent is now operating in the current tree."
Advancing in `check()` normalized drift silently even when the agent ignored the warning, turning a single warning into "warn once, then forget."

**Alternatives considered:**

- Advance in `check()` after warning (original implementation): warnings fired once per drift event, then the baseline moved forward regardless of agent behavior.
  An agent that ignored the warning would see no further indication that its mental model was stale.
- Advance in `check()` on every call (no warning): eliminates warnings entirely; rejected outright.

### Decision: PostToolUseMatcherScope

**Chosen:** `update()` fires after every Bash PostToolUse, not only git-mutating commands

**Rationale:** The hook's policy is "inform, not enforce."
Any Bash command the agent runs is evidence it is operating in the current environment.
Maintaining a regex of git-mutating commands is brittle (misses `git am`, `git worktree add`, shell aliases) and provides no material improvement: an agent that ignores drift warnings will normalize the baseline on the next innocent `ls` either way.
The overhead is one `git rev-parse HEAD` (~5 ms) per Bash PostToolUse.

**Alternatives considered:**

- Only update after Bash commands matching a git-mutation regex: complex, brittle, same behavioral outcome for ignoring agents.

### Decision: PreToolUseMatcherScope

**Chosen:** `check()` fires before Bash, Write, Edit, apply_patch — not before Read

**Rationale:** Read is the recovery action after detecting drift.
Warning the agent immediately before it re-reads a potentially-changed file is accurate but counterproductive — the read is the fix.
The damage case (overwriting concurrent changes) requires a write operation, not a read.

**Alternatives considered:**

- Include Read in matcher: adds overhead on read-heavy turns; warns right before the corrective action.
- Match all tools: captures MCP tool calls with no material benefit; each additional MCP tool call incurs a git subprocess call.

### Decision: ImplementationLanguage

**Chosen:** Bash (`git-baseline.sh`), not Python

**Rationale:** Hook startup latency for an informational hook matters — the check fires before every qualifying tool call.
Bash cold-starts in ~5–15 ms; a Python interpreter adds ~30–80 ms per invocation.
`jq` is already validated by `session-tool-checks.sh` at session start, so the JSON dependency is guaranteed.
The implementation is I/O and subprocess calls, not data transformation — bash is idiomatic for this.
Session ID sanitization uses `tr -c 'a-zA-Z0-9-' '-'`, which is portable and straightforward.

**Alternatives considered:**

- Python (`uv run --script`): adds 30–80 ms startup overhead per invocation; appropriate for hooks with complex data transformation or library dependencies, not for this use case.

### Decision: SingleScriptArgvDispatch

**Chosen:** One script file (`git-baseline.sh`), stage selected by `argv[1]` (`init` / `check` / `update`)

**Rationale:** All three stages share GIT_DIR resolution, baseline file path construction (including sanitization), and fail-open error handling.
Duplicating this across three files creates divergence risk — a bug fix in the shared path logic applied to one file but not the others.
The hook config passes the stage as an argument, which is idiomatic for multi-stage hooks.

**Alternatives considered:**

- Three separate scripts: simpler per-file, but shared logic diverges silently.

### Decision: FailOpenPolicy

**Chosen:** Exit 0 silently on all internal errors, non-git directories, and missing baseline files

**Rationale:** This hook is informational.
Silent failure degrades to "hook does not exist" — the agent proceeds without drift awareness, which is the same as the pre-hook state.
This is qualitatively different from the security hooks (block-dangerous-bash, block-destructive-ops), which are fail-closed because their failure mode is "allow a dangerous operation."

**Alternatives considered:**

- Fail-closed (exit 2): would block tool calls on any git configuration edge case, network filesystem latency spike, or version incompatibility — unacceptable for an informational hook.

### Decision: SessionIdSanitization

**Chosen:** Replace all characters outside `[a-zA-Z0-9\-]` with `-` using a compiled regex

**Rationale:** Codex session IDs are UUIDs (alphanumeric + dashes) in practice, so sanitization fires only on unexpected input.
Replacing rather than hashing preserves readability during debugging.
`Path()` construction with an unsanitized ID containing `/` would silently traverse directories; the sanitization prevents that.

**Alternatives considered:**

- SHA-256 hash of session ID: opaque, harder to correlate with a running session during debugging.
- No sanitization: safe for UUIDs but fragile against future session ID format changes.

## Architecture

```text
UserPromptSubmit
  └─▶ git-baseline.sh init
        ├─ git rev-parse --git-dir  (resolve $GIT_DIR)
        ├─ git rev-parse HEAD        (current SHA)
        └─ write $GIT_DIR/agent-baseline-<safe_id>

PreToolUse (Bash|Write|Edit|apply_patch)
  └─▶ git-baseline.sh check
        ├─ git rev-parse --git-dir
        ├─ read $GIT_DIR/agent-baseline-<safe_id>   [baseline]
        ├─ git rev-parse HEAD                        [current]
        ├─ if current == baseline → exit 0 (silent)
        └─ if current ≠ baseline  → print JSON additionalContext, exit 0
             (baseline file NOT updated here)

PostToolUse (Bash)
  └─▶ git-baseline.sh update
        ├─ git rev-parse --git-dir
        ├─ git rev-parse HEAD
        └─ overwrite $GIT_DIR/agent-baseline-<safe_id>
```

Drift warning example:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "\u26a0 git HEAD has moved since this turn started: abc12345 \u2192 def67890 (branch: main). Re-read any files you plan to modify to avoid overwriting concurrent changes."
  }
}
```

## Risks

- **Agent ignores repeated warnings:** The hook cannot enforce re-reads.
  Mitigation: the spec explicitly documents "inform, not enforce" as the policy boundary; future work could add file-level mtime tracking.
- **Baseline file accumulates across sessions:** Each session writes one small file to `.git/`.
  Mitigation: files are trivially small; a session-end cleanup hook is out of scope but addable.
- **`$GIT_DIR` not writable:** The hook exits 0 silently (fail-open).
  Mitigation: acceptable given the hook's informational nature.
- **Detached HEAD state:** `git rev-parse --abbrev-ref HEAD` returns `"HEAD"` in detached state; the warning will display `branch: HEAD`, which is accurate if unusual.

## Verification Waivers

- **Requirement:** BaselineScoping (ConcurrentSessions scenario) **Reason:** Exercising two truly concurrent agent sessions against the same worktree requires a live Codex multi-agent setup; no unit test harness can reproduce the actual race condition, only the file-naming invariant.
  **Manual evidence:** Filename uniqueness verified by `modules/home/ai/claude/tests/test_git_baseline.py::TestSessionIdSafety::test_two_session_ids_produce_distinct_filenames` (passing); the ConcurrentSessions scenario exercises the naming contract, not the race condition itself.
  **Recorded:** 2026-06-24
