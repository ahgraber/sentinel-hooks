# Design: pytest-uv-run-rule

## Context

The hook uses Perl regex via `matches_pattern` and the `rule` registration pattern.
All existing redirect rules follow the same shape: a pattern that detects a bare invocation plus a human-readable message.
The validator checks every registered rule against the full command string.

## Decisions

### Decision: Negative lookbehind for `uv run`

**Choice:** Use `(?<!uv run )pytest\b` as the core guard against matching `uv run pytest`.

**Rationale:** The `uv run` prefix is always `uv run` (with a trailing space) immediately before `pytest`.
A negative lookbehind of fixed length handles this cleanly in PCRE (Perl regex).
Variable-length lookbehinds are not needed here.

**Alternative considered:** Anchor the pattern to command-start positions only (like the existing `^grep` rule).
Rejected because `pytest` can appear after a `;`, `&&`, or `(`, and we still want to catch those while exempting `uv run pytest` in any position.

**Alternative considered:** Allow-list approach — match all `pytest` occurrences then suppress if `uv run` is present elsewhere.
Rejected: the `matches_pattern` function returns a single boolean per rule; there is no post-filter step.

### Decision: Cover `py.test` alias in the same rule

**Choice:** Use an alternation `py(?:\.test|test)` to match both `pytest` and `py.test`.

**Rationale:** Single `rule` declaration, single message, no index-desync risk.
Both forms are identical in intent.
In regex, `.` must be escaped to match a literal dot: `py\.test`.

### Final pattern

```text
(?<!\w)(?<!uv run )py(?:test|\.test)\b
```

- `(?<!\w)` — negative lookbehind prevents matching inside a longer word (e.g., `mypytest`)
- `(?<!uv run )` — negative lookbehind (7 chars, fixed-length, valid PCRE) exempts `uv run pytest`
- `py(?:test|\.test)` — matches `pytest` and `py.test`
- `\b` — word boundary at the end (defence-in-depth)

Both lookbehinds are evaluated at the same position (before `p`).
They have different lengths so each checks a different slice of the preceding text — there is no conflict.

## Risks

- **Lookbehind length assumption:** If a user writes `uv  run pytest` (double space), the lookbehind will not fire and the rule will block.
  Accepted — double spaces are not a supported invocation form.
- **`python -m pytest`:** Not matched by this rule; already covered by `RedirectPythonToUv`.
