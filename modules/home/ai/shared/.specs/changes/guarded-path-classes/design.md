# Design: guarded-path-classes

## Context

The deployed hooks are symlinks into `~/.nixconfig`, and `shared/hooks.nix` enumerates `hooks/` at activation.
A file added there has no deployed symlink until the next `just nix switch home`, and an import of a module that is not yet deployed fails every judged tool call: `internal_error` asks under Claude and refuses under Codex.
This change adds one such file, `hooks/shell_words.py`.
The work happens in the `ai-guardrails` worktree, the main checkout stays what the live agents run, and the activation runs once after merge.

Two hooks judge a Bash command by the paths it names.
`block-hook-tampering.py` decides whether a command mutates a guarded location and whether it is a recognized read or run.
`block-sensitive-paths.py` decides whether a command reads material an agent must never see.
Both take their declarations from `guarded-paths.toml` through `guarded_paths.py`, and each carries its own lexer.

`guarded_paths.GuardedLocations` already answers two questions.
`contains(path)` resolves a path and asks whether any of its spellings lies inside a declared location.
`mentioned_in(text)` searches a string for the written form of a declaration.
The `location-only` table exists because the second question over-refuses for an agent home, whose written form is `.claude`.

The deployed layout shapes the link rules.
`~/.claude/hooks/` is a real directory whose entries are per-file links into the repository; `~/.claude/hooks/instructions` is one link to a store path that links on to the repository; `~/.claude/skills/x` links to `~/.agents/skills/x`.

The Claude permission list resolves `deny` over `ask` over `allow` with no carve-out.
The sandbox has allow-within-deny; the permission list does not.
The floor conformance tests require every guarded declaration to be covered on both, and a base declaration for an agent home with a write-through directory beneath it cannot be.

`security-posture-alignment` is pending in the same tree.
Its committed delta carries the read-through declarations, the lexer requirement, and the grep-overtrigger task.
Both changes cannot sync in either order as written, so the items this change owns move out of that delta.

The specs are split by what they govern.
`shell-lexing`, `path-matching`, `guarded-path-declarations`, the two hook specs, and `session-tool-checks` are mechanism: what a class does and how declarations combine, with no location named.
`guarded-surface` is posture: which locations are declared in which class, and why.
The decisions below are split the same way.

## Decisions

### Mechanism decisions

### Decision: TheManifestIsPolicyAndTheHookIsItsInterpreter

**Chosen:** the manifest declares one guarded list and three delta classes, block, exec-through, and write-through, plus the declared exceptions.
A directory entry covers its subtree.
The hook implements the classes and the precedence rule and carries no table that steers its own matching.
The class is named `guarded` after the manifest and the module that read it.

**Rationale:** an operator reads the manifest to learn the policy, and a table that encodes how the hook matches does not tell them.
With the classes and the precedence fixed, the same policy can be written as a base entry with carve-outs or as an enumeration, and `EquivalentPoliciesReachEqualVerdicts` holds the hook to reaching the same verdicts either way.

**Alternatives considered:**

- Keep `deployed` and `sources` as two keys under the guarded table: the split records where a path came from, which the hook never uses and the reader does not need.
- Entries as tables with per-entry flags: every entry pays a line of ceremony for the three that would carry a flag, and the flag would encode matching, not policy.

### Decision: OnePrecedenceRuleOverEveryHop

**Chosen:** a supplied path is expanded into its chain of hops: as written, with `~` and traversal applied, each link along the way, and the final target.
Every declaration is expanded the same way at load.
At each hop of the path, the declarations covering that hop are collected from the classes relevant to the operation, and a verdict is reached there: a block declaration decides; otherwise the closest declaration decides, closeness being the number of path segments between the declared location and the hop in the spelling where they matched; a tie between classes goes to the delta class.
The path's verdict is the strictest across its hops, block over guarded over carve-out over undeclared.
Manifest order is never consulted.

A write consults write-through and guarded.
A run consults exec-through and guarded.
A read consults block alone.
Build the guarded set from explicit guarded entries and the locations of every exec-through and write-through entry.
Each carve-out therefore supplies a guarded default for operations it does not permit.
This default applies even when no separate guarded declaration covers the location.
A removal, rename, or replacement is a write.

**Rationale:** one rule gives the right answer for restriction and permission without a case for either.
A restriction holds when any hop reaches it, so a write through `instructions/x.md` linked to a hook asks.
A permission holds only when every hop allows it, and an undeclared hop allows everything, so a run through `~/.claude/skills/x` linked into `~/.agents/skills/x` proceeds whether or not the target is declared.
Closeness measured in the matching spelling is the same number whichever prefix the spelling carries, so a link spelling and its resolved spelling compare without an artifact.

