# shell-lexing Specification

## Purpose

A hook that judges a shell command by the paths it names must read the command as the shell does, or a command can reach a guarded file through a spelling the hook reads differently.
These requirements cover how a path hook reads words and their kinds, splits a command into segments, tracks the directories each segment may run in, and reaches a verdict on every command.

## Requirements

### Requirement: OneReadingForEveryHook

Every path hook SHALL read a Bash command the same way.
A path hook is any hook that judges a Bash command by the paths it names.
If one path hook resolves a spelling, every path hook SHALL resolve it to the same words.
If one path hook treats a word as unresolvable, every path hook SHALL treat it as unresolvable.

Two readings of one command are two chances to hand a program a word neither reading judged.
A spelling one hook resolves and another does not is a route the second hook never sees.
A hook that matches patterns over the command text and names no path is outside this requirement.

#### Scenario: TwoHooksOneReading

- **GIVEN** two path hooks
- **WHEN** each judges the same command text
- **THEN** both judge the same segments and the same words

#### Scenario: ASpellingResolvedForOneIsResolvedForAll

- **GIVEN** a command spelling one path hook resolves
- **WHEN** any path hook judges that command
- **THEN** that hook judges the resolved words, not the spelling

### Requirement: AWordTheShellRewritesIsResolvedOrRefused

For any command, every word a path hook judges SHALL be a word bash would pass to the program.
If the hook cannot tell how bash expands a word, it SHALL treat the word as unresolvable.
It SHALL NOT judge that word as written.

Bash is the reference shell.
The shell builds the words a program receives after the hook has counted them, and where the two readings differ the program receives something the hook never judged.
`{--output=/tmp/out,FILE}`, `${UNSET:---output=/tmp/out} FILE`, `?-output=/tmp/out FILE`, and `$'\x2d\x2doutput=/tmp/out' FILE` each reach a program as the option the same command is gated for when it is written plainly.

Quoting is resolved, ANSI-C quoting included, because what a quoted word stands for follows from the text.
Tilde is resolved against the home the hook runs under, and so is `$HOME` or `${HOME}` at the start of a word, which bash expands to the same directory.
After a command assigns `HOME`, both are unresolvable, because the home the hook runs under is no longer the one bash uses.
Pathname expansion is resolved against each directory the segment may run in, and a pattern matching nothing stays as written, which is what bash does with `nullglob` unset.
If a glob character, such as `*` or `?`, is inside quotes or follows a backslash, the word is unresolvable.
Bash reads that character as itself, but the hook would read it as a pattern.
Quotes around other parts of the word do not stop the expansion.

Every other substitution, and brace expansion, are unresolvable.
Such a substitution names a value the hook's environment does not hold; a brace expansion states its words in text the hook would have to build for itself.
Unresolvable is not a verdict: each hook decides what an unresolvable word means for the command.

A path hook SHALL still see the paths written inside an unresolvable word.
Otherwise, the syntax that stops the hook from judging a word would also hide the paths in it.

#### Scenario: AQuotedWordIsResolved

- **GIVEN** a word in any quoting form, ANSI-C quoting included
- **WHEN** a path hook judges the command
- **THEN** the hook judges the characters the shell would pass

#### Scenario: APatternIsResolvedByWhatItMatches

- **GIVEN** a word carrying a pathname pattern that matches entries in the supplied working directory
- **WHEN** a path hook judges the command
- **THEN** the hook judges the matched names in its place

#### Scenario: APatternMatchingNothingStaysAsWritten

- **GIVEN** a word carrying a pathname pattern that matches nothing
- **WHEN** a path hook judges the command
- **THEN** the hook judges the word as written, as a pattern rather than a path

#### Scenario: ASubstitutionIsUnresolvable

- **GIVEN** a word carrying a parameter or command substitution other than a leading `$HOME`
- **WHEN** a path hook judges the command
- **THEN** the hook treats the word as unresolvable

#### Scenario: ALeadingHomeReferenceIsResolved

- **GIVEN** a word beginning with `$HOME` or `${HOME}`, quoted or not
- **WHEN** a path hook judges the command
- **THEN** the hook puts the home it runs under in place of the home reference, as it does for a leading `~`

#### Scenario: AHomeAssignmentUnresolvesLaterHomeWords

- **GIVEN** `HOME=/x; cat ~/a` or `export HOME=/x; cat $HOME/a`
- **WHEN** a path hook judges the command
- **THEN** the hook treats the home-relative word as unresolvable

#### Scenario: APatternQuotedOnlyAroundLiteralTextIsResolved

- **GIVEN** `cat ~/.config/"mcp"*`
- **WHEN** a path hook judges the command
- **THEN** the hook judges the pattern by what it matches, as it judges `cat ~/.config/mcp*`

