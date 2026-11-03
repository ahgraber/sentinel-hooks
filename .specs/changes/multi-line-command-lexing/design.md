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
The tokenizer reads a multi-line command into the segments bash runs: commands joined by newlines and list operators, with comments, quoted newlines, line continuations, here-documents, substitutions, and compound commands.
A newline after `|`, `&&`, `||`, `;`, or `&` is whitespace, and any other unquoted newline ends the command.
`case`, `function`, and `coproc` read across lines as on one line; a substitution holding a `case` ends at the first `)` before which its text reads as complete commands.
After any other reserved word that leads a command, a newline ends an empty command, which adds no segment, so `if`, `while`, `for`, and `{ … }` read across lines as on one line, and so do subshells and `((…))`, whose `<<` the arithmetic scan reads as a shift.
A line continuation is removed where the tokenizer reaches it, outside single quotes and comments and inside an operator too, so the rest of the scan reads the joined text.
`((…))` and `[[ … ]]` in command position are each one unresolvable word, and so is a word holding an array subscript or value where bash reads one: before the command word, or after an assignment builtin such as `declare`.
A substitution ends where bash ends it: `_expansion_end` matches quotes, comments, here-documents, `case` patterns, and nesting inside `$(…)`, `${…}`, and backquotes.
Command position is tracked in the tokenizer: the first word, or the first word after a control operator; an assignment or a redirection before a word takes the position, as in bash.
Each gap the reviews below found is closed, and its expected-failure test now passes as an ordinary test.
A form the tokenizer does not read, a process substitution, has no reading, which a property test holds, so the fallback keeps it from hiding a command.

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

**Chosen:** a here-document body is data only where its reader is a data reader or one of four named sinks.
A recognized read is a data reader only where it takes only content from its standard input, never file names, arguments, or a program; `DATA_READERS` names those reads, and a recognized read is not one until it is listed.
A recognized read is one `read_only()` admits, judged without the body, which may expand.
A utility that takes the names of the files it reads from a file or its input, such as `sort --files0-from=-` or `file -f -`, is not a recognized read: it reads files its words do not name, here-document or not, so `WRITE_OPTIONS` lists those options.
For the same reason `jq` with `-f`, `--from-file`, `-L`, `--library-path`, or a word holding `import` or `include` is not a recognized read, since its program can then load a module its words do not name, and `strings` with an argument starting with `@` is not one, since it reads further arguments from that file.
The user chose on 2026-10-21 to keep plain `jq` a recognized read, because agents read guarded JSON with it and Codex, which cannot ask, would refuse every such read; a module route those rules miss stays open on one line, and the data-reader list keeps it from hiding in a here-document.
The named sinks are `git commit` or `git tag` with `-F -` or `--file=-` and no `-c`, `-e`, or `--edit`, `gh pr` or `gh issue` with `--body-file -`, and `tee`.
The reader is the first word of its segment, with no assignment or wrapper before it, and its segment does not pipe.
`bash_commands.unread_here_document()` applies that test, beside `DATA_READERS`.
Every other here-document leaves the command with no reading: `bash_commands.read()` reports it as unlexable, and `block-sensitive-paths.py` applies the same test before it judges any word, so both hooks reach their fallbacks.
A git alias is not a sink.

**Rationale:** the hazard is any program whose effects only the body names, not only shells.
A Fable review on 2026-10-08 showed `xargs`, `sudo sh`, `source /dev/stdin`, `awk -f -`, `sed -f -`, `sqlite3`, `git apply`, `patch`, `crontab -`, `osascript`, and `docker exec -i … sh` each act on input; with a body treated as data, `xargs rm <<EOF` naming a guarded path passed the classifier.
An allowlist refuses what it does not know, which is the rule `ReadClassifierAdmitsOnlySelfDescribingUtilities` applies to utilities.
A count of the 500 here-documents agents sent in the 30 days to 2026-10-08 found 314 read by `cat` writing a file and 176 by `python`, `python3`, or `uv`; the 15 program bodies naming a guarded path are gated today as multi-line commands, so the allowlist adds no refusal.
The user chose generic sinks on 2026-10-08: `git agent-commit` is a git alias, and an alias can run a shell, so the hook cannot know what it does.
The first implementation judged a program body as text the classifier scans, and admitted any recognized read and any wrapper or assignment before a sink.
The 2026-10-15 review showed five ways a named reader still runs its input: a pipe into `sh`, `env -S`, `GIT_EDITOR=sh` or `git -c core.editor=sh -e`, a `PATH=` assignment, and a gh alias.
An interim step on 2026-10-15 admitted only `cat` and the sinks, and a later step admitted every recognized read.
Verification twice found a recognized read that takes file names or a program from its input: checksum `-c` on 2026-10-20, and `strings @/dev/stdin` and `jq -f /dev/stdin` on 2026-10-21.
Each was also a one-line gap in the recognized reads, closed there after an audit of every recognized read against the files its words name.
The user chose on 2026-10-21 to name the data readers as well, so a recognized read the audit misses still does not hide a body; every other here-document reaches the fallback, which judges the whole text as before this change.
`grep -f -` and the other pattern options take patterns from the body, which are content: a pattern selects lines and names no file.

