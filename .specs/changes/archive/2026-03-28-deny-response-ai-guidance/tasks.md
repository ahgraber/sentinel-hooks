# Tasks: deny-response-ai-guidance

## Task 1: Update hook-interface baseline spec

- [x] Merge `ExplanationContract` MODIFIED section into `.specs/specs/hook-interface/spec.md`
- [x] Add `BlockAIGuidance` requirement to `.specs/specs/hook-interface/spec.md`
- [x] Update `BlockExplanation` scenario in `.specs/specs/hook-interface/spec.md`

## Task 2: Update dangerous-bash-blocking hook

- [x] Append AI instruction block to every `exit 2` message in `block-dangerous-bash.sh`
- [x] Verify block messages follow the two-section format (human explanation + `---\nAI INSTRUCTIONS:` section)

## Task 3: Update destructive-ops-blocking hook

- [x] Append AI instruction block to every `block`-mode rule match exit in `block-destructive-ops.py`
- [x] Verify block messages follow the two-section format

## Task 4: Update secret-access-blocking hook

- [x] Append AI instruction block to every `exit 2` message in `block-secrets.py`
- [x] Verify block messages follow the two-section format

## Task 5: Update sensitive-path-blocking hook

- [x] Append AI instruction block to every `exit 2` message in `block-sensitive-paths.py`
- [x] Verify block messages follow the two-section format

## Task 6: Verify

- [x] Run pre-commit hooks to confirm no formatting issues
- [x] Review each hook's block output to confirm: human section names the specific operation and risk; AI section begins with `---\nAI INSTRUCTIONS:` and contains all four directive items
