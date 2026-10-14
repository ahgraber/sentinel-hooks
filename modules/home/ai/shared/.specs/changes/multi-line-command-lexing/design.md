# Design: multi-line-command-lexing

## Context

`shell_words.py` reads Bash command text for every path-judging hook.
`_lex` returns no reading for any command holding a newline, a carriage return, or a null byte.
Within a line, `_split_words` already tracks single and double quotes, backslash escapes, `$(…)` through `_substitution_end`, and a word-initial `#`, at which it stops reading the command.
`bash_commands.py` classifies the lexer's segments: `read_only` admits a segment, `program_text` collects inline code handed to an interpreter, `_builder` marks a segment that runs text it cannot see, and `piped_programs` collects text `echo` or `printf` pipes into a shell.

Both hooks fall back when the lexer returns nothing.
`block-hook-tampering.py` gates the command if its text mentions a guarded location.
`block-sensitive-paths.py` judges each piece of the text between shell syntax by the strong rules, with no placeholder exemption.
It judges each piece separately because the rules match only at the end of a name.
A rule applied to multi-line text as a whole matches only on the last line.

This change depends on `guarded-path-classes` and `security-posture-alignment`, which own the current `shell-lexing` text, `UnrecognizedCommandsAreGated`, and both fallbacks, and must sync first.

Two decisions in `guarded-path-classes` bound this one.
`TheLexerIsWrittenRatherThanTakenFromAPackage` keeps the lexer in this module, with `dependencies = []` in both hooks, and rejected `tree-sitter-bash` and `bashlex` for what they cost a hook and for leaving word resolution here.
`BashIsTheReferenceShell` makes bash the reference: Claude is pinned to the nix-darwin bash, Codex runs `bash -lc`, and `shellprobe` runs generated commands through bash with every program replaced by a recorder, so the differential property `test_bash_runs_only_the_words_the_lexer_handed` holds the lexer to what bash hands each program.
A survey of shell parsers and agent guard products on 2026-10-05 found no tool that answers which files a command reads, writes, or runs, so only the syntax layer was ever a candidate for a package.

## Decisions

### Decision: NewlinesAreReadInTheTokenizer

**Chosen:** `_split_words` reads newlines, line continuations, comments across lines, and here-document bodies in the one pass that already tracks quotes.
A newline that ends a command becomes a `;` operator token.
A newline after `|`, `&&`, `||`, or a list-opening reserved word is skipped as whitespace.
A here-document body becomes one token, attached after the operator's line is read.

**Rationale:** whether a newline separates, joins, or belongs to a word depends on the quote and substitution state the tokenizer already holds.
A pre-pass that rewrote newlines to `;` would need its own copy of that state, and two copies of quote tracking drift; the lexer exists so that every hook shares one reading.
Emitting `;` keeps every consumer of segments unchanged, so a multi-line command reaches the code paths its one-line form already exercises.

**Alternatives considered:**

- A pre-pass that joins continuations and splits lines, then lexes each line: duplicates quote tracking, and cannot place a here-document body, which spans lines the pre-pass would split.
- Adopt `tree-sitter-bash` for the syntax layer now that the lexer must read newlines and here-documents, which it parses natively: `TheLexerIsWrittenRatherThanTakenFromAPackage` rejected it for two dependencies in hooks that declare none and about 40 ms per process, and those costs have not changed.
  `lex(command, cwd)` stays the boundary, so the package can still replace `_split_words` later against the same differential property.
- `bashlex`: rejected by the same decision, and the survey found it raises on `$((…))`, `[[ ]]`, and `case`.

### Decision: TheNewlineRulesFollowBashInOrder

**Chosen:** the tokenizer applies the rules in bash's order.
A backslash before a newline, outside single quotes and outside a comment, is removed first.
A word-initial `#` then starts a comment that runs to the next newline; a backslash inside it continues nothing.
A newline inside quotes, `$(…)`, `${…}`, or backquotes is a character of the word.
A newline after an operator or a list-opening reserved word is whitespace.
Any other unquoted newline ends the command.

**Rationale:** bash 5.3.9 shows the order matters: `a\` followed by a line `#x` is the one word `a#x`, and a comment ending in `\` does not swallow the next line.
`if true; then; echo a; fi` is a syntax error, so a newline after `then` is not a `;`; reading it as one would hand `cat` to a rule as a command word in a multi-line form whose one-line form makes `then` the command word, and the multi-line form would read more permissively.
Backquotes are not tracked today; a newline inside them is the case that needs them tracked, and they become unresolvable as before.