Two conditions on the reader follow from what a name and a pipe mean to bash, not from the reader alone.
A reader's output reaches another program through its own `|`, through a compound command around it that is piped, as in `{ cat <<'EOF' … }  | sh`, or as a coprocess, so the lexer marks each segment whose output goes to a pipe and each whose input comes from one, including through every compound around it.
The marks also feed the shell that reads piped text, so `echo … | { true; sh; }` and `{ echo …; } | sh` are judged as `echo … | sh` is.
A reader's name says which program runs only while nothing rebinds it: a function definition, `hash -p`, `alias` with a value, a write to `BASH_CMDS` or `BASH_ALIASES`, and `enable` each change what a name runs, and `eval` and `trap` with code, and `source`, run text the reading cannot see, which may do the same, as may a program the reading cannot name, such as `$E` holding `eval`.
In a command holding any of them, no here-document is data, wherever the rebinding stands: a loop runs a rebinding written after the reader before the reader's next pass, which reviews on 2026-10-23 confirmed against bash.
All but `source` also leave the command unrecognized, as a function definition already left it, so `BASH_CMDS[cat]=/bin/rm; cat <guarded file>` is gated; `alias` and `enable` that only list, and `trap` that lists or resets, rebind nothing.
`source` runs a file the hook cannot see; what the file does on its own is the stated limit for a script a command runs, and it counts here only because it can rebind a here-document's reader.
The lexer decides a function definition once, as a mark on the segment, for `name()` with any name bash accepts and for `function name`; the classifier reads the mark.
An earlier `export PATH=` stays the limit decided on 2026-10-17.
A body a data reader writes to a file that the same command then runs, as in `cat > x.sh <<'EOF'` then `sh x.sh`, is data here, as `echo '…' > x.sh; sh x.sh` is on one line: a hook judges one tool call, so linking the write to the run in one command would miss the same script run in the next call.
The user chose on 2026-10-23 to leave it as a stated limit of this change and to propose `script-content-judging`, which judges a script's text where a command runs it.
The fallback meets the requirement that a body read by any other program is judged as program text: the command is not recognized, and a guarded or block path in the body is found.
The conditions on the reader are policy and stay.

**Alternatives considered:**

- Keep program bodies as scanned text and add the pipe and sink conditions: two code paths for the same text, where the fallback already judges it.

- Treat a body as program text only for shells and interpreters, from `INTERPRETERS`: misses every program above, and that list answers which programs take inline code, not which run their standard input.

- Name `git agent-commit` as a sink: lets two commits a month proceed, at the cost of trusting an alias whose meaning lives outside the repository.

### Decision: AnExpandedBodyIsUnresolvable

**Chosen:** a body under an unquoted delimiter that holds a `$` or a backquote no backslash escapes is unresolvable.
A delimiter is taken after quote removal alone, as bash takes it, so `<<$X` ends at a line reading `$X`.
An unquoted body joins continued lines before the delimiter is matched, and loses only the backslashes before `$`, a backquote, or a backslash.
Where two here-documents feed one descriptor, as in `cat <<A <<B`, the program reads only the last, but bash expands each body under an unquoted delimiter, so a substitution in the first runs.
The lexer keeps every body in the reading: a quoted body is data and changes no verdict, and an expanding body is unresolvable, so the paths written in it are judged.

**Rationale:** bash expands parameters, command substitutions, and arithmetic in such a body before the command starts, so the body runs code whatever reads it.
Treating any `$` as an expansion over-refuses a body holding a literal dollar; a narrower test would have to reimplement bash's expansion rules.
Only 3 of the 500 here-documents counted had an unquoted delimiter, so the over-refusal has little to reach.

### Decision: ALoopHeaderIsASegmentThatRunsNoProgram

**Chosen:** the header of a `for` or `select` loop is its own segment, marked `loop_header`, whose first word is the reserved word and whose other words are the values after `in`, with their usual kinds; the loop variable and `in` are dropped, and a `for ((…))` header holds one unresolvable word.
No word of a header is a `command`, and `shell-lexing` `EveryWordHasAKind` names the command only in a segment that runs a program.
`block-sensitive-paths.py` judges every header value as a read.

**Rationale:** the lexer read `for` as a program and its header as arguments, so `for i do foo; done` hid `foo`, which bash runs.
Dropping the header words, as `if` and `while` are dropped, would remove values that reach the body through the loop variable: `cat "$f"` names no path, so only the header shows what is read.
The reserved word stays first because about a dozen helpers take a segment's first word as its program; `for` matches no program table, so a value such as `rm` is never taken for one, and directory tracking still counts the loop.
On 2026-10-19 a probe found the one-line `for f in <secret>; do cat "$f"; done` allowed by the sensitive-path hook, which judged words only in a segment holding a recognized read; judging header values as reads closes it, and the verdict tables hold the case.
The body's program is not known from the header, so a placeholder value gets the write verdict.

### Decision: TheFallbacksStayForUnreadableText

