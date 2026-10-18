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

**Chosen:** `_split_words` reads newlines, comments across lines, and here-document bodies in the one pass that already tracks quotes.
A newline that ends a command becomes a `;` operator token.
A newline after `|`, `&&`, `||`, `;`, or `&` is skipped as whitespace.
A here-document body becomes one token, attached after the operator's line is read.
`UnreadFormsFallBackUntilEachGapCloses` sets which multi-line forms the tokenizer reads today.

**Rationale:** whether a newline separates, joins, or belongs to a word depends on the quote and substitution state the tokenizer already holds.
A pre-pass that rewrote newlines to `;` would need its own copy of that state, and two copies of quote tracking drift; the lexer exists so that every hook shares one reading.
Emitting `;` keeps every consumer of segments unchanged, so a multi-line command reaches the code paths its one-line form already exercises.

**Alternatives considered:**

- A pre-pass that joins continuations and splits lines, then lexes each line: duplicates quote tracking, and cannot place a here-document body, which spans lines the pre-pass would split.
- Adopt `tree-sitter-bash` for the syntax layer now that the lexer must read newlines and here-documents, which it parses natively: `TheLexerIsWrittenRatherThanTakenFromAPackage` rejected it for two dependencies in hooks that declare none and about 40 ms per process, and those costs have not changed.
  `lex(command, cwd)` stays the boundary, so the package can still replace `_split_words` later against the same differential property.
- `bashlex`: rejected by the same decision, and the survey found it raises on `$((…))`, `[[ ]]`, and `case`.

### Decision: UnreadFormsFallBackUntilEachGapCloses

**Chosen:** the requirements state what bash reads.
The tokenizer reads a multi-line command today only when it is plain: commands joined by newlines and list operators, with comments, quoted newlines in single quotes or in double quotes that hold no substitution, and here-documents.
A newline after `|`, `&&`, `||`, `;`, or `&` is whitespace, and any other unquoted newline ends the command.
A multi-line command that holds a line continuation, a `(` operator, or an unquoted reserved word in command position has no reading, so the hooks judge its whole text.
A substitution ends where bash ends it: `_expansion_end` matches quotes, comments, and nesting inside `$(…)`, `${…}`, and backquotes, and refuses one holding a here-document or a `case` pattern.
Command position is tracked in the tokenizer: the first word, or the first word after a control operator; an assignment or a redirection before a word takes the position, as in bash.
Each form the tokenizer does not read as bash does is a gap, with a task to close it and a strict expected-failure test that states bash's reading.
The tests that each such form has no reading stay until its gap closes, because they hold the fallback that keeps the gap from hiding a command.

**Rationale:** the first implementation read every multi-line form, following bash's rules in order.
A review on 2026-10-15, by Codex and two Opus agents and confirmed against bash 5.3.9, found five forms it read more permissively than bash:

- `echo if then` followed by a command made the newline after `then` whitespace, because the test for command position looked only at the previous word.
- A continuation inside `&&` split it into two `&`.
- `_substitution_end` treats a `'` in a comment or a here-document inside `$(…)` as a quote, so it read past the real `)`.
- A backquote inside double quotes ended the quoted word early.
- `((cat<<2))` read the shift as a here-document.

Each needs grammar this lexer does not follow: compound commands, operators split by continuations, and the inside of a substitution.
On 2026-10-15 the user accepted these as gaps and allowed the work to reach bash's reading in steps, provided no step weakens the posture.
The first step gives each such form no reading, so the hooks judge its whole text as they judged every multi-line command before this change; this is the implementation's interim fallback, not the scope of the change.
A verification on 2026-10-17 found a sixth: bash reads quotes inside a `${…}` within double quotes, and the lexer ended the word at the first `"`, so a later `'` hid the next line.
The same step gives no reading to any such `${…}` across lines until the lexer reads quotes inside it.
A leading `${HOME}` stays read, because the lexer resolves it to the home directory before it scans the quoted text, and it holds no quote.
Without reserved words and parentheses, nothing but a list operator puts a word in command position, so the command-position test misses no reserved word bash reads.
An assignment or a redirection takes command position too, so in `X=1 if` the test, like bash, reads `if` as the name of a program.
The forms left out reach the fallbacks, as every multi-line command did before this change.
The 2026-10-15 and 2026-10-17 spec edits wrote this interim fallback into the requirements, so lexer defects became specified behavior.
On 2026-10-18 the user restored the requirement that the hooks read commands as bash does; the fallback stays, and each form it covers is a gap to close.

**Alternatives considered:**

- Fix each divergence and read every form: more of the 1,906 multi-line commands proceed, and each fix extends grammar the lexer reads on no other path, where the review found the divergences.
- Refuse a reserved word in any position: simpler, and leaves `echo done`, which agents end scripts with, without a reading.

### Decision: AHereDocumentIsDataOnlyForNamedReaders

