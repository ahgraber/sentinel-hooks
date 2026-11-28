# Tasks: shared-hook-contracts

## 1. Path matching

- [x] Add a shared path-matching helper alongside the hooks it serves, importable by each of them as a sibling.
- [x] Give it one declaration of guarded locations per caller, from which both fragment matching and resolved comparison derive.
- [x] Make letter case significant only where the filesystem makes it significant.
  Determine this from the filesystem, not from the platform name.
- [x] Treat a path that cannot be resolved as guarded when the path as written denotes a guarded location.
- [x] Record the stated limits in the module docstring: working-directory change within one command, hard links, and routes that present no path.

## 2. Tests for the new contract

- [x] Case-variant spelling of a guarded location blocks on a case-insensitive filesystem.
- [x] Case-variant spelling does not block where the filesystem is case-sensitive.
  Skip rather than assert the wrong thing when the running filesystem cannot exercise the branch.
- [x] A path that cannot be resolved but denotes a guarded location blocks.
- [x] Symbolic-link alias and traversal spellings continue to block.

## 3. Consolidate tamper blocking

- [x] Replace the three tamper implementations with one, covering the union of tool surfaces: shell, file write, file edit, and patch application.
- [x] Carry the union of protected sets.
  Every agent enforces every agent's.
- [x] Keep the block explanation contract intact, including the AI instruction block.
- [x] Keep all three existing tamper test suites running against the consolidated hook.
  Green across all three is the evidence that no per-agent expectation was dropped; a suite that needs editing to pass is a finding, not a chore.
- [x] Delete the two forked implementations.
- [x] Update each agent's hook registration to invoke the consolidated hook once.
- [x] Remove the now-redundant second registration from Claude's settings.

## 4. Response encoding

- [x] Identify the invoking agent from the path the hook was invoked by.
  Do not add an entry to any hook registration to carry it.
- [x] Add a response helper taking a canonical decision — allow, warn, block, ask — and encoding it for that agent.
- [x] Encode `warn` as a visible, non-blocking outcome where the agent supports one, and as `allow` where it does not.
  Never as `block`.
- [x] Emit `warn` when a payload cannot be parsed, so a harness change that breaks every hook stops being silent.
- [x] Verify the encoding against each agent's documented behaviour, and record the check date.
  Codex leaves non-blocking exit codes unspecified, so treat its support as absent until observed.
- [x] Test that a decision maps to the expected encoding per agent, including the degrade path.
- [x] Have Copilot's adapter name itself, since it reaches these scripts from outside its own hook directory.

## 5. Adopt in the remaining hooks

- [x] Move `block-sensitive-paths` path-shaped matching onto the shared helper, leaving its glob and name-pattern policy alone.
- [x] Move `block-secrets` directory-prefix matching onto the shared helper.
- [x] Confirm the two hooks' existing suites stay green.

## 6. Guardrail declaration drift

- [x] Add a conformance test asserting that the guarded repository sources named by the hooks, the Claude settings deny rules, and the Codex permission entries all cover the same set.
  This is the check that would have caught the path-rename errors made while moving these modules.
- [x] Bring the configuration files up to the set the test names.
  Copilot's instructions directory was guarded by the hook and named by neither permission layer, and one Claude settings file named no repository source at all.

## 7. Spec corrections found while implementing

- [x] `hook-tampering-blocking` `FailureMode` still says an unparsable payload exits 0.
  It is now a `warn` decision, whose encoding is agent-specific; exit 0 is the degraded form, not the contract.
- [x] The name-based exemption in `sensitive-path-blocking` no longer covers the shared hook directory, so `block-secrets.py` is unreachable by its own maintainers.
- [x] Declare that exemption once for the whole family rather than agent by agent, and in one place rather than in each hook that applies it.

## 8. Second pass on the matching mechanism

A review of the work above found that it had reintroduced, inside the new code, the duplication it exists to remove.

- [x] Judge a `<repo>` declaration by the repository containing the path, found by walking up to a `.git` entry, rather than by matching its text anywhere.
  This covers a worktree and a second clone, and stops a path outside any repository from matching on shape alone.
