# Tasks: guardrail-ask-gate

## 1. Empirical probes

Both probes need an interactive session in the user's terminal; the tool sandbox can run neither surface.
Record each outcome in this change's `.verify/` directory — the two waivers in `design.md` point at these records.

- [x] Probe the VS Code Copilot surface: register a minimal PreToolUse hook through the adapter that answers `permissionDecision: "ask"`, attempt a matching tool call, and record whether the call is held for a prompt, which JSON shape was honoured (top-level `permissionDecision` or `hookSpecificOutput` wrapper), and whether the user saw one dialog or two.
  Copilot stays on the block encoding until this passes.
- [x] Probe Codex escalation: from a session under `approval_policy = "on-request"`, attempt an `apply_patch` and a shell write to a sandbox read-only path, and record whether each surfaces an escalation prompt or fails bare.
  No task below depends on the answer; it decides whether the recorded delegate option is real.

## 2. Ask encoding in the response helper

- [x] Encode `Ask` as a refusal — exit 2, explanation, AI instruction block — for every (agent, tool) pairing not in the ask-capable set, and assert stdout stays empty on that path so the prompt JSON is never written to a surface that would fail open on it.
  The capability check takes the tool name from the calling hook; the 2026-08-27 probe showed one agent honouring the prompt on file edits and failing open on shell.
- [x] Test: `Ask` under Codex and under an unidentifiable agent produces the refusal encoding, with no stdout.
- [x] Test: `Ask` under Claude Code produces exit 0 and the `hookSpecificOutput` ask JSON, with the reason satisfying the explanation contract.
- [x] Add Copilot to the ask-capable set for file-mutation tools only, emitting the wrapped `hookSpecificOutput` shape the probe recorded; keep the shell tool on the refusal encoding — the probe observed the surface failing open past an ask there.
- [x] Test: `Ask` under Copilot for a Write or Edit tool produces exit 0 and the wrapped JSON; `Ask` under Copilot for Bash produces the refusal encoding with no stdout.
- [x] Test: the Copilot adapter passes an ask response through intact — exit code preserved, JSON still parseable after the agent-name rewrite.

## 3. Class partition in the guarded declarations

- [x] Split the credential entries out of the flat guarded declaration into their own declaration, so the protected class is structural.
  `~/.codex/auth.json` is the only current member.
- [x] Keep the conformance test green: the union of both declarations must still equal the set the settings files and Codex TOMLs name.
- [x] Test: a credential path and an enforcement path report their classes distinctly; every other declared path reports the gated class.

## 4. The gate in the tamper hook

- [x] Restore the hook's entry point.
- [x] Decide `Ask` for mutations of deployed enforcement, repository sources, and per-user configuration; decide `Block` for agent credentials, on every agent.
- [x] Give a command naming protected paths in more than one class the most restrictive outcome among them.
- [x] Write the ask explanation to the `GateResponse` contract: name the file, state that it is enforcement, state what approving the mutation would permit, and do not present it as routine.
- [x] Test: an Edit of deployed enforcement asks under Claude (exit 0, ask JSON) and refuses under Codex (exit 2, explanation).
- [x] Test: a Bash command naming a repository source asks; the operand-attached spelling reaches the same outcome as the spaced form.
- [x] Test: an Edit of another user's agent configuration asks.
- [x] Test: a mutation of `~/.codex/auth.json` blocks under every agent, ask-capable or not.
- [x] Test: a Bash command naming both a repository source and a credential blocks.
- [x] Test: a case-variant spelling of a protected path reaches the gate on a case-insensitive filesystem.
- [x] Test: an unresolvable path that denotes a protected location as written reaches the gate.
- [x] Test: the instruction-markdown carve-out still allows direct markdown and gates the nested, non-markdown, and link-to-enforcement cases.
- [x] Test: the ask reason names the specific file and states the enforcement consequence.

## 5. Per-agent tamper suites

