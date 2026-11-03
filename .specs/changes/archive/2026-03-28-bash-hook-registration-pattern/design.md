# Design: bash-hook-registration-pattern

## Context

The three bash hooks (`bash-command-validator.sh`, `block-dangerous-bash.sh`, `session-tool-checks.sh`) all follow a common pattern: declare data, then evaluate it.
The current implementations encode data in parallel or per-category arrays where the coupling between elements is implicit (index-based or proximity-based).
The registration function pattern makes coupling explicit at the call site.

## Decisions

### Decision: Triplet flat array for `block-dangerous-bash.sh`

**Choice**: Single flat `rules` array with triplets `(exemption, pattern, message)`, evaluated by one loop.

**Rationale**: `block-dangerous-bash.sh` already encodes exemption metadata in the `exemption_type:pattern` prefix format used by `reverse_shell_entries`.
Promoting this to a first-class positional argument in a registration function makes the exemption type explicit and consistent across all rule families, not just reverse shells.
A single loop replaces eight separate category loops, reducing structural duplication.

**Alternative considered**: Keep per-category arrays, add `rule()` within each.
Rejected because it doesn't eliminate the per-category loop repetition and still requires a developer to know which category array to add a new rule to.

### Decision: Message variables for shared category messages

**Choice**: Extract long block messages shared across a category into named variables (e.g. `_MSG_REVERSE_SHELL`, `_MSG_PIPE_TO_SHELL`) rather than repeating inline strings.

**Rationale**: Inline repetition of multi-line strings across multiple `rule` calls would make the rule declarations noisy and the messages harder to update consistently.
Named variables keep the rule declarations concise while making it obvious that multiple rules share the same message.

**Alternative considered**: Define message per rule (inline repetition).
Acceptable for categories with one rule; rejected for multi-rule categories.

### Decision: Two-array approach for `session-tool-checks.sh`

**Choice**: `require_tool` appends to `required_tools`; `recommend_tool` appends to `recommended_tools`.
Two evaluation loops, each with distinct exit behavior.

**Rationale**: Required and recommended tools have different evaluation semantics (exit 2 vs. warn + exit 0).
Keeping them in separate arrays means each loop's exit logic is uniform and simple.
A unified array would require a third field (severity) and a conditional inside the loop.

**Alternative considered**: Single array with severity field `(name, hint, required|recommended)`.
Rejected — adds complexity to the loop for no gain given the small number of tools checked.

### Decision: No behavioral changes in this refactor

**Choice**: Patterns, messages, exemptions, and exit codes are preserved exactly.

**Rationale**: The registration pattern is a structural change only.
Mixing behavioral changes with structural refactoring makes the diff harder to review and the spec harder to verify.
Any new rules (e.g., additional blocking patterns) should be separate changes.

## Architecture

```text
bash-command-validator.sh
  rule()               ← registration function
  rule 'pat' 'msg'     ← N rule declarations (co-located pairs)
  ──────────────────
  for idx in rules:    ← single evaluation loop (unchanged)
    matches_pattern → exit 2 + message

block-dangerous-bash.sh
  rule()               ← registration function (triplet)
  _MSG_* variables     ← shared message strings per category
  rule 'ex' 'pat' msg  ← N rule declarations (co-located triplets)
  ──────────────────
  for i in 0..N step3: ← single evaluation loop (replaces 8 loops)
    exemption / pattern / message unpacked
    matches_pattern + exemption check → block() or continue

session-tool-checks.sh
  require_tool()       ← registration function
  recommend_tool()     ← registration function
  require_tool n hint  ← required tool declarations
  recommend_tool n h   ← recommended tool declarations
  ──────────────────
  for required_tools:  ← exits 2 if missing
  for recommended_tools: ← warns if missing, exits 0
```

## Risks

**Risk**: Triplet loop indexing in `block-dangerous-bash.sh` is error-prone if the array length is not a multiple of 3.

**Mitigation**: The `rule()` function always appends exactly 3 elements.
As long as all rules are declared via `rule()` and the raw `rules` array is never directly mutated, invariant is maintained.
A guard assertion (`(( ${#rules[@]} % 3 == 0 ))`) can be added before the loop if desired, but is not required by this change.
