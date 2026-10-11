# Delta for shell-lexing

## MODIFIED Requirements

### Requirement: SegmentsFollowControlOperators

> Previously: a command carrying a newline was reported as a whole as unresolvable.

A command SHALL be split into segments at pipes, list operators, subshell boundaries, and the unquoted newlines that end a command, each segment holding one command word and the words bash would pass with it, and a command written across lines SHALL yield the segments and words bash reads in it, which are those of the same command written on one line.

Serves: a-multi-line-command-is-read-line-by-line

A hook judges a segment by its command word, so the split decides which words each rule sees.

Bash reads a newline by where it stands, and the lexer SHALL read it the same way:

- A backslash before a newline, outside single quotes and outside a comment, removes both, so the two lines are one.
- A newline inside quotes, or inside `$(…)`, `${…}`, or backquotes, is a character of the word that holds it.
- A newline after `|`, `&&`, `||`, or a reserved word that opens a list, `then`, `do`, `else`, `elif`, `if`, `while`, `until`, `!`, or `(`, is whitespace and ends nothing, because bash reads the list that follows.
- Any other unquoted newline ends a command as `;` does.

The third rule keeps a multi-line form from reading more permissively than its one-line form.
On one line, `if true; then cat <file>; fi` makes `then` the command word of its segment; splitting at a newline after `then` would hand `cat` to a rule as a command bash never runs alone.

A `#` that begins a word starts a comment, and the comment runs to the end of its line.
Bash runs nothing in a comment, so no word of it is handed on.
The order of the rules decides what is a comment: a line continuation joins first, so `a\` and a next line `#x` are the one word `a#x`; a comment then runs to its newline, and a backslash at its end continues nothing.
A `#` inside a word, as in `a#b`, `$#`, or `${#x}`, inside quotes, or after a backslash, is a character of the word.

Text the lexer cannot read on one line it cannot read across lines either, and such a command is still reported as a whole as unresolvable.
A here-string, `<<<`, stays as it is read on one line.

#### Scenario: APipelineIsSplit

- **GIVEN** a command joining two programs with a pipe
- **WHEN** it is lexed
- **THEN** two segments result, each with its own command word

#### Scenario: AQuotedOperatorDoesNotSplit

- **GIVEN** a command carrying a pipe or list operator inside quotes
- **WHEN** it is lexed
- **THEN** one segment results, and the operator is part of a word

#### Scenario: ANewlineSeparatesCommands

- **GIVEN** two commands on two lines
- **WHEN** the text is lexed
- **THEN** it yields the segments the two commands joined by `;` yield

#### Scenario: ABackslashNewlineJoinsTheLines

- **GIVEN** a command whose line ends in an unquoted backslash
- **WHEN** it is lexed
- **THEN** it yields the words of the same command written on one line without the backslash and the newline

#### Scenario: ABackslashNewlineInSingleQuotesIsKept

- **GIVEN** a backslash and a newline inside single quotes
- **WHEN** the command is lexed
- **THEN** both are characters of the quoted word

#### Scenario: AQuotedNewlineIsPartOfTheWord

- **GIVEN** a newline inside double or single quotes, or inside `$(…)`, `${…}`, or backquotes
- **WHEN** the command is lexed
- **THEN** one word holds it, and no segment ends there

#### Scenario: ANewlineAfterAnOperatorOrAnOpeningWordEndsNothing

- **GIVEN** a newline after `|`, `&&`, or `||`, or after `then`, `do`, or `else` in an `if`, `for`, `while`, or `until` command
- **WHEN** the command is lexed
- **THEN** it yields the segments, words, and directories of the same command on one line with a space in place of that newline

#### Scenario: ACommentIsNotHandedOn

- **GIVEN** a command followed by `#` and text, on one line or on its own line
- **WHEN** it is lexed
- **THEN** no word of the comment is handed on

#### Scenario: AHashInsideAWordIsNotAComment

- **GIVEN** `#` inside a word, as `a#b`, `$#`, or `${#x}`, inside quotes, or after a backslash
- **WHEN** the command is lexed
- **THEN** it is a character of that word

#### Scenario: AContinuationJoinsBeforeACommentIsFound

- **GIVEN** a line ending in a backslash, followed by a line that begins with `#`
- **WHEN** the command is lexed
- **THEN** the two lines are one word holding `#`, and no comment results

#### Scenario: ABackslashEndingACommentContinuesNothing

- **GIVEN** a comment that ends in a backslash, followed by a command on the next line
- **WHEN** the command is lexed
- **THEN** the next line is a segment of its own

