# Draft: program semantics catalog

This is a working document for the user to react to, not a spec, design, or task list.
It proposes the schema of the program catalog under `hooks/programs/`, which `proposal.md` describes, and shows its shape on a few rows.
The rows below illustrate the schema and are not audited; the audit writes the real rows.

## Purpose

The hooks read a Bash command through the shared lexer, then ask what the program in command position does with its arguments.
The catalog types every argument of every listed program by effect: a file read, written, or deleted, a command or code run, or a plain value.
One walker reads a command against the catalog, and every hook consumes the walker's reading.
The catalog holds no policy.

## Prior art

No existing project holds per-argument effects for many programs; the schema combines the first four below, and the fifth seeds rows and bypass cases.

- Fig completion specs (`withfig/autocomplete`, MIT): the option, argument, and subcommand tree, `isCommand` for an argument that is a command line, and parser directives for options that must precede operands, single-dash long options, and required separators.
  The data is shallow: `src/sudo.ts` declares two of sudo's value options.
- Codex's removed `execpolicy-legacy` (Apache-2.0): operand types `ARG_RFILES` and `ARG_WFILE`, and per-program `should_match` and `should_not_match` cases.
- GTFOBins (GPL-3.0): a per-program list of capabilities such as shell, command, file read, and file write, used as a checklist of programs to audit.
- `cc-safety-net` (MIT): wrapper stripping for `sudo`, `env`, `env -S`, and `command -pv`, whose tests are a source of bypass cases for the verdict table.
- Tracekit (`Cygnux-Labs/Tracekit`, MIT, read at `218f2bf`, 2026-10-25): `tracekit/policy2/shell.py` holds tables of about 60 passthrough wrappers and 12 launchers (`WRAPPERS`, `RUNNERS`, `PARALLEL_OPTS`, `DASH_C`, `SHELL_VALUE_OPTS`, `INTERP_VALUE_OPTS`), each with the options that take a value and the positional words before the command, plus interpreter code flags (`CODE_FLAGS`) and the shells it reads (`SHELLS`) and does not (`FOREIGN_SHELLS`).
  It has no file effects, so it seeds the wrapper, launcher, and interpreter rows and `_coverage.toml`, and each seeded row is still audited from primary sources.
  `docs/limits.md` lists, per rule, the spellings its parser misses (a wrapper not in its tables such as `bwrap`, `git -c alias.*`, SQL sent to `psql` by here-document, `git apply`), which are bypass cases for the verdict table.

## Schema

The catalog is one TOML file per program, `hooks/programs/<name>.toml`, named by base name, with an alias index beside it.
The illustrative rows below write each file's table as `[programs.<name>]` to show several in one block.

### Program fields

- `aliases`: other base names that run the same program, as `python3` for `python` and `gtar` for `tar`.
- `implementations`: the implementations audited, each an identifier and the source read, as `gnu = "coreutils 9.5 info manual"`.
- `parser`: how the program splits its words.
  - `options-before-operands`: options end at the first operand, as getopt does with a leading `+` or `POSIXLY_CORRECT`; default false, which permits GNU permutation.
  - There is no field for abbreviated long options: an abbreviation is an option the entry does not list, and it ends the reading (decided 2026-10-17); the validator rejects a `long-prefixes` field.
  - `long-single-dash`: options with one dash may be whole words, as `find -name`; clusters are then off.
  - `clusters`: short options may be joined, as `-ims`; default true.
    A letter that takes a value takes the rest of the cluster, or the next word when it ends the cluster, so `-nu root` gives `u` the value `root`.
  - `dashless-cluster`: the first word may be a cluster with no dash, as `tar xzf`.
  - `numeric-option`: the option a bare `-<number>` stands for, as `-n` for `head -5`.
- `hidden-inputs`: what changes the program's behavior without appearing on its command line: environment variables and configuration files, as `LESSOPEN` for `less` or `RIPGREP_CONFIG_PATH` for `rg`.
  `ReadClassifierAdmitsOnlySelfDescribingUtilities` is judged against this field.
