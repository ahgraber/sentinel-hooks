# Tasks: multi-line-command-lexing

## Before starting

- [x] Confirm `guarded-path-classes` and `security-posture-alignment` are synced and archived, so the baseline holds the `shell-lexing` text and the `UnrecognizedCommandsAreGated` version this change modifies.
- [x] Settle the order against `single-command-rule-engine`, and record it in `proposal.md` under Resolved Questions.

## Read newlines in the lexer

- [x] Write failing tests for the newline rules in `shell_words`: two lines yield the segments of the same commands joined by `;`; a backslash-newline joins the lines, except inside single quotes; a newline inside double quotes, single quotes, `$(…)`, or `${…}` is part of the word; a newline after `|`, `&&`, `||`, `then`, `do`, `else`, `elif`, `if`, `while`, `until`, `!`, or `(` yields the segments of the same command with a space — evidence for `SegmentsFollowControlOperators` `ANewlineSeparatesCommands`, `ABackslashNewlineJoinsTheLines`, `ABackslashNewlineInSingleQuotesIsKept`, `AQuotedNewlineIsPartOfTheWord`, and `ANewlineAfterAnOperatorOrAnOpeningWordEndsNothing`.
- [x] Write failing tests for comments across lines: a comment on its own line hands on no word; a continuation before `#` yields one word holding `#`; a comment ending in a backslash leaves the next line a segment; `#` inside a word, quotes, or after a backslash is a character — evidence for `ACommentIsNotHandedOn`, `AContinuationJoinsBeforeACommentIsFound`, `ABackslashEndingACommentContinuesNothing`, and `AHashInsideAWordIsNotAComment`.
- [x] Write failing tests that an unclosed quote across lines, a carriage return, a null byte, a newline inside backquotes, and syntax unresolvable on one line still make the command unresolvable as a whole — evidence for `UnreadableTextAcrossLinesIsUnresolvable`.
- [x] Implement the rules in `_split_words` in the order the design states, emit a `;` operator token for a newline that ends a command, and remove the newline refusal from `_lex`, keeping the refusal of a carriage return and a null byte.
- [x] Update the `shell_words` module docstring, which says newlines refuse the whole command.

## Read here-documents in the lexer

- [x] Write failing tests for the here-document word: a quoted-delimiter body is one `here-document` word with no segment or comment inside it; an unquoted body holding `$` or a backquote is unresolvable with its paths still seen; an unquoted body without either is a `here-document` word; an expanded delimiter makes the command unresolvable — evidence for `AHereDocumentBodyIsInput` `AQuotedDelimiterBodyIsAsWritten`, `AnUnquotedBodyWithAnExpansionIsUnresolvable`, `AnUnquotedBodyWithoutAnExpansion`, and `AnExpandedDelimiterIsUnresolvable`.
- [x] Write failing tests for body boundaries: the rest of the operator's line is lexed before the body; only an exact delimiter line ends the body; `<<-` strips tabs and keeps spaces; two operators take their bodies in order; an unterminated body makes the command unresolvable — evidence for `TheRestOfTheOperatorLineIsReadFirst`, `OnlyAnExactLineEndsTheBody`, `TheDashFormStripsTabsOnly`, `SeveralHereDocumentsOnOneCommand`, and `AnUnterminatedHereDocumentIsUnresolvable`.
- [x] Add the `here-document` kind to `Kind`, with a test that every word still carries one kind — evidence for `EveryWordHasAKind` `KindsAreDisjoint`.
- [x] Implement the body capture in `_split_words`, attaching each body to the segment of the command that reads it.

## Classify here-document readers