**Alternatives considered:**

- Longest declared location by segment count after resolution: a link spelling and its resolved spelling have different depths, so the comparison measured the prefix rather than the declaration.
- Class precedence only: `GuardedBeneathWriteThrough` cannot be expressed.
- Last-match wins, as the OS sandbox profile does: the policy would change when a line moved.
- Any-hop for carve-outs as for restrictions: a link created under a write-through name would write through to whatever it points at.

### Decision: DeclarationsFollowTheirOwnChainAndNotTheirEntries

**Chosen:** a declaration covers every hop of its own chain, so `~/.claude/hooks/instructions/` also names the store path and the repository directory it resolves to.
A declaration does not follow links held inside the directory it names.
`spellings()` is extended to return every hop rather than the two ends, and `GuardedLocations` holds each declaration's hops.

**Rationale:** following a declared location's chain is one `readlink` walk at load.
Following the entries inside every declared directory at every tool call is a directory walk per call, and the case it would serve, a link inside a carve-out whose target lies under a stricter declaration, is one the validator reports at session start instead.
Computing a carve-out for a target from a link inside a carve-out directory is refused on security grounds: creating a link inside a write-through directory is a permitted write, so inheritance would let an agent widen its own permissions in one unprompted step.

**Alternatives considered:**

- Resolve every entry of a declared directory at load: a walk per hook invocation, and every skills root holds dozens of entries.
- Inherit the carve-out through links: the escalation above.

### Decision: ReadIsTheDefault

**Chosen:** a read of any guarded location proceeds, by the Read tool and by a recognized shell read.
The `read-through` table, `READ_THROUGH`, `only_carved_out`, and `_carved_out` are deleted.
A read is refused only where a block declaration covers the path.

**Rationale:** every guarded location holds material an agent may inspect, and `git log -p` prints the repository sources without reaching any gate.
The read-through table had grown to cover the three agent homes, the four skills roots, and the whole module tree, which is every guarded location an agent reads in ordinary work.
A table that lists everything is a default written the long way.

**Alternatives considered:**

- Keep read-through explicit: each new guarded location prompts on its first read until someone lists it, which is the habituation the north star names.

### Decision: TheTextCheckIsForUnresolvableWordsOnly

**Chosen:** `mentioned_in` is applied to words `shell-lexing` reports as unresolvable, and to nothing else.
A resolved word is judged by `contains` alone.
The `location-only` table and the `location_only` parameter of `GuardedLocations` are deleted, and every declaration contributes a fragment.

**Rationale:** the text check was applied to the whole command because the old lexer could not resolve the words.
The lexer now resolves quoting, tilde, and pathname expansion, so a resolved word is a path and gets the path question.
The text check remains for a substitution or a brace expansion, where a guarded path written inside must still be found.
Scoped this way, the fragment `.claude` matches only inside an unresolvable word, which is the one place matching it is right, and the agent homes need no exemption.

**Alternatives considered:**

- Derive the exemption from the fragment's shape, skipping any single-component fragment: a rule the reader has to know, to reach the same result as scoping the check.
- Keep the whole-command text check and accept the noise on `.claude`: a `git add .claude/settings.local.json` in this repository would ask on every agent and refuse on Codex.

### Decision: OneGlobForm

**Chosen:** `*` matches exactly one path segment in whichever component it appears, including the last.
No `**`.
`fragment()` no longer cuts a declaration at its last `*`; it yields the trailing literal components with the glob component included as a pattern, so a declaration ending `instructions/*.md` matches `instructions/x.md` and not `.md`.

**Rationale:** a directory entry covers its subtree, which is what `**` mostly expresses, and a broad name pattern is the name heuristic's job.
The one glob wrinkle that mattered was `fragment()` producing `.md`, which matched every markdown file in any text.

**Alternatives considered:**

- Add `**` with `fnmatch`: a few lines, and an invitation to write `**/.env` in a manifest that has a hook for that.

### Decision: WriteThroughIsAClassWithNoNamedLocation

**Chosen:** `[write-through]` replaces `[instruction-layers]` as a class.
Its mechanism is stated once, in `WriteThroughLocationsAreWritable`: a write proceeds where every hop of the target is under a write-through declaration or under none, and a glob in the last component narrows a declaration to one file shape directly within a directory.
Which locations are declared write-through is posture.

**Rationale:** the `[location, layer]` pair shape said "markdown directly within" in a form only the hook could read, and the requirement that carried it named a location, which put posture in a mechanism spec.

### Decision: FloorConformanceCoversTheBlockClass