#### Scenario: AQuotedGlobCharacterIsUnresolvable

- **GIVEN** `cat '*'x*`
- **WHEN** a path hook judges the command
- **THEN** the hook treats the word as unresolvable

#### Scenario: ABraceExpansionIsUnresolvable

- **GIVEN** a word carrying a brace expansion
- **WHEN** a path hook judges the command
- **THEN** the hook treats the word as unresolvable

#### Scenario: APathInsideAnUnresolvableWordIsStillSeen

- **GIVEN** a path written inside a word that is unresolvable
- **WHEN** a path hook judges the command
- **THEN** the hook sees that path

#### Scenario: BashRunsOnlyWordsTheHookJudged

- **GIVEN** any command whose words are all resolvable
- **WHEN** bash runs it with every program replaced by a recorder
- **THEN** every word a program receives is one a path hook judged for that program

### Requirement: EveryWordHasAKind

A path hook SHALL give every word it judges exactly one kind: command, option, assignment, redirection target, pattern, path candidate, plain word, or unresolvable.

The kinds are disjoint and cover every word.
A hook that decides from words decides from their kinds, so a rule that applies to a path applies to path candidates and redirection targets, whichever hook holds the rule.

The command is the first word of a segment that is not an assignment.
An option is a word beginning with `-` in a position bash would pass to the program.
A redirection target is the operand of a redirection operator, whether or not a space separates the two.

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

### Requirement: APathCandidateDenotesAFile

A word SHALL be a path candidate only where it denotes a file: it carries a path separator or a leading tilde, or it names an entry that exists relative to the directory the tool call supplies.
A redirection target keeps its own kind, and a rule that applies to a path SHALL apply to a redirection target as well.
A word beginning with `-` in an option position SHALL retain the option kind even where an entry of that name exists; the option rule takes precedence over the existing-entry rule.

A rule that guesses contents from a name has nothing to guess about a word that names no file.
A search pattern, a commit subject, and a selector expression are words a read utility receives, and none of them is read from disk.
Refusing one costs a prompt on ordinary work, and on an agent whose gate is a refusal it stops the work.

A word that denotes a file whether or not the file exists, because it carries a separator, is a candidate whether or not the file exists.
A path a command would create is a path.

#### Scenario: ABareWordThatNamesNoEntry

- **GIVEN** a word with no separator and no leading tilde, naming no entry in the supplied working directory
- **WHEN** a path hook judges the command
- **THEN** the hook does not judge the word as a path candidate

#### Scenario: ABareWordThatNamesAnEntry

- **GIVEN** the same word, where an entry of that name exists in the supplied working directory
- **WHEN** a path hook judges the command
- **THEN** the hook judges the word as a path candidate

#### Scenario: AWordWithASeparator

- **GIVEN** a word carrying a path separator, naming a file that does not exist
- **WHEN** a path hook judges the command
- **THEN** the hook judges the word as a path candidate

#### Scenario: AnInputRedirectionOperand

- **GIVEN** a bare word that is the operand of an input redirection
- **WHEN** a path hook judges the command
- **THEN** the hook treats the word as a redirection target, not a path candidate, and a path rule for the command still applies to it

### Requirement: SegmentsFollowControlOperators

A path hook SHALL split a command into the segments bash runs.
Pipes, list operators, and subshell boundaries separate the segments.
Each segment holds one command word and the words bash passes with it.
If a command contains a newline, the hook SHALL treat the whole command as unresolvable.

A hook judges a segment by its command word, so the split decides which words each rule sees.
A newline separates commands the same way `;` does, and a backslash before it does not; which reading applies is not yet established, so the whole command is refused rather than half-read.

#### Scenario: APipelineIsSplit

- **GIVEN** a command joining two programs with a pipe
- **WHEN** a path hook judges it
- **THEN** the hook judges two segments, each with its own command word

#### Scenario: AQuotedOperatorDoesNotSplit

- **GIVEN** a command carrying a pipe or list operator inside quotes
- **WHEN** a path hook judges it
- **THEN** the hook judges one segment, and the operator is part of a word

#### Scenario: ANewlineRefusesTheCommand

- **GIVEN** a command carrying a newline
- **WHEN** a path hook judges it
- **THEN** the hook treats the command as unresolvable as a whole

### Requirement: EachSegmentCarriesTheDirectoriesItMayRunIn

A path hook SHALL judge each segment in every directory where bash can run it.
After a directory change, the hook SHALL judge a relative path in each of those directories.
If a directory change before a segment does not resolve, the hook SHALL treat the segment's directory as unknown.

A relative path names a file only together with the directory it is read in.
A hook that judged it against the directory the tool call supplies would judge a different file from the one the program opens.

