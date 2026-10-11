# Proposal: guarded-path-classes

## Intent

The manifest has grown one table per decision that was ever made about a path: `gated` split into `deployed` and `sources`, `credentials`, `instruction-layers`, `location-only`, `read-through`, `exec-through`, `secret-floor`, and `exceptions`.
Three of those exist to work around the hook rather than to state policy.
`location-only` exempts the agent homes from a text matcher whose fragment for `~/.claude/` would be `.claude`.
`read-through` lists locations a recognized read may proceed under, when no recognized read of a guarded location has ever carried a risk the read gate addressed.
`instruction-layers` carries a carve-out shape of its own, `[location, layer]` pairs, that a plain path with a glob already expresses.
Reading the manifest does not tell an operator what the policy is, and the same policy cannot be written a second way, because the tables encode how the hook matches rather than what the operator decided.

The specs mix the two as well.
`hook-tampering-blocking` names the four kinds of location the manifest holds, which is posture, beside the rule that every agent enforces every agent's set, which is implementation.
A posture change then reads as a hook change, and a hook change has to be checked against a list of paths it never consults.

The two hooks that judge a Bash command each carry a lexer.
The tamper hook's lexer now reads a command the way bash does; the sensitive-path hook's still uses `shlex` over the whole command text and applies its name heuristic to every word of a read segment, so a search pattern carrying a sensitive word is refused as a read of a file that does not exist.
Five such refusals were met in one session on 2026-09-13, each stopping ordinary work over this module on the agent whose gate is a refusal.

The floor conformance tests require every guarded declaration to be covered by the Claude permission list, the Codex workspace, and the VS Code approval globs.
Those surfaces cannot express a gate with a carve-out beneath it, so a base-location declaration for an agent home cannot pass them, and every manifest edit reaches three settings files only the user can commit.
The check earns its cost where a miss is unrecoverable, which is the block class, and nowhere else.

The change that first declared `exec-through`, `skill-script-exec-through`, shipped as `2a77f4d` with specs that cannot verify or sync beside `security-posture-alignment`.
This change replaces it: its requirements are restated here against the new class model, and its directory is renamed rather than archived.

## User Stories

### Story: one-list-then-deltas

As the maintainer of these guardrails, I want the manifest to read as one guarded list plus named deltas, so that the policy can be understood by reading it and the same policy can be written more than one way. (North star: "the policy is written once and holds for every agent"; a policy only its implementer can read is written for one reader.)

### Story: posture-and-mechanism-are-separate

As the maintainer of these guardrails, I want the posture, which locations are in which class and why, recorded apart from the mechanism, how a class is enforced, so that a change to one is reviewed against that one alone. (North star: "a rule found in any surface is an expression of this posture"; a rule that cannot be told from the surface enforcing it cannot be checked against the posture.)

### Story: reads-are-frictionless

As the operator of these agents, I want a recognized read or search of any guarded location to proceed without a prompt, so that reviewing a guardrail, a skill, or this module never trains me to approve prompts about my own tooling. (North star: "ordinary, recoverable work proceeds without friction".)

### Story: skill-scripts-run

As the operator of these agents, I want a run of a script already held in a skills directory to proceed without a prompt, so that using an installed skill does not train me to approve prompts about my own tooling. (North star: "response matches risk".)

### Story: one-lexer

As the maintainer of these guardrails, I want every hook that judges a Bash command to read it through one lexer held to the shell that runs it, so that a spelling one hook resolves is never one another hook misreads. (North star: "layers are independent, and a denial from any layer is final"; two readings of one command are two chances to miss the same word.)

### Story: floors-are-checked-where-a-miss-is-unrecoverable

As the maintainer of these guardrails, I want floor conformance to cover the block class and nothing the floors cannot express, so that the check holds where a leak cannot be undone and a manifest edit does not demand a settings edit it cannot be given. (North star: "response matches risk"; a check that fails on what a surface cannot say is a check that gets waived.)