- [x] Match a wildcard segment by pattern rather than by listing the directory, so a location that does not exist yet is still covered.
- [x] Declare a location too broad to identify as text — an agent's whole home directory — as matched by resolution alone.
  This replaces a second, hand-written matching layer whose comment claimed coverage it did not have.
- [x] Derive the instruction carve-out from the guarded declarations rather than restating them.
- [x] Judge a shell command by each path it names as well as by its text.
- [x] Remove the private reimplementation of the shared spelling helper.
- [x] Adopt the response helper in every Python hook, so the module has consumers rather than one caller.
  This removes three copies of the block explanation and folds two agent-detection mechanisms into one.
- [x] Cut the comment volume back.

## 9. Gaps found in review of the matching mechanism

Both were reachable, and both came from judging a path by its name rather than by where it leads.

- [x] Decide the instruction carve-out on the location a write lands on.
  A link named as instruction markdown was a write to the enforcement file it led to.
- [x] Read the path out of an operand written against shell syntax, so a redirection or an option carrying a path is judged like the spaced form.
- [x] Carry both corrections into pi's port, whose resolver also gave up on a link whose target does not exist yet.
- [x] Cover both with tests that build a link, which a table of path verdicts cannot express.

## 10. Bring pi's port up to the same contract

pi matched paths as written and judged a shell command as one string, so a link, a case variant, and a mixed command each reached enforcement the Python hook refuses.

- [x] Give the port the resolution and case-folding layers, and declare its guarded set in the notation the hook uses so the two lists read side by side.
- [x] Judge a shell command path by path, so the markdown carve-out covers a command only when every guarded path in it qualifies.
- [x] Pin the two declaration lists to each other, so a surface added on one side cannot be forgotten on the other.
  Sampled path verdicts only cover what someone thought to write down.
- [x] Let a protected path be read, which the port refused and the contract permits.
  Read enforcement one agent applies and the others cannot is not enforcement.

## 11. Gaps found in review of the shared modules

- [x] Ask a path where it leads and arbitrary text what it names, rather than asking both of a path.
  A backup directory, an archived copy, and an unrelated file of the same name each read as guarded.
  A relative path keeps both questions, because the working directory it resolves against is not knowable.
- [x] Match a wildcard home declaration by pattern, which the resolved-location layer alone cannot carry.
- [x] Honour the home a caller declares, rather than the process's own, so an injected home means what it says.
- [x] Probe case significance per path rather than once per caller.
  A checkout, a worktree, and a home directory need not share a volume.
- [x] Route the remaining terminal outcomes through the response helper.
  A bare exit 1 is a warning to one agent and a refusal to another.
- [x] Stop bytecode being cached beside the hooks, which the interface contract forbids and which put the guard's own writes inside what it guards.
- [x] Run the shared suite under `nix flake check`, which covered only the dispatcher and pi.

## 12. Findings from verification

- [x] Give both fail-closed refusals in `block-destructive-ops` an explanation.
  Each exited 2 with an empty stderr, so the agent was told to stop and report a reason it had never been given.
  The test that covered them asserted the exit code alone, which is why the suite never saw it.
- [x] Cover the three case-variant scenarios, each judged against the volume the path is on rather than against the platform.
- [x] State what `ZeroAccessPaths` actually adopts.
  It claimed membership is decided by `path-matching`, which would make letter case follow the volume.
  That set asks what a path looks like, not which file it is, so it matches without regard to case everywhere.
- [x] Record that VS Code's own settings are not enforcement, and what that costs under Copilot.

## Verification

- [x] `just apps test all`
- [x] `nix flake check --all-systems --impure`
- [x] `prek run --files` over every changed file, guardrail files included.
  One file is outside the sandbox's write allowance, so it needs a run from the user's shell.
- [ ] Re-run the three tamper suites with `block-hook-tampering.py` armed, before this change is committed.
  See `design.md` § Verification Overrides.