#### Scenario: UnreadableTextAcrossLinesIsUnresolvable

- **GIVEN** a command across lines that holds syntax the lexer reports unresolvable on one line, an unclosed quote, a carriage return, or a null byte
- **WHEN** it is lexed
- **THEN** the command is reported as a whole as unresolvable

### Requirement: EveryWordHasAKind

> Previously: the kinds were command, option, assignment, redirection target, pattern, path candidate, plain word, and unresolvable.

Every word this capability hands on SHALL carry exactly one kind: command, option, assignment, redirection target, here-document, pattern, path candidate, plain word, or unresolvable.

Serves: a-multi-line-command-is-read-line-by-line

The kinds are disjoint and cover every word.
A hook that decides from words decides from their kinds, so a rule that applies to a path applies to path candidates and redirection targets, whichever hook holds the rule.

The command is the first word of a segment that is not an assignment.
An option is a word beginning with `-` in a position bash would pass to the program.
A redirection target is the operand of a redirection operator, whether or not a space separates the two.
A here-document is the body of a `<<` or `<<-` redirection: text its command reads on its standard input, not a file it names.

#### Scenario: KindsAreDisjoint

- **GIVEN** any command
- **WHEN** it is lexed
- **THEN** every word carries one kind, and no word carries two

#### Scenario: AnAttachedRedirectionTargetIsATarget

- **GIVEN** a redirection operator written against its operand with no space
- **WHEN** the command is lexed
- **THEN** the operand is a redirection target

#### Scenario: AnAssignmentIsNotACommand

- **GIVEN** a segment beginning with a variable assignment
- **WHEN** the command is lexed
- **THEN** the assignment carries the assignment kind and the following word is the command

## ADDED Requirements

### Requirement: AHereDocumentBodyIsInput

A here-document's body SHALL be handed on as one word of the here-document kind, in the segment of the command that reads it, holding the lines between the end of the operator's line and the delimiter line; the body SHALL NOT be split into segments, and SHALL be reported as unresolvable wherever bash would expand any part of it.

Serves: a-multi-line-command-is-read-line-by-line

Bash hands the body to the command's standard input.
A line in the body that reads as a command, such as `rm <file>`, runs only if the command that reads the body runs it, so the lexer makes it no segment.
Whether that command runs or applies its input is a question for each hook, which the lexer answers only by handing on the command beside the body.

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
- **WHEN** the command is lexed
- **THEN** its body is one here-document word holding the lines as written, and no line of it is a segment or a comment

#### Scenario: AnUnquotedBodyWithAnExpansionIsUnresolvable

- **GIVEN** a here-document whose delimiter is unquoted and whose body holds `$` or a backquote
- **WHEN** the command is lexed
- **THEN** the body is unresolvable, and a path inside it is still seen

#### Scenario: AnUnquotedBodyWithoutAnExpansion

- **GIVEN** a here-document whose delimiter is unquoted and whose body holds no `$` and no backquote
- **WHEN** the command is lexed
- **THEN** the body is a here-document word

#### Scenario: AnExpandedDelimiterIsUnresolvable

- **GIVEN** a here-document operator whose delimiter holds a parameter or a substitution
- **WHEN** the command is lexed
- **THEN** the command is reported as a whole as unresolvable

#### Scenario: TheRestOfTheOperatorLineIsReadFirst

- **GIVEN** a here-document operator followed on its line by a pipe or a list operator and another command
- **WHEN** the command is lexed
- **THEN** that command is a segment, and the body starts on the next line

#### Scenario: OnlyAnExactLineEndsTheBody

- **GIVEN** a body line that holds the delimiter followed by a space
- **WHEN** the command is lexed
- **THEN** the body does not end there

#### Scenario: TheDashFormStripsTabsOnly

- **GIVEN** a `<<-` here-document whose body lines and delimiter line begin with tabs, and one line that begins with spaces
- **WHEN** the command is lexed
- **THEN** the tabs are removed, the spaces are kept, and the tab-indented delimiter ends the body

#### Scenario: SeveralHereDocumentsOnOneCommand

- **GIVEN** a command carrying two here-document operators
- **WHEN** it is lexed
- **THEN** each body follows the operator it belongs to, in order

#### Scenario: AnUnterminatedHereDocumentIsUnresolvable

- **GIVEN** a here-document whose delimiter line never appears
- **WHEN** the command is lexed
- **THEN** the command is reported as a whole as unresolvable