**Chosen:** `test_guardrail_declarations.py` loses its guarded-source and deployed-declaration checks over the Claude permission list, the Codex workspace, and the VS Code approval globs.
`test_secret_floor_declarations.py` keeps its three floor checks over the block class plus the sops representatives, which move from the manifest's `[secret-floor]` table into `tests/conformance.py`.
The `vscode-edit-approvals` and `codex-guarded-workspace` exceptions leave with the checks they served.

**Rationale:** a credential read cannot be undone, so the floor there is worth a test that fails when a surface misses.
An unprompted edit to a guarded location is recoverable, and the surfaces cannot express the ask-with-carve-out the manifest now states.
The representatives are evidence for a test, not policy, so they belong with the test.

**Alternatives considered:**

- Skip only the entries the floors cannot express: reintroduces a derived exclusion for the homes and keeps three settings files in every manifest edit.
- Delete conformance entirely: gives up the test that caught the `secrets.d` glob miss.

Superseded in part by `security-posture-alignment` `TheHooksAreAPackageIndependentOfAnyAgentConfiguration`: the block-class floor stays a requirement, but the three checks move from `test_secret_floor_declarations.py` into an assessment an agent runs against each configuration, because a test reading agent configuration pins the hooks package to one vendor's keys.
The representatives stay in `tests/conformance.py` as the assessment's inputs.
The `ConfigurationSurfacesCoverTheDeclarations` delta in this change is edited to say so.

Reevaluated on 2026-10-06, and kept: the user decided that floor conformance does not broaden back over the guarded class.
A read-only measurement of each agent's own layer against every guarded declaration and enforcement-floor location found the coverage partial on every agent.
Pi's sandbox wraps only its shell tool, so its file tools write every guarded location unless a hook refuses.
Codex's workspace leaves unlisted settings variants, the Pi hook-runner sources, and unlisted users writable, and runs readable hook scripts without approval.
Claude's source asks name the main checkout literally, so a worktree is not covered, and it allows edits to the plugin cache.
Copilot prompts for every terminal command and for direct edits in this checkout.
Closing the gap, even only over the enforcement locations, would need edits to every agent's settings, four of them files only the user can commit, and a new all-tool boundary for Pi.
The shared hooks therefore stay the only complete gate over the guarded class, including the files that load and implement them.

### Decision: OneLexerModuleWithWordKinds

**Chosen:** `hooks/shell_words.py` holds what `_split_words`, `_resolve`, `_candidate_words`, and `_segments` do in the tamper hook today, and returns segments of `Word` values, each with its resolved text and a kind.
The kinds are command, option, assignment, redirection target, pattern, path candidate, plain word, and unresolvable.
A path candidate is a word that carries a separator or a leading `~`, or names an entry that exists relative to the working directory the payload supplies.
A redirection target keeps its own kind, and every path rule in both hooks applies to path candidates and redirection targets alike.
The existence test runs only for a bare word, so it is one `stat` per bare word per command.

`block-hook-tampering.py` builds its read and run classification over the kinds.
`block-sensitive-paths.py` replaces `_lex_tokens`, `_decode_ansi_c`, `_candidate_paths`, and `expand_glob_candidates` with the module, applies its strong rules to every word, and applies `NAME_PATTERN_RE` to path candidates alone.

**Rationale:** the overtrigger task already defined "path candidate" as a lexical property plus an existence check.
Two hooks deciding that separately is the duplication the shared lexer exists to remove.
Tagging in the lexer means the tamper hook's option handling and the sensitive-path hook's candidate selection read one answer.

**Alternatives considered:**

- Words only, kinds in each hook: the overtrigger fix stays a `block-sensitive-paths` edit, and the two hooks keep separate ideas of what an option is.
- A path-candidate helper without full kinds: the tamper hook keeps its own option and pattern handling beside the helper.

### Decision: TheLexerIsWrittenRatherThanTakenFromAPackage

**Chosen:** `shell_words.py` is written here, and both hooks keep `dependencies = []`.

**Rationale:** the lexer has two halves, and a package supplies one of them.
Splitting a command into segments and words is a parsing problem several packages solve.
Resolving a word to what bash would hand a program is not: no Python package performs quote removal, ANSI-C decoding, tilde expansion, and pathname expansion without running a shell.
A package leaves `_ansi_c` and `_resolve` here and adds a translation into `Word` beside them.

The differential property against a real bash holds the lexer to its contract, whatever sits underneath it.
`lex(command, cwd)` is the boundary, so a package can be adopted later against that same property without either hook changing.

**Alternatives considered**, with times measured on a warm cache:

