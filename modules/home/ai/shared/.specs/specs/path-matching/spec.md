# Spec: path-matching

## Purpose

A guarded location can be named by many spellings, and a hook that recognizes only one leaves the others open.
These requirements cover how a path is matched to a declared location whatever its spelling, when text matching applies, and the limits of that matching.

## Requirements

### Requirement: Purpose

The system SHALL provide one answer to the question every path-guarding hook asks: does this path, as supplied by a tool call, denote a location the caller must not modify?

The answer SHALL NOT depend on which hook asks it.
A guarded location that one hook refuses and another permits is not guarded.

### Requirement: GuardedLocations

A caller of this capability SHALL declare the locations it guards.

A guarded location SHALL be declared once.
A change to that declaration SHALL change every judgment about the location, for shell text and for resolved paths, with no other edit.

This exists to remove a failure mode that has occurred: the same location written twice, in two shapes, and one of the two updated when it moved.

The same SHALL hold for any narrower rule that applies within a guarded location: when the location changes, the rule SHALL move with it.
A carve-out that restates the location it applies within is the same failure mode in a different layer.

### Requirement: RepositoryContainment

A location declared as belonging to this repository SHALL be judged by the repository that contains the supplied path, not by the checkout the deciding code was loaded from.

A repository has more than one working tree over its life: a second clone, and a worktree.
A guarded source is guarded in each of them.

Membership SHALL NOT be established by the written form of a path alone.
A path that merely reads like a repository location — a backup, an archived copy — is not a repository location, and treating it as one refuses writes that carry no risk.

Where a supplied path names a location that does not yet exist, it SHALL still be judged.
Enumerating what is present would leave a file unguarded until the moment after it was created.

#### Scenario: SecondWorkingTree

- **GIVEN** a tool call names a guarded repository source
- **WHEN** the path lies in a different working tree of that repository
- **THEN** the path is treated as guarded

### Requirement: SpellingIndependence

A guarded location SHALL remain guarded when the supplied path reaches it by any of:

- home-relative notation
- traversal components that cancel earlier segments
- a symbolic link, at any depth, including a link that leaves the guarded location and returns to it
- a difference of letter case, where the filesystem treats such spellings as the same file

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

### Requirement: TextMatchingIsForTextThatMayHoldNoPath

The system SHALL judge a resolved word by where it leads, and SHALL judge an unresolvable word by whether its text contains the written form of a guarded location.

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

### Requirement: UnresolvablePathIsGuarded

Where a supplied path cannot be resolved, the system SHALL fall back to the best determination it can make from the path as written, and SHALL NOT treat failure to resolve as permission.

A path that cannot be examined is not thereby safe.
Resolution can fail for reasons a caller does not control, including a path the operating system refuses to interpret.
Treating that as an allow converts an unreadable input into an unguarded write.

#### Scenario: ResolutionFails

- **GIVEN** a tool call names a path that cannot be resolved
- **WHEN** the path as written denotes a guarded location
- **THEN** the path is treated as guarded

### Requirement: StatedLimits

The system SHALL NOT be represented as a boundary.

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
