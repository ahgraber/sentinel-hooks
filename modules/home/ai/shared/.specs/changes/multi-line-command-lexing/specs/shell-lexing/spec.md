# Delta for shell-lexing

## MODIFIED Requirements

### Requirement: SegmentsFollowControlOperators

> Previously: a path hook treated a command that contains a newline as unresolvable as a whole.

A path hook SHALL split a command into the segments bash runs.
Pipes such as `|`, list operators such as `;` and `&&`, subshell boundaries, and the unquoted newlines that end a command separate the segments.
Each segment holds one command word and the words bash passes with it.
For a command written across lines, the hook SHALL judge the segments and words bash reads in it.
These are the same as for the command written on one line.

Serves: a-multi-line-command-is-read-line-by-line

A hook judges a segment by its command word, so the split decides which words each rule sees.

Bash treats a newline by its position, and a path hook SHALL treat it the same way:

- A backslash before a newline, outside single quotes and outside a comment, removes both, so the two lines are one.
- A newline inside quotes, or inside `$(…)`, `${…}`, or backquotes, is a character of the word that holds it.
- A newline after `|`, `&&`, `||`, or a reserved word that opens a list, `then`, `do`, `else`, `elif`, `if`, `while`, `until`, `!`, or `(`, is whitespace and ends nothing, because bash reads the list that follows.
- Any other unquoted newline ends a command as `;` does.

The third rule keeps a multi-line form from reading more permissively than its one-line form.
On one line, `if true; then cat <file>; fi` makes `then` the command word of its segment; splitting at a newline after `then` would hand `cat` to a rule as a command bash never runs alone.

A `#` that begins a word starts a comment, and the comment runs to the end of its line.
Bash runs nothing in a comment, so no word of it is judged.
The order of the rules decides what is a comment: a line continuation joins first, so `a\` and a next line `#x` are the one word `a#x`; a comment then runs to its newline, and a backslash at its end continues nothing.
A `#` inside a word, as in `a#b`, `$#`, or `${#x}`, inside quotes, or after a backslash, is a character of the word.

If a path hook cannot read text on one line, it cannot read it across lines either.
It still treats such a command as unresolvable as a whole.
A here-string, `<<<`, stays as it is read on one line.

#### Scenario: APipelineIsSplit

- **GIVEN** a command joining two programs with a pipe
- **WHEN** a path hook judges it
- **THEN** the hook judges two segments, each with its own command word

#### Scenario: AQuotedOperatorDoesNotSplit

- **GIVEN** a command carrying a pipe or list operator inside quotes
- **WHEN** a path hook judges it
- **THEN** the hook judges one segment, and the operator is part of a word

#### Scenario: ANewlineSeparatesCommands

- **GIVEN** two commands on two lines
- **WHEN** a path hook judges the text
- **THEN** the hook judges the segments it judges for the two commands joined by `;`

#### Scenario: ABackslashNewlineJoinsTheLines

- **GIVEN** a command whose line ends in an unquoted backslash
- **WHEN** a path hook judges it
- **THEN** the hook judges the words of the same command written on one line without the backslash and the newline

#### Scenario: ABackslashNewlineInSingleQuotesIsKept

- **GIVEN** a backslash and a newline inside single quotes
- **WHEN** a path hook judges the command
- **THEN** both are characters of the quoted word

#### Scenario: AQuotedNewlineIsPartOfTheWord

- **GIVEN** a newline inside double or single quotes, or inside `$(…)`, `${…}`, or backquotes
- **WHEN** a path hook judges the command
- **THEN** one word holds it, and no segment ends there

#### Scenario: ANewlineAfterAnOperatorOrAnOpeningWordEndsNothing

- **GIVEN** a newline after `|`, `&&`, or `||`, or after `then`, `do`, or `else` in an `if`, `for`, `while`, or `until` command
- **WHEN** a path hook judges the command
- **THEN** the hook judges the segments, words, and directories of the same command on one line with a space in place of that newline

#### Scenario: ACommentIsNotHandedOn

- **GIVEN** a command followed by `#` and text, on one line or on its own line
- **WHEN** a path hook judges it
- **THEN** the hook judges no word of the comment

#### Scenario: AHashInsideAWordIsNotAComment

- **GIVEN** `#` inside a word, as `a#b`, `$#`, or `${#x}`, inside quotes, or after a backslash
- **WHEN** a path hook judges the command
- **THEN** it is a character of that word

#### Scenario: AContinuationJoinsBeforeACommentIsFound

- **GIVEN** a line ending in a backslash, followed by a line that begins with `#`
- **WHEN** a path hook judges the command
- **THEN** the hook judges the two lines as one word holding `#`, and finds no comment

#### Scenario: ABackslashEndingACommentContinuesNothing

- **GIVEN** a comment that ends in a backslash, followed by a command on the next line
- **WHEN** a path hook judges the command
- **THEN** the next line is a segment of its own

#### Scenario: UnreadableTextAcrossLinesIsUnresolvable

- **GIVEN** a command across lines that holds an unclosed quote, a carriage return, a null byte, or other syntax a path hook treats as unresolvable on one line
- **WHEN** a path hook judges it
- **THEN** the hook treats the command as unresolvable as a whole

### Requirement: EveryWordHasAKind

