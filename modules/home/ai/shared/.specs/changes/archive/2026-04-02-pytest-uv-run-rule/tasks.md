# Tasks: pytest-uv-run-rule

## Implementation

- [x] **T1** Add `rule` declaration to `bash-command-validator.sh` after the pip3 rule:

  ```bash
  rule '(?<!\w)(?<!uv run )py(?:test|\.test)\b' \
    "Use 'uv run pytest' instead of invoking pytest/py.test directly"
  ```

  _Note: pattern updated from proposal — added `(?<!\w)` to prevent matching inside longer tokens (e.g., `mypytest`)._

- [x] **T2** Verify the pattern manually against key cases using Perl:

  - `pytest tests/` → MATCH ✓
  - `py.test tests/` → MATCH ✓
  - `uv run pytest tests/` → NO MATCH ✓
  - `uv run py.test tests/` → NO MATCH ✓
  - `cd myproject && pytest` → MATCH ✓
  - `mypytest` → NO MATCH ✓

## Spec Update

- [x] **T3** Add `RedirectPytestToUv` requirement and scenarios to
  `.specs/specs/bash-command-validator/spec.md` (sync from delta spec)
