# Delta for shell-lexing

## ADDED Requirements

### Requirement: OneLexerForEveryHook

Every hook that judges a Bash command by the paths it names SHALL obtain the command's segments and words from this capability, and SHALL NOT carry a second reading of the command.

Serves: one-lexer

Two readings of one command are two chances to hand a program a word neither reading judged.
A spelling one hook resolves and another does not is a route the second hook never sees.
A hook that matches patterns over the command text and names no path is outside this requirement.

#### Scenario: TwoHooksOneReading

- **GIVEN** two hooks that judge a Bash command by the paths it names
- **WHEN** each reads the same command text
- **THEN** each receives the same segments and the same words, because both obtain them from this capability

#### Scenario: ASpellingResolvedForOneIsResolvedForAll

- **GIVEN** a command spelling this capability resolves
- **WHEN** any hook judges that command
- **THEN** that hook judges the resolved words, not the spelling

### Requirement: AWordTheShellRewritesIsResolvedOrRefused

For any command, every word this capability hands a hook SHALL be a word bash would hand the program, and a word whose expansion this capability cannot determine SHALL be reported as unresolvable rather than handed on as written.

Serves: one-lexer, reads-are-frictionless

Bash is the reference shell.
The shell builds the words a program receives after the hook has counted them, and where the two readings differ the program receives something the hook never judged.
`{--output=/tmp/out,FILE}`, `${UNSET:---output=/tmp/out} FILE`, `?-output=/tmp/out FILE`, and `$'\x2d\x2doutput=/tmp/out' FILE` each reach a program as the option the same command is gated for when it is written plainly.

Quoting is resolved, ANSI-C quoting included, because what a quoted word stands for follows from the text.
Tilde is resolved against the home the hook runs under.
Pathname expansion is resolved against the directory the tool call supplies, and a pattern matching nothing stays as written, which is what bash does with `nullglob` unset.

Substitution and brace expansion are refused.
A substitution names a value the hook's environment does not hold; a brace expansion states its words in text the hook would have to build for itself.
A refusal is a report, not a verdict: the hook that receives an unresolvable word decides what that means for the command.

An unresolvable word SHALL still yield the paths written inside it.
Otherwise the syntax that stops a word being judged also stops it being seen.

#### Scenario: AQuotedWordIsResolved

- **GIVEN** a word in any quoting form, ANSI-C quoting included
- **WHEN** the command is lexed
- **THEN** the word is handed on as the characters the shell would pass

#### Scenario: APatternIsResolvedByWhatItMatches

- **GIVEN** a word carrying a pathname pattern that matches entries in the supplied working directory
- **WHEN** the command is lexed
- **THEN** the matched names are handed on in its place

#### Scenario: APatternMatchingNothingStaysAsWritten

- **GIVEN** a word carrying a pathname pattern that matches nothing
- **WHEN** the command is lexed
- **THEN** the word is handed on as written, and it is a pattern rather than a path

#### Scenario: ASubstitutionIsUnresolvable

- **GIVEN** a word carrying a parameter or command substitution
- **WHEN** the command is lexed
- **THEN** the word is reported as unresolvable

#### Scenario: ABraceExpansionIsUnresolvable

- **GIVEN** a word carrying a brace expansion
- **WHEN** the command is lexed
- **THEN** the word is reported as unresolvable

#### Scenario: APathInsideAnUnresolvableWordIsStillSeen

- **GIVEN** a path written inside a word that is unresolvable
- **WHEN** the command is lexed
- **THEN** that path is reported among the paths the word holds

#### Scenario: BashRunsOnlyWordsTheLexerHanded

- **GIVEN** any command whose words are all resolvable
- **WHEN** bash runs it with every program replaced by a recorder
- **THEN** every word a program receives is one the lexer handed on for that program

### Requirement: EveryWordHasAKind

Every word this capability hands on SHALL carry exactly one kind: command, option, assignment, redirection target, pattern, path candidate, plain word, or unresolvable.