A `cd` or `pushd` moves the segments after it when it stands in command position: first after any assignments, after an unquoted reserved word such as `!`, `{`, `if`, `then`, or `do`, or after `builtin` or `command` and their own leading options, unless those include `-v` or `-V`.
A quoted reserved word is an ordinary command name, so `'if' cd sub` runs a program called `if`.
Options end at `--`, so `cd -- -L` enters a directory named `-L`.
Elsewhere the word is an operand: `grep cd file` and `env cd sub` do not move the shell.

The change may succeed or fail, and the list operators decide which segments run after each.
A segment joined by `&&` runs only after a success, one joined by `||` only after a failure, `!` swaps the two, and one joined by `;` runs either way.
For each directory the shell can be in, the hook also keeps whether the command that led there succeeded or failed, where that is known.
So `cd A || cd B && cat a` runs in `A` or `B`, and `cd sub; cat a` runs in the starting directory or in `sub`.
A change inside a subshell, a pipeline, or a background job does not outlast it, and a redirection after a subshell opens its target where the subshell started.
A `cd` given an empty operand fails.

A segment's directory is unknown after any of these:

- a change to a substituted operand, `cd -`, `cd -P`, `popd`, or a `pushd` with no operand or a stack position
- a command word that is a substitution, and `eval`, `source`, `.`, `trap`, or `shopt`, which run text these words do not show or change how `cd` resolves
- a function definition, since calling it later may run any `cd` in its body
- a `cd` inside a `for`, `select`, `while`, or `until` loop, which may run any number of times
- an assignment to `HOME` or `CDPATH`, which change where `cd` goes
- a bare relative operand while the hook's own environment sets `CDPATH`

#### Scenario: AChangeThenAPath

- **GIVEN** `cd sub && cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in `sub`, and judges `sub/a` among its paths

#### Scenario: AChangeThatMayFail

- **GIVEN** `cd sub; cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in the starting directory and in `sub`, and judges its relative word in both

#### Scenario: AChangeOnlyAFailureFollows

- **GIVEN** `cd sub || cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in the starting directory

#### Scenario: AMixedChain

- **GIVEN** `cd A || cd B && cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the last segment in `A` and in `B`

#### Scenario: AChangeBehindAReservedWord

- **GIVEN** `if cd sub; then cat a; fi`, `! cd sub || cat a`, or `command -p cd sub && cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the segment holding `cat a` in `sub`, among the directories it may run in

#### Scenario: ACdWordThatIsAnOperand

- **GIVEN** `grep cd file && cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in the starting directory

#### Scenario: ATextRunningBuiltin

- **GIVEN** `eval cd sub; cat a`, `source env.sh; cat a`, or `f() { cd sub; }; f; cat a`
- **WHEN** a path hook judges it
- **THEN** the hook treats the directory of the segment holding `cat a` as unknown

#### Scenario: AChangeInsideALoop

- **GIVEN** `for i in 1 2; do cd sub; done; cat a`
- **WHEN** a path hook judges it
- **THEN** the hook treats the directory of the segment holding `cat a` as unknown

#### Scenario: AQuotedReservedWord

- **GIVEN** `'if' cd sub && cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in the starting directory

#### Scenario: AnOperandAfterTheEndOfOptions

- **GIVEN** `cd -- -L && cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in `-L`

#### Scenario: ARedirectionAfterASubshell

- **GIVEN** `(cd sub && true) > out`
- **WHEN** a path hook judges it
- **THEN** the hook judges the redirection target `out` in the starting directory

#### Scenario: AChangeInsideASubshell

- **GIVEN** `(cd sub); cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in the starting directory

#### Scenario: AChangeInAPipeline

- **GIVEN** `cd sub | cat a`
- **WHEN** a path hook judges it
- **THEN** the hook judges the second segment in the starting directory

#### Scenario: AnUnresolvedChange

- **GIVEN** `cd $DIR && cat a`
- **WHEN** a path hook judges it
- **THEN** the hook treats the second segment's directory as unknown, and its relative word as unresolvable

### Requirement: EveryCommandReachesAVerdict

For any command text, a path hook SHALL reach its verdict by applying its rules.
If the hook cannot read the text, it SHALL treat the text as unresolvable and apply its rules to that.
A hook error SHALL NOT decide the verdict.

If a hook fails on input it did not expect, its error handling decides the outcome.
Where that handling lets the call proceed, the command that broke the hook proceeds unchecked.

#### Scenario: ArbitraryText

- **GIVEN** any string, including one that is no shell command
- **WHEN** a path hook judges it
- **THEN** the hook reaches a verdict from its rules, not from an error

#### Scenario: ArbitraryUnicode

- **GIVEN** a string carrying characters outside ASCII, including a null byte and a component of unusual length
- **WHEN** a path hook judges it
- **THEN** the hook reaches a verdict from its rules, not from an error
