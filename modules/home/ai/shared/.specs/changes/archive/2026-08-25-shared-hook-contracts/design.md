# Design: shared-hook-contracts

## Context

Each hook is a standalone PEP 723 script with no declared dependencies, executed by absolute path.
They share a directory, `modules/home/ai/shared/hooks`, and are deployed to each agent as individual symlinks.

Five of them resolve paths: the three tamper hooks, `block-sensitive-paths.py`, and `block-secrets.py`.
Tamper blocking is implemented three times because the second and third were forked from the first.

Guarded repository sources are also named outside Python — in three Claude settings files and three Codex TOMLs.
Those surfaces cannot import shared code.

## Decisions

### Decision: SiblingModuleOverDuplication

**Chosen:** one helper module beside the hooks, imported by each

**Rationale:** A script run by path puts its own directory first on the import path, so a sibling import needs no path manipulation.
This was verified for the deployed shape as well: invoked through a symlink, the import path entry is the resolved directory, so the helper is found whether the hook is reached from the repository or from an agent's hook directory.
`readDir` in `shared/hooks.nix` deploys every entry, so the helper travels with the hooks automatically.

**Alternatives considered:**

- Keep duplicating the logic: the status quo, and the direct cause of the drift this change exists to remove
- Generate the hooks from a template at build time: single-source, but the generated files become store copies and stop being editable in place, which is the property `mkRepoSymlink` exists to provide
- Publish the helper as a package and declare it as a script dependency: adds a release step and a network fetch to every hook invocation

**Consequence:** importing would write bytecode into the guarded hooks directory, which the `hook-interface` contract forbids and which would make the guard the one writing into what it guards.
Each hook therefore turns bytecode generation off before importing a sibling.

### Decision: FilesystemProbeOverPlatformAssumption

**Chosen:** determine case significance from the filesystem holding the path

**Rationale:** Case sensitivity is a property of the volume, not the operating system.
A case-sensitive APFS volume exists on darwin, and a case-insensitive volume can be mounted on Linux.
Assuming from the platform name would under-protect the first and over-protect the second, and over-protection here means refusing writes to files that genuinely differ.

**Alternatives considered:**

- Assume darwin is case-insensitive: wrong on a case-sensitive APFS volume
- Always compare case-insensitively: refuses legitimate writes on case-sensitive filesystems, where the two spellings are different files

### Decision: UnresolvableIsGuarded

**Chosen:** a path that cannot be resolved is judged from the path as written, and is not permitted by default

**Rationale:** The hook fails open on an unparsable payload because it covers read-only tools and cannot infer damage potential.
Resolution failure is a different case: the tool name and the path string are both known, so damage potential is known.
Treating an unreadable path as permission converts a malformed input into an unguarded write.

**Alternatives considered:**

- Let the error reach the fail-open handler: the current behaviour in two of the three tamper hooks, and the reason a correction in the third never propagated
- Block unconditionally on resolution failure: refuses paths that fail to resolve for unrelated reasons, with no security gain over judging the written form

### Decision: OneTamperHookOverThree

**Chosen:** consolidate the three tamper implementations into one carrying the union of protected sets

**Rationale:** The Codex and Copilot implementations are already the same program with different data — identical function inventory, identical order.
Claude's settings registers two of the three back to back, so the union is already what runs there, at the cost of an extra process per tool call.
A single implementation cannot drift from itself.

**Alternatives considered:**

- Keep three and share only the path predicate: removes the resolution drift but leaves three copies of the policy, three protected-path declarations, and three places for a correction to miss
- Keep three and add a conformance test asserting they agree: detects drift rather than preventing it, and still pays three processes per tool call

**Consequence:** every agent enforces every agent's protected set.
This removes no protection and adds some, but it changes which operations are refused.

### Decision: VSCodeSettingsAreNotEnforcement

**Chosen:** the tamper hook does not refuse writes to VS Code's own user settings

**Rationale:** VS Code's `settings.json` is a preference file.
The files beside it that do constrain an agent — the instruction markdown under `prompts/` — stay protected.
Refusing the preference file outright means refusing every ordinary editor change an agent is asked to make.
Under Claude and Codex the permission layer prompts for it instead, which is the right weight for a file that is usually a preference and occasionally a lever.

**Alternatives considered:**

- Keep refusing it: safe, and wrong often enough that it trains the user to relieve the hook, which is worse than the exposure
- Refuse only the keys that affect an agent: the hook matches paths, not file contents, and a JSON-aware rule is a second parser to keep correct

**Consequence:** Copilot has no permission surface of its own, so nothing prompts there.
A write to VS Code's settings from a Copilot session is neither refused nor confirmed.
This is accepted: the sandbox still applies, and Copilot's own instruction files remain protected.

### Decision: TestSuitesAsTheContract