- [x] Update the Claude suite: enforcement-class writes now expect the ask encoding; credential writes still expect exit 2.
- [x] Keep the Codex suite asserting exit 2 for every protected mutation — the degraded gate is byte-identical to the old block from Codex's side.
- [x] Update the Copilot suite to the probed per-tool encodings: wrapped ask for file-mutation tools, refusal for shell.
- [x] Update the shared `hook_response` suite for the new ask-capable set.

## 6. Pi port

- [x] Gate the tamper branch on `ctx.ui.confirm` for the three enforcement classes, blocking when `ctx.hasUI` is false; keep credentials an unconditional block.
- [x] Match the confirm text to the `GateResponse` contract: the file, that it is enforcement, what approval permits.
- [x] Test: enforcement write with UI prompts and honours the answer; without UI it blocks; credential write blocks with and without UI.
- [x] Keep the pi guarded-declaration conformance test green against the split declarations.

## 7. Companion configuration

- [x] Add `chat.tools.edits.autoApprove` to the repo-managed VS Code settings (`users/alex.graber/home-manager/vscode/settings.json`): `false` globs for the guarded set — agent hook directories, agent settings files, the repo guardrail sources, and the VS Code prompts files — so Copilot edits to them get VS Code's diff-and-approve prompt even when the tamper hook fails open.
  This is Copilot's analogue of Claude's `permissions.ask` fallback layer.
- [x] Mirror the same `autoApprove` block into this machine's live `~/Library/Application Support/Code/User/settings.json`.
  The file is hand-managed; the user pasted the block themselves after the in-session edit was declined at the permission layer on 2026-08-27.
  Confirmed present, including the `modules/home/apps/vscode/settings.json` self-entry added by this change's Section 14, on 2026-08-28.
- [x] Extend the guardrail-declaration conformance test to cover the `autoApprove` globs, so this surface tracks the guarded set the way the Claude settings and Codex TOMLs already do.
- [x] In both platform TOMLs, change the `auto_review` clause covering security-hook modification from flat denial to `USER_APPROVAL_REQUIRED` routing: without explicit user authorization in the conversation, deny and instruct the agent to ask; with it, approve only the authorized edit.
- [x] Reconcile the environment-profile clause "a denial from any layer is final and must not be routed around" with the routing above.
  The 2026-08-27 probe showed this clause, not the hook-modification clause, auto-denies a user-authorized guardrail escalation; carve the user-approved escalation path out of it, or the routing never fires.
- [x] Keep the two TOMLs byte-identical outside the platform block, and run both through the strict-config test.
  The `auto_review` policy wording is platform-adapted by design (Seatbelt versus Landlock/bubblewrap); the same semantic edit was applied to both, and `codex --strict-config` accepts both files.

## 8. Findings from probes

- [x] Stop the Copilot adapter writing bytecode into the guarded hooks directory.
  Reversed by Section 16: the suppression protected nothing, and it is removed along with every other site.

## 9. Verification

- [x] `just apps test all`
- [x] `nix flake check --all-systems --impure`
- [x] `prek run --files` over every changed file.
  Editing the hook and its tests is itself a gated write: expect one approval per edit under Claude, and hand the commit to the user if any staged path is one the sandbox denies.

## 10. The manifest (amended 2026-08-28)

- [x] Create `modules/home/ai/shared/hooks/guarded-paths.toml` with the current declarations, structured per `design.md`: `[gated]` (deployed + sources), `[credentials]`, `[instruction-layers]`, `[location-only]`, `[secret-floor]`, and `[[exceptions]]` with the `**/Code/User/workspaceStorage/**` vscode-edit-approvals entry.
- [x] Declare the manifest in its own `[gated]` sources, and add `<repo>/modules/home/apps/vscode/settings.json` to the gated sources.
  The manifest itself rides on the existing `<repo>/modules/home/ai/shared/hooks/` instruction-layer declaration rather than a second literal entry — adding one created two distinct "sources" for one file and broke the exact-match coverage tests over the config surfaces, which the design's "without new entries" consequence already anticipated.
- [x] Test: the manifest parses with `tomllib`, every section is present, and every entry uses the `~/`, `<repo>/`, or glob notation the hooks accept.

## 11. Python hooks read the manifest