- [x] Write failing tests in `bash_commands` that a body read by a recognized read, `git commit -F -`, `git commit --file=-`, `git tag -F -`, `gh … --body-file -`, or `tee` is data and leaves the segment's recognition as its words decide, and that a body read by `bash`, `python3 -`, `uv run python -`, `xargs`, `sudo sh`, `source /dev/stdin`, `awk -f -`, `sed -f -`, `git apply`, `crontab -`, `git agent-commit -F -`, or an unknown program is program text that keeps the command from being recognized.
- [x] Add the data sinks beside `READ_ONLY_UTILITIES`, and add a program body to the text the classifier scans, as `piped_programs` holds text piped into a shell.

## Judge multi-line commands in the tamper hook

- [x] Write failing tests that a multi-line read of a guarded location proceeds, that each multi-line form in the lexer tests reaches the decision and reason of its one-line form, that a data body naming a guarded path is not judged while the command's output target still is, and that a program body naming a guarded path gates and one naming a block path refuses — evidence for `UnrecognizedCommandsAreGated` `AMultiLineReadIsRecognized`, `AMultiLineCommandReachesItsOneLineVerdict`, `AHereDocumentReadAsDataIsNotJudged`, and `AHereDocumentReadByAnyOtherProgramIsProgramText`.
- [x] Update `test_unrecognized_reason_names_syntax` and any test that expects "a newline" as the stopping syntax, and keep a case where an unterminated here-document still reaches the fallback.
- [x] Judge program bodies in `block-hook-tampering.py` through the classifier's scanned text.

## Judge multi-line commands in the sensitive-path hook

- [x] Write failing tests that a secret read on any line of a multi-line command is refused, that a placeholder read across lines proceeds, that a name inside a data body is not refused, that a name inside a program body is refused, and that a command the lexer still cannot read is judged piece by piece, a placeholder included — evidence for `AMultiLineCommandReachesItsOneLineVerdict` `ASecretReadOnAnyLineIsRefused`, `APlaceholderReadAcrossLinesProceeds`, `ANameInsideAHereDocumentIsText`, `ANameInsideAProgramBodyIsRefused`, and `UnreadableTextIsJudgedPieceByPiece`.
- [x] Update the multi-line cases in `sensitive-path-cases.json` that the per-piece fallback refuses today and the lexer now reads, such as `cat .env.example` followed by a newline, which proceeds.
- [x] Judge a program body piece by piece in `block-sensitive-paths.py`, and leave the fallback for unlexable text in place.

## Check the lexer against bash

- [x] Add a property test that a command built from the lexer's one-line grammar and the same command with newlines inserted where bash reads them as whitespace or `;` lex to the same segments and words.
- [x] Extend the generators of `test_bash_runs_only_the_words_the_lexer_handed` in `test_shell_words_properties.py` with newlines between commands, newlines after operators and opening reserved words, continuations, comments, and here-documents, so `shellprobe` holds each form to the words bash hands each program.
- [x] Teach the `shellprobe` recorder to save the standard input a program receives, and check that a here-document word holds exactly the body bash delivers, `<<-` tab stripping included.
- [x] Run every suite (`just apps test`) and the cross-validation tests, and record the counts and any exclusion.
  2026-10-15, no exclusions: shared 2303 passed, 1 skipped; claude 589 passed, 2 xfailed; codex 53 passed; copilot 66 passed; pi 37 passed and 290 node tests passed.
  The `shellprobe` differential properties run inside the shared suite; this module has no separate cross-validation marker.

## Narrow to plain multi-line commands

- [x] Revise the `shell-lexing`, `hook-tampering-blocking`, and `sensitive-path-blocking` deltas, the design, and the proposal to read only plain multi-line commands and here-documents `cat` or a record sink reads.
- [x] Write failing tests for each form the review found read more permissively than bash: a reserved word as an argument before a newline, a continuation inside `&&`, a comment inside `$(…)`, a backquote inside double quotes, `((…<<…))`, a pipe after a record reader, `env -S`, `GIT_EDITOR=sh`, `git -c` and `-e`, an assignment before a sink, and a gh alias.
- [x] Give no reading in the lexer for a multi-line command with a continuation, a `$(…)` or backquote, a parenthesis, or a reserved word in command position, and replace the newline rules after reserved words with a command-position test.
- [x] Replace program bodies in `bash_commands.py` with `unread_here_document()`, and send a command it reports to the fallback in both hooks.
- [x] Restrict the `line_pairs` generator to plain commands, and add a property that every form beyond plain commands has no reading.
- [x] Run every suite (`just apps test`), and record the counts and any exclusion.
  2026-10-15, no exclusions: shared 2362 passed, 1 skipped; claude 589 passed, 2 xfailed; codex 53 passed; copilot 66 passed; pi 37 passed and 293 node tests passed.

