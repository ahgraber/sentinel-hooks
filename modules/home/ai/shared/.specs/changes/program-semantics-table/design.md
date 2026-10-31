# Design: program-semantics-table

## Context

- The shared hooks run as one short Python process per tool call, on four agents.
  `block-hook-tampering.py`, `block-sensitive-paths.py`, `block-leaks.py`, and `block-destructive-ops.py` read every Bash command, and every agent already registers all four (Claude Code settings, Codex `hooks.json`, Copilot `security-policy.json`, Pi `hook-dispatch.py`).
  The design adds no hook and changes no registration, so no agent settings file changes.
- The hooks read repository files through symlinks (`mkRepoSymlink`), so an edit is live on the next tool call and no build step stands between an edit and enforcement.
  `hooks.nix` creates one link per top-level entry of `hooks/`, from `builtins.readDir` at build time, so a new file or directory reaches each agent's hook directory only after a home-manager switch.
- `hook-interface` `ErrorHandlingByDamagePotential` sends `block-destructive-ops.py`, a hook that refuses a named class of command, to `Block` on an error judging a call, and the path hooks to `Ask`.
- `shell_words.py` lexes a command into segments of typed words with the directories each segment may run in; it stays as it is.
  `bash_commands.py` holds today's per-program knowledge; this design replaces that knowledge with the catalog and keeps the module as the place hooks call.
- `hook-interface` `NoSideEffects` binds a hook while it judges a tool call; the session-start check is not judging one.
- `block-leaks.py` `_invocation_read` bounds nesting at 4 today.
- The pilot rows, verification reports, and the macOS host inventory are in `._scratch/program-semantics-pilot/`; they seed the audit and are not shipped.
- Claude Code's shell defines `find` and `grep` as functions that run binaries built into `claude`; the hooks treat those as the harness's own and do not judge their identity.

## Decisions

The decisions are ordered by build dependency: the catalog format, then the loader, then the walker and its reading, then each consumer.

### Decision: OneTomlFilePerProgram

**Chosen:** `hooks/programs/<name>.toml`, one file per program keyed by base name, plus `hooks/programs/_aliases.toml` mapping other base names to entries.
The schema is the tree in `draft-table.md`, with the changes recorded there from the pilot and the review: effect sets, `implicit-effects`, typed `hidden-inputs`, per-implementation `parser` overrides, `values` counts, `terminators`, `default-subcommand`, `config-key-effects`, and a `verification` table per implementation (`sources`, `verified-by`, `date`, `effect-under = 0`).
No `long-prefixes` field: an abbreviation is an unlisted option, and the walker does not interpret it.

**Rationale:** a hook loads only the files a command reaches; the ten pilot rows parse in 6.6 ms together, so one file for several hundred programs would cost up to about 230 ms in each hook process.
One file per program makes an invalid entry disable one program, and lets audit workers write in parallel without touching one file.
TOML stays reviewable in a diff, which a security artifact needs.

**Alternatives considered:**

- One file: whole-catalog parse cost on every call, and one parse error disables every program.
- SQLite: as fast, but a binary file in review, and a generated database lags its source between builds.
- A build step that splits one source file: the live hooks read the repository, so the split output would lag the source.

### Decision: LoaderValidatesWhatACommandReaches

**Chosen:** a module `program_catalog.py` with one public lookup, `entry(name) -> Entry | InvalidEntry | None`, that reads the file from disk on each call, validates it against the schema, follows `_aliases.toml` and shared grammars with a cycle check, and returns an `InvalidEntry` value (name, defect) instead of raising.
`validate_all() -> list[InvalidEntry]` serves the session check and the flake check.
No cache outlives the process.

**Rationale:** reading from disk per process gives the freshness `AnInvalidEntryDisablesOnlyItsProgram` requires (a repaired entry is used on the next call).
Errors as values keep `shell-lexing` `EveryCommandReachesAVerdict`: no exception decides a verdict.

**Alternatives considered:**