- `privilege`: the program runs its command as another user; boolean.
- `reads-program-from-stdin`: the conditions under which the program reads its program text from standard input: `no-operand`, or option names such as `-s` and `-`.
- `options`, `operands`, `subcommands`, `modes`: below.
- `note`: why the row is as it is.

### Options

Each entry of `options` has:

- `names`: every spelling, short and long.
- `value`: `none` (default), `separate` (the next word or attached), `attached-only` (only `-iSUFFIX` or `--opt=value`), or `optional-attached`.
- `arg`: the effect type of the value, from the list below.
- `ends-options`: after this option and its value, no word is an option, as `python -c <code> <args>`.
- `sets-mode`: the mode this option selects, as `-x` for `tar`'s extract mode.
- `retypes-operands`: the effect type the option gives the operands, as `-i` gives `sed` operands `path-write`.
- `when-no-command`: what the program does when this option is present and no command follows, as `stdin-shell` for `sudo -s`.
- `implementations`: the implementations that accept this spelling with this meaning; absent means all.

### Operands

Each entry of `operands` has an `arg` type and a `count`: a number, `rest`, `rest-but-last`, or `last`, and an optional `mode`.

### Subcommands and modes

`subcommands` holds child rows keyed by word, as `git rm`, `uv run`, and `op read`; each child takes the same fields, and `persistent-options` on the parent apply in every child.
`modes` holds child rows selected by an option instead of a word, as `tar -x` and `tar -c`.

### Effect types

- `value`: a plain value, not a path.
- `path-read`, `path-write`, `path-delete`, `path-modify` (permissions, ownership, or times), `path-run` (a script or program the command runs).
- `chdir`: the directory the command runs in, as `env -C`, `git -C`, and `sudo -D`.
- `command`: the rest of the words are a command line, read again from the start of the catalog.
- `shell-text`: text the program runs as Bash-like shell code, lexed again by the hooks, as `bash -c` and `su -c`.
- `code`: program text in another language, with `language`, as `python -c`.
- `opaque`: recognition ends with no reading, as `env -S`.
- `unknown`: the audit could not decide; the word carries every effect its position allows.

A word may carry several effects, and the reading keeps all of them with their targets: `sed -i -e p <file>` runs `sed` code and writes `<file>`.
Where implementations disagree, the reading is the union of each implementation's effects.
A mode or a subcommand states the grammar for its own words and replaces the parent's typing for them; a retype adds effects to the operands it names.
An option the row does not list, a program with no row, and an invalid row end recognition for that program, and each hook does what it does today with an unrecognized command.

### Changes from the review

A Codex critic reviewed the proposal and this draft on 2026-10-16; these changes follow from its findings.

- Effects are a set per word, not one most severe effect, so no hook loses the target it checks.
- Each effect and each nested command carries its context: the directory its paths resolve in, the shell that expands it (outer or nested), and its environment.
  `env -C /d cat *.txt` expands the glob before the directory change; `env -C /d sh -c 'cat *.txt'` expands it after.
  `git --git-dir` and `--work-tree` locate repository state; they are not a directory change.
- Launchers that build arguments at run time (`xargs`, `find -exec`, `find -execdir`, `parallel`) record unknown generated arguments, the replacement string, and the directory each child runs in, and keep their builder status.
- An unresolvable word ends recognition, in a trailing operand list as elsewhere, since it can expand to an option.
- Assignments stay in the reading; `env --env0-from <file>` and similar options replace the environment and carry an effect of their own.
- Rules that detect a danger match a program by base name; the read exemption applies only to a bare name or a trusted system directory.
- `uvx <name>` keeps `uv`'s install effects when `<name>` has a row.
- Nesting is bounded, and the bound ends recognition.

### Changes from the pilot

A pilot on 2026-10-16 wrote rows for `sudo`, `su`, `env`, `xargs`, `find`, `tar`, `sed`, `rg`, `git`, and `python3`, and a second pass checked them against the sources.
The rows could not express these cases; each becomes a schema field before the full audit.

