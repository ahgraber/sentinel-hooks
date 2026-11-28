# Proposal: bash-hook-registration-pattern

## Intent

Bash hooks currently use parallel arrays (`patterns[]` / `messages[]`) where the relationship between a pattern and its message is maintained only by index position.
This makes rules fragile to edit: adding, removing, or reordering a rule requires synchronized changes to two separate array declarations.
A developer looking at one array has no local indication of what the corresponding message says.

The same structural problem appears in `session-tool-checks.sh`, where each tool check is a repeated `if ! command -v ... >/dev/null` block with duplicated structure across required and recommended tools.

A registration function (`rule pattern message`, `require_tool name hint`, `recommend_tool name hint`) co-locates each pair as a single atomic declaration, eliminating the index-coupling problem and making each rule self-contained and easy to read, add, or remove.

Additionally, `bash-command-validator.sh` currently has no spec documenting its behavior.
This change introduces one.

## Scope

### In

- New `bash-command-validator` spec documenting existing + new rules (signed commit enforcement)
- `RuleRegistrationPattern` structural requirement added to `dangerous-bash-blocking` spec
- `ToolRegistrationPattern` structural requirement added to `session-tool-checks` spec
- Refactor `bash-command-validator.sh` to use `rule pattern message`
- Refactor `block-dangerous-bash.sh` to use `rule exemption pattern message` (flat, single loop)
- Refactor `session-tool-checks.sh` to use `require_tool name hint` / `recommend_tool name hint`

### Out

- No behavioral changes to what any hook blocks or allows
- `posttooluse-precommit.sh` — no pattern/message pairs, not applicable
- Python hooks (`block-secrets.py`, `block-sensitive-paths.py`, etc.)

## Approach

### `bash-command-validator.sh`

Define `rule() { patterns+=("$1"); messages+=("$2"); }` before the rule declarations.
Each rule becomes a single `rule 'pattern' 'message'` call.
Existing loop logic is unchanged.

### `block-dangerous-bash.sh`

Define `rule() { rules+=("$1" "$2" "$3"); }` (triplet: exemption, pattern, message).
Define message variables for multi-pattern categories (e.g. `_MSG_REVERSE_SHELL`) to avoid repeating long strings.
All rules register into a single flat `rules` array evaluated by one loop at the bottom, replacing the current per-category loop structure.

### `session-tool-checks.sh`

Define `require_tool name install_hint` and `recommend_tool name install_hint` functions.
Each function appends to a `required_tools` or `recommended_tools` array.
A single evaluation loop at the bottom replaces the current repeated `if ! command -v` blocks.

## Open Questions

None — behavioral scope is fixed; this is a pure structural refactor with a new spec.