- Load and validate everything at import: correct, but pays the whole-catalog cost on every call.
- A validity cache file: needs its own freshness rule and a writer, and a hook judging a call may not write it.

### Decision: TheReadingContainsItsOwnFaults

**Chosen:** `bash_commands.read` catches every exception raised while it loads an entry or walks a segment, records the fault on that segment as the reason its recognition ended, and returns the reading; it raises only for faults outside the reading, such as a missing module.
`program_catalog` validates each entry's field types before the walker sees it, so a wrong type is an `InvalidEntry`, not an exception.
Data files are located from `Path(__file__).resolve()` of the module that reads them, never from the hook script's path.

**Rationale:** the privilege refusal puts the walker inside `block-destructive-ops.py`, which reaches `Block` on an error; an uncaught walker fault on a common command would refuse it on every agent.
An ended recognition leaves each hook's rule for incomplete readings in force, which is conservative where it matters and silent elsewhere.
Resolving from the module keeps a new data file reachable before the home-manager switch that links it into each agent's hook directory, because Python resolves a script's symlink when it builds the import path, so the module itself is the repository copy.

**Alternatives considered:**

- Let faults propagate to each hook's error handling: turns a walker bug into a `Block` on every Bash call it occurs on in the privilege hook.
- Locate data from the hook script's directory: misses a new file until activation, and the hook then reports a missing catalog.

### Decision: AGetoptWalkerWithNoGuessing

**Chosen:** `bash_commands.read(command, cwd)` returns a `Reading` built by a walker over the lexer's segments and the catalog:

- Assignments and redirection targets stay in the reading; redirections resolve in the outer shell's directory.
- The program is looked up by base name, then alias; the spelling is kept for the read exemption.
- Options follow the entry's parser rules: clusters letter by letter, a value letter taking the rest of the cluster or the next word, attached `--opt=value`, `--`, numeric options, single-dash long options, and dashless clusters with value letters consuming following words in order.
  Options stop at the first operand where `options-before-operands` holds for the implementation.
- An unlisted option, an unresolvable word, an `opaque` value, a missing or invalid entry, or the nesting bound (4) ends the reading.
- Each implementation the entry covers is read separately.
  An option the entry tags for other implementations only is a documented rejection, and that implementation contributes nothing; any other failure makes the reading incomplete.
  The reading is the union of the accepting implementations.
- A `command` operand is read again from the top with the context the wrapper sets; `shell-text` is lexed with `shell_words` in that context; `code` is kept as text with its language.
- A launcher that generates arguments yields a nested reading of its shown words, marked as built at run time, with unknown generated words and the child's directory.

