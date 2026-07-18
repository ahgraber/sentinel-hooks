# Proposal: pytest-uv-run-rule

## Intent

Raw `pytest` invocations bypass `uv`'s virtual environment management, leading to test runs that use the wrong interpreter or missing dependencies.
This change adds a redirect rule to the bash-command-validator hook so that bare `pytest` calls are rejected and the AI is directed to use `uv run pytest` instead — consistent with the existing python/pip redirect rules.

## Scope

**In:**

- New `rule` declaration in `bash-command-validator.sh` matching bare `pytest` invocations
- New requirement and scenarios in the `bash-command-validator` baseline spec

**Out:**

- Changes to any other hook or validator
- Handling of `pytest` when invoked via `uv run pytest` (already correct, must not match)
- Handling of `python -m pytest` (covered by the existing `RedirectPythonToUv` rule)

## Approach

Add a single `rule` call after the existing pip rules:

```bash
rule '(?<!\w)pytest\b' \
  "Use 'uv run pytest' instead of invoking pytest directly"
```

The negative lookbehind `(?<!\w)` prevents matching inside longer tokens.
The pattern must not match `uv run pytest` — confirmed: `uv run pytest` does not start with a word-boundary `pytest` at position 0, and the lookbehind guards against `...pytest` suffixes.
However, the simple pattern _would_ match `uv run pytest` because `pytest` appears as a standalone word.
A more precise pattern anchors to command-position or uses a negative lookbehind for `uv run`:

```bash
rule '(?<![/\w])pytest\b' \
  "Use 'uv run pytest' instead of invoking pytest directly"
```

The design phase will settle the exact regex after testing.

## Open Questions

_Resolved:_

- `py.test` (legacy alias) is also blocked — same rationale, included in scope.
- `uv run pytest` must not match — the pattern must not fire when `uv run` precedes `pytest`.