- `effect` on an option that takes no value but acts, as `find -delete` and `tar --remove-files`.
  The pilot rows put `arg` there, which the schema does not define.
- `retypes-operands` names the operand positions it changes.
  Applied to every operand, `git worktree add -b <branch> <path>` loses the `path-write` on `<path>`.
- `terminators` on an option whose value is a command, as `[";", "+"]` for `find -exec`, so the reading resumes after it.
- `values`, a count for an option that takes more than one word, as `find -fprintf <file> <format>`.
- `implicit-effects` on a program or subcommand that acts on a place no operand names, as `git stash pop`, `git config set`, and `git clean` with no pathspec writing the work tree or `.git/config`.
- `default-subcommand`, as `push` for a bare `git stash`.
- `config-key-effects`: a key-to-effect table for options whose value is `key=value`, as `git -c core.pager=<cmd>` and `git config set alias.x '!<cmd>'`.
- `hidden-inputs` entries become tables with a `kind`: `supplies-options` (`TAR_OPTIONS`, which can inject `--to-command`), `runs` (`PAGER`, `EDITOR`, `PYTHONSTARTUP`), or `changes-behavior`.
- Assignment effects: `env LD_PRELOAD=<lib> ls`, `env DYLD_INSERT_LIBRARIES=<lib> ls`, and `env PATH=<dir> ls` change which code runs, and the walker drops the assignments.
  The same holds for a bare `LD_PRELOAD=<lib> ls` before any program.
  A catalog-level table of environment names that load or locate code types those assignments as `path-run`.
- `root`, an effect type for an option that changes the root directory, as `sudo -R` and `chroot`.
  Every path after it resolves elsewhere, so it ranks with `opaque`.
- `parser` may differ per implementation: BSD `sed`, `tar`, and `find` stop options at the first operand where GNU permutes.
- Dashless clusters with several value letters consume the following words in order, as `tar cfC a.tar dir`.
- `negates`, for an option that undoes another, as `rg --no-pre`.

The pilot also showed that `find` run from Claude Code's Bash tool reports `bfs` 4.1.1.
Claude Code's shell defines `find` as a function that runs the `bfs` built into the `claude` binary, and `grep` as a function that runs a built-in `ugrep`, falling back to the `grep` on `PATH` only for options that start a filter, a pager, or a configuration file.
On the same host, `PATH` resolves `find` to GNU findutils 4.10.0, `sed` to GNU sed 4.10, `tar` to GNU tar 1.35, and `sudo` and `make` to the system binaries.
The implementations a row covers therefore come from what each agent's shell runs on each host, including functions its harness defines, not from the platform's default.
The audit starts with an inventory per host and per agent; the macOS inventory for Claude Code is in `._scratch/program-semantics-pilot/inventory-darwin.json`.

## Illustrative rows

These rows show the schema on hard cases and are not audited.