- [x] Replace the declaration tuples in `block-hook-tampering.py` with a loader that builds `GUARDED`, `CREDENTIALS`, `INSTRUCTION_LAYERS`, and `LOCATION_ONLY` from the manifest.
- [x] Respond `Warn` — call proceeds, reason reported — when the manifest is missing or unparsable.
- [x] Test: a path added to a manifest class in a temporary copy is guarded by the hook with no code edit (point the loader at the copy).
- [x] Test: a mutation of the manifest itself reaches the gate.
- [x] Test: with the manifest missing, a tool call proceeds and the failure is reported where the agent can report it; same for an unparsable manifest.
- [x] Build `block-sensitive-paths.py`'s agent-credential matcher from `[credentials]`; shape heuristics unchanged.
- [x] Test: each manifest credential path is zero-access through `block-sensitive-paths.py`, and the hook degrades the same way as the tamper hook when the manifest cannot be loaded.
- [x] Keep every existing suite green: the tamper and sensitive-path verdicts must not change from the re-sourcing alone.

## 12. Pi port reads the manifest

- [x] Parse `guarded-paths.toml` with `smol-toml` in the security extension and build its guarded structures from it; retire the mirrored `GUARDED_FILES`, `CREDENTIAL_FILES`, `INSTRUCTION_LAYERS`, and `LOCATION_ONLY` literals.
- [x] Degrade a manifest load failure to a UI notification with the tool call proceeding, matching the Python hooks' posture.
- [x] Test: the extension's verdicts against `guarded-path-cases.json` and `sensitive-path-cases.json` are unchanged.
- [x] Test: the extension under a temporary manifest copy guards a path added to a class, with no code edit.
- [x] Retire the literal-scraping comparisons in `test_pi_guarded_declarations.py`; keep the instruction-layer and location-only behavioural coverage that remains meaningful.

## 13. Conformance tests use the manifest as oracle

- [x] Re-point `test_guardrail_declarations.py` at the manifest's gated sources (instead of importing the hook), keeping the floor semantics and the VS Code oracle covering both the module file and the per-user profile copies.
- [x] Re-point `test_secret_floor_declarations.py` at `[credentials]` and `[secret-floor]`.
- [x] Honour `[[exceptions]]`: a surface entry matching a declared exception passes conformance.
- [x] Test: an undeclared loosening fails conformance — exercised against a fixture settings file with a `true` glob the manifest does not except.
- [x] Test: the declared workspaceStorage exception passes while `**/Code/User/globalStorage/**` is still required to be `false`.

## 14. Configuration surfaces cover the manifest

- [x] Add the manifest's repository path to the Claude settings guarded entries (all users, both platforms where split) and to the Codex TOML repo-sources blocks, so the sandbox and permission layers cover it without reading it.
  The manifest rides on the existing `shared/hooks/**` declarations already covering it (see the note under Section 10); no surface needed a literal new entry for the manifest itself.
- [x] Add `modules/home/apps/vscode/settings.json` to the same surfaces, as the deployed settings' repository source.
- [x] Keep the conformance suites green over the updated surfaces.

## 15. Verification (after the manifest amendment)

- [x] `just apps test all` — shared 297 passed/1 skipped, claude 529 passed/2 xfailed, codex 47 passed, copilot 29 passed, pi 147 passed.
- [x] `nix flake check --all-systems --impure` — all checks passed (`mkPiSecurityValidatorCheck` needed `modules/home/ai/shared/hooks/guarded-paths.toml` added to its sandboxed layout; fixed in `flake.nix`).
- [x] `prek run --files` over every changed file, excluding the four Claude settings files the agent sandbox denies writing to.
  Confirmed: `end-of-file-fixer` failed with `Operation not permitted` on `settings.darwin.json`, and the file was left untouched.
  Hand those four files' commit to the user: `users/mithras/home-manager/claude/settings.darwin.json`, `users/mithras/home-manager/claude/settings.linux.json`, `users/alex.graber/home-manager/claude/settings.json`, `users/nrl/home-manager/claude/settings.json`.

## 16. NoSideEffects states its property (amended 2026-08-28)