**Chosen:** all three existing tamper suites run against the consolidated hook, unmodified

**Rationale:** No baseline spec existed for tamper blocking before this change, so the per-agent expectations live only in the tests.
Requiring all three green is what demonstrates the consolidation dropped nothing.
A suite that needs editing to pass marks a behaviour difference that was not deliberate, and is a finding to resolve rather than a test to adjust.

Two edits were made and are the exceptions this rule exists to surface.
The Codex suite names the hook under test, and the hook was renamed.
The Copilot suite asserted that VS Code's own settings are refused, which `VSCodeSettingsAreNotEnforcement` deliberately stops; the assertion was inverted rather than deleted, so the new behaviour is pinned as explicitly as the old one was.

**Alternatives considered:**

- Write one merged suite: loses the per-agent expectations before they have been shown to be preserved

### Decision: SingleDeclarationPerCaller

**Chosen:** each caller declares its guarded locations once, and both the fragment form and the resolved form derive from that declaration

**Rationale:** The same location written twice, in two shapes, is what produced the path errors during the module move: one shape was updated and the other was not.
Deriving both removes the possibility.

**Alternatives considered:**

- Two declarations kept in step by a test: catches the drift after it is written rather than making it unrepresentable

### Decision: ConformanceTestForNonPythonSurfaces

**Chosen:** a test asserting the hooks, the Claude settings deny rules, and the Codex permission entries cover the same set

**Rationale:** Those six configuration files cannot import shared code, so single-sourcing is unavailable without generating them.
A test is the next best guarantee and needs no change to how the files are authored.

**Alternatives considered:**

- Generate the settings and TOMLs from Nix: gives single-source, but makes them store copies and ends live editing, and the JSON is deliberately hand-authored
- Leave them unchecked: the current state, and the reason a rename silently dropped protection until a test failure surfaced it

### Decision: ResponseEncodingIsAgentSpecific

**Chosen:** hooks reach a canonical decision; a shared helper encodes it for the invoking agent, identified from the invocation path

**Rationale:** The three agents assign incompatible meanings to the same exit code.
A non-zero, non-blocking code means "proceed, and show this to the user" under Claude Code, is undocumented under Codex, and denies the tool call under Copilot.
A hook emitting one code for all three is confined to the codes they already agree on, which is why a warn outcome cannot be expressed today.
The invocation path already names the agent, because hooks are deployed into per-agent directories, so identification costs nothing and adds no registration entry.

**Alternatives considered:**

- Emit one exit code everywhere: keeps the current limitation, and any attempt to warn would deny every tool call under Copilot
- Give each agent an input-normalizing adapter process, as Copilot has: pays a process per hook per tool call to solve a problem Claude and Codex do not have, since both already send the canonical payload.
  Copilot's adapter carries a benchmark note that this overhead is measurable
- Pass the agent name in each hook registration: works, but adds an entry to enforcement configuration for every hook and every agent — more places for a rename to drop protection silently

**Consequence:** `Warn` degrades to `Allow` where an agent cannot express it, never to `Block`.
Degrading upward would refuse every tool call for as long as the condition lasted.

## Verification Waivers

### Waiver: path-matching StatedLimits

**Evidence:** the module docstring of `modules/home/ai/shared/hooks/guarded_paths.py`, which names each limit the requirement lists: a relative path judged against the working directory the hook runs in, a working-directory change within one shell command, hard links, a tree that is not a repository, and any route that presents no path.

**Why manual:** the requirement constrains how the capability is described, not what it computes.
It has no observable behaviour to assert.
A test that grepped the docstring would pin the wording rather than the property, and would pass a docstring that listed the limits and contradicted them a line later.

**Provenance:** added during verification of this change; the requirement and the docstring both predate it.

## Verification Overrides

### Override: TamperSuiteVerifiedOutOfBand

**Finding:** 11 tests in the three tamper suites fail while `main()` is commented out in `block-hook-tampering.py`, which makes the hook allow every tool call.

**Stage:** sync.

**Reason:** the hook is deliberately disarmed for unrelated work in the same working tree.
The user ran the suites with it armed and reports them green; the agent cannot reproduce that while it stays disarmed.

**Constraints:** no test was modified, skipped, or marked expected-to-fail to obtain a pass.
The disarm is a working-tree state, not a change to the hook's behaviour, and is not part of this change's diff.

**Follow-up:** `tasks.md` § Verification carries an unchecked task to re-run the suites with the hook armed before the change is committed.

**Approved by:** the user, in session, 2026-08-26.

**Recorded:** 2026-08-26.

## Risks

Consolidation changes which operations are refused, and refusals are visible.
An agent that could previously edit another agent's guardrails will now be refused.

The case-insensitivity fix refuses spellings accepted today.
Any tooling that reaches a guarded path under a differing case will start failing, and the failure will present as a tamper block.