```toml
[programs.sudo]
implementations = { sudo = "sudo 1.9 manual" }
privilege = true
parser = { options-before-operands = true }
options = [
  { names = ["-u", "--user"], value = "separate", arg = "value" },
  { names = ["-g", "--group"], value = "separate", arg = "value" },
  { names = ["-D", "--chdir"], value = "separate", arg = "chdir" },
  { names = ["-s", "--shell"], when-no-command = "stdin-shell" },
  { names = ["-i", "--login"], when-no-command = "stdin-shell" },
  { names = ["-n", "--non-interactive"] },
  { names = ["-e", "--edit"], retypes-operands = "path-write" },
]
operands = [{ arg = "command", count = "rest" }]
note = "Partial: the audit lists every option; `-l`, `-v`, `-k`, and `-V` run no command."

[programs.caffeinate]
implementations = { macos = "caffeinate(8)" }
parser = { options-before-operands = true }
options = [
  { names = ["-d"] },
  { names = ["-i"] },
  { names = ["-m"] },
  { names = ["-s"] },
  { names = ["-u"] },
  { names = ["-t"], value = "separate", arg = "value" },
  { names = ["-w"], value = "separate", arg = "value" },
]
operands = [{ arg = "command", count = "rest" }]

[programs.env]
implementations = { gnu = "coreutils", bsd = "macOS env(1)" }
parser = { options-before-operands = true }
options = [
  { names = [
    "-u",
    "--unset",
  ], value = "separate", arg = "value" },
  { names = [
    "-C",
    "--chdir",
  ], value = "separate", arg = "chdir", implementations = [
    "gnu",
  ] },
  { names = [
    "-P",
  ], value = "separate", arg = "value", implementations = [
    "bsd",
  ] },
  { names = [
    "-S",
    "--split-string",
  ], value = "separate", arg = "opaque" },
  { names = [
    "-i",
    "--ignore-environment",
  ] },
]
operands = [{ arg = "command", count = "rest" }]
note = "Leading NAME=value operands belong to env; the walker reads them before the command."

[programs.bash]
reads-program-from-stdin = ["no-operand", "-s"]
options = [
  { names = [
    "-c",
  ], value = "separate", arg = "shell-text", ends-options = true },
  { names = [
    "-o",
    "+o",
    "-O",
    "+O",
  ], value = "separate", arg = "value" },
  { names = [
    "--rcfile",
    "--init-file",
  ], value = "separate", arg = "path-run" },
  { names = [
    "-e",
  ] },
  { names = [
    "-x",
  ] },
]
operands = [{ arg = "path-run", count = 1 }, { arg = "value", count = "rest" }]
note = "`-e` is errexit and takes no value."

[programs.sed]
implementations = { gnu = "GNU sed 4.9", bsd = "macOS sed(1)" }
options = [
  { names = [
    "-i",
    "--in-place",
  ], value = "optional-attached", arg = "value", retypes-operands = "path-write", implementations = [
    "gnu",
  ] },
  { names = [
    "-i",
  ], value = "separate", arg = "value", retypes-operands = "path-write", implementations = [
    "bsd",
  ] },
  { names = [
    "-e",
    "--expression",
  ], value = "separate", arg = "code", language = "sed" },
  { names = [
    "-f",
    "--file",
  ], value = "separate", arg = "path-run" },
  { names = [
    "-n",
    "--quiet",
    "--silent",
  ] },
]
operands = [{ arg = "path-read", count = "rest" }]
note = "GNU `-i` takes only an attached suffix; BSD `-i` takes the next word. `sed -i -e x f` reads differently under each, so the walker reads both."

[programs.tar]
aliases = ["gtar", "bsdtar"]
parser = { dashless-cluster = true }
options = [
  { names = [
    "-x",
    "--extract",
    "--get",
  ], sets-mode = "extract" },
  { names = [
    "-c",
    "--create",
  ], sets-mode = "create" },
  { names = [
    "-t",
    "--list",
  ], sets-mode = "list" },
  { names = [
    "-C",
    "--directory",
  ], value = "separate", arg = "chdir" },
  { names = [
    "-f",
    "--file",
  ], value = "separate", arg = "unknown" },
  { names = [
    "--to-command",
    "--use-compress-program",
    "-I",
  ], value = "separate", arg = "shell-text" },
]
modes.extract = { options = [
  { names = [
    "-f",
    "--file",
  ], value = "separate", arg = "path-read" },
], operands = [
  { arg = "path-write", count = "rest" },
] }
modes.create = { options = [
  { names = [
    "-f",
    "--file",
  ], value = "separate", arg = "path-write" },
], operands = [
  { arg = "path-read", count = "rest" },
] }
modes.list = { options = [
  { names = [
    "-f",
    "--file",
  ], value = "separate", arg = "path-read" },
], operands = [
  { arg = "value", count = "rest" },
] }
note = "Extract writes beneath the `-C` directory or the working directory as well as any named member."

[programs.git]
parser = { options-before-operands = true }
persistent-options = [
  { names = ["-C"], value = "separate", arg = "chdir" },
  { names = ["-c"], value = "separate", arg = "value" },
  { names = ["--git-dir", "--work-tree"], value = "separate", arg = "chdir" },
]
subcommands.rm = { operands = [{ arg = "path-delete", count = "rest" }] }
subcommands.clean = { operands = [{ arg = "path-delete", count = "rest" }] }
note = "Partial. `-c core.pager=...` and `alias.*=!...` carry shell text; a value-pattern field may be needed, and the pilot decides."

[programs.rg]
hidden-inputs = ["env:RIPGREP_CONFIG_PATH"]
options = [
  { names = ["--pre"], value = "separate", arg = "path-run" },
  { names = ["-z", "--search-zip"], note = "runs decompression programs" },
  { names = ["-e", "--regexp"], value = "separate", arg = "value" },
  { names = ["-f", "--file"], value = "separate", arg = "path-read" },
]
operands = [{ arg = "value", count = 1 }, { arg = "path-read", count = "rest" }]
note = "Partial. `--no-config` removes the hidden input; the read classifier requires it."
```