## Scope

**In scope:**

Mechanism, in build order:

- `shell-lexing` (new capability): one lexer for both path-judging hooks.
  It splits a command into segments and words the way bash does, resolves quoting, ANSI-C quoting, tilde, and pathname expansion, refuses substitution and brace expansion, and tags each word with its kind.
  Its contract is held by a differential property against a real bash, metamorphic properties, totality, and parametrized examples.
  The requirement `AWordTheShellRewritesIsResolvedOrRefused` moves here from `security-posture-alignment`, with the tasks that implemented it.
- `path-matching`: a declaration and a supplied path each cover every hop of their link chains.
  The text question is asked of words the lexer cannot resolve, and of nothing else.
  `LocationsWithNoUsableWrittenForm` is removed, because an entry no longer needs to opt out of text matching.
- `guarded-path-declarations`: the class model.
  One `[guarded]` list, `[block]` replacing `[credentials]`, `[exec-through]`, `[write-through]` replacing `[instruction-layers]`, and `[[exceptions]]` for hook surfaces.
  `location-only`, `read-through`, and `secret-floor` are deleted.
  A read of a guarded location proceeds unless the location is blocked.
  One precedence rule: at each hop of a path, block is absolute and the closest declaration decides; across hops the strictest verdict wins.
  `*` matching one path segment is the single glob form.
  A carve-out over the manifest, a hook, or their sources is inert and reported, and a validator shared by the loader, the session-start hook, and the manifest tests reports conflicting declarations.
  Floor conformance covers the block class and the sops representatives, which move to `tests/conformance.py`.
- `hook-tampering-blocking`: the gate restated over the class model, with no named location in it.
  A recognized read of a guarded location proceeds, a recognized run of an existing program under an exec-through location proceeds, a write under a write-through location proceeds, and everything else asks where the harness honors an ask and refuses where it does not.
  The reason for an unrecognized command names the syntax that stopped recognition beside the forms that would have proceeded, and tells the agent to name paths absolutely, so an agent that meets the gate knows what to rewrite.
- `sensitive-path-blocking`: the hook reads a command through `shell-lexing`, and the name heuristic applies to a word only where that word is a path.
- `session-tool-checks`: a warning at session start where a Claude session has no `CLAUDE_CODE_SHELL` pin naming bash, and a warning for every manifest finding the validator reports.

Posture:

- `guarded-surface` (new capability): what the manifest declares and why.
  The agent homes and `~/.pi/agent/` as guarded base entries; the repository sources enumerated; agent credentials and `~/.claude.json` blocked; the skills roots exec-through; the memory an agent keeps under its home write-through; instruction text guarded like any other enforcement.
  Its evidence is the verdict the hooks reach on a representative path for each declaration.

Around both:

- The Pi manifest reader, updated to the new section names so the extension keeps loading and `pi-security-validator-tests` stays green.
  No Pi behavior changes.
- `security-posture-alignment`: its delta and tasks give up the read-through declarations, the `ReadThroughCoversTheAgentModuleTree` decision, the lexer requirement and tasks, the backslash-continuation and hermetic-fixture tasks, and the grep-overtrigger task, all of which this change carries.
- Operator documentation: the bash expectation and the `CLAUDE_CODE_SHELL` pin in the Claude module README; the lexer's bash assumption and the absolute-path instruction in the shared `AGENTS.md` and the session instructions.

**Out of scope:**

- The Pi migration onto the shared hooks, and the remaining `security-posture-alignment` groups.
  Both wait for this change to land.
- Tracking `cd` within a command.
  The rule is designed and deferred: agents are told to name paths absolutely, and a relative path after a `cd` stays a stated limit until the deferred task is taken up.
- A `**` glob form.
  A directory entry already covers its subtree, and a broad name pattern is the name heuristic's job.
