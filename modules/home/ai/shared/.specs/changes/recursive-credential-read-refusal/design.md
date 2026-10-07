# Design: recursive-credential-read-refusal

## Context

`block-sensitive-paths.py` judges the words a Bash command names.
It reads each word through `shell_words`, resolves it, and refuses a word that reaches a block-class declaration or matches a name rule.
A recursive read names a directory, and the credential beneath it is never a word, so no check reaches it.

`block-hook-tampering.py` already judges what an operation reaches beneath its operands.
Its ancestor gate refuses a destroy, replace, or mode change on a directory that holds a declaration, using a per-program operand table in `bash_commands.py` (`_OPERAND_EXTRACTORS`) and helpers for `find`, `tar`, and copy destinations.
`test_ancestor_tree_properties.py` checks that table against real commands on a temporary tree.

`test_credential_read_properties.py` does the same for reads: it plants credentials that hold a marker and fails when an allowed command prints one.
It found this gap.

The block class declares five paths today: `~/.claude.json`, `~/.claude/.credentials.json`, `~/.codex/auth.json`, `~/.pi/agent/auth.json`, and `~/.config/mcp-secrets.env`.

A review in debate with a second agent (Codex, GPT-6.1-Sol) on 2026-10-03 changed four decisions in the first draft: the hidden-entry exemption for `rg` and `ag` is gone, existence no longer matters, both sides of the path comparison are spelled out, and the search retry form forbids reaching the credential by another route.

## Decisions

### Decision: ARecursiveReaderTableBesideTheOperandTable

**Chosen:** a `_RECURSIVE_READERS` table in `bash_commands.py`, mapping each program to a function that returns the roots it reads recursively, or nothing when the command is not in a recursive form.
`bash_commands.recursive_roots(segment, directory)` reads it.

| Program                  | Recursive when                                                                              | Roots                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `grep`, `egrep`, `fgrep` | `-r`, `-R`, `--recursive`, `--dereference-recursive`, `-d recurse`, `--directories=recurse` | operands after the pattern, or the current directory                                            |
| `rg`, `ag`               | always, except a name-listing mode                                                          | operands after the pattern, or the current directory                                            |
| `find`                   | `-exec`, `-execdir`, `-ok`, or `-okdir` running a program in `READ_CMDS`                    | the `find` roots                                                                                |
| `tar`                    | `-c`, `-r`, `-u`, their long forms, or a bundled first word (`tar cf`)                      | the operands that are not the archive, each against the directory the last `-C` before it names |
| `cp`, `scp`              | `-r`, `-R`, `-a`, `--recursive`, `--archive`                                                | the source operands, with `-t` and `--target-directory` taken as the destination                |
| `rsync`                  | `-r`, `-a`, `--recursive`, `--archive`                                                      | the source operands                                                                             |
| `zip`                    | `-r`, `--recurse-paths`                                                                     | the operands after the archive                                                                  |
| `ditto`                  | always                                                                                      | the source operands                                                                             |

The name-listing modes are `rg --files`, `rg --type-list`, `ag -g`, `ag --list-file-types`.
`rg -l` and `grep -rl` are not name-listing modes: with a pattern, the names they print reveal content.

Option parsing handles each of the following, with a verdict case for each: an option that takes a value, given separately or attached; a short-option cluster; a repeated flag; `--` ending options; a pattern given by `-e` or `-f`, which makes the first operand a root.
The extractors reuse `_operands`, `_option_value`, `_find_roots`, `_destination`, and the `tar` helpers, and extend `_operands` where it keeps a separate option value as an operand.

**Rationale:** the two tables answer the same question for two effects: which directories an operation reaches beneath.
Keeping them in one module keeps the lexer reading, the privilege stripping (`sudo`, `doas`), and the operand parsing shared.

**Alternatives considered:**

- One table for both effects: a program that destroys beneath its operand and one that reads beneath it are different sets (`rm -r` destroys and does not print; `grep -r` prints and does not destroy), so a shared table needs two flags per row and serves neither reader.
- A table in `block-sensitive-paths.py`: the operand helpers are private to `bash_commands.py`, and a copy of them would drift.

### Decision: TheCheckLivesInTheReadHook

**Chosen:** `block-sensitive-paths.py` refuses, after its existing word checks, for each segment whose `recursive_roots` are not empty.

**Rationale:** the refusal is a read refusal of the block class, which is this hook's capability.
The tamper hook gates the block class for writes and runs, and adding reads there would split one capability across two hooks.

**Alternatives considered:**

- The tamper hook: it already walks ancestors, but its ancestor gate is about taking a directory away, and reads beneath an ancestor are what that gate leaves unprompted by decision.

### Decision: EveryDeclarationCounts

**Chosen:** every block-class declaration counts whether or not a file exists at its path.

**Rationale:** a pre-command existence check misses a credential the same command creates (`codex login && grep -r x ~`), and `os.path.lexists` returns false when inspection fails, which conflates "absent" with "could not look".
Without the check, the rule has no race and no inspection error.

**Alternatives considered:**