## Walker

- Keep assignments and redirection targets in the reading; redirections are judged by the outer shell's directory, and assignments by the environment-name table and the inner program's hidden inputs.
- Look up the first word's base name, then its aliases; keep the spelling as written, for the read exemption.
  No row: unrecognized.
- Read options by the row's parser rules: clusters letter by letter, values separate or attached, unique long prefixes, `--`, numeric options, and dashless clusters.
  An unlisted option ends the reading as unrecognized.
- Apply modes and retyped operands, then type the operands by `count`.
  An unresolvable word ends the reading.
- For a `command` operand, read the rest from the top in the context the wrapper sets, so wrappers nest in any order.
  For `shell-text`, lex the text in that context and read it as a new command.
  Stop at the nesting bound with no reading.
- Where implementations disagree, read the command under each and keep the union of the effects.
- The result is a set of effects, each with its target and context, plus the commands nested beneath them, which each hook judges by its own policy.

## Decisions

The user decided each item below on 2026-10-16; none is open.

Decided 2026-10-16, restated after review: the read classifier keeps an explicit admitted list.
Each entry names a program, the options it refuses, and the options that neutralize its hidden inputs.
A test fails when a listed program's row holds an effect beyond `path-read` and `value` that no refused option covers, or a hidden input that no neutralizing option covers.
The destroy reading and the leak check consume catalog effects directly.

Decided 2026-10-16: an invalid row disables only its program, and the session-start check and each refusal that touches it report the row.

Decided 2026-10-16: a program with no row, an invalid row, or an unknown option is treated by each hook as it treats an unrecognized command today.
No global gate on unknown programs is added.
A program the catalog does not list is reported with a warning at each use on Claude Code and Pi, and counted, with a report file, at session start.

Decided 2026-10-16: every rule that detects a danger matches a program by base name, so `/usr/bin/sudo` and a nix store `sudo` are `sudo`.
The read exemption applies only to a bare name or a path in a trusted system directory.

Decided 2026-10-16: one TOML file per program under `hooks/programs/`, with an alias index, loaded by `program_catalog.py`.

Decided 2026-10-16: an interpreter given no script operand reads its program from standard input, for every interpreter row, not the shells alone.

Decided 2026-10-16: the read list names the wrappers that keep a read beneath them a read: `time`, `timeout`, `stdbuf`, `setsid`, `nice`, and `caffeinate`.
`nohup` is not listed, because it writes `nohup.out`.
`env` is transparent only when its assignments, and any leading assignment before a program, name none of the inner program's hidden inputs, since `env RIPGREP_CONFIG_PATH=<file> rg` turns on `rg`'s configuration.

Decided 2026-10-16: `watch -x`, `node -p`, and `deno eval` are read now, as a `command` operand, inline `code`, and a subcommand whose operand is `code`.

