# Tasks: skill-script-exec-through

Implementation preceded these artifacts.
The change was written on 2026-09-09, the specs were reconstructed from it the same day, and the boxes below record what exists rather than what remains.

## Manifest

- [x] Add the `[exec-through]` table to `hooks/guarded-paths.toml`, listing `~/.claude/skills/`, `~/.codex/skills/`, `~/.agents/skills/`.
- [x] Read `exec-through` in `build_guarded` and return it as a `GuardedLocations`, alongside the existing `read-through`.
- [x] Fail the same way on a broken manifest: an unreadable `exec-through` leaves the class empty and reports, rather than guessing.
- [x] Extend `tests/test_guarded_paths_manifest.py` `_all_path_entries` and the required-section list to cover `exec-through` — evidence for `SingleDeclarationSource`.
- [x] Add `TestReadAndExecAreSeparateClasses` over a substituted manifest that declares a location read-through only, asserting it is read-through and is not exec-through — evidence for `ReadAndRunAreSeparateClasses`.

## Classifier

- [x] Extract the lexer and pipeline split out of `is_read_only_command` into `_segments`, returning `None` where the command cannot be judged.
- [x] Add `_exec_through_script`: the token resolves into an exec-through location, the file exists, and it carries the execute bit or a script suffix — evidence for `ARunTargetsAnExistingScript`.
- [x] Add `_script_exec_segment`: the script is the command itself or the file argument to a named interpreter, exactly one token is that script, and an inline-code option disqualifies the segment.
- [x] Add `runs_exec_through_script`: one segment is a run and every other segment is a recognized read.
- [x] Rename `only_read_through` to `only_carved_out` and admit exec-through paths, so a run reaches the classifier instead of the gate.
- [x] Delete `reads_through`, which had no caller.

## Gate

- [x] Accept a recognized run in the Bash branch alongside a recognized read.
- [x] Reword the ask reason and the refusal to name both accepted forms, and list the interpreters beside the read utilities — evidence for `CarvedOutLocationsAreClassified`'s reason clause.

## Tests

- [x] Add a `home` parameter to `run_gate`, `write`, and `bash` in `tests/test_tamper_gate.py`, substituting the home the hook expands `~` against.
- [x] Add the `skills_home` fixture: an executable `run.sh`, a non-executable `helper.cjs`, an `audit.py`, and a `SKILL.md`.
- [x] Add `RUNS` covering the direct form, the direct form with arguments, `uv run`, `python3`, `node` on a file with no execute bit, and a run piped into a read — evidence for `RecognizedRunUnderExecThrough` and for both arms of the program-shape test.
- [x] Add `NOT_RUNS` covering inline program text, a target that is not a program, a second command, a substituted binary, a write dressed as an argument, an absent path, and two scripts in one segment — evidence for `EffectHiddenFromTheCommandText`, `TargetIsNotAProgram`, and `TargetDoesNotExist`.
- [x] Assert the run cases proceed under all four agents, and the rejected cases ask under Claude and refuse where no prompt is honored — evidence for `UnrecognizedCommandNamesTheAcceptedForms`.
- [x] Assert a run carrying a protected path outside the carve-out keeps the enforcement wording — evidence for `CarveOutMixedWithProtectedPath`.
- [x] Assert a `Write` to a script under the substituted home still gates.
- [x] Run `pytest -q modules/home/ai/shared/tests` and `nix build .#checks.aarch64-darwin.shared-hook-tests`.
- [x] Run `node --test ai/pi/security/index.test.mjs` against the new manifest, confirming the added table is inert to the Pi port.

## Follow-up

- [ ] Decide whether the Pi security extension should implement the read-through and exec-through carve-outs, or whether gating skill use on Pi is intended.