- `tree-sitter-bash`: typed nodes for the pipeline split, `command_name`, `variable_assignment`, `file_redirect` attached and spaced, `raw_string`, `ansi_c_string`, `expansion`, and `command_substitution`, which is what `_split_words` and the segment loop produce, about 190 of 352 lines.
  It reports syntax and not values: quotes stay in the node text, ANSI-C is not decoded, a tilde and a pathname pattern come back as written, and a brace expansion has no node of its own, so every resolution and refusal stays here.
  It costs two dependencies in hooks that declare none, 40 ms per process and so 80 ms per judged Bash call against a 120 ms hook, and a package fetch on a cold `uv` cache where the hooks now need none.
  `time cat x` parses `time` as the command name.
- `bashlex`: bash's own grammar transliterated to Python, and no expansion either.
  90 ms to import, GPL-3.0, last release 2024, one maintainer.
- `mvdan.cc/sh/v3/expand`: the one library that expands words without running them, and a command substitution is an error where no handler is set.
  It is Go, so it costs a subprocess per judged call.
- libc `wordexp` with `WRDE_NOCMD`: one call for the whole expansion, and a history of command substitutions escaping through that flag.
- An existing gate, `bash-classify`, `sh-guard`, `kjell`, `yah`, or `shush`: each scores a command for risk from a bundled command database against a path list written into the tool.
  None reads a path manifest, none carries the per-agent ask-or-refuse split, and each is months old with one maintainer.

### Decision: BashIsTheReferenceShell

**Chosen:** the lexer reproduces bash.
`shellprobe` runs each generated command through bash with every program replaced by a recorder, and the differential property holds the lexer to it, stated as containment: every word a program receives is one the lexer handed on for that program.
Claude is pinned with `CLAUDE_CODE_SHELL=/run/current-system/sw/bin/bash` in the `env` block of the settings file every launcher reads.
Codex runs `bash -lc`.
Copilot runs the editor's terminal profile, zsh here, and stays there.
The differential property is run once under zsh as a measurement, and the divergence set is recorded in `AGENTS.md`.

**Rationale:** the override was found in the Claude binary and confirmed in a live session; the `env` route reaches the CLI, the desktop app, and the editor extension from one file.
`/bin/bash` is Apple's 3.2, so the pin names the nix-darwin bash, and nix-darwin's `/etc/bashrc` sources the nix environment, so PATH is intact without a Home Manager bash configuration.
Pinning Copilot means changing the user's own terminal profile, which is not this module's to set.

**Alternatives considered:**

- Parametrize the property over bash and zsh: a second interpreter in the fixture, and every divergence becomes a form the lexer must refuse under both, for one agent that does not honor an ask on the shell tool anyway.

### Decision: TheLexerIsItsOwnCapability

**Chosen:** `shell-lexing` is a new spec, and `AWordTheShellRewritesIsResolvedOrRefused` moves there from `security-posture-alignment`'s `hook-tampering-blocking` delta, with the property suite that proves it.

**Rationale:** the same shape as `path-matching`: one module, two callers, a contract neither owns.

### Decision: DirectoryChangeTrackingIsDeferred

**Chosen:** the lexer does not track `cd` in this change.
A relative path after a `cd` is an unresolvable word, which gates, and the gate's reason instructs the agent to name paths absolutely.
The session instructions and `AGENTS.md` say the same.

The design, for when the deferred task is taken up: a `cd` or `pushd` segment whose operand resolves sets the working directory for the segments that follow it across `;` and `&&`; the directory reverts after `||` and at the close of a subshell; a `cd` with an unresolvable operand, a `cd -`, or a `popd` makes every later relative word unresolvable.

**Rationale:** the rule is cheap once the lexer exists, and the `cd <path> && ...` form is common when an agent works outside its starting directory, so the limit will cost prompts.
Deferring it keeps this change to the class model and the lexer's move; the design is recorded so the follow-up starts from a decision rather than a question.

**Alternatives considered:**

- Track it now: one more expansion rule in a change that already replaces the manifest model, with its own property to write.

**Taken up** in `security-posture-alignment` on 2026-10-04, after its read property found `cd ~/.config && cat mcp-secrets.env` allowed.
The rule differs from the design above in three places, each found by a review against bash.
A `cd` may fail, so each directory is carried with the status that left it there, and `&&`, `||`, and `!` select from those states; reverting after `||` missed `cd A || cd B && cat a`, which bash runs in `A` when the first `cd` succeeds.
A `cd` moves the shell only in command position, which reaches past `!`, `{`, `if`, `then`, `do`, `builtin`, and `command`.
A larger set of forms leaves the directory unresolved: `eval`, `source`, `trap`, `shopt`, a function definition, a `cd` inside a loop, and an assignment to `HOME` or `CDPATH`.
A relative path joined onto a directory keeps its `..`, because `cd link && cat ../file` reaches the parent of the link's target, which collapsing `link/..` would miss.
A union of every directory any `cd` named was considered and rejected: it gates `cd /tmp && tar -xf archive.tar` by judging the extraction in the starting directory too.
`shell-lexing` `EachSegmentCarriesTheDirectoriesItMayRunIn` states the rule, and the probe that checked it recorded 64 runs against bash with none outside the predicted set.