## Remediate the verification findings

- [x] Write failing tests that a multi-line command whose `${…}` holds `$(` or a backquote has no reading, including the comment-inside-`${…}` form, and give such a command no reading in the lexer.
- [x] Write a failing test that a data body whose first line has the shape `NAME=<path>` is not judged by either hook, and skip here-document words in `bash_commands.word_paths`.
- [x] Add a test that an unquoted here-document body with a line ending in a backslash leaves the command with no reading.
- [x] Add hook-level tests for an unquoted-delimiter body holding `$` and a guarded path, and holding `$` and a secret-looking path.
- [x] Add hook-level tests for the sink forms `--file -`, `--file=-`, `--body-file=-`, `git -C <dir>`, and `git tag`, and for a here-document before `|&`.
- [x] Make the refusal reason for an unread here-document name a sink with an editor, a wrapper, an assignment, or a pipe, and end the multi-line reason with syntax the lexer does not read on one line.
- [x] Rebase the `hook-tampering-blocking` delta onto the current baseline, keeping only the multi-line additions.
- [x] Add the `modified-removes` marker for `ANewlineRefusesTheCommand` to the `shell-lexing` delta.
- [x] Bring the `NewlinesAreReadInTheTokenizer` decision in line with the narrowing.
- [x] Replace the claim that the command-position test is exact with the over-refusal it makes.
- [x] Record the editorial rewording of the deltas in the design, and mark the 2026-10-15 Resolved Questions line as decided with the user.
- [x] Run every suite (`just apps test`), and record the counts and any exclusion.
  2026-10-17, on main at `2b7fe34`, no exclusions: shared 2445 passed, 1 skipped; claude 645 passed, 2 xfailed; codex 54 passed; copilot 66 passed; pi 37 passed and 295 node tests passed.

## Remediate the second verification

- [x] Write failing tests that a multi-line command with `${` inside double quotes has no reading, including the form whose `${…}` holds a quote that hides the next line, and give such a command no reading in the lexer.
- [x] Add the form to the `shell-lexing` delta's list of forms beyond plain commands, and to the `BEYOND_PLAIN` property generator.
- [x] Narrow the `hook-tampering-blocking` claim about `PATH=` to an assignment in the reader's own segment.
- [x] Run every suite (`just apps test`), and record the counts and any exclusion.
  2026-10-17, on main at `2b7fe34`, no exclusions: shared 2447 passed, 1 skipped; claude 645 passed, 2 xfailed; codex 54 passed; copilot 66 passed; pi 37 passed and 295 node tests passed.

## Restore the original requirements

- [x] Write failing tests that `block-leaks.py` refuses a credential-store read in a here-document a shell or `xargs` reads, and allows the same text in a here-document `cat` or `git commit -F -` reads; send an unread here-document to its text check, and keep here-document words out of `reads_stdin_program`'s operands.
- [x] Write failing tests that a vertical tab, a form feed, or a Unicode space before `#` starts no comment, in the lexer, the tamper hook, and the verdict table; separate words on space and tab only.
- [x] Restore the requirement text of the three deltas as approved in the proposal commit, keeping the here-document reader conditions, the `echo if then` scenario, and the removal marker; correct the delimiter rule to bash's.
- [x] Record each form the implementation does not read as bash does as a gap, with a task to close it and a strict expected-failure test, and move the verdict-table case that encoded a gap into those tests.
- [x] Rename the refusal tests and the generator for forms the lexer does not yet read.
- [x] Run every suite (`just apps test`), and record the counts and any exclusion.
  2026-10-18, on main at `2b7fe34`, no exclusions: shared 2473 passed, 1 skipped, 36 xfailed (the known-gap tests); claude 651 passed, 2 xfailed; codex 54 passed; copilot 66 passed; pi 37 passed and 297 node tests passed.

