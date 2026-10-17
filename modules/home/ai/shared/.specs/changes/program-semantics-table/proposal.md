# Proposal: program-semantics-table

Status: draft.
The schema is settled, with the additions a ten-program pilot audit found on 2026-10-16; the full audit has not started.
This change has no delta specs, design, or tasks yet.

## Intent

The hooks read a Bash command through the shared lexer, then ask what the program in command position does with its arguments: which words it reads, writes, or deletes, and which words it runs as a command, a script, or inline code.
That knowledge is spread across `bash_commands.py`, `block-sensitive-paths.py`, `block-leaks.py`, and `block-hook-tampering.py` as separate sets, dicts, and functions, and the copies disagree.

Probes on 2026-10-16 found forms the hooks judge wrongly:

- `env sudo rm -rf <dir>`: `invoked` finds `rm`, but `destroyed_operands` finds nothing, because it strips one privilege wrapper and one execution wrapper instead of repeating as `invoked` does.
- `sudo --user root <cmd>` and `sudo -nu root <cmd>`: `invoked` returns `root` as the program.
  The privilege table lists only short options that take a value, and the walker does not read a value letter inside a cluster.
- `env -S '<cmd> <args>'`: the whole quoted string becomes the program name.
- `caffeinate -ims rm -rf <dir>`: no hook knows that `caffeinate` runs a command, so the destroy is not seen.
- `rm -- -precious`: no destroyed operand, because every word that starts with `-` is read as an option, including words after `--`.
- `bash -e <script>` is read as inline code whose text is the script path; one option set serves every interpreter.
- `doas -a <style> <cmd>` takes `<style>` as the program.
- `watch -x <cmd>` is joined as `sh -c` text, though `-x` runs its arguments as argv.

Each gap has the same cause: the hooks hold a partial, hand-written grammar for each program they know, and none for the rest.

## User Stories

### Story: a-wrapper-read-once-holds-everywhere

As the operator of four agents, I want a command judged the same way through `sudo`, `env`, `caffeinate`, and every other wrapper, whichever hook reads it, so that a destroy or a secret read refused in plain spelling is refused under a wrapper as well.

North star: "a denial from any layer is final"; a denial that `env` in front of `sudo` undoes is not final.
It also serves "response matches risk": privilege escalation is refused whatever wrapper carries it.

### Story: every-argument-has-a-stated-effect

As the maintainer of these guardrails, I want each program's arguments typed as read, write, delete, run, or plain once, as data, so that every hook reads the same effects and a fix reaches all of them.

North star: "the policy is written once"; today the reading beneath the policy is written four times.

### Story: unknown-reads-as-dangerous

As the maintainer, I want a program or argument the catalog cannot read never judged safer than the hooks judge it today, and reported where it is used, so that a missing or stale row is a visible gap and not a silent allowance.

North star: "degradation keeps the user in control"; a row the catalog lacks or cannot read never grants the agent more than a complete row would.

## Scope

**In scope:**

- A program catalog, one file per program under `hooks/programs/`, that types each program's options, operands, and subcommands by effect.
  The schema is in `draft-table.md`.
  The catalog holds no policy: it never says what is refused, asked about, or allowed.
- Coverage: privilege tools, passthrough wrappers, launchers, interpreters and shells, Bash and zsh builtins that run or read, the POSIX utilities, GNU coreutils, findutils, diffutils, and util-linux, the macOS and BSD counterparts, and common tools such as `rg`, `fd`, `jq`, `git`, `curl`, and `kubectl`.
  Privilege tools include `sudo`, `doas`, `su`, `runuser`, `pkexec`, `run0`, `setpriv`, `chroot`, `systemd-run`, and macOS `osascript ... with administrator privileges`.
- An audit that writes the rows from primary sources: man pages and `--help` output for each implementation, and the distribution manual archives for Debian, Ubuntu, Fedora, RHEL, Arch, and BusyBox.
  Fig completion specs (MIT) seed rows; GTFOBins is a checklist of programs that run commands or touch files, not a copy source.