**Rationale:** these are the forms agents write in ordinary work; refusing them would gate routine commands.
Abbreviations are not interpreted, because whether a program accepts them varies by program and by subcommand (git's global options do not; its subcommands do), and the stop rule already handles every case where an abbreviation could hide danger.

**Alternatives considered:**

- Interpret unique prefixes per program: more facts to audit per program, and a wrong fact is a silent miss.
- A dedicated refusal of abbreviations: adds friction only to commands with no risk (`git log --oneli`); rejected by the user on 2026-10-17 under "response matches risk".

### Decision: ReadingIsASetOfEffectsWithContext

**Chosen:** `Reading` holds, per segment, a list of `Effect(kind, target, context, program, spelling, certainty)`, where `kind` is one of the schema's effects, `target` is a resolved path, a path pattern, a word, or text, `context` carries the resolving directory (or unknown), the expanding shell (outer or nested), the environment changes in force (assignments, replaced environment, `PATH` changed), and `certainty` is `known` or `possible`.
A segment also records `complete` and where it stopped.

**Rationale:** each hook judges the effects its policy covers, so no effect is dropped for being less severe, and the context lets a write resolve in the child's directory while a redirection resolves in the outer shell's.

**Alternatives considered:**

- One most-severe effect per word: loses the target another hook needs (`sed -i -e p <file>`).

### Decision: OneStopRule

**Chosen:** when a segment's reading stops, these yield `possible` effects, each with every path the segment names as a possible target:

- the program whose reading stopped;

- every later word that names a cataloged program by base name;

- every name a command-string wrapper would split out of a later word, taken as the union of three readings of that word, so no one grammar's miss is final:

  - the wrapper's own documented grammar, where its entry names one: `env -S` (`split-string`) decodes quotes, `\_` as a separator, the other backslash escapes, and `${NAME}` as unknown, per the GNU and FreeBSD manuals;
  - the word lexed with `shell_words` as Bash text;
  - the word cut into maximal runs of characters a program name can hold, splitting at every quote, backslash, whitespace, and other separator.

  `env -S "'doas' id"` yields `doas` from the first two readings, and `env -S 'doas\_id'` yields `doas` from the first and third.
  A decode error in the first reading leaves the other two.

A program with a valid entry yields the effects anywhere in its grammar.
A program whose entry is invalid yields the effects it had before the catalog, from a table held in `bash_commands.py` apart from the catalog and seeded from today's sets (`_OPERAND_EXTRACTORS`, the sensitive-path write forms, the privilege tools, and the store commands).
Refusing and gating hooks judge `possible` effects as they judge `known` ones; read admission rejects any incomplete segment.

**Rationale:** one rule covers `env -S '<cmd>'`, an abbreviated option, an invalid wrapper entry, and nesting beyond the bound, for privilege, destroy, write, and store checks alike.
It fires only where a dangerous program appears after the stop, so it adds no friction elsewhere.

**Alternatives considered:**

- Per-hook fallbacks: three separate rules, and the review found one that missed `env --chd /x rm -rf <ancestor>`.
- Later words only: the final review found that it loses the stopped program, so an invalid `chmod` entry would drop today's ancestor gate on `chmod 000 <ancestor>`.
- Whitespace splitting alone: misses `'doas'` inside `env -S "'doas' id"`, which `env -S` unquotes before it runs the name.
- Bash lexing alone: reads `env -S 'doas\_id'` as one word `doas_id`, where `env -S` takes `\_` as a separator and runs `doas id` (final review, N1, confirmed with a harmless probe).
- A global gate on every incomplete reading: the user rejected it on 2026-10-16; most incomplete readings come from `$VAR` operands in ordinary work.

### Decision: ShellStateChangesEndAdmission

**Chosen:** a segment that changes the shell's state for later segments ends read and run recognition for every later segment of the same shell.
The class is defined by builtin, not by variable: a segment that is only an assignment, and `export`, `declare`, `typeset`, `local`, `readonly`, `unset`, `set`, `shopt`, `enable`, `hash`, `alias`, `source`, `.`, `eval`, `read`, `printf -v`, `mapfile`, `readarray`, and a function definition.
`cd`, `pushd`, and `popd` are not in the class; the lexer follows them as directory changes.
A command whose segments are not read or run recognized is judged by the gates as today: it is asked about when it names a guarded location and proceeds when it does not.
Reads under a launcher (`uv run`, `nix develop -c`, `direnv exec`, and the rest) are never admitted, because only the wrappers `read-admission.toml` lists are transparent, so no launcher list is kept.

**Rationale:** the probe on 2026-10-17 found `source <file>; cat <guarded>`, `PATH=<dir>; cat <guarded>`, `export NAME=value; <reader> <guarded>`, `hash -p <path> cat; cat <guarded>`, and `enable -f <file> cat; cat <guarded>` each admitted as a read today, because each segment is judged alone.
A rule keyed on `PATH` or on named variables misses the forms it does not list (round-3 review, D2 and D3); a rule keyed on the builtin class does not need to know which name changed.
It only withholds admission, so a command that names nothing guarded proceeds as before, and `source .venv/bin/activate && pytest` is unaffected.

**Alternatives considered:**

- A rule keyed on `PATH` and a list of launchers: the round-3 review found five forms outside it.
- An allowlist of `PATH`-changing commands with every other one refused on every agent: refuses ordinary builds where no grant is at stake; kept as the fallback if the builtin class proves hard to hold complete.
- Resolving bare names through `PATH` in the hook: the hook cannot see the shell's `PATH`, its functions, or a program an earlier segment places.

### Decision: ReadAdmissionIsAPolicyFile

**Chosen:** `hooks/read-admission.toml` lists each admitted utility with `refuse` (options), `neutralize` (options that turn off hidden inputs), `require-first` (the option that must come first), and the transparent wrappers with `env`'s condition.
A test checks each entry against its catalog entry: every effect beyond reading a file and a plain value belongs to a refused option, and every hidden input of kind `supplies-options`, `runs`, or `names-files` is neutralized or reachable only through a refused option.
The trusted directories are `/usr/bin`, `/bin`, `/run/current-system/sw/bin`, and `/etc/profiles/per-user/<user>/bin`.

**Rationale:** admission is policy and stays reviewable apart from the catalog's facts; the test binds the two so neither admits on its own.
The trusted directories are the ones only root can change; a bare name keeps today's treatment, and the `PATH` hijack it allows is recorded as a limit for `path-directory-guarding`.

**Alternatives considered:**

- Admit every program the catalog shows as read-only: makes catalog accuracy the only barrier to an unprompted command; rejected by the user on 2026-10-16.

### Decision: ConsumersMoveOneAtATime

**Chosen:** each consumer moves onto the reading in its own task group, judged against the verdict cases recorded before the move:

- `block-hook-tampering.py`: read recognition from the reading and `read-admission.toml`; the ancestor gate from delete, write, and permission effects, `known` and `possible`, refusing on every agent where the ancestor holds an enforcement-floor location and asking otherwise.
- `block-sensitive-paths.py`: write targets from the reading's write, delete, and permission effects, combined with today's by-name forms, which stay; `READ_CMDS` and the broad read check stay unchanged.
- `block-leaks.py`: store commands from the reading; its current lexer-based store recognizer stays as the fallback for an incomplete reading or an invalid `op` or `kubectl` entry, with its own copies of the helpers it calls, so it imports neither the walker nor the catalog and survives their removal from `bash_commands.py`.
- `block-destructive-ops.py`: a privilege check over the reading, `known` and `possible`, apart from its pattern table; `block-dangerous-bash.sh` keeps its text match.
- `session-policy-checks.py`: `validate_all()` and the uncataloged report.

**Rationale:** the store refusal and the privilege refusal keep a path that does not depend on the catalog being right, so a bad entry cannot remove a refusal that exists today; one consumer at a time keeps each verdict change attributable.

**Alternatives considered:**

- Retire the leak hook's own recognizer: S1 of the review showed the raw-text fallback alone misses `kubectl get pods,secrets` and ANSI-C spellings.
- A new privilege hook: needs a registration in every agent's settings, which the user must commit by hand for Claude Code.

### Decision: TheAncestorGateRefusesOnTheFloor

**Chosen:** removing, renaming, or replacing a directory that holds an enforcement-floor location is refused on every agent, with a reason that tells the user to run the command in their own terminal; a directory holding only guarded locations is asked about, with a reason naming the declared locations it would remove.
Editing a single file on the floor stays an ask.

The floor refusal has a backstop that does not use the catalog: a segment invoking `rm`, `rmdir`, `mv`, `shred`, `trash`, `unlink`, or `find` with `-delete` or an execution action, by base name and through any wrapper the text shows, that names a path enclosing a floor location, is refused whatever the reading holds.
An operand that cannot be resolved and could enclose a floor location is refused.

**Rationale:** every agent runs its hooks through symlinks into the repository (the round-3 review confirmed the links for Claude Code, Codex, and Pi), so removing the hook sources turns the guardrails off for every agent at once, and an ask is what alert fatigue lets through; a refusal leaves the user able to do it as a deliberate act outside the agent.
Guarded files are tracked by git, so asking there matches "response matches risk".
The backstop keeps the module's strongest refusal independent of the catalog, as the store and privilege fallbacks are, so a valid but wrong `rm` entry cannot drop it.

The refusal closes the direct removal of the hook sources only.
A branch switch or `git reset --hard` to a commit without them empties the same directories, and the command text cannot show a commit's contents; this is a recorded limit.

**Alternatives considered:**

- Keep the ask everywhere: one approved prompt disables every agent's hooks.
- A filesystem flag such as `chflags uchg`: the agent runs as the user and can clear it; it would also stop the branch-switch case, so it stays open as a defense the user may opt into.
- A session-start check that the hook links resolve: the check runs from the same hook directory, so it does not run once that directory is gone.

### Decision: UncatalogedProgramsAreWarnedAtUse

**Chosen:** a hook that reads a Bash command and finds an uncataloged program, or an invalid entry, on an allowed call emits a warning on agents that show one (Claude Code and Pi); `session-policy-checks.py` prints one line at session start with the count of names on `PATH` that have no entry and the path of a file listing them, written under `$XDG_STATE_HOME/ai-hooks/`.

**Rationale:** the warning reaches the user where the gap is used; the session line reaches Codex and Copilot, which show no warning on a tool call.

**Alternatives considered:**

- Warn about every uncataloged name at session start: on the maintainer's Mac `PATH` holds about 2,500 names, so a list would be noise.

## Architecture

```text
command text
    │
    ▼
shell_words.lex ──► segments of typed words + directories
    │
    ▼
bash_commands.read ──► walker ◄── program_catalog.entry(name)
    │                     │            │
    │                     │            └── hooks/programs/*.toml, _aliases.toml
    ▼                     ▼
Reading: per segment, effects (kind, target, context, program, spelling, certainty),
         complete / stopped-at, nested readings
    │
    ├──► block-hook-tampering.py   read admission (read-admission.toml), ancestor gate (floor: refuse)
    ├──► block-sensitive-paths.py  write targets ∪ by-name forms; broad read check unchanged
    ├──► block-leaks.py            store commands; lexer-based fallback recognizer
    ├──► block-destructive-ops.py  privilege refusal (known and possible)
    └──► session-policy-checks.py  validate_all(), uncataloged count and list file
```

## Risks

- **Rows that are valid but wrong.**
  Every hook agrees on a wrong reading.
  Mitigation: the verification record per implementation, the read-admission test, the store and privilege fallbacks that do not use the catalog, the by-name write forms, and `NoRecognitionIsLostInTheMove` over the recorded verdict cases.
- **Audit cost and staleness.**
  Several hundred rows at about 80k haiku tokens each, and rows drift as tools release.
  Mitigation: the first batch covers the programs the hooks recognize today and the tools agents run most; a new option ends the reading, so drift produces gates, not passes; a cross-validation test compares option spellings with each installed binary's `--help`.
- **More asks from the stop rule.**
  An incomplete reading that names a destroyer gates on ancestors.
  Mitigation: the rule fires only when a cataloged program with that effect follows the stop; the floor refusal and named-location reasons keep the asks that matter distinct.
- **`PATH` hijack of bare names across tool calls.**
  On the maintainer's Mac twelve user-owned directories precede `/usr/bin` on `PATH`, and Claude Code's sandbox lets the agent write at least `~/.cargo/bin`.
  A program placed there in one tool call answers to an admitted name in a later one, and nothing in this change sees that: neither command changes the shell's state.
  `ShellStateChangesEndAdmission` closes only the same-command forms.
  Mitigation: `path-directory-guarding` gates a hand-placed binary when the command names the directory; a program that writes there from its own code remains outside every command-text hook, and only the sandbox's write list can close it.
- **An import failure in a Bash-reading hook.**
  If `bash_commands.py` or `program_catalog.py` cannot be imported, `block-destructive-ops.py` fails at startup, which at least one agent encodes as a refusal of every Bash call; today that hook imports neither.
  Mitigation: the import-path test in task 12.6, the flake check that imports each hook, and deployment through a home-manager switch before the consumers move.
- **Per-process load cost.**
  Unmeasured for the full walker.
  Mitigation: a benchmark task measures the full hook path on the verdict cases before the consumers move, against today's timing.