## Close the known gaps

- [x] Extract the shell inputs from `mvdan/sh`'s parser tests into a corpus, with its BSD-3-Clause notice, keeping only inputs bash 5.3 accepts; add properties that every program bash runs for a corpus input is in the reading, and that inputs the corpus groups as one program read alike.

- [x] Read a named descriptor, `{fd}<f`, as part of its redirection, which the corpus found read as an argument.

- [x] Close `OneLineCompoundCommand`: read loop headers and bodies as bash does, and remove its expected-failure marks.

- [x] Judge a loop header's values as reads in `block-sensitive-paths.py`, which allowed a secret named only in a one-line header; add the cases to the sensitive-path verdict table.

- [x] Close `ConditionalExpression`: read `[[ … ]]` as one command that runs no program, and remove its expected-failure marks.

- [x] Close `ArrayAssignment`: read array and subscript assignments and `let` operands as bash does, and remove its expected-failure marks.

- [x] Read `NAME+=` and `NAME[…]=` as assignments, which the array probe found read as the program name, and treat `HOME+=` and `HOME[…]=` as moving `~`.

- [x] End an ANSI-C quote, `$'…'`, inside a substitution at its first unescaped `'`.

- [x] Close `LineContinuation`: read a backslash-newline outside single quotes and comments as nothing, and remove its expected-failure marks.

- [x] Close `CompoundCommandAcrossLines`: track command position and compound state across lines, and remove its expected-failure marks.
  `if`, `while`, `until`, `for`, `select`, `!`, and `{ … }` read across lines; `case`, `function`, and `coproc` move to their own gap.

- [x] Close `CaseFunctionOrCoprocessAcrossLines`: read `case` patterns, `function` bodies, and coprocesses as bash does, on one line and across lines, and remove its expected-failure marks.

- [x] Close `SubstitutionAcrossLines`: read substitutions with a recursive scanner, and remove its expected-failure marks.

- [x] Close `ParenthesisAcrossLines`: read subshells and arithmetic commands across lines, and remove its expected-failure marks.

- [x] Close `ParameterExpansionInDoubleQuotesAcrossLines`: admit the form once quotes inside `${…}` are read, and remove its expected-failure marks.

- [x] Close the comment half of `CommentOrHereDocumentInsideSubstitution`: a comment inside a substitution runs to its newline.

- [x] Close the here-document half of `HereDocumentOrCaseInsideSubstitution`: a here-document body inside a substitution is input, skipped to its delimiter line.

- [x] Close `CaseInsideSubstitution`: read `case` patterns inside a substitution, and remove its expected-failure marks.

- [x] Close `QuoteInsideNestedExpansionInDoubleQuotes`: scan nested expansions inside double quotes with their own quote state, and remove its expected-failure marks.

- [x] Close `UnquotedBackquoteSplit`: scan backquote substitutions as one word, and remove its expected-failure marks.

- [x] Close `ReservedWordAfterAssignmentOrRedirection`: remove reserved words only in command position, and remove its expected-failure marks.

- [x] Close `ArithmeticCommand`: scan `((…))` as arithmetic, and remove its expected-failure marks.

- [x] Close `HereDocumentDelimiterWithDollar`: read a delimiter with quote removal only, and remove its expected-failure marks.

- [x] Close `HereDocumentBodyEscapes`: scan an unquoted body with bash's backslash rules, and remove its expected-failure marks.

- [x] Close `HereDocumentReadByARecognizedRead`: admit every recognized read as a data reader under the reader conditions, and remove its expected-failure marks.

