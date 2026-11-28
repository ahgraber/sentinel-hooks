# Proposal: single-command-rule-engine

## Intent

Two hooks judge a Bash command by matching patterns against its text, and each has its own engine.
`block-destructive-ops.py` reads its rules from a TOML file and matches them in Python.
`block-dangerous-bash.sh` declares its rules in shell arrays and starts a Perl process for each one.
Both rewrite the command before matching to undo quote splices, and the two rewrites are the same algorithm in two languages.

Neither rewrite undoes a backslash escape or an ANSI-C string, so a rule written for a command name does not hold against those spellings.
On 2026-10-05 both hooks allowed:

- `\r\m -r <dir>` and `$'\x72m' -r <dir>`, which `block-destructive-ops.py` asks about when spelled `rm -r <dir>`
- `c\url <url> | s\h` and `$'\x63url' <url> | sh`, which `block-dangerous-bash.sh` refuses when spelled `curl <url> | sh`
- `$'\x70bpaste'`, which it refuses when spelled `pbpaste`

The shared lexer `shell_words` already resolves both spellings for the path hooks.
The command hooks do not use it.

The shell hook is also the slowest of the seven hooks a Bash call runs, at 150 ms, because of the Perl process per rule.

## User Stories

- **a-command-rule-holds-for-every-spelling** — As the operator of four agents, I want a dangerous or destructive command to be refused or put to me however its name is spelled, so that a rule written once holds against escaped and encoded spellings of the same command.
  (North star: "a denial from any layer is final"; a denial that a backslash undoes is not final.)
- **one-engine-judges-every-command-rule** — As the maintainer of these guardrails, I want every command-pattern rule to be data judged by one engine, so that a fix to how a command is read reaches every rule, and the engine can be reimplemented in another language without rewriting the rules.
  (North star: "the policy is written once"; today the reading step is written twice and is wrong the same way in both.)

## Scope

**In scope:**

- `command-rule-engine` (new capability): one engine judges every command-pattern rule.
  It loads rules from declared rule files, validates them, matches each rule against every spelling of the command, applies a rule's loopback exemption, and reaches the rule's outcome.
  The spellings are the command as written and one rewritten copy: the lexer's reading when the command has no newline, and the quote-splice rewrite when it has one.
  The contract names no implementation language.
- `dangerous-bash-blocking`: its rules become data the engine judges.
  The shell `rule()` registration requirement is removed, and the outcome requirements stay as they are.
  The rules keep their own stop instruction, which `security-posture-alignment` recorded as theirs.
- `destructive-ops-blocking`: the pattern-file and validation contract moves to the engine; the rule catalog and modes stay.
- `session-tool-checks`: `perl` is no longer required.
- `bash-command-validator`: `ReviewHeredocsForBangHistory` matches here-document syntax, not a `<<` inside quotes, with a new `QuotedHereDocumentOperatorAllowed` scenario.
  The validator also starts Perl for every rule, so `perl` stays required until its rules move to the engine or to another matcher.
- Retiring `block-dangerous-bash.sh`, and updating every registration that names it: the Claude, Codex, and Copilot configurations, the Copilot adapter, and the Pi dispatcher.
- Verdict cases for each rule family over the plain, quote-spliced, backslash-escaped, and ANSI-C spellings, run against the engine.

**Out of scope:**

- A command name held in a variable, such as `x=rm; $x -r <dir>`.
  The lexer marks the word unresolvable; treating every unresolvable command name as suspect is a separate decision.
- `block-leaks.py`.
  Its checks are about network destinations, credential stores, and literal secrets in the text, which the lexer does not judge.
- Resolving brace expansions, which the lexer does not do.
- Changing what any rule refuses or asks about when the command is spelled plainly.
- A port to another language.
  The contract permits one; this change does not make one.

## Approach

- The engine reads one rule file format.
  Each rule carries its pattern, mode, description, reason, case sensitivity, and an optional loopback exemption (`devtcp`, `nc`, or `generic`, as the shell hook names them today).
- The engine builds the spellings once per call, then matches every rule against each.
  A `block` match outranks an `ask` match, as `block-destructive-ops.py` does today.
- The lexer's reading is rendered as text for the patterns to match: each segment's resolved words joined by spaces, with the separator between segments.
  Patterns written against the raw text, such as `curl … | sh`, then match the rendered copy unchanged.
- The rendering is new code beside the lexer; the lexer itself does not change.
- Rule outcomes keep their messages.
  The dangerous-command rules keep their stop instruction; the destructive-operation rules keep theirs.
- Python's `re` and Perl's PCRE differ at the edges, so each moved pattern is checked against the shell hook's verdicts before the shell hook is removed.

## Dependencies

- `security-posture-alignment` must sync first.
  It modifies `ExternalPatternFile` and `ErrorHandlingByDamagePotential`, which this change builds on.

## Notes for implementation