Decided 2026-10-16: `uv run` is a launcher, not an interpreter.

- `uv run <cmd> <args>` is a nested `command`, so `uv run python -c <code>` reaches the `python` row.
- `uv run <script>`, `-s`, and `--gui-script` take a `path-run` operand.
- `uv run -` reads a Python program from standard input (`uv help run`, uv 0.13.1).
- `uv run -m <module>` is `code` of unknown text, since no file names the module.
- `--with`, `--with-requirements`, `--index`, and `--find-links` take values that choose the packages installed.
- Before it runs, `uv run` syncs the project environment: it writes `.venv` and `uv.lock`, and building a package from source runs that package's build code.
  These are `implicit-effects`.
  `pyproject.toml`, `uv.toml`, inline script metadata, `--env-file` files, and `UV_*` variables are `hidden-inputs`.
  `uv sync`, `uv add`, and `uv pip install` carry the same implicit effects.
- `uvx <name> <args>` and `uv tool run <name> <args>` read as the nested command `<name>`, through `<name>`'s own row.
  `--from` with a URL or a git source, and `--with`, make the code that runs arbitrary, so they read as `unknown`.
- `uvx <name>` keeps `uv`'s install effects whether or not `<name>` has a row.
  A `uvx` tool with no row is unrecognized and reported as uncataloged; tools agents run often, such as `ruff` and `pre-commit`, get rows in the first audit batch, as `uv` does.

## Inconsistencies the catalog resolves

Each item was verified on 2026-10-16 against commit `b5817eb` with a scratch script importing the hook modules.

- `env sudo rm -rf <dir>`: `invoked` returns `rm`; `destroyed_operands` returns nothing, because it strips one privilege wrapper and one execution wrapper instead of repeating.
- `sudo --user root <cmd>` and `sudo -nu root <cmd>`: `invoked` returns `root` as the program.
  The privilege table lists only short value options, and the walker does not read a value letter inside a cluster.
- `sudo --us root <cmd>`: `--us` is a unique prefix of `--user` under getopt_long; `invoked` returns `root`.
  Under the catalog the abbreviation ends the reading, and `sudo` is still refused as the program.
  Whether sudo accepts the prefix is unverified: `block-dangerous-bash.sh` refuses the agent's probe, a `sudo` call with a shortened `--version`.
- `env -S '<cmd> <args>'`: the quoted string becomes the program name.
- `caffeinate -ims rm -rf <dir>`: `invoked` returns `caffeinate`, and no destroy is read.
- `rm -- -precious`: no destroyed operand, because `_operands` drops every word that starts with `-`.
- `doas -a <style> <cmd>`: `<style>` becomes the program name.
- Three wrapper lists disagree on transparency: `READ_WRAPPERS`, the wrapper set in `invocation`, and `shell_words.command_position`.
- One `INLINE_CODE_OPTIONS` set serves every interpreter: `bash -e <script>` is read as inline code whose text is the path, and `python3 -e x` as code though python has no `-e`.
- `reads_stdin_program` covers the shells only.
- `node -p <code>` and `deno eval <code>` yield no program text.
- `watch -x <cmd> <args>` is joined as `sh -c` text though `-x` runs argv.
- `uv run --with x python -c <code>` is read because the interpreter scan finds `-c` anywhere, not because `uv run` is read as a launcher.
- `block-leaks.py` `_subcommand_words` and `bash_commands._after_options` walk options the same way with separate value-option sets, and `block-leaks.py` holds the `op` and `kubectl` grammar beside its policy.
- `block-sensitive-paths.py` `_write_words` drops every word that starts with `-` and takes the last word as the destination of `cp`, `mv`, and `install`, so `cp -t <dest> <src>` names `<src>`.
- `block-dangerous-bash.sh` matches `sudo` and `su` by text at the start of a command, so `env sudo`, `/usr/bin/sudo`, and `doas` pass.
  A later program rule over the walker resolves it.
