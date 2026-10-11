# Tasks: multi-line-command-lexing

## Before starting

- [ ] Confirm `guarded-path-classes` and `security-posture-alignment` are synced and archived, so the baseline holds the `shell-lexing` text and the `UnrecognizedCommandsAreGated` version this change modifies.
- [ ] Settle the order against `single-command-rule-engine`, and record it in `proposal.md` under Resolved Questions.

## Read newlines in the lexer

- [ ] Write failing tests for the newline rules in `shell_words`: two lines yield the segments of the same commands joined by `;`; a backslash-newline joins the lines, except inside single quotes; a newline inside double quotes, single quotes, `$(…)`, or `${…}` is part of the word; a newline after `|`, `&&`, `||`, `then`, `do`, `else`, `elif`, `if`, `while`, `until`, `!`, or `(` yields the segments of the same command with a space — evidence for `SegmentsFollowControlOperators` `ANewlineSeparatesCommands`, `ABackslashNewlineJoinsTheLines`, `ABackslashNewlineInSingleQuotesIsKept`, `AQuotedNewlineIsPartOfTheWord`, and `ANewlineAfterAnOperatorOrAnOpeningWordEndsNothing`.
- [ ] Write failing tests for comments across lines: a comment on its own line hands on no word; a continuation before `#` yields one word holding `#`; a comment ending in a backslash leaves the next line a segment; `#` inside a word, quotes, or after a backslash is a character — evidence for `ACommentIsNotHandedOn`, `AContinuationJoinsBeforeACommentIsFound`, `ABackslashEndingACommentContinuesNothing`, and `AHashInsideAWordIsNotAComment`.
- [ ] Write failing tests that an unclosed quote across lines, a carriage return, a null byte, a newline inside backquotes, and syntax unresolvable on one line still make the command unresolvable as a whole — evidence for `UnreadableTextAcrossLinesIsUnresolvable`.
- [ ] Implement the rules in `_split_words` in the order the design states, emit a `;` operator token for a newline that ends a command, and remove the newline refusal from `_lex`, keeping the refusal of a carriage return and a null byte.
- [ ] Update the `shell_words` module docstring, which says newlines refuse the whole command.

## Read here-documents in the lexer

- [ ] Write failing tests for the here-document word: a quoted-delimiter body is one `here-document` word with no segment or comment inside it; an unquoted body holding `$` or a backquote is unresolvable with its paths still seen; an unquoted body without either is a `here-document` word; an expanded delimiter makes the command unresolvable — evidence for `AHereDocumentBodyIsInput` `AQuotedDelimiterBodyIsAsWritten`, `AnUnquotedBodyWithAnExpansionIsUnresolvable`, `AnUnquotedBodyWithoutAnExpansion`, and `AnExpandedDelimiterIsUnresolvable`.
- [ ] Write failing tests for body boundaries: the rest of the operator's line is lexed before the body; only an exact delimiter line ends the body; `<<-` strips tabs and keeps spaces; two operators take their bodies in order; an unterminated body makes the command unresolvable — evidence for `TheRestOfTheOperatorLineIsReadFirst`, `OnlyAnExactLineEndsTheBody`, `TheDashFormStripsTabsOnly`, `SeveralHereDocumentsOnOneCommand`, and `AnUnterminatedHereDocumentIsUnresolvable`.
- [ ] Add the `here-document` kind to `Kind`, with a test that every word still carries one kind — evidence for `EveryWordHasAKind` `KindsAreDisjoint`.
- [ ] Implement the body capture in `_split_words`, attaching each body to the segment of the command that reads it.

## Classify here-document readers

- [ ] Write failing tests in `bash_commands` that a body read by a recognized read, `git commit -F -`, `git commit --file=-`, `git tag -F -`, `gh … --body-file -`, or `tee` is data and leaves the segment's recognition as its words decide, and that a body read by `bash`, `python3 -`, `uv run python -`, `xargs`, `sudo sh`, `source /dev/stdin`, `awk -f -`, `sed -f -`, `git apply`, `crontab -`, `git agent-commit -F -`, or an unknown program is program text that keeps the command from being recognized.
- [ ] Add the data sinks beside `READ_ONLY_UTILITIES`, and add a program body to the text the classifier scans, as `piped_programs` holds text piped into a shell.

## Judge multi-line commands in the tamper hook

- [ ] Write failing tests that a multi-line read of a guarded location proceeds, that each multi-line form in the lexer tests reaches the decision and reason of its one-line form, that a data body naming a guarded path is not judged while the command's output target still is, and that a program body naming a guarded path gates and one naming a block path refuses — evidence for `UnrecognizedCommandsAreGated` `AMultiLineReadIsRecognized`, `AMultiLineCommandReachesItsOneLineVerdict`, `AHereDocumentReadAsDataIsNotJudged`, and `AHereDocumentReadByAnyOtherProgramIsProgramText`.
- [ ] Update `test_unrecognized_reason_names_syntax` and any test that expects "a newline" as the stopping syntax, and keep a case where an unterminated here-document still reaches the fallback.
- [ ] Judge program bodies in `block-hook-tampering.py` through the classifier's scanned text.

## Judge multi-line commands in the sensitive-path hook

- [ ] Write failing tests that a secret read on any line of a multi-line command is refused, that a placeholder read across lines proceeds, that a name inside a data body is not refused, that a name inside a program body is refused, and that a command the lexer still cannot read is judged piece by piece, a placeholder included — evidence for `AMultiLineCommandReachesItsOneLineVerdict` `ASecretReadOnAnyLineIsRefused`, `APlaceholderReadAcrossLinesProceeds`, `ANameInsideAHereDocumentIsText`, `ANameInsideAProgramBodyIsRefused`, and `UnreadableTextIsJudgedPieceByPiece`.
- [ ] Update the multi-line cases in `sensitive-path-cases.json` that the per-piece fallback refuses today and the lexer now reads, such as `cat .env.example` followed by a newline, which proceeds.
- [ ] Judge a program body piece by piece in `block-sensitive-paths.py`, and leave the fallback for unlexable text in place.

## Check the lexer against bash

- [ ] Add a property test that a command built from the lexer's one-line grammar and the same command with newlines inserted where bash reads them as whitespace or `;` lex to the same segments and words.
- [ ] Extend the generators of `test_bash_runs_only_the_words_the_lexer_handed` in `test_shell_words_properties.py` with newlines between commands, newlines after operators and opening reserved words, continuations, comments, and here-documents, so `shellprobe` holds each form to the words bash hands each program.
- [ ] Teach the `shellprobe` recorder to save the standard input a program receives, and check that a here-document word holds exactly the body bash delivers, `<<-` tab stripping included.
- [ ] Run every suite (`just apps test`) and the cross-validation tests, and record the counts and any exclusion.