- One argument walker over the catalog, which replaces `invocation`, `invoked`, `_strip_privilege`, `_su_code`, `_privileged_shell`, `_inline_code`, `launched_arguments`, `watch_script`, `_after_options`, `_operands`, `_option_value`, and the per-program extractors behind `destroyed_operands`.
- Every reader of the lexer's `option` kind moves to the walker in this change: `bash_commands.py`, `block-hook-tampering.py`, `block-sensitive-paths.py`, and `block-leaks.py`.
  The lexer keeps the kind as a hint; no consumer decides an operand from it.
- The read classifier and the destroy reading move onto catalog effects.
  `WRITE_OPTIONS`, `REQUIRED_FIRST_OPTION`, `_OPERAND_EXTRACTORS`, and `_write_words` are replaced by catalog lookups; `READ_ONLY_UTILITIES` becomes the admitted list described below.
  `block-sensitive-paths.py` `READ_CMDS` stays a policy list: it decides which segments the broad check of `BlockBashReadFromZeroAccessPath` covers, and replacing it with every program whose row reads a file would widen that check to nearly every program.
  The set of utilities admitted as reads stays an explicit list, a policy decision under `ReadClassifierAdmitsOnlySelfDescribingUtilities`.
  Each entry names a program, the options it refuses, and the options that neutralize its hidden inputs, as `--no-config` neutralizes `rg`'s.
  A command is read-only when its program is listed, its invocation finds only `path-read` and `value` effects, and it carries no refused option.
  A test fails when a listed program's row holds an effect beyond those that no refused option covers, or a hidden input that no neutralizing option covers: a complete row keeps `rg --pre` and `find -exec`, and the list refuses them.
  A catalog error alone therefore never admits a program; the destroy reading and the leak check consume catalog effects directly, where a new row only adds coverage.
- A program spelled with a path reaches the row of its base name, so `/usr/bin/sudo` and a nix store `sudo` meet every rule `sudo` meets.
  The read exemption is narrower: it applies to a bare name, or to a path in a trusted system directory (`/usr/bin`, `/bin`, `/run/current-system/sw/bin`, and `/etc/profiles/per-user/<user>/bin`: directories only root can change).
  A directory the user owns, such as `~/.nix-profile/bin` or `~/.cargo/bin`, is not trusted, because the agent runs as the user.
  A bare name is admitted as today and is not resolved: on this Mac `~/.cargo/bin`, which Claude Code's sandbox lets the agent write, precedes `/usr/bin` on `PATH`, so bare `column` can run a program the agent placed.
  That is a limit of every command-text hook; the sandbox's write list is where it can be closed.
  A path directly in the nix store is not trusted, because any build can place a program of any name there.
  The trusted-directory rule applies to each transparent wrapper as well as to the reader.
  `/project/bin/cat` is not admitted as a read.
- A program the catalog does not list is reported: a warning at each use on agents that can show one, and a count with a report file at session start.
- `block-leaks.py` reads the `op` and `kubectl` subcommands through the catalog and keeps only the store policy.
- `dangerous-bash-blocking` `BlockPrivilegeEscalation` is enforced over the reading: a Python hook that reads every Bash command refuses any command that invokes a program with a privilege effect, at any nesting depth and under any spelling of its path.
  `block-dangerous-bash.sh` keeps its text match as a backstop.
  A lookup such as `command -v sudo` does not invoke `sudo`.
- A verdict table under `tests/`, checked in before code moves, with each probe form above as a failing row.
- A flake check that validates the catalog, and cross-validation tests that compare rows against the installed binaries' `--help` output.

**Out of scope:**

- Policy: which subcommands read a secret, which operations ask, which paths are guarded.
  Policy stays in `block-leaks.py`, `guarded-paths.toml`, and `block-destructive-ops-patterns.toml`.
- A command name held in a variable, a `$(…)` substitution, a backtick, an alias, or a shell function.
  The lexer marks these unresolvable, and the walker stops on them.
- The meaning of text inside interpreter code in another language (`python -c`, SQL, `awk` programs beyond `system()` and pipes).
  The catalog marks such text as inline code in its language; rules over it stay with `single-command-rule-engine`.