- Computing a carve-out for a link's target from the carve-out on the link.
  Creating a link inside a write-through directory is itself a permitted write, so inheritance would let an agent widen its own permissions in one unprompted step.
  Carve-outs stay explicit, and the validator names the target an operator would need to declare.
- Broadening floor conformance back over the guarded class.
  A closing task records the case for it and why it is expected to be hard.
- Writes to skill content.
  `Write`, `Edit`, and any command that is neither a recognized read nor a recognized run still gate.
- Backslash line continuation.
  A newline anywhere in a command still refuses it, so the question is only reachable once that is narrowed, and the task that establishes the answer moves here with the lexer.
- Adopting the lexer in the other Bash-judging hooks.
  `block-destructive-ops.py` and `block-secrets.py` match patterns over the command text and are meant to over-match; the two shell hooks cannot import a Python module without a Python start per call.
  The lexer's contract is written for any hook, and a closing task records the case for the two Python hooks.
- Pinning Copilot's shell.
  It follows the editor's terminal profile, which is also the user's terminal, so it stays on zsh and the lexer's bash assumption is recorded as a limit there and measured once.

## Approach

The manifest is policy and the hook is its interpreter.
A directory entry covers its subtree.
Given the classes and the precedence rule, an operator can write a policy as a base entry with carve-outs beneath it or as an enumeration of the enforcement it holds, and the hook reaches the same verdicts either way.
Which to write is a posture decision, recorded in `guarded-surface`, and the mechanism specs never name a location.

Links are handled by one rule.
A supplied path has a chain of hops: as written, each link along the way, and the final target.
A declaration has a chain the same way.
At each hop of the path the covering declarations are found, block is absolute, and the closest declaration decides; the path's verdict is the strictest across its hops.
This makes a restriction hold when any hop reaches it and a permission hold only when every hop allows it, with no rule written for either case.
A link at a declared location is followed by the declaration's own chain.
A link inside a declared directory is not, because a declaration names a location and not its entries; the validator lists a carve-out directory's immediate entries and reports a link whose target lands under a stricter declaration.

The text layer is what forced `location-only` into existence, and scoping it is what removes the need.
Once the lexer resolves a word, that word is a path and is judged by where it leads.
The text question remains only for a word the lexer refuses: a substitution, a brace expansion, a form the shell would rewrite in a way the hook cannot reproduce.
Such a word still states the paths it holds, and the fragment search finds them.

The lexer becomes `hooks/shell_words.py`, imported by both hooks.
It carries what `_split_words`, `_resolve`, `_candidate_words`, and `_segments` do today, plus a kind for each word: command, option, path candidate, pattern, redirection target, assignment, unresolvable.
The tamper hook's read and run classification and the sensitive-path hook's candidate selection both read those kinds.
The path-candidate rule is the one the overtrigger task already states: a separator or `~`, the operand of an input redirection, or a name that exists relative to the payload's working directory.
Every strong rule in `block-sensitive-paths` keeps judging every word; the name heuristic alone narrows to path candidates.

Bash is the reference shell.
`shellprobe` already runs each generated command through bash with every program replaced by a recorder, and the differential property already holds the tamper hook's lexer to it.
The property moves to the lexer module and is stated once.
Claude is pinned to bash through `CLAUDE_CODE_SHELL` in the settings file every launcher reads; Codex runs `bash -lc` by construction; Copilot runs the editor's terminal profile, which is zsh here.
The session-start hook warns where the pin is absent under Claude.
The differential property is run once under zsh, as a measurement rather than a suite, to record where zsh and bash hand a program different words; a form zsh runs more permissively than bash lexes becomes a follow-up.

`hooks.nix` enumerates `hooks/` at activation, so `shell_words.py` has no deployed symlink until the next `just nix switch home`.
The work happens in the `ai-guardrails` worktree, and the activation runs once after merge.

## Resolved Questions

- 2026-10-10: the `sensitive-path-nix-hook-wrapper` exception surface is removed, because renaming the hook it excused left it excusing nothing.
  Decided with the user.