### Decision: EnforcementCarveOutsAreInert

**Chosen:** the guard derives an enforcement floor independently of manifest declarations from its implementation and launch locations and known harness enforcement locations, including project-local permission settings and repository sources.
At each hop, block decides first; the floor requires approval for writes and runs next, before grant distance or tie rules apply.
Reads are unchanged.
Grants remain effective outside the floor, including for instruction text.
Reports name the floor paths where a grant does not apply: at gate time on the call the grant does not reach, and at session start only for a grant lying at or inside the floor.
The floor's locations are the code-held lists `HOOK_DIRECTORIES` and `PERMISSION_FILES` plus the manifest and the running hook's own directory; a manifest entry never extends the floor, so two manifests assigning the same classes reach the same verdicts however an entry is spelled.

**Rationale:** the north star's degradation rule: a manifest that cannot be honored in full grants nothing a valid one would.
Honoring the carve-out would let an approved manifest edit remove the ask on every later edit.
A session-start warning for a broad grant that merely contains floor paths would fire every session for a manifest the operator wrote knowingly, which is the habituation the north star argues against; the gate-time report explains the one call it stops.
Deriving part of the floor from declared paths ending in `hooks` was tried and reverted: the permissive spelling of a grant escaped the floor, and `EquivalentPoliciesReachEqualVerdicts` failed.

**Alternatives considered:**

- Treat it as a load failure: under `AnUnloadableManifestAsksOnMutatingTools` every mutating call would ask for a declaration that has no effect, which is disproportionate to a defect the tests already keep out of the tree.
- Report every overlap at session start: the noisier option, rejected for the reason above.
- Discover hook directories from the filesystem, for example every `hooks/` directory under the agent module tree: deferred, because a glob written for this repository's layout pins the floor to it, and the generic rule is not yet known.

### Decision: AnUnloadableManifestAsksOnMutatingTools

**Chosen:** where the manifest is absent, unparsable, or missing a required table, the tamper hook routes every call to a tool it covers through `internal_error`, which asks under Claude and refuses where no prompt is honored, and lets a `Read` proceed with the failure reported.
`block-sensitive-paths.py` keeps proceeding on a load failure, because its strong rules and the sandbox enforce the block class without the manifest; only its declared-path alternation is lost, and that is reported.
The session-start check prints an error and exits 2 for this state, and a warning with exit 0 for every other finding.

**Rationale:** an unloadable manifest leaves the tamper hook with no policy, and a mutation judged against no policy is what `ErrorHandlingByDamagePotential` forbids.
`Ask` rather than `Block` follows `AnInternalErrorAsksRatherThanBlocks` in `security-posture-alignment`: most mutating calls reach nothing guarded, and a recurring fault would otherwise refuse every mutation with no route left for the user.
No harness lets a session-start hook stop a session, so the hard failure has to live at the tool call; the session-start error is what tells the operator why the prompts are about to start.
Conflicts and grants restricted by the floor stay warnings because precedence and the floor retain their restrictions at verdict time.

**Alternatives considered:**

- Proceed on every tool, as the baseline did: a guard that checks nothing while reporting that it checks nothing, on the one tool class where that matters.
- `Block` on every covered call: no route for the user until the manifest is repaired from outside the agent, which is the agent the user may be using to repair it.
- Make a grant that overlaps the floor a load failure: every mutating call would ask even though the floor already protects enforcement and the grant remains valid for content.

### Decision: OneValidatorForLoaderSessionAndTests

**Chosen:** `guarded_paths.validate(manifest)` returns floor restrictions and conflicts: a hop under block and a carve-out, and a link held directly inside a carve-out directory whose target lands under a stricter declaration with no carve-out of the same class.
The loader records floor restrictions; conflict directory walks run during validation.
`session-tool-checks.sh` calls it and prints each finding as a warning.
`test_guarded_paths_manifest.py` asserts the real manifest returns none.

**Rationale:** three consumers of one answer.
A PreToolUse hook can warn only under Claude; session start is the moment every agent shows output; the test is what stops a conflict being committed.

### Decision: InlineProgramsAreTextCheckedAndBuildersAreNeverReads