**Chosen:** both fallbacks stay, and apply only where the lexer still returns no reading: an unclosed quote, an unterminated here-document, a here-document no data reader reads, a multi-line form the tokenizer does not yet read, a carriage return, a null byte, or syntax the lexer cannot read on one line.

**Rationale:** the lexer's reach grows, but text it cannot read still reaches the hooks, and a hook that cannot read a command must still refuse what the text names.

Both fallbacks judge the same path spellings, which `shell_words.unlexable_text_paths()` takes from the text: quotes group words, a quote left open ends at its line, and a backslash escapes the next character, so a path that holds a space stays one spelling.
It also takes every piece between quotes, operators, and braces, read without quoting rules, and judges the union.
Quoting rules alone cost recall: an escaped or `$'…'` quote in a program body reads as an opening quote and hides every later name, which verification on 2026-10-23 found after `09e863ba` had refused those commands.
A fallback must find every name, so it keeps both readings; a wrong extra spelling only adds text to judge.
A relative spelling is also joined to the working directory and to every directory a chain of `cd` or `pushd` targets in the text may reach, since unreadable text may change directory before it names a file.
Verification on 2026-10-21 and 2026-10-22 found each fallback missing a case the other caught: a quoted block path with a space, the same path with an escaped space, and `auth.json` after `cd ~/.codex`.
The fallbacks had split text their own ways; one splitter for both keeps them from disagreeing again.

## Architecture

```text
command text
    │
    ▼
shell_words._split_words ── quotes, comments, newline → ";" or whitespace,
    │                        here-document body, substitutions, compound
    │                        commands; no reading for text it cannot read
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
  A property test holds that the programs in a reading are exactly the programs bash runs, and another that a form the lexer does not read, a process substitution, has no reading.
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
- **Change:** `shell-lexing` `EveryWordHasAKind`: the command is the first word of a segment that runs a program and is not an assignment; a loop header, a `case` subject or pattern, `((…))`, and `[[ … ]]` run no program.
  **Source:** `ALoopHeaderIsASegmentThatRunsNoProgram`, and the verification report of 2026-10-21.
  **Rationale:** the definition named the first word of every segment the command, which a segment that runs no program contradicts; the forms named are examples of the behavior.
  **Approved by user:** 2026-10-21
- **Change:** `sensitive-path-blocking` `BlockBashReadFromZeroAccessPath`: a value a loop passes to its body through the loop variable is a read-from-path form; add `AZeroAccessPathALoopPassesToItsBody`.
  **Source:** `ALoopHeaderIsASegmentThatRunsNoProgram`, and the verification report of 2026-10-21.
  **Rationale:** the hook judges a loop's values as reads, which no requirement stated; without it, a later change could drop the rule and reopen the one-line route it closed.
  **Approved by user:** 2026-10-21
- **Change:** proposal Out of scope: `case` and `{ …; }` groups leave it; a here-string and a process substitution stay.
  **Source:** the user, 2026-10-21, after the verification report of 2026-10-21.
  **Rationale:** reading `case`, `function`, and `coproc` across lines required reading them on one line; the proposal still named `case` out of scope.
  **Approved by user:** 2026-10-21
- **Change:** `hook-tampering-blocking` `UnrecognizedCommandsAreGated`: a recognized read is a data reader only where it takes only content from its standard input, never file names, arguments, or a program, in place of any recognized read; `AHereDocumentReadByAnyOtherProgramIsProgramText` names such reads.
  **Source:** `AHereDocumentIsDataOnlyForNamedReaders`, and the verification report of 2026-10-21.
  **Rationale:** a recognized read promises to read only the files its words name; a body it takes as names or a program, as `strings @/dev/stdin` and `jq -f /dev/stdin` do, is not data, and the audit of recognized reads that closes each case can miss one.
  **Approved by user:** 2026-10-21
- **Change:** `shell-lexing` `AHereDocumentBodyIsInput`: each here-document word holds its body as bash reads it, and a body a later redirection replaces is still judged, in place of a word holding the text bash delivers.
  **Source:** `AnExpandedBodyIsUnresolvable`, and the verification report of 2026-10-21.
  **Rationale:** for `cat <<A <<B` bash delivers only the second body but expands both, so a substitution in the first runs; the requirement named only the delivered text.
  **Approved by user:** 2026-10-22
- **Change:** `hook-tampering-blocking` `UnrecognizedCommandsAreGated`: the reader shares its command with nothing that can rebind a name, before or after it, and does not pipe its output through a compound command around it or as a coprocess; `ANamedReaderThatMayRunItsInputFallsBack` and `TextPipedIntoAShellNamingAGuardedPath` name these forms.
  **Source:** `AHereDocumentIsDataOnlyForNamedReaders`, and the verification report of 2026-10-22.
  **Rationale:** `{ cat <<'EOF' … } | sh` and `cat() { sh; }` before a `cat` here-document each turned a data body into a program, and `{ echo …; } | sh` hid piped text from the baseline scenario; reviews on 2026-10-23 found a rebinding after the reader in a loop, inside `eval` or `trap`, and through `BASH_CMDS` did the same.
  **Approved by user:** 2026-10-22, and the whole-command rule on 2026-10-23