- A port of the walker to another language.

## Approach

- The schema follows Fig completion specs: a program has options, operands, and subcommands; an option or operand that takes a value has an argument object.
  Fig's parser rules carry over (`options-before-operands`, `long-single-dash`, `requires-separator`, `load-spec`).
  The catalog adds effect types per argument and the parser rules Fig lacks: values that only attach, options that end option parsing, `--`, numeric options, and dashless leading clusters as in `tar xzf`.
  An abbreviated long option is not interpreted; it ends the reading.
- The lexer stays as it is.
  It already hands over words after quote removal and expansion, with redirection targets and leading assignments marked.
  An unresolvable word can stand for any number of words, any of which may be an option, so the walker ends recognition at one, as `UnrecognizedCommandsAreGated` requires today; an unmatched glob stays one literal word, as `AWordTheShellRewritesIsResolvedOrRefused` states.
- A reading is a set of effects, each with its target and its context: the directory it resolves in, the environment it runs with, and the nested command it belongs to.
  No effect is dropped because another is more severe: `sed -i -e p <file>` runs `sed` code and writes `<file>`, and each hook judges the effects its policy covers.
- GNU and BSD spellings live in one row, each option tagged with the implementations that accept it.
  The platform does not decide the implementation: a Mac with nix tools on `PATH` runs GNU `rm`, and Claude Code's shell runs a built-in `bfs` for `find`.
  Where implementations disagree, the walker reads the command under each and keeps the union of the effects.
- Launchers that build arguments at run time (`xargs`, `find -exec`, `parallel`) keep the status `_builder` gives them today: the words they run are not on the command line, so the reading records unknown arguments and the directory each child runs in.
- Assignments, leading or given to `env`, stay in the reading; `env --env0-from <file>` replaces the environment, an effect of its own.
- An option the row does not list, a program with no row, and an invalid row each end recognition for that program.
  Each hook then does what it does today with an unrecognized command: the tamper hook gates it when it names guarded locations, and the leak check keeps its text fallback for store commands, so `op read` stays refused if the `op` row is invalid.
- Nested readings through `command`, `shell-text`, and reused specs are bounded in depth, and the bound ends recognition, so no error decides a verdict (`EveryCommandReachesAVerdict`).
- Verdict table first, then the walker, then each consumer, each step judged against the table.

## Consequences

- Two hooks change role.
  `block-destructive-ops.py`, today a pattern table, also refuses privilege escalation over the reading, so it imports the walker and the catalog.
  It reaches `Block` on an error judging a call, under `ErrorHandlingByDamagePotential`, so a walker error would refuse that command on every agent; `ReadingACommandNeverFails` turns every such fault into an ended recognition instead.
  An import failure of the walker or the catalog makes the hook fail at startup, which at least one agent encodes as a refusal of every Bash call.
  `single-command-rule-engine` reworks the same hook, and the change that lands second merges into the other's form of it.
  `session-policy-checks.py`, today a check of the shell pin and the manifest, also validates the catalog and writes the uncataloged list under `$XDG_STATE_HOME/ai-hooks/`, its first write; session start judges no tool call, so `NoSideEffects` does not bind it.
- `bash_commands.py`, `block-hook-tampering.py`, `block-sensitive-paths.py`, and `block-leaks.py` are refactored within their roles.
  `shell_words.py`, `block-dangerous-bash.sh`, the registrations, the Copilot adapter, and Pi's dispatcher do not change.
- No manifest changes.
  The new policy and data files, `hooks/programs/` and `hooks/read-admission.toml`, sit under `<repo>/modules/home/ai/shared/hooks/`, which the manifest already declares as enforcement floor, so an agent's edit to them asks.
- `hooks.nix` links each top-level entry of `hooks/` into every agent's hook directory from a listing taken when the configuration builds.
  A new file or directory reaches the agents only after a home-manager switch; an edit to an existing file is live at once, as today.
  A hook that finds a data file from its own script's location would look in the agent's hook directory, where a new file is absent until that switch, so data files are located relative to the module that reads them.
