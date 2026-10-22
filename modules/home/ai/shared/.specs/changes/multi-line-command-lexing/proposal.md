# Proposal: multi-line-command-lexing

## Intent

The shared lexer `shell_words` refuses every Bash command that holds a newline, including a backslash line continuation and a newline inside quotes.
`shell-lexing` `SegmentsFollowControlOperators` records why: "which reading applies is not yet established, so the whole command is refused rather than half-read."
Bash establishes the reading.
An unquoted newline ends a command as `;` does, a backslash before a newline joins the two lines, and a newline inside quotes is a character of the word.

Every hook that reads the lexer therefore falls back for a multi-line command.
`block-hook-tampering.py` gates any multi-line command whose text names a guarded location, a read included, and names "a newline" as the syntax that stopped recognition.
`block-sensitive-paths.py` judges each piece of the unparsed text by the strong rules, so it refuses a multi-line command that only mentions a secret-looking name, and it refuses a placeholder dotenv file there that it lets a single-line read take.
Neither hook can tell what a multi-line command reads, writes, or runs.

A measurement over the 30 days to 2026-10-08 found 1,906 multi-line commands among about 29,700 shell commands the four agents sent, 6.4%.
469 were here-documents, 20 of them commit messages; 62 used a backslash continuation; 1,383 held another newline.
20 of the multi-line commands named a secret-looking file, nearly all while testing these hooks.
The measurement did not count multi-line commands that name a guarded location, which is the case the tamper hook gates.

## User Stories

- **a-multi-line-command-is-read-line-by-line** — As the operator of these agents, I want a multi-line command judged by what each of its lines does, so that a script written by here-document, or a multi-line commit, is gated only for what it does, and a secret named on any line is refused by its real reading rather than by a guess over the text.
  (North star: "ordinary, recoverable work proceeds without friction", and "a denial from any layer is final"; a refusal of text the hook could not read is neither.)

## Scope

**In scope:**

- `shell-lexing`: reading a multi-line command into the segments bash runs, as bash reads it, with bash as the reference shell.
  The spec states the reading as bash's and does not restate bash's grammar; the differential property against bash checks it.
  A here-document's body is one word of a new kind, the standard input of its command, and is unresolvable wherever bash would expand part of it.
- `hook-tampering-blocking`: `UnrecognizedCommandsAreGated` classifies a multi-line command on the segments the lexer reads, and judges a here-document as data only where a recognized read or a named sink reads it, and as program text everywhere else.
- `sensitive-path-blocking`: the per-piece fallback applies only to a command the lexer still cannot read and to a here-document a program other than a data reader reads, so a placeholder read in a multi-line command proceeds as it does on one line.
- Verdict cases that pair each multi-line form with its one-line equivalent, run against both hooks, so the two forms reach the same verdict.

**Out of scope:**

- Syntax the lexer does not read on one line either, a here-string and a process substitution: it stays unresolvable, and the fallbacks stay as they are.
- `single-command-rule-engine`'s quote-splice rewrite for newline commands.
  That change decides whether to drop it once this one lands.

## Approach

Extend the tokenizer rather than adding a second pass: newline handling, continuation, and comments belong where quotes are already tracked.
A here-document needs its delimiter read at the operator and its body captured up to the delimiter line, honoring `<<-` tab stripping.
The body becomes one word of a new kind.
The hooks treat it as data only where the reading command is a recognized read or a named sink (`git commit -F -`, `git tag -F -`, `gh --body-file -`, `tee`), and as program text, judged as `bash -c` text is, everywhere else.
An allowlist, not a list of interpreters, because `xargs`, `sudo sh`, `sed -f -`, `git apply`, `crontab -`, and others act on input whose effects only the body names.
The order of the newline rules is part of the contract: a continuation joins first, a comment then runs to its newline, and a backslash at a comment's end continues nothing.
Each multi-line form is tested against the verdict the same command on one line reaches.

## Dependencies

- `guarded-path-classes` and `security-posture-alignment` must sync first.
  They own the current text of `shell-lexing`, `UnrecognizedCommandsAreGated`, and the sensitive-path fallback.