> Previously: the kinds were command, option, assignment, redirection target, pattern, path candidate, plain word, and unresolvable.

A path hook SHALL give every word it judges exactly one kind: command, option, assignment, redirection target, here-document, pattern, path candidate, plain word, or unresolvable.

Serves: a-multi-line-command-is-read-line-by-line

The kinds are disjoint and cover every word.
A hook that decides from words decides from their kinds, so a rule that applies to a path applies to path candidates and redirection targets, whichever hook holds the rule.

The command is the first word of a segment that is not an assignment.
An option is a word beginning with `-` in a position bash would pass to the program.
A redirection target is the operand of a redirection operator, whether or not a space separates the two.
A here-document is the body of a `<<` or `<<-` redirection: text its command reads on its standard input, not a file it names.

#### Scenario: KindsAreDisjoint

- **GIVEN** any command
- **WHEN** a path hook judges it
- **THEN** every word has one kind, and no word has two

#### Scenario: AnAttachedRedirectionTargetIsATarget

- **GIVEN** a redirection operator written against its operand with no space
- **WHEN** a path hook judges the command
- **THEN** the hook judges the operand as a redirection target

#### Scenario: AnAssignmentIsNotACommand

- **GIVEN** a segment beginning with a variable assignment
- **WHEN** a path hook judges the command
- **THEN** the hook judges the assignment as an assignment and the following word as the command

## ADDED Requirements

### Requirement: AHereDocumentBodyIsInput

A path hook SHALL judge a here-document body as one word of the here-document kind.
The word belongs to the segment of the command that reads the body.
It holds the lines after the operator's line and before the delimiter line.
The hook SHALL NOT split the body into segments.
If bash would expand any part of the body, the hook SHALL treat the body as unresolvable.

Serves: a-multi-line-command-is-read-line-by-line

Bash hands the body to the command's standard input.
A line in the body that reads as a command, such as `rm <file>`, runs only if the command that reads the body runs it.
So the line is not a segment.
Each hook decides whether that command runs its input or acts on it, and judges the body together with that command.

The delimiter decides whether bash rewrites the body.
A quoted delimiter, any part of it quoted, as in `<<'EOF'`, `<<"EOF"`, or `<<E\OF`, leaves the body as written.
An unquoted delimiter makes bash expand parameters, command substitutions, and arithmetic in the body, so a body holding `$` or a backquote is unresolvable as any expanded word is, and a path inside it is still seen.
A delimiter that is itself expanded, as in `<<$X`, is unresolvable.

The body starts on the line after the operator, after the rest of that line, so `cat <<EOF | tr a b` and `cat <<EOF; echo done` read the whole first line before the body.
It ends at the first line that is exactly the delimiter; a line that holds the delimiter with other characters, a trailing space included, does not end it.
`<<-` removes leading tab characters, and only tabs, from each body line and from the delimiter line.
A command may carry several here-documents; their bodies follow in the order of their operators.
A `#` inside a body is a character of it.

#### Scenario: AQuotedDelimiterBodyIsAsWritten

- **GIVEN** a here-document whose delimiter is quoted
- **WHEN** a path hook judges the command
- **THEN** the hook judges its body as one here-document word holding the lines as written, and no line of it is a segment or a comment

#### Scenario: AnUnquotedBodyWithAnExpansionIsUnresolvable

- **GIVEN** a here-document whose delimiter is unquoted and whose body holds `$` or a backquote
- **WHEN** a path hook judges the command
- **THEN** the hook treats the body as unresolvable, and still sees a path inside it

#### Scenario: AnUnquotedBodyWithoutAnExpansion

- **GIVEN** a here-document whose delimiter is unquoted and whose body holds no `$` and no backquote
- **WHEN** a path hook judges the command
- **THEN** the hook judges the body as a here-document word

#### Scenario: AnExpandedDelimiterIsUnresolvable

- **GIVEN** a here-document operator whose delimiter holds a parameter or a substitution
- **WHEN** a path hook judges the command
- **THEN** the hook treats the command as unresolvable as a whole

#### Scenario: TheRestOfTheOperatorLineIsReadFirst

- **GIVEN** a here-document operator followed on its line by a pipe or a list operator and another command
- **WHEN** a path hook judges the command
- **THEN** that command is a segment, and the body starts on the next line

#### Scenario: OnlyAnExactLineEndsTheBody

- **GIVEN** a body line that holds the delimiter followed by a space
- **WHEN** a path hook judges the command
- **THEN** the body does not end there

#### Scenario: TheDashFormStripsTabsOnly

- **GIVEN** a `<<-` here-document whose body lines and delimiter line begin with tabs, and one line that begins with spaces
- **WHEN** a path hook judges the command
- **THEN** the tabs are removed, the spaces are kept, and the tab-indented delimiter ends the body

#### Scenario: SeveralHereDocumentsOnOneCommand

- **GIVEN** a command carrying two here-document operators
- **WHEN** a path hook judges it
- **THEN** each body follows the operator it belongs to, in order

#### Scenario: AnUnterminatedHereDocumentIsUnresolvable

- **GIVEN** a here-document whose delimiter line never appears
- **WHEN** a path hook judges the command
- **THEN** the hook treats the command as unresolvable as a whole