**Alternatives considered:**

- Treat every unquoted newline as `;`: the simple rule, and wrong after `then`, `do`, `else`, `|`, `&&`, and `||`.

### Decision: AHereDocumentIsDataOnlyForNamedReaders

**Chosen:** a here-document body is data only where the command that reads it is a recognized read (`read_only`) or one of four named sinks: `git commit` or `git tag` with `-F -` or `--file=-`, `gh` with `--body-file -`, and `tee`.
The sinks live in `bash_commands.py` beside `READ_ONLY_UTILITIES`.
Every other reader's body is program text: the classifier adds it to the text it already scans for guarded and block paths, as it does text `echo` pipes into a shell, and the command is not recognized.
`block-sensitive-paths.py` judges a program body piece by piece by the strong rules, as it judges text it cannot lex.
A git alias is not a sink.

**Rationale:** the hazard is any program whose effects only the body names, not only shells.
A Fable review on 2026-10-08 showed `xargs`, `sudo sh`, `source /dev/stdin`, `awk -f -`, `sed -f -`, `sqlite3`, `git apply`, `patch`, `crontab -`, `osascript`, and `docker exec -i … sh` each act on input; with a body treated as data, `xargs rm <<EOF` naming a guarded path passed the classifier.
An allowlist refuses what it does not know, which is the rule `ReadClassifierAdmitsOnlySelfDescribingUtilities` applies to utilities.
A count of the 500 here-documents agents sent in the 30 days to 2026-10-08 found 314 read by `cat` writing a file and 176 by `python`, `python3`, or `uv`; the 15 program bodies naming a guarded path are gated today as multi-line commands, so the allowlist adds no refusal.
The user chose generic sinks on 2026-10-08: `git agent-commit` is a git alias, and an alias can run a shell, so the hook cannot know what it does.

**Alternatives considered:**

- Treat a body as program text only for shells and interpreters, from `INTERPRETERS`: misses every program above, and that list answers which programs take inline code, not which run their standard input.
- Name `git agent-commit` as a sink: lets two commits a month proceed, at the cost of trusting an alias whose meaning lives outside the repository.

### Decision: AnExpandedBodyIsUnresolvable

**Chosen:** a body under an unquoted delimiter that holds `$` or a backquote is unresolvable, and a delimiter that is itself expanded makes the command unresolvable.

**Rationale:** bash expands parameters, command substitutions, and arithmetic in such a body before the command starts, so the body runs code whatever reads it.
Treating any `$` as an expansion over-refuses a body holding a literal dollar; a narrower test would have to reimplement bash's expansion rules.
Only 3 of the 500 here-documents counted had an unquoted delimiter, so the over-refusal has little to reach.

### Decision: TheFallbacksStayForUnreadableText

**Chosen:** both fallbacks stay, and apply only where the lexer still returns no reading: an unclosed quote, an unterminated here-document, a carriage return, a null byte, or syntax the lexer cannot read on one line.

**Rationale:** the lexer's reach grows, but text it cannot read still reaches the hooks, and a hook that cannot read a command must still refuse what the text names.

## Architecture

```text
command text
    │
    ▼
shell_words._split_words ── quotes, $(…), continuation, comments,
    │                        newline → ";" or whitespace, here-document body
    ▼
shell_words._lex ────────── segments with word kinds; "here-document" kind
    │
    ├──► bash_commands.read ─ read_only, program_text (+ program bodies),
    │        │                 builder, the data sinks
    │        ▼
    │    block-hook-tampering.py ── classify; gate a guarded write or an
    │                               unrecognized command naming a guarded path
    │
    └──► block-sensitive-paths.py ─ judge read and write words; judge a
                                     program body piece by piece
```

## Risks

- **A lexer change reaches every path-judging hook.**
  Mitigation: a property test that a command and its multi-line form, built by inserting newlines where bash reads them as whitespace or `;`, lex to the same segments and words.
  The existing differential property, `test_bash_runs_only_the_words_the_lexer_handed`, gains generators for newlines, continuations, comments, and here-documents, so `shellprobe` holds every new form to what bash hands each program.
  `shellprobe` records argv, not standard input, so a here-document body's content needs a recorder that also saves its input.
- **A program the sink list should include is missing.**
  The cost is a gate or refusal where a body names a guarded or secret-looking path, the same verdict every multi-line command reaches today.
- **`single-command-rule-engine` keeps its quote-splice rewrite for newline commands.**
  If this change lands first, that change can read every command through the lexer; the order is an open question in the proposal.