**Chosen:** a here-document body is data only where its reader is a recognized read or one of four named sinks.
The implementation admits only `cat` with no word but its redirections among the recognized reads; the rest is the gap `HereDocumentReadByARecognizedRead`.
The named sinks are `git commit` or `git tag` with `-F -` or `--file=-` and no `-c`, `-e`, or `--edit`, `gh pr` or `gh issue` with `--body-file -`, and `tee`.
The reader is the first word of its segment, with no assignment or wrapper before it, and its segment does not pipe.
`bash_commands.unread_here_document()` applies that test, beside `READ_ONLY_UTILITIES`.
Every other here-document leaves the command with no reading: `bash_commands.read()` reports it as unlexable, and `block-sensitive-paths.py` applies the same test before it judges any word, so both hooks reach their fallbacks.
A git alias is not a sink.

**Rationale:** the hazard is any program whose effects only the body names, not only shells.
A Fable review on 2026-10-08 showed `xargs`, `sudo sh`, `source /dev/stdin`, `awk -f -`, `sed -f -`, `sqlite3`, `git apply`, `patch`, `crontab -`, `osascript`, and `docker exec -i … sh` each act on input; with a body treated as data, `xargs rm <<EOF` naming a guarded path passed the classifier.
An allowlist refuses what it does not know, which is the rule `ReadClassifierAdmitsOnlySelfDescribingUtilities` applies to utilities.
A count of the 500 here-documents agents sent in the 30 days to 2026-10-08 found 314 read by `cat` writing a file and 176 by `python`, `python3`, or `uv`; the 15 program bodies naming a guarded path are gated today as multi-line commands, so the allowlist adds no refusal.
The user chose generic sinks on 2026-10-08: `git agent-commit` is a git alias, and an alias can run a shell, so the hook cannot know what it does.
The first implementation judged a program body as text the classifier scans, and admitted any recognized read and any wrapper or assignment before a sink.
The 2026-10-15 review showed five ways a named reader still runs its input: a pipe into `sh`, `env -S`, `GIT_EDITOR=sh` or `git -c core.editor=sh -e`, a `PATH=` assignment, and a gh alias.
As an interim step on 2026-10-15, the implementation admits only `cat` and the sinks, and every other here-document reaches the fallback, which judges the whole text as before this change.
The fallback meets the requirement that a body read by any other program is judged as program text: the command is not recognized, and a guarded or block path in the body is found.
The conditions on the reader are policy and stay; the restriction of recognized reads to `cat` is a gap.

**Alternatives considered:**

- Keep program bodies as scanned text and add the pipe and sink conditions: two code paths for the same text, where the fallback already judges it.

- Treat a body as program text only for shells and interpreters, from `INTERPRETERS`: misses every program above, and that list answers which programs take inline code, not which run their standard input.

- Name `git agent-commit` as a sink: lets two commits a month proceed, at the cost of trusting an alias whose meaning lives outside the repository.

### Decision: AnExpandedBodyIsUnresolvable

**Chosen:** a body under an unquoted delimiter that holds `$` or a backquote is unresolvable.
The implementation also refuses a delimiter that holds `$` or a backquote, which bash takes literally, and a body with an escape or a continuation; both are gaps.

**Rationale:** bash expands parameters, command substitutions, and arithmetic in such a body before the command starts, so the body runs code whatever reads it.
Treating any `$` as an expansion over-refuses a body holding a literal dollar; a narrower test would have to reimplement bash's expansion rules.
Only 3 of the 500 here-documents counted had an unquoted delimiter, so the over-refusal has little to reach.

### Decision: TheFallbacksStayForUnreadableText

**Chosen:** both fallbacks stay, and apply only where the lexer still returns no reading: an unclosed quote, an unterminated here-document, a here-document no data reader reads, a multi-line form the tokenizer does not yet read, a carriage return, a null byte, or syntax the lexer cannot read on one line.

**Rationale:** the lexer's reach grows, but text it cannot read still reaches the hooks, and a hook that cannot read a command must still refuse what the text names.

## Architecture

```text
command text
    │
    ▼
shell_words._split_words ── quotes, comments, newline → ";" or whitespace,
    │                        here-document body; no reading for a multi-line
    │                        form that is not plain
    ▼
shell_words._lex ────────── segments with word kinds; "here-document" kind
    │
    ├──► bash_commands.read ─ unlexable when unread_here_document(); else
    │        │                 read_only, program_text, builder
    │        ▼
    │    block-hook-tampering.py ── classify; gate a guarded write or an
    │                               unrecognized command naming a guarded path
    │
    └──► block-sensitive-paths.py ─ fallback when unread_here_document();
                                     else judge read and write words
```

## Risks

- **A lexer change reaches every path-judging hook.**
  Mitigation: a property test that plain commands and their multi-line form, built by inserting newlines where bash reads them as whitespace or `;`, lex to the same segments and words.
  The existing differential property, `test_bash_runs_only_the_words_the_lexer_handed`, gains generators for newlines, comments, and here-documents, so `shellprobe` holds every new form to what bash hands each program, standard input included.
  A property test holds that every multi-line form outside the plain set has no reading.
- **A program the sink list should include is missing.**
  The cost is a gate or refusal where a body names a guarded or secret-looking path, the same verdict every multi-line command reaches today.
