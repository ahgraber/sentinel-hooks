# Delta for Shell Lexing

## MODIFIED Requirements

### Requirement: EveryWordHasAKind

> Previously: a hook that decided from words decided from their kinds, so a word beginning with `-` was an option to every hook, whatever the program did with it.

A path hook SHALL give every word it judges exactly one kind: command, option, assignment, redirection target, pattern, path candidate, plain word, or unresolvable.

The kinds are disjoint and cover every word.
A hook that decides from words decides from their kinds, so a rule that applies to a path applies to path candidates and redirection targets, whichever hook holds the rule.

The command is the first word of a segment that is not an assignment.
An option is a word beginning with `-` in a position bash would pass to the program.
A redirection target is the operand of a redirection operator, whether or not a space separates the two.

The option kind describes the spelling, not what the program does with the word.
Which words a program takes as options, which words are their values, and which words it opens as files SHALL be decided by the reading `program-catalog` gives, where the program has a catalog entry; a hook SHALL NOT decide from the option kind alone that a word is not a file the program opens.
A word after `--`, a value that begins with `-`, and a negative number are options by spelling and operands or values by the reading.

Serves: every-argument-has-a-stated-effect

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

#### Scenario: AnOperandSpelledLikeAnOption

- **GIVEN** the segment `rm -- -precious`
- **WHEN** a path hook judges which files it removes
- **THEN** `-precious` is a removed file, though its kind is option