- Moving every reader of the `option` kind changes some verdicts in `guarded-path-cases.json` and `sensitive-path-cases.json`.
  Each changed verdict is reviewed as a behavior change, and the Pi suite runs the same tables.
- The catalog is one TOML file per program under `hooks/programs/`, with an alias index, loaded by a `program_catalog.py` module that `bash_commands` and `session-policy-checks.py` share.
  A hook loads only the rows a command names.
  The ten pilot rows parse in 6.6 ms together; one file for 350 programs at that density would cost up to about 230 ms in every hook process that reads a Bash command.
  SQLite would be as fast but would put a binary file under review, and a build step that generated it would leave the live file behind the source.
- The hooks read the catalog through a repository symlink, so an edit takes effect on the next tool call and the flake check cannot stop it first.
  An invalid row disables only its program, which each hook then treats as unrecognized, as it does today.
  A row reached through `aliases` or a reused spec is invalid with it.
  A hook validates only the rows a command reaches, the alias index included, so a broken file a command does not reach changes nothing for that command.
  An invalid alias index disables every program that needs an alias lookup, not the rows found by base name.
  `session-policy-checks.py` reports every invalid row at session start, as it reports manifest defects, for Claude Code, Codex, Copilot, and Pi.
  A refusal or ask on a disabled program names the invalid row, so every agent shows it at the point of use; Claude Code and Pi also show a warning on each call that names it.- A program with no row is judged as the hooks judge an unrecognized command today, so no verdict tightens for lack of a row.
  The warning for an uncataloged program shows on Claude Code and Pi; Codex and Copilot cannot show a warning on a tool call, so they see only the session-start count.
  The first audit batch covers the tools agents run most, including `uv`, `ruff`, and `pre-commit`, so the warnings start few.
- Comparing rows with `--help` output checks option spellings only.
  Effects are checked by the verification pass, by verdict-table rows, and by harmless differential tests that run a program and observe which files it opens.
- Rows go stale as tools add options.
  A new option is unknown, so it is gated or asked about until the row is updated; the cross-validation tests report the drift.
- Fig rows may be copied with attribution.
  GTFOBins is GPL-3.0 and is read, not copied.
  `destructive_command_guard` excludes Anthropic and OpenAI from its license and is not used.

## Dependencies

- `credential-store-handoff` is archived; its tests in `tests/test_invoked_program.py` become verdict-table rows.
- `recursive-credential-read-refusal` applies after this change: its recursive readers become catalog rows instead of a fourth table.
- `single-command-rule-engine` is independent in order but shares `dangerous-bash-blocking`.
  This change owns `BlockPrivilegeEscalation`; that change's proposal records the hand-off, and its remaining command rules may render from the walker.
- `multi-line-command-lexing` is independent: it changes what the lexer produces, and the walker reads that output.
  It shares `sensitive-path-blocking` with this change.
- `ORDER.md` lists this change before `recursive-credential-read-refusal`, and the two shared specs.

## Resolved Questions

- 2026-10-17 Corrected parses: a verdict that a misparse made stricter than its baseline requirement states is a bug, and the corrected verdict is a spec correction, not a loosening.
  `bash -e <existing exec-through script>` proceeds, as `UnrecognizedCommandsAreGated` already requires for a recognized run of an exec-through program; today's gate comes from reading `-e` as inline code.
  Each spec correction is listed with the requirement it restores, so the regression check does not flag it and a return of the bug fails.
  A verdict change that no baseline requirement supports stays a policy loosening and needs the user's approval.
  Decided with the user.

- 2026-10-16 Scope: the catalog covers privilege tools, passthrough wrappers, launchers, interpreters, readers, and destroyers, audited for exhaustive coverage with a preference for false positives.
  Decided with the user.

- 2026-10-16 Row shape: a Fig-style tree of options, operands, subcommands, and modes, each argument typed by effect, because prior art shows the shape works.
  Decided with the user.

- 2026-10-16 Audit sources: man pages and `--help` per implementation, with Debian, Ubuntu, Fedora, RHEL, Arch, and BusyBox manuals; haiku workers with one sonnet verification pass, after a ten-program pilot.
  Decided with the user.