- **`single-command-rule-engine` keeps its quote-splice rewrite for newline commands.**
  This change lands first, so that change can read every command through the lexer.

## Spec Changes

- 2026-10-13, editorial: commit `fc9e568` rewrote the delta specs and this design in the repository's plain-language style, as part of a pass across every open change.
  It split long sentences and restated each rule in active voice.
  It changed no requirement, scenario outcome, or scope.
  Source: the repository's writing rules, not a decision of this change.
- **Change:** `shell-lexing`, `hook-tampering-blocking`, `sensitive-path-blocking`: read only plain multi-line commands, and read a here-document only where `cat` or a named sink reads it.
  Superseded on 2026-10-18: the user had accepted the forms left out as gaps to close in steps, not as the scope of the change.
  **Source:** `UnreadFormsFallBackUntilEachGapCloses` and `AHereDocumentIsDataOnlyForNamedReaders`.
  **Rationale:** the review of 2026-10-15 found nine forms the first implementation read more permissively than bash, and each needs grammar the lexer does not follow.
  **Approved by user:** 2026-10-15, as an interim step
- **Change:** `shell-lexing` `SegmentsFollowControlOperators`: state that the command-position test over-refuses a reserved word after an assignment or a redirection, as in `X=1 if`, in place of the claim that the test is exact.
  Superseded on 2026-10-18 with the requirement text it amended.
  **Source:** `UnreadFormsFallBackUntilEachGapCloses`, and the verification report of 2026-10-17.
  **Rationale:** bash reads a reserved word only in command position, and an assignment or a redirection before it leaves the word a command name, so the refusal is wider than bash's grammar requires.
  **Approved by user:** 2026-10-17
- **Change:** `hook-tampering-blocking` `UnrecognizedCommandsAreGated`: rebase the delta onto the baseline that `b398eb4` synced, so it keeps the `GateResponse` reason clause, the rule for unknown wrappers, and the `ReasonNamesTheAcceptedForms` wording; mark `ANewlineRefusesTheCommand` as removed in the `shell-lexing` delta.
  **Source:** rebase onto the synced baseline, and the verification report of 2026-10-17.
  **Rationale:** a MODIFIED block holds the complete post-change requirement, so a delta written against an older baseline would drop clauses another change added.
  **Approved by user:** 2026-10-17
- **Change:** `shell-lexing` `SegmentsFollowControlOperators`: add a `${…}` inside double quotes, other than a leading `${HOME}`, to the multi-line forms that have no reading.
  Superseded on 2026-10-18 with the requirement text it amended; the fallback remains as the gap `ParameterExpansionInDoubleQuotesAcrossLines`.
  **Source:** `UnreadFormsFallBackUntilEachGapCloses`, and the verification report of 2026-10-17.
  **Rationale:** bash reads quotes inside such a `${…}`, so a lexer that ends the word at the first `"` can hide the command on the next line.
  **Approved by user:** 2026-10-17
- **Change:** `hook-tampering-blocking` `UnrecognizedCommandsAreGated`: state that the reader conditions close the `PATH=` route only for an assignment in the reader's own segment.
  **Source:** the verification report of 2026-10-17.
  **Rationale:** an `export PATH=` on an earlier line is not read, and the same command on one line proceeds too, so the earlier claim was wider than the rule.
  **Approved by user:** 2026-10-17
- **Change:** `shell-lexing`, `hook-tampering-blocking`, `sensitive-path-blocking`: restore the requirements as approved in the proposal commit, so a command written across lines is judged as bash reads it; keep the here-document reader conditions and the removal marker; record each form the implementation does not read as bash does as a gap, with a task and a strict expected-failure test.
  This supersedes the requirement text of the 2026-10-15 and 2026-10-17 edits, which wrote the interim fallback into the requirements; the fallback remains in the implementation until each gap closes.
  **Source:** the user, 2026-10-18.
  **Rationale:** the narrowing wrote lexer defects into the requirements, so the specs described the defects as correct behavior and no test could show them as defects.
  **Approved by user:** 2026-10-18
- **Change:** `shell-lexing` `SegmentsFollowControlOperators` and `AHereDocumentBodyIsInput`: state the reading as bash's, with bash as the reference shell, instead of restating bash's rules for newlines, continuations, comments, reserved words, and here-document boundaries; keep `APipelineIsSplit` and `AQuotedOperatorDoesNotSplit`, add `AReadingMatchesBash`, `UnreadableTextIsUnresolvable`, and `ABodyIsNotASegment`, and drop the scenarios that restated bash's rules.
  `hook-tampering-blocking` `AMultiLineCommandReachesItsOneLineVerdict` no longer lists the forms of a multi-line command.
  **Source:** the user, 2026-10-18: "the specs should mandate following bash/posix".
  **Rationale:** a restatement of bash's grammar is a second grammar that drifts; the original said `<<$X` expands its delimiter, which bash does not do.
  Specific forms live in the differential property against bash and in the gap tests.
  **Approved by user:** 2026-10-18