- [x] Stop admitting as a recognized read a utility that takes the names of the files it reads from a file or its input (`du`, `sort`, and `wc` with `--files0-from`, `file -f` or `--files-from`, `find -files0-from`), which read files its words do not name.

- [x] Stop admitting a checksum check (`-c`, `--check`) as a recognized read, and give one refusal reason for a command the lexer cannot read, on one line or across lines.

- [x] Audit every recognized read against the files its words name: stop admitting `strings` with an `@` argument, and `jq` with a program file, a library path, or a module directive.

- [x] Name the data readers, the recognized reads that take only content from standard input, and judge a here-document any other recognized read takes as program text.

- [x] Give `function` and the name a `name()` definition binds the plain-word kind, since a definition runs no program.

- [x] Search unreadable text whole for the declared block paths in `block-sensitive-paths.py`, so a block path that holds a space is refused inside a shell's here-document.

- [x] Run every agent's suite after these fixes: shared 2883 passed and 1 skipped, claude 651 passed and 2 expected failures, codex 54, copilot 66, pi 37, and 310 node tests, on 2026-10-22.

- [x] Mark each segment whose output goes to a pipe or whose input comes from one, through every compound command around it and for a coprocess, and judge here-document readers, piped shells, and pipe-fed programs by those marks.

- [x] Leave no here-document data, and the command unrecognized, after a command that rebinds a name: a function definition, `hash -p`, `alias`, or `enable`.

- [x] Take the path spellings in unreadable text from one place for both hooks, keeping quoted and escaped spaces and joining relative spellings to the working directory and each `cd` target.

- [x] Admit `sort` with `-T` or `--temporary-directory` as a write, after a second audit of every recognized read for options that write or run.

- [x] Record whether each recorded program's output and input are pipes, compare them with the reading in a property, and generate piped compound commands, `until`, `select`, `coproc`, function calls, and here-documents inside compound commands.

- [x] Run every agent's suite after these fixes: shared 2949 passed and 1 skipped, claude 651 passed and 2 expected failures, codex 54, copilot 66, pi 37, and 315 node tests, on 2026-10-22.

- [x] Apply the rebinding rule to the whole command, so a rebinding after the reader in a loop counts, and add writes to `BASH_CMDS` and `BASH_ALIASES`, `eval` and `trap` with code, and `source`; leave `alias`, `enable`, and `trap` that only list or reset out of it.

- [x] Record a function definition once, as a lexer mark the classifier reads, for any name bash accepts.

- [x] Take the `cd` target after its options in unreadable text, and rename that splitter `unlexable_text_paths`.

- [x] Count a command whose program the reading cannot name, such as `$E` or `$(echo eval)`, as one that can rebind a name.

- [x] Judge the union of the quote-aware spellings and the pieces between every quote, operator, and brace in unreadable text, and follow a chain of relative `cd` targets there.

- [x] Compare a program's standard input with the last here-document body on descriptor 0 in the bash comparison.

- [x] Make the directory after `cd -P` unknown again, as the baseline states: `-P` sets the directory to the physical path, so a later `cd ..` climbs from a link's target, which verification on 2026-10-23 confirmed with a real link.

- [x] Read `time` before a compound command and a `{ …; }` body of `for`, and give no reading to a `|` after no command, as in `{ …; }& | cat`.

- [x] Build the words a program receives with one helper in the property tests, which drops redirection targets.

- [x] Run every agent's suite after these fixes: shared 2979 passed and 1 skipped, claude 651 passed and 2 expected failures, codex 54, copilot 66, pi 37, and 318 node tests, on 2026-10-23.

- [x] Run every agent's suite after the `cd -P` revert, the unnamed-program rebinder, and the fallback union: shared 2987 passed and 1 skipped, claude 651 passed and 2 expected failures, codex 54, copilot 66, pi 37, and 322 node tests, on 2026-10-23.