- Count only existing declarations: avoids refusing a user who has no Pi over `~/.pi/agent/auth.json`, at the cost of the race and the inspection case.
  Home-wide reads are refused anyway while any credential exists, so the gain is small.

### Decision: BothSidesAreComparedThroughEverySpelling

**Chosen:** a root reaches a declaration when any spelling of the root is the declaration or a directory above it, comparing against every spelling of the declaration.
Spellings come from `guarded_paths.spellings`, which covers the written path, each link hop, the resolved path, and letter case on a volume that ignores it.

**Rationale:** resolving only the root misses a declaration whose parent is a link: with `~/.config` linked to `/Volumes/config`, a root of `/Volumes/config` must reach `~/.config/mcp-secrets.env`.
The spelling machinery already makes this comparison for every other path check, so one rule governs all of them.

**Alternatives considered:**

- `os.path.realpath` on the root alone: misses a linked declaration parent.

### Decision: RipgrepIsJudgedLikeGrep

**Chosen:** `rg` and `ag` are recursive readers in every mode except name listing, with no exemption for hidden entries.
`rg foo ~` is refused.

**Rationale:** both readers skip hidden entries by default, but a probe on 2026-10-03 showed two common ways past that: `rg -g '**' TOKEN .` searched `.codex/auth.json`, and an ignore-file whitelist (`!.codex/`) did the same with no flag at all.
Ignore files can sit in the root, in any directory above it, in `.git/info/exclude`, and in the global excludes file, so the hook cannot see them all without reading the tree.

**Alternatives considered:**

- Skip a declaration with a hidden component below the root: unsound, by the probe above.
- Trust only the fixed form `rg --no-config --no-ignore --no-ignore-files --no-hidden -- PATTERN ROOT...`, which disables configuration, ignore files, and globs: sound, but a form no agent writes unprompted.
  It can be added later as a tested exception if refused home-wide searches prove costly.

### Decision: SelectionFlagsAreNotRead

**Chosen:** `--exclude`, `--exclude-dir`, `--include`, `--glob`, `-g`, `--type`, ignore files, and `find` tests are not parsed.
A root above a declaration is refused whatever they select.

**Rationale:** each reader has its own pattern language, and a hook that judged them would need a matcher per reader that agrees with the reader's own.
A wrong match in that matcher exposes a credential.
The refusal message says that an exclude flag does not change the verdict, so an agent does not retry with one.

### Decision: TheRetryFormStatesItsOwnCause

**Chosen:** `hook_response` gains an `Instruction.SEARCH` text for the search retry form, beside `STOP` and `RETRY`, and the four reporting points stay one shared string.
The human explanation labels the path `Protected file:`, which the instruction quotes.
The instruction forbids reaching the refused credential by another command, link, copy, or equivalent read, and does not permit retrying an operation another layer denied.

**Rationale:** `BlockAIGuidance` decides the form by whether the message names an accepted alternative.
The search refusal names one, so it is a retry form; its cause is not the classifier's, so its opening sentence differs.
The north star allows no layer to offer a workaround for another, so the narrower search is stated as a different operation that abandons the credential, and the prohibition is explicit.

**Alternatives considered:**

- The stop form: it forbids the narrower search the refusal exists to direct the agent to.
- The existing retry text: it tells the agent that reading is allowed and writing needs approval, which is false for this refusal.
- A third form: adds a branch to the decision rule for no difference in what the agent does.

## Architecture

```text
Bash payload
    │
    ▼
block-sensitive-paths.py
    │  shell_words.lex(command, cwd)  ── segments, with every directory each may run in
    │
    ├─ word checks (existing): a named word reaching the block class or a name rule  → refuse, stop form
    │
    └─ for each segment, for each directory it may run in:
         bash_commands.recursive_roots(segment, directory)
             │  _RECURSIVE_READERS[program](segment) → roots, or none
             ▼
         for each root and each block-class declaration:
             any spelling of the root at or above any spelling of the declaration?
             ▼
         refuse: message names the declaration under "Protected file:",
                 closes with Instruction.SEARCH
```

## Risks

- **The table goes stale as readers are added.**
  `test_credential_read_properties.py` runs commands from a catalog kept apart from the table, which is sampled coverage, not proof of completeness.
  The verdict cases pin each reader and root form the table states.
  A reader nobody adds to either stays a stated limit.
- **Home-wide searches are refused.**
  `grep -r TODO ~`, `rg foo ~`, and `tar -czf backup.tgz ~` are refused.
  The message directs the agent to roots that hold no declared credential.
- **A link beneath the root reaches a credential.**
  `grep -R` follows links, and a link beneath the root can point at a declared file.
  `BashReadBestEffort` names a link beneath a recursive read's root, and the sandbox floor is the boundary.
- **The `find -exec` rule depends on `READ_CMDS`.**
  A reader missing from `READ_CMDS` run through `find -exec` is not refused.
  The read property's catalog includes `find -exec` with readers outside that set.
- **The directory a reader runs in can be ambiguous.**
  After `cd X ||` or a subshell, the reader may run in more than one directory.
  This change judges every candidate the lexer reports, and depends on the `cd` tracking `security-posture-alignment` moves into `shell_words` to report them.
