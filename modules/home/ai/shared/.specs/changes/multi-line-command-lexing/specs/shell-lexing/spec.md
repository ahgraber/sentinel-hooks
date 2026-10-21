# Delta for shell-lexing

## MODIFIED Requirements

### Requirement: SegmentsFollowControlOperators

> Previously: a path hook treated a command that contains a newline as unresolvable as a whole.

A path hook SHALL read a command as bash reads it: into the segments bash runs, each holding one command word and the words bash passes with it, whether the command is written on one line or across lines.
Bash is the reference shell; where POSIX `sh` and bash differ, the hook follows bash.
Where the hook cannot read text as bash does, it SHALL treat the command as unresolvable as a whole, and SHALL NOT hand on segments or words bash would not run or pass.

Serves: a-multi-line-command-is-read-line-by-line

A hook judges a segment by its command word, so the split decides which words each rule sees.
A reading that differs from bash either hides a command bash runs or invents one it does not.

Bash's grammar is the specification of the reading, and this requirement does not restate it.
A restatement is a second grammar, and it drifts from bash where bash's rules are least obvious: quotes inside nested expansions, continuations, comments, and here-document delimiters.
Conformance is checked against bash itself: a property runs generated commands through bash with every program replaced by a recorder, and compares what each program receives with what the hook read.
A form the hook does not yet read as bash does is a gap, recorded with a test that states bash's reading; it is not part of this requirement.

#### Scenario: AReadingMatchesBash

- **GIVEN** a command bash accepts, on one line or across lines
- **WHEN** a path hook reads it
- **THEN** the hook judges the segments bash runs and the words bash passes to each program, or treats the command as unresolvable as a whole

#### Scenario: APipelineIsSplit

- **GIVEN** a command joining two programs with a pipe
- **WHEN** a path hook judges it
- **THEN** the hook judges two segments, each with its own command word

#### Scenario: AQuotedOperatorDoesNotSplit

- **GIVEN** a command carrying a pipe or list operator inside quotes
- **WHEN** a path hook judges it
- **THEN** the hook judges one segment, and the operator is part of a word

#### Scenario: UnreadableTextIsUnresolvable

- **GIVEN** a command holding text the hook does not read as bash does, such as an unclosed quote, a carriage return, a null byte, or a form recorded as a gap
- **WHEN** a path hook judges it
- **THEN** the hook treats the command as unresolvable as a whole

<!-- modified-removes: ANewlineRefusesTheCommand -->

### Requirement: EveryWordHasAKind

> Previously: the kinds were command, option, assignment, redirection target, pattern, path candidate, plain word, and unresolvable.

A path hook SHALL give every word it judges exactly one kind: command, option, assignment, redirection target, here-document, pattern, path candidate, plain word, or unresolvable.

Serves: a-multi-line-command-is-read-line-by-line

The kinds are disjoint and cover every word.
A hook that decides from words decides from their kinds, so a rule that applies to a path applies to path candidates and redirection targets, whichever hook holds the rule.

The command is the first word of a segment that runs a program and is not an assignment; a loop header, a `case` subject or pattern, `((…))`, and `[[ … ]]` run no program, so no word of theirs is the command.
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

A path hook SHALL judge a here-document body as one word of the here-document kind, holding the text bash delivers to the standard input of the command that reads it.
The word belongs to that command's segment.
The hook SHALL NOT split the body into segments.
If bash would expand any part of the body, the hook SHALL treat the body as unresolvable.

Serves: a-multi-line-command-is-read-line-by-line

Bash decides where the body starts and ends and what it delivers; `SegmentsFollowControlOperators` makes that reading bash's.
A line in the body that reads as a command, such as `rm <file>`, runs only if the command that reads the body runs it, so the line is not a segment.
Each hook decides whether that command runs its input or acts on it, and judges the body together with that command.

An expanded part has a value only bash knows when the command runs, so the body is unresolvable as any expanded word is, and a path inside it is still seen.

#### Scenario: ABodyIsNotASegment

- **GIVEN** a here-document whose body holds lines that read as commands, comments, or list operators
- **WHEN** a path hook judges the command
- **THEN** the hook judges the body as one here-document word holding the text bash delivers, and no line of it is a segment or a comment

#### Scenario: AnExpandedBodyIsUnresolvable

- **GIVEN** a here-document whose body bash would expand in part
- **WHEN** a path hook judges the command
- **THEN** the hook treats the body as unresolvable, and still sees a path inside it