- 2026-10-16 Read admission: an explicit admitted list, checked against catalog effects by a test; the destroy reading and the leak check consume catalog effects directly.
  Decided with the user.

- 2026-10-16 Invalid rows: an invalid row disables only its program, reported loudly at session start and at each use.
  Decided with the user.

- 2026-10-16 Location: one TOML file per program under `hooks/programs/`, not one file and not SQLite.
  Decided with the user.

- 2026-10-16 Interpreters: an interpreter with no script operand reads its program from standard input.
  Decided with the user.

- 2026-10-16 Transparent wrappers: `time`, `timeout`, `stdbuf`, `setsid`, `nice`, and `caffeinate` keep a read a read; `nohup` does not; `env` does only when its assignments name none of the inner program's hidden inputs.
  Decided with the user.

- 2026-10-16 `watch -x`, `node -p`, and `deno eval` are read in this change.
  Decided with the user.

- 2026-10-16 Read admission, restated after review: each admitted program lists the options it refuses and the options that neutralize its hidden inputs, and the test checks that these cover every effect in its row beyond `path-read` and `value`.
  Decided with the user.

- 2026-10-16 Unreadable programs: a program with no row, an invalid row, or an unknown option is treated by each hook as it treats an unrecognized command today; no global gate on unknown programs is added.
  A program the catalog does not list is reported at each use where the agent can show a warning, and counted at session start.
  Decided with the user.

- 2026-10-16 Path-qualified programs: every rule that detects a danger matches by base name, so `/usr/bin/sudo` and a nix store `sudo` are `sudo`; the read exemption applies only to a bare name or a trusted system directory.
  Decided with the user.
  After review, a path directly in the nix store is not a trusted directory, and the rule covers transparent wrappers too.

- 2026-10-17 Trusted directories are the ones only root can change; user-owned directories such as `~/.nix-profile/bin` and `~/.cargo/bin` are not trusted.
  Bare names are not resolved through `PATH`; the `PATH` hijack is recorded as a limit for the sandbox layer.
  Decided with the user.

- 2026-10-17 Incomplete readings: one rule for every hook that refuses or gates: after the reading stops, every later word naming a cataloged program may run, with every path a possible target.
  Hooks do not rewrite commands, and `env` is not refused as a whole.
  Decided with the user.

- 2026-10-17 Abbreviated long options get no refusal of their own: an abbreviation ends the reading, the stop rule refuses or gates the dangerous cases, and a separate refusal would add friction only to commands with no risk, against "response matches risk".
  The user delegated this decision.

- 2026-10-17 Shell-state changes: a segment that is only an assignment, or a builtin that changes variables, options, builtins, the command hash, aliases, or functions, or that sources or evaluates text, ends read and run recognition for every later segment in the same shell.
  The rule is keyed on the builtin class, not on `PATH`, after the round-3 review found five same-command forms admitted as reads today.
  An allowlist with refusals stays the fallback.
  Decided with the user.

- 2026-10-17 Floor ancestors: removing, renaming, or replacing a directory that holds an enforcement-floor location is refused on every agent, with a base-name backstop that does not read the catalog and a refusal for an unresolved operand; directories holding only guarded locations are asked about.
  A branch switch or reset that empties the hook sources is a recorded limit.
  Decided with the user.

- 2026-10-16 Privilege refusal: this change enforces `BlockPrivilegeEscalation` over the reading, so wrapped and path-qualified privilege tools are refused; `single-command-rule-engine` is told and does not add its own privilege rule.
  Decided with the user.

- 2026-10-16 Sensitive-path words: `BlockBashReadFromZeroAccessPath` keeps judging every word of a reader's segment; the catalog does not narrow it.
  `sensitive-path-word-narrowing` is stubbed to narrow it once evidence shows false negatives stay minimal.
  Decided with the user.

- 2026-10-16 `uv run` is a launcher, and `uvx <name>` reads as the nested command `<name>`, as `draft-table.md` "Decisions" records.
  Decided with the user.