Serves: one-lexer, reads-are-frictionless

The kinds are disjoint and cover every word.
A hook that decides from words decides from their kinds, so a rule that applies to a path applies to path candidates and redirection targets, whichever hook holds the rule.

The command is the first word of a segment that is not an assignment.
An option is a word beginning with `-` in a position bash would pass to the program.
A redirection target is the operand of a redirection operator, whether or not a space separates the two.

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

### Requirement: APathCandidateDenotesAFile

A word SHALL be a path candidate only where it denotes a file: it carries a path separator or a leading tilde, or it names an entry that exists relative to the directory the tool call supplies.
A redirection target keeps its own kind, and a rule that applies to a path SHALL apply to a redirection target as well.
A word beginning with `-` in an option position SHALL retain the option kind even where an entry of that name exists; the option rule takes precedence over the existing-entry rule.

Serves: reads-are-frictionless

A rule that guesses contents from a name has nothing to guess about a word that names no file.
A search pattern, a commit subject, and a selector expression are words a read utility receives, and none of them is read from disk.
Refusing one costs a prompt on ordinary work, and on an agent whose gate is a refusal it stops the work.

A word that denotes a file whether or not the file exists, because it carries a separator, is a candidate whether or not the file exists.
A path a command would create is a path.

#### Scenario: ABareWordThatNamesNoEntry

- **GIVEN** a word with no separator and no leading tilde, naming no entry in the supplied working directory
- **WHEN** the command is lexed
- **THEN** the word is not a path candidate

#### Scenario: ABareWordThatNamesAnEntry

- **GIVEN** the same word, where an entry of that name exists in the supplied working directory
- **WHEN** the command is lexed
- **THEN** the word is a path candidate

#### Scenario: AWordWithASeparator

- **GIVEN** a word carrying a path separator, naming a file that does not exist
- **WHEN** the command is lexed
- **THEN** the word is a path candidate

#### Scenario: AnInputRedirectionOperand

- **GIVEN** a bare word that is the operand of an input redirection
- **WHEN** the command is lexed
- **THEN** the word is a redirection target and not a path candidate, and a path rule applied to the command judges it

### Requirement: SegmentsFollowControlOperators

A command SHALL be split into segments at pipes, list operators, and subshell boundaries, each segment holding one command word and the words bash would pass with it, and a command carrying a newline SHALL be reported as a whole as unresolvable.

Serves: one-lexer

A hook judges a segment by its command word, so the split decides which words each rule sees.
A newline separates commands the same way `;` does, and a backslash before it does not; which reading applies is not yet established, so the whole command is refused rather than half-read.

#### Scenario: APipelineIsSplit

- **GIVEN** a command joining two programs with a pipe
- **WHEN** it is lexed
- **THEN** two segments result, each with its own command word

#### Scenario: AQuotedOperatorDoesNotSplit

- **GIVEN** a command carrying a pipe or list operator inside quotes
- **WHEN** it is lexed
- **THEN** one segment results, and the operator is part of a word

#### Scenario: ANewlineRefusesTheCommand

- **GIVEN** a command carrying a newline
- **WHEN** it is lexed
- **THEN** the command is reported as unresolvable as a whole

### Requirement: LexingIsTotal

For any text, this capability SHALL return segments and words or report the text as unresolvable, and SHALL NOT raise.

Serves: one-lexer

A hook that raises on an input it did not foresee reaches its failure branch, and where that branch proceeds, the syntax that broke the lexer is the syntax that proceeds unjudged.

#### Scenario: ArbitraryText

- **GIVEN** any string, including one that is no shell command
- **WHEN** it is lexed
- **THEN** a result or an unresolvable report is returned

#### Scenario: ArbitraryUnicode

- **GIVEN** a string carrying characters outside ASCII, including a null byte and a component of unusual length
- **WHEN** it is lexed
- **THEN** a result or an unresolvable report is returned