**Chosen:** the tamper hook, which already holds `INTERPRETERS` and `INLINE_CODE_OPTIONS` for the run classifier, recognizes an interpreter followed by an inline-code option and applies `mentioned_in` to the word after it, so `bash -c 'rm ~/.claude/settings.json'` names the guarded path.
A command with any segment whose program executes text it receives, `xargs`, `eval`, an interpreter with inline code, or a shell reading standard input, is never a recognized read or run, so `echo ~/.claude/settings.json | xargs rm` gates although the `xargs` segment names nothing.
The guard identifies programs through `time`, `timeout`, `stdbuf`, and `setsid`, including their option operands and the timeout duration.
A pipe-fed program outside the recognized read utilities is a builder, including interpreters and unknown wrappers.
Recognized reads through these wrappers remain permitted, but wrapper options that can write output do not qualify as reads.
The lexer keeps its eight kinds.

**Rationale:** the lexer's contract is what bash does with the text, and its evidence is a differential property against bash.
Bash does not know that `-c` means "execute this", so a program-text kind would be a claim that property cannot check.
The interpreter table has one consumer, the tamper hook, and `sensitive-path-blocking` `BashReadBestEffort` puts interpreters that open files in code out of that hook's scope on purpose.
Both holes were reproduced against the worktree hook on 2026-09-15: each exited 0 under Codex, while the `main` hook blocked both.

**Alternatives considered:**

- A ninth word kind, program text, assigned by the lexer from the interpreter table: moves program semantics into a module whose evidence is bash's reading, and gives the sensitive-path hook coverage its spec declines.
- Lexing the inline program recursively when the interpreter is a shell: a fuller reading, deferred; the text check finds the same guarded paths, and the command is unrecognized either way.

### Decision: TheReasonNamesWhatStoppedRecognition

**Chosen:** when a command naming guarded locations is neither a recognized read nor a recognized run, the ask reason and the refusal name the syntax that stopped recognition, a newline, a substitution, a brace expansion, a redirection, program text to an interpreter, a command builder, a relative path after a directory change, beside the read utilities and interpreters that would have proceeded, and tell the agent to name paths absolutely.

**Rationale:** an agent whose gate is a refusal has no prompt to answer, and a reason that does not say what to rewrite leaves it with nothing to do but look for another route.

### Decision: PiReadsTheNewSectionsWithNoBehaviorChange

**Chosen:** `pi/security/manifest.ts` reads the guarded, block, exec-through, and write-through tables, and derives what `guarded-paths.ts` consumed from the old tables.
Nothing else in the Pi port changes.

Pi has a temporary exception from the new class outcomes and shared-lexer behavior until `security-posture-alignment` migrates it onto the shared hooks.
The reader must still load the new tables and preserve credential blocking.
Pi can continue to gate reads, script runs, and memory writes that the shared hooks permit.
Its existing matching does not implement the new per-hop precedence or word kinds.
Record each affected shared-table case as a Pi divergence; do not present the Pi suite as evidence of parity or silently omit cases.
Remove the exception when the adapter passes those cases through the shared implementation.

**Rationale:** the reader falls back to empty lists on a missing section, so an unchanged reader would run Pi with no guarded files and no error.

The Pi suite is unhooked from `outputs.checks` and from `just apps test` until the migration lands, and stays runnable by name.
The migration WIP in the same tree imports `shell-quote`, which neither the check derivation nor the test layout supplies, so the suite cannot run here whatever the reader does, and a red check on every commit of the branch would hide a real failure behind an expected one.
The reader update is therefore committed unverified, and the port is judged when the migration replaces it.

**Alternatives considered:**

- Keep the check and accept a red `nix flake check` on every commit until the migration: an expected failure trains the operator to ignore the check.
- Supply `shell-quote` to the check derivation: builds tooling for a port that is being deleted.

### Decision: TheOldChangeIsRenamedAndPostureAlignmentIsRevised

**Chosen:** `changes/skill-script-exec-through` is renamed to `changes/guarded-path-classes` with `git mv`, and its requirements are restated here.
`security-posture-alignment` gives up the read-through declarations and tasks, the `ReadThroughCoversTheAgentModuleTree` decision, the lexer requirement and its done tasks, the backslash-continuation task, the hermetic-fixture task, and the grep-overtrigger task.
It keeps the ancestor gating, the patch judgment, the ripgrep criterion, and the classifier-level property tasks.

**Rationale:** nothing from the old change synced, so its delta is free to restate.
The two changes touch the same requirements only where the items move, and after the move they touch none in common.

### Posture decisions

### Decision: AgentHomesAreBaseEntriesAndTheRepositoryIsEnumerated

**Chosen:** `~/.claude/`, `~/.codex/`, `~/.copilot/`, and `~/.pi/agent/` are guarded entries, and their enumerated children leave the guarded list except where a child carries a delta class.
The repository side keeps its enumerated sources.