- [x] Establish whether bytecode suppression protects the guarded surface at all.
  It does not: the interpreter loads an existing cache entry whether or not the running process may write one, so a planted entry executes either way (measured both with and without the setting).
  Write protection at the permission, sandbox, and tamper layers is what prevents the plant.
- [x] Restate `NoSideEffects` as a prohibition on modifying the state a hook is judging, binding a hook at invocation, and exclude interpreter-managed derived data explicitly.
- [x] Remove `sys.dont_write_bytecode` from the four shared hooks, the Copilot adapter, and both test conftest files.
  Roughly 3ms per hook invocation against a ~30ms baseline, across five PreToolUse hooks per tool call.
- [x] Reverse the Section 8 finding, which added the suppression to the Copilot adapter on the same false premise.

## 17. Verification (after the contract amendment)

- [x] `just apps test all` — shared 298 passed/1 skipped, claude 530 passed/2 xfailed, codex 47 passed, copilot 29 passed, pi 148 passed.
- [x] `nix flake check --all-systems --impure` — all checks passed.
- [x] `prek run --files` over every changed file — 19 hooks passed, none failed.
  Ruff dropped the `sys` import left unused in the Copilot test conftest; every other file still imports and uses it.

## 18. Containment is judged in every spelling (found 2026-08-28)

- [x] Judge containment across every spelling in `contains`, not the resolved one alone.
  A declaratively managed file is inside a guarded directory as written and resolves outside it, so judging the resolved form alone silently allowed a read of `~/.ssh/config` — exit 0, no prompt.
- [x] Apply the same to `guardsPath` and `isCredentialPath` in the Pi port.
  `isInstructionMarkdown` stays resolved-only: a link is a write to whatever it points at, which is the carve-out rule.
- [x] Store each home location expanded as well as resolved in the Pi port, matching `_home_prefixes` in `guarded_paths.py`.
  Verified as a real disagreement first: the same path under a symlinked home returned `True` in Python and `false` in TypeScript.
- [x] Regression tests on both sides, each confirmed to fail against the pre-fix code.

## 19. Verification (after the containment fix)

- [x] `just apps test all` — shared 299 passed/1 skipped, claude 530 passed/2 xfailed, codex 47 passed, copilot 29 passed, pi 149 passed.
- [x] `nix flake check --all-systems --impure` — all checks passed.
- [x] `prek run --files` over every changed file — no failures.

## 20. Verify findings (2026-08-29)

- [x] Waive `NoSideEffects`.
  The interpreter clause is definitional and the behavioural clause is a negative universal over everything a hook does, so neither is reachable by assertion.
  The waiver in `design.md` carries the planted-bytecode measurement itself, because `.verify/` is excluded by the root `.gitignore` and would not survive a clone.
- [x] Test the Pi port's manifest-load-failure path, the one enforcement implementation whose degradation had no coverage.
  Both arms: a missing manifest, and a parse failure driven by substituting the TOML parser — the suite's own stub is lenient by design and never throws.
- [x] Give the Pi tamper refusals the second half of the `GateResponse` contract.
  They named the path and stated enforcement, but never closed off another route or sent the decision back to the user, and the extension emits no instruction block of its own.
  The extension API has no channel for it, so it rides on the reason text.
- [x] Test the fail-open paths.
  The blind `except Exception` arms were unreachable from the suite, so a defect that made every check raise would have left the hooks exiting 0 with nothing turning red.
  Each arm is confirmed load-bearing: with the handler deleted, all three cases exit 1 instead.
  The suite now pins the asymmetry too — the two hooks covering read-only tools fail open, and the Bash-only hook fails closed.
- [ ] Decide whether `block-secrets.py` should pass its tool name to `supports_ask`.
  It does not, so a secret-access ask on a Copilot file edit refuses where the tamper hook would prompt; the adapter already normalises `create_file`/`editFiles` to `Write`/`Edit`, so the tool name is available.
  Not a regression and safe in direction, but the two hooks now answer differently for the same (agent, tool) pairing.
  Changing it loosens a hook this change's proposal put out of scope, so it is the user's call.
