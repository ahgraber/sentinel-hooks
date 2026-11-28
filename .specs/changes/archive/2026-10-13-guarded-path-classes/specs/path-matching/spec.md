# Delta for path-matching

## MODIFIED Requirements

### Requirement: TextMatchingIsForTextThatMayHoldNoPath

> Previously: the text question was asked of a whole shell command, so a declaration whose written form was a bare directory name had to opt out of text matching, and a relative path was judged by both questions because the working directory was not known.

The system SHALL judge a resolved word by where it leads, and SHALL judge an unresolvable word by whether its text contains the written form of a guarded location.

Serves: one-list-then-deltas, reads-are-frictionless

The written form of a declaration is the path as a command would write it, such as `.claude/settings.json`.

A resolved word is a path.
The hook judges it by the file or folder it leads to, never by its text.
If a resolved path were judged by its text, a backup directory, an archived copy, or an unrelated file with the same name would look guarded.
For the same reason, a declaration for an agent home cannot be matched as text: its written form, `.claude`, appears in ordinary commands that touch nothing guarded.

An unresolvable word, such as one with a substitution, leads to no location the system can find.
It is judged by its text, because a guarded location written inside it must still be found.
A hook MAY also judge a resolved word by its text if a program will run that word as code, such as an interpreter's inline program.
The reason is the same: the shell passes the word as one path, but the program can find many paths in it.

A relative path SHALL be resolved against the working directory the tool call supplies.
Where the tool call supplies none, the path is unresolvable, and refusing it on shape is the conservative reading of an ambiguous path.

#### Scenario: AbsolutePathOfGuardedShape

- **GIVEN** a tool call names an absolute path shaped like a guarded location
- **WHEN** it resolves outside every guarded location
- **THEN** the path is not treated as guarded

#### Scenario: RelativePathOfGuardedShape

- **GIVEN** a tool call names a relative path shaped like a guarded location
- **WHEN** the tool call supplies no working directory to resolve it against
- **THEN** the path is treated as guarded

#### Scenario: RelativePathResolvedAgainstTheSuppliedDirectory

- **GIVEN** a tool call names a relative path and supplies a working directory
- **WHEN** the path resolves outside every guarded location
- **THEN** the path is not treated as guarded

#### Scenario: ResolvedWordNamingADeclarationElsewhere

- **GIVEN** a shell command whose resolved word carries the written form of a guarded location
- **WHEN** the word resolves outside every guarded location
- **THEN** the command is not treated as naming a guarded location

#### Scenario: UnresolvableWordHoldingADeclaration

- **GIVEN** a shell command whose unresolvable word carries the written form of a guarded location
- **WHEN** the command is judged
- **THEN** the command is treated as naming a guarded location

### Requirement: SpellingIndependence

> Previously: spelling independence was stated for the supplied path alone, as written and as fully resolved, and nothing recorded that a declaration also covers every hop of its own link chain.

A guarded location SHALL remain guarded when the supplied path reaches it by any of:

- home-relative notation
- traversal components that cancel earlier segments
- a symbolic link, at any depth, including a link that leaves the guarded location and returns to it
- a difference of letter case, where the filesystem treats such spellings as the same file

Serves: one-list-then-deltas

A supplied path has a chain of hops: as written, with home notation and traversal applied, each link along the way, and the final target.
A declaration has a chain the same way.
Every hop of the path SHALL be judged against every hop of every declaration.
So a call that names a link is caught by a declaration of the target, a call that names the target is caught by a declaration of the link, and a store path in the middle of a chain is caught by a declaration of either end.

Case significance SHALL be determined per path, from the volume holding that path.
A checkout, a worktree, and a home directory need not share one volume, so a single determination made once for the caller is right for one of them and wrong for the others.

#### Scenario: SymbolicLinkAlias

- **GIVEN** a tool call names a path outside any guarded location
- **WHEN** that path is a symbolic link resolving to a guarded location
- **THEN** the path is treated as guarded

#### Scenario: DeclaredLinkReachedByItsTarget

- **GIVEN** a declaration names a symbolic link
- **WHEN** a tool call names the location the link resolves to
- **THEN** the path is treated as guarded

#### Scenario: IntermediateHopReached

- **GIVEN** a declaration names a link that resolves through an intermediate link to its target
- **WHEN** a tool call names the intermediate link
- **THEN** the path is treated as guarded

#### Scenario: TraversalSpelling

- **GIVEN** a tool call names a path containing traversal components
- **WHEN** the path denotes a guarded location once those components are applied
- **THEN** the path is treated as guarded

#### Scenario: CaseVariantOnCaseInsensitiveFilesystem

- **GIVEN** the filesystem treats two spellings differing only in letter case as the same file
- **WHEN** a tool call names a guarded location under a differing case
- **THEN** the path is treated as guarded

#### Scenario: CaseVariantOnCaseSensitiveFilesystem

- **GIVEN** the filesystem treats two spellings differing only in letter case as different files
- **WHEN** a tool call names a path differing only in case from a guarded location
- **THEN** the path is not treated as guarded, because it denotes a different file

### Requirement: StatedLimits

> Previously: the limits did not record that a declaration does not follow links held inside the directory it names, and stated that a command changing directory and then naming a target relatively was not judged against the changed directory.

The system SHALL NOT be represented as a boundary.

Serves: one-list-then-deltas

The following defeat it and SHALL be recorded wherever the capability is described:

- **A directory change the words do not resolve.**
  `shell-lexing` `EachSegmentCarriesTheDirectoriesItMayRunIn` judges a relative path after a resolved `cd` or `pushd` in every directory the command may be in.
  The forms that requirement lists as unresolved, among them a substituted operand, `cd -`, `cd -P`, `popd`, `eval`, `source`, and a function definition, leave no directory to judge against, so a relative path after one is an unresolvable word.
  A `CDPATH` set in the agent's shell rather than in the hook's environment, and the `pushd` stack, are not visible to the hook.
  `|&` is not read at all, so a command holding it is unresolvable as a whole.
  Agents are instructed to name paths absolutely.
- **Hard links.**
  A second name for the same file is indistinguishable by path.
- **Links held inside a declared directory.**
  A declaration names a location and follows that location's own chain.
  It does not follow the links held inside the directory it names, so the target of such a link is judged by whatever declarations cover the target.
  This matters only where the target lies under a stricter declaration, and `guarded-path-declarations` `ConflictingDeclarationsAreReported` reports that case.
- **Any route that does not present a path.**
  This capability inspects paths supplied by tool calls, and nothing else.

The operating system sandbox and the agent permission layer are the boundary.
This capability is defense in depth: it catches the accidental and the casual, and raises the cost of the deliberate.

## REMOVED Requirements

### Requirement: LocationsWithNoUsableWrittenForm

Removed because: the text question applies only to words that do not resolve.
So a declaration whose written form is a bare directory name does not cause extra refusals, and it does not need to opt out of text matching.
A broad directory is declared like any other location, and `TextMatchingIsForTextThatMayHoldNoPath` covers what `BroadDirectoryReachedByResolution` and `SameNameElsewhere` sampled.