**Rationale:** an agent home holds little that is not enforcement, so one entry with two carve-outs beneath it is the shortest true statement.
The module tree is mostly ordinary Nix and tests, and a base entry there would ask on every edit to them.
This is a choice the manifest records, and `EquivalentPoliciesReachEqualVerdicts` is what makes it a choice rather than a constraint.

**Alternatives considered:**

- Enumerate the homes: a directory kind a harness adds later is unguarded until listed.
- A base entry for `<repo>/modules/home/ai/`: prompts on tests and Nix, which the north star names as habituation.

### Decision: TheBlockClassGainsTheClaudeStateFile

**Chosen:** `~/.claude.json` moves from the guarded list to `[block]`.

**Rationale:** the file holds account state and OAuth material beside MCP configuration, and the sandbox already denies reading it.
No in-session flow maintains it, so a prompt there trains approval of a request that should never come, which is the credential rule.

### Decision: InstructionTextIsGuarded

**Chosen:** no instructions directory is declared write-through.
`InstructionTextIsWritable` is removed and no write-through entry replaces it.

**Rationale:** instruction markdown is prompt text an agent loads, and prompt text shapes what the agent does with every other guardrail.
An edit to it is an edit to the agent's behavior, and that is the user's decision, as for a hook.
The cost is one prompt per instruction edit, which is authoring the operator does rarely and deliberately.

**Alternatives considered:**

- Keep the carve-out as `instructions/*.md` write-through entries: ordinary authoring without a prompt, at the price of an unprompted route to change what the agent is told.

### Decision: AgentMemoryIsWriteThrough

**Chosen:** `~/.claude/projects/` is declared write-through.

**Rationale:** memory is written in ordinary sessions and changes no enforcement.
It gated only because the home was a `location-only` catch-all with no carve-out, and every session paid a prompt for it.

### Decision: SkillsRootsAreExecThroughIncludingTheSharedRoot

**Chosen:** `~/.claude/skills/`, `~/.codex/skills/`, `~/.pi/agent/skills/`, and `~/.agents/skills/` are exec-through.

**Rationale:** the per-agent roots hold links into `~/.agents/skills/`, and a declaration does not follow the links inside the directory it names.
Under the precedence rule an undeclared target would still allow the run, so the shared root is declared for the day it acquires a stricter declaration of its own, and so the validator has nothing to report.

## Architecture

```text
guarded-paths.toml
  [guarded] [block] [exec-through] [write-through] [[exceptions]]
        │
        ▼
guarded_paths.py ── load ── validate ──► floor restrictions, conflicts
        │                                       │
        │  each declaration as its chain of hops├──► session-tool-checks.sh (warn)
        │  verdict(path, operation)             └──► test_guarded_paths_manifest.py
        │  contains / mentioned_in / encloses
        │
        ├──────────────────────────────┐
        ▼                              ▼
block-hook-tampering.py        block-sensitive-paths.py
  verdict per path               strong rules over every word
  read / run recognition         name heuristic over path candidates
        ▲                              ▲
        └──────────┬───────────────────┘
                   │  segments of Word(text, kind)
            shell_words.py
                   ▲
                   │  differential (containment), metamorphic, totality
     test_shell_words_properties.py + shellprobe.py (bash)
```

Judging one Bash command in the tamper hook:

```text
segments = shell_words.lex(command, cwd)
paths    = resolved words that are path candidates or redirection targets
         + paths held inside unresolvable words (text check)
verdict  = strictest over paths of verdict(path, operation)
block            → Block
nothing guarded  → exit 0
recognized read  → exit 0
recognized run   → exit 0            (every run target under exec-through, exists, is a program)
write-through    → exit 0            (every written path under write-through at every hop)
otherwise        → Ask, degrading to Block, reason names what stopped recognition
```

Judging one path:

```text
for hop in chain(path):                         # written, expanded, each link, target
    covering = declarations whose chain covers hop, in the operation's classes
    if any block in covering:      hop_verdict = block
    elif covering:                 hop_verdict = class of the closest declaration
    else:                          hop_verdict = undeclared
verdict = strictest(hop_verdicts)               # block > guarded > carve-out > undeclared
```

## Risks

- **A hook imports a module with no deployed symlink.**
  Every judged call fails until activation.
  Mitigation: merge and `just nix switch home` in one sitting, and the task list carries the step.
- **Narrowing the name heuristic is a loosening.**
  A bare word that names no entry now proceeds.
  Mitigation: the strong rules still judge every word, the existence check refuses the same word the moment a file exists, and `sensitive-path-cases.json` pins the three cases the change introduces.
- **Base entries widen the text check inside unresolvable words.**
  `$X/.claude/y` now gates where it did not.
  Mitigation: that is the intended reading; an unresolvable word naming an agent home is exactly the case the text check exists for.
