# Tasks: git-baseline-drift-detection

## Hook Script

- [x] Create `configs/home-manager/codex/hooks/git-baseline.sh` with `init`, `check`, `update` stages dispatched by `$1` (bash, `set -uo pipefail`, fail-open)
- [x] Sanitize session ID with `tr -c 'a-zA-Z0-9-' '-'` before use in baseline filename
- [x] Restrict baseline advance to `update()` only — `check()` warns but does not advance
- [x] Convert all Python hooks in `hooks.json` from `python3` to `uv run --script`

## Hook Registration

- [x] Add `UserPromptSubmit` entry in `hooks.json` invoking `git-baseline.sh init`
- [x] Add `PreToolUse` group (matcher `^(Bash|Write|Edit|apply_patch)$`) invoking `git-baseline.sh check`
- [x] Add `PostToolUse` group (matcher `^Bash$`) invoking `git-baseline.sh update`

## Sanitization Tests (no git subprocess required — exercise `tr` sanitization via script invocations with crafted session IDs)

- [x] Test sanitization: alphanumeric session ID produces baseline filename with ID unchanged (covers `SessionIdSafety/AlphanumericId`)
- [x] Test sanitization: session ID with `/`, `.`, `@` produces baseline filename with those chars replaced by dashes (covers `SessionIdSafety/SpecialCharId`)
- [x] Test sanitization: two distinct session IDs produce two distinct baseline filenames under the same GIT_DIR (covers `BaselineScoping/ConcurrentSessions` filename invariant)
- [x] Test sanitization: two distinct GIT_DIR values produce baseline paths under their respective directories (covers `BaselineScoping/ConcurrentWorktrees` path invariant)

## Integration Tests (require a real git repo fixture — `mktemp -d` + `git init`)

- [x] Test `init` stage: baseline file is written with current HEAD SHA in a git repo (covers `BaselineCapture/GitRepository`)
- [x] Test `init` stage: no file written and exit 0 in a non-git directory (covers `BaselineCapture/NonGitDirectory`, `FailSilent/NonGitDirectory`)
- [x] Test `check` stage: exit 0, no stdout when HEAD matches baseline (covers `DriftWarning/NoDrift`)
- [x] Test `check` stage: exit 0, JSON `additionalContext` on stdout containing old SHA, new SHA, and branch when HEAD differs from baseline (covers `DriftWarning/DriftDetected`)
- [x] Test `check` stage: baseline file is NOT modified after a warning (write-site absence — covers `DriftWarningPersistence/RepeatedWarning`; call `check` twice, assert baseline still holds old SHA on second call)
- [x] Test `check` then `update` then `check` sequence: first check warns, update advances baseline, second check is silent (covers `DriftWarningPersistence/WarningClearedAfterBash`)
- [x] Test `update` stage: baseline file reflects HEAD after a Bash PostToolUse (covers `BaselineAdvancement/BashAdvancesBaseline`)
- [x] Test `check` stage: exit 0, no output when no baseline file exists (covers `FailSilent/NoBaseline`)
- [x] Test all three stages: exit 0, no output when stdin is not valid JSON (covers `FailSilent/InternalError` via the parse-error path)