- The registrations that name either hook are `plugins/sentinel/harnesses/claude/hooks.json`, `plugins/sentinel/harnesses/codex/hooks.json`, `plugins/sentinel/com.github.copilot/hooks/hooks.json`, `plugins/sentinel/harnesses/copilot/copilot-vscode-hook-adapter.py` (its `HOOK_SCOPES` table), `plugins/sentinel/harnesses/pi/hooks.json`, and `plugins/sentinel/harnesses/pi/hook-dispatch.py`.
  The agent sandbox denies writes to the Claude settings files, so the user commits any change that touches them.
- The lexer refuses every command that holds a newline, including a backslash line continuation.
  The quote-splice rewrite is therefore kept for those commands, not deleted.
- A Bash command that spells a probe such as `c\url <url> | s\h` inline is judged by the live hooks of the agent running it.
  Write probe payloads to a file and pass the file to the hook under test.
- `credential-store-handoff` exports the program-reading helpers this engine's rendering needs: `bash_commands.invoked` (the program past `sudo`, `doas`, `env`, `nohup`, `timeout`, `exec`, `command`, and assignments, in any order), `program_text` (inline code, including `bash -lc` and `su -c`), `launched_arguments` (`xargs`, `find -exec`), `watch_script`, and `reads_stdin_program` (including `sudo -s`, `sudo -i`, `doas -s`, and `su` with no `-c`).
  Rendering each segment from `invoked` instead of from the raw words makes a rule written for a program name hold through every wrapper.
- A probe of the live hooks on 2026-10-16 found `block-dangerous-bash.sh` allows `/usr/bin/sudo …`, `command sudo …`, `sudo …` preceded by spaces, `\sudo …`, `env sudo …`, `nohup sudo …`, `timeout 5 sudo …`, `exec sudo …`, and `doas …`; it refuses `sudo …`, `'sudo' …`, `sudo -u root -- …`, and `su -c …`.
  The same hook refused a `grep` whose pattern held `sudo -s`, because it matches the text anywhere rather than the program a segment runs.
- `bash-command-validator.sh` matches its here-document rule, `(?<!<)<<[^<]`, against the raw command, so on 2026-10-25 it refused `grep -n "heredoc\|<<\|newline" <file>`, which holds no here-document.
  Tasks: a failing test in `claude/tests/test_bash_command_validator.py` that a command whose only `<<` is quoted (`grep -n '<<' file`, `grep -e "<<-" file`) exits 0, and that an unquoted here-document, one after a quoted `<<` included, still exits 2; the `bash-command-validator` delta; then the fix.
  The rendered reading resolves quotes, so a quoted `<<` renders as a bare `<<` and the same pattern would still match it.
  The fix reads the lexer's `here-document` word kind instead; if the validator stays a shell hook, its existing `rule_command` subject, which strips quoted spans, is the smaller fix and misses `$'…'` and escaped quotes.
- The `security-posture-alignment` audit ledger, `.simplify/ledger-2026-10-05-2343.md` (untracked), counts the blast radius of adopting the lexer in `block-destructive-ops.py`, and names the tests that pin the current rewrite: `TestNormalize`, `test_obfuscated_command_still_blocks`, `test_multiword_rule_is_not_assembled_across_arguments`, and `TestCatalogueNormalizationParity` in `claude/tests/test_block_destructive_ops.py`.

## Open Questions

- One hook or two entry points over one engine.
  One hook saves a process on every Bash call; two keep the registrations and test files as they are.
  If one, `block-destructive-ops` no longer describes reverse shells and clipboard reads, so it would need a new name.
- Whether a command rule matches the program each segment invokes, not only its spelling.
  `dangerous-bash-blocking` `SudoCommand` refuses `sudo` "at the start of a command or after a command separator", which by its own wording excludes a leading space, a full path, and a wrapper (`env sudo`, `command sudo`, `nohup sudo`).
  Matching the invoked program covers those, and the spelling cases this change already targets, with one rendering.
  The same question decides whether `doas` joins `sudo` and `su` in the privilege-escalation rule, and whether a pattern that appears only inside a quoted argument (a `grep` pattern, a commit message) stops matching.
  `program-semantics-table` answers the privilege half (decided with the user on 2026-10-16): it modifies `dangerous-bash-blocking` `BlockPrivilegeEscalation` so that a Python hook refuses every command whose reading invokes a program with a privilege effect, at any nesting depth, by base name (`/usr/bin/sudo`, a nix store `sudo`, `doas`, `pkexec`, `run0`, and the rest of its catalog).
  `block-dangerous-bash.sh` keeps its text match as a backstop.
  This change then decides only whether the remaining command rules match the invoked program; it does not need its own catalog-based privilege rule.
  It does own the text backstop if it retires `block-dangerous-bash.sh`: the text match of `sudo` and `su` at the start of a command or after a command separator moves into its engine unchanged, in either landing order, until a later change removes it on purpose.
  `program-semantics-table` also replaces `invoked`, `program_text`, `launched_arguments`, `watch_script`, and `reads_stdin_program` with one walker over a program catalog; whichever change lands second renders segments from what the other left in place.