- **Removing the instruction carve-out adds prompts.**
  Every instruction edit asks, on every agent, and refuses on Codex.
  Mitigation: accepted as posture; the operator authors instructions rarely, and the ask names the file.
- **The settings pin and the settings edits are the user's to commit.**
  The sandbox denies the agent that file.
  Mitigation: the tasks name the edit and the command, and the session-start warning makes an absent pin visible in the next session.
- **Copilot runs zsh.**
  A form zsh runs more permissively than bash lexes would proceed unjudged there.
  Mitigation: the one-off zsh measurement records the divergence set; a permissive divergence becomes a follow-up, and Copilot honors no ask on the shell tool, so the gate there is already a refusal.
- **A bare-word existence check on every command.**
  Mitigation: one `stat` per bare word, against the payload's working directory; a command holds few bare words.
- **Chains of hops multiply the containment tests.**
  Mitigation: a chain is short, three to four hops for every deployed path here, and each declaration's chain is computed once at load.
- **The Pi verdict tables drift from the shared hooks.**
  Mitigation: run both tables against both implementations and report the temporary Pi divergences explicitly.
  The migration onto shared hooks must close them before removing the exception.

## Implementation note: bounded resolution caching and lazy construction

A policy memoizes `spellings()` across every `GuardedLocations` it builds, for declarations only, and enumerates files with `os.scandir()`.
Verdicts resolve supplied paths again, so retargeting a symlink changes the next verdict; `TestLinkRetargeting` exercises this with Hypothesis stateful tests.
No policy cache is persisted across invocations.
A declaration's parent-directory metadata does not detect retargeting an ancestor symlink, so the proposed cache key would miss a policy change.

The enforcement floor is a `cached_property`, built on the first query that consults it rather than at construction, and `_project_floor` caches one floor per working directory.
A verdict for a read returns before reaching either, so a read of an absolute path builds neither.
The exception is a path that stays relative because the tool call supplied no working directory: that verdict falls through to the text check over `guarded`, which is itself built from the floor's declarations.
`block-hook-tampering.py` reaches the same property for an unlexable command and for an unresolvable word, whichever operation the call names.

Two consequences follow from deferring the walk.
A failure scanning the enforcement directories surfaces on the first call that needs the floor rather than at import; it reaches `internal_error` either way, so a mutating call still asks or refuses and a read still warns and proceeds.
`PathPolicy.validate()` computes its grant restrictions rather than reading what earlier queries recorded, because construction no longer takes them.

Hard-link identity remains an unimplemented optimization, and the stated hard-link limit remains.

## Verification Overrides

- **User direction, 2026-09-15:** stop Pi tests and incorporation because Pi will be replaced.
  Existing Pi edits remain unverified.
  Do not use them as parity evidence.
  This direction supersedes the reader and test obligations in the temporary exception below.

- **Finding:** Pi's reader-only update cannot satisfy the new class outcomes, link precedence, or shared-lexer behavior required of every implementation.
  **Stage:** apply **Reason:** avoid reimplementing behavior in the TypeScript port that `security-posture-alignment` deletes.
  **Constraints:** the exception applies only to Pi's new behavior in this change.
  Load the new manifest sections, preserve credential blocking, run the Pi suite, and report affected table cases without silent exclusions.
  It does not waive failures on the shared Python hooks.
  **Follow-up task:** migrate Pi onto the shared hooks, verify the deferred outcomes, and remove the temporary exception.
  **Approved by:** user **Recorded:** 2026-09-15 **Closed:** 2026-09-26, by `security-posture-alignment`: Pi runs the shared hooks through its hook runner, which reaches the direct outcome on both verdict tables and on cases for each class outcome, symlink precedence, and lexer form; the `pi_blocked` record is removed.

- **Finding:** the Codex and Copilot suites fail `test_bash_touching_repo_hook_blocks`, because their `_AI_BLOCK_CHECKS` block contract requires `do not attempt` in every exit 2 and the retry instruction form omits it.
  **Stage:** verify **Reason:** the defect is in `security-posture-alignment`'s per-agent test helpers, not in any code this change's structural payoff touches; the shared suite that covers that payoff is green at 1,494 passed.
  **Constraints:** the override covers this verify run only.
  Contract, Coverage, and Coherence conclusions in it are advisory.
  It does not waive a failure on the shared hooks and does not clear either change for sync.
  **Follow-up task:** `changes/security-posture-alignment/tasks.md`, "Split the refusal instruction in two" — update the Codex and Copilot block contract to accept the retry form.
  **Approved by:** user **Recorded:** 2026-09-20 **Closed:** 2026-09-20, follow-up done; all four suites pass.
  The entry stays because it records how that verify run reached its conclusions, which a later reader cannot recover from a green suite.