## Open Questions

- Whether to count, before building, how many multi-line commands name a guarded location, since that is the friction the tamper hook adds today.
- Whether to add `block-leaks.py`'s 1Password and Kubernetes check to the verdict cases.
  `credential-store-handoff` judges a command the lexer cannot read by a text pattern, so today a multi-line command that only mentions `op read`, such as a here-document commit message, is refused.
  Once this change lexes newlines, that check reads such a command by its segments, and the here-document body is data where a named sink reads it.
  `sudo sh` in the allowlist rationale above is now read as a shell reading its standard input (`bash_commands.reads_stdin_program`), as are `sudo -s`, `sudo -i`, `doas -s`, and `su` with no `-c`.

## Resolved Questions

- 2026-10-08: a comment runs to the end of its line and is not handed on, with the continuation-before-comment order stated in the spec.
  The lexer already drops a one-line comment, so this changes only commands written across lines.
- 2026-10-08: a here-document is data only where a recognized read or a named sink reads it, and program text everywhere else; the interpreter list is not used for this.
- 2026-10-08: the sinks stay generic; a git alias such as `git agent-commit` is not named, because the hook cannot know what an alias runs.
- 2026-10-08: a count of the 500 here-documents agents sent in the 30 days to 2026-10-08 found 314 read by `cat` writing a file, 176 by `python`, `python3`, or `uv`, 6 by a plain `cat` or `tr`, 2 by `git agent-commit -F -`, and 2 by other programs; none sat inside `$(…)`, and 497 had a quoted delimiter.
  15 of the program bodies named a guarded path, all while editing this repository's hooks, and every one is gated today, so the allowlist adds no refusal.
- 2026-10-14: this change lands before `single-command-rule-engine`.
  The rule engine then reads every command through the lexer and drops its quote-splice rewrite, instead of keeping the rewrite for newline commands until this change retires it.
- 2026-10-15: the forms a review found the first implementation read more permissively than bash are gaps, to be closed in steps without weakening the posture.
  A review by Codex and two Opus agents, confirmed against bash 5.3.9, found nine such forms.
  As the first step, the lexer gives them no reading, and reads a here-document only where `cat` or a named sink reads it as the first word of a segment that does not pipe; every form left out reaches the fallbacks, as all multi-line commands did before this change.
  This is an interim fallback, not the scope of the change.
  Decided with the user.
- 2026-10-17: the interim fallback also covers a multi-line command with a `${…}` inside double quotes, other than a leading `${HOME}`, because bash reads quotes inside it that the lexer took for the end of the word; the command-position test over-refuses a reserved word after an assignment or a redirection, as in `X=1 if`.
  The `PATH=` route the reader conditions close is an assignment in the reader's own segment; an earlier `export PATH=` proceeds as it does on one line.
  Decided with the user.
- 2026-10-18: the requirements return to the scope above: a command written across lines is judged as bash reads it.
  The 2026-10-15 and 2026-10-17 spec edits had written the interim fallback into the requirements; it stays in the implementation, and each form it covers is a gap, with a task to close it and a strict expected-failure test.
  The here-document reader conditions stay as policy.
  Decided with the user.
- 2026-10-18: the `shell-lexing` requirements mandate bash's reading and do not restate bash's rules; specific forms are checked against bash by the differential property and the gap tests.
  Decided with the user.
- 2026-10-21: the scope grows to `case`, `function`, and `coproc`, on one line and across lines, which closing the compound-command gap brought in: a multi-line command reads as its one-line form, so its one-line form must be read.
  A here-string and a process substitution stay out of scope.
- 2026-10-21: a here-document is data only where a named sink or a recognized read that takes only content from its standard input reads it; a recognized read that takes file names or a program from its input is not a data reader.
  Verification found `strings @/dev/stdin` and `jq -f /dev/stdin` after checksum `-c`, so the data readers are named, beside the audit of the recognized reads.
  Decided with the user.
  Decided with the user.
