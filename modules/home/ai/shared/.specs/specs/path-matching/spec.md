# Spec: path-matching

## Requirement: Purpose

The system SHALL provide one answer to the question every path-guarding hook asks: does this path, as supplied by a tool call, denote a location the caller must not modify?

The answer SHALL NOT depend on which hook asks it.
A guarded location that one hook refuses and another permits is not guarded.

### Requirement: GuardedLocations

A caller of this capability SHALL declare the locations it guards.

A guarded location SHALL be declared once, in one form, and SHALL serve every use the caller makes of it.
Where a caller both matches a path against a fragment and compares it against a resolved location, both SHALL derive from the same declaration.

This exists to remove a failure mode that has occurred: the same location written twice, in two shapes, and one of the two updated when it moved.

Every use a caller makes of a declaration SHALL derive from it, including any narrower rule that applies within a guarded location.
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

### Requirement: LocationsWithNoUsableWrittenForm

A caller SHALL be able to declare a location that is guarded by where a path resolves and never by how it is written.

Some guarded locations have no written form specific enough to match as text.
An agent's home directory reduces to a bare directory name, which occurs throughout ordinary work; matching it as text would refuse every command that names a session transcript or a project-local agent definition.

Such a declaration SHALL contribute nothing to text matching, and SHALL still guard everything that resolves within it.

#### Scenario: BroadDirectoryReachedByResolution

- **GIVEN** a tool call names a path under an agent's home directory
- **WHEN** the path is written in full rather than in home-relative notation
- **THEN** the path is treated as guarded

#### Scenario: SameNameElsewhere

- **GIVEN** a tool call names a directory whose name matches a guarded one
- **WHEN** it resolves outside every guarded location
- **THEN** the path is not treated as guarded

### Requirement: SpellingIndependence

A guarded location SHALL remain guarded when the supplied path reaches it by any of:

- home-relative notation
- traversal components that cancel earlier segments
- a symbolic link, at any depth, including a link that leaves the guarded location and returns to it
- a difference of letter case, where the filesystem treats such spellings as the same file

Case significance SHALL be determined per path, from the volume holding that path.
A checkout, a worktree, and a home directory need not share one volume, so a single determination made once for the caller is right for one of them and wrong for the others.

#### Scenario: SymbolicLinkAlias

- **GIVEN** a tool call names a path outside any guarded location
- **WHEN** that path is a symbolic link resolving to a guarded location
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

The system SHALL distinguish the question asked of a path from the question asked of arbitrary text.

A path SHALL be judged by where it leads.
Arbitrary text — a whole shell command — SHALL be judged by whether it names a guarded location, because it may carry no path the system can resolve.

Applying the text question to a path is what makes a backup directory, an archived copy, or an unrelated file of the same name read as guarded.

A relative path is the exception, and SHALL be judged by both.
Its meaning depends on a working directory the system is not told, so it cannot be resolved with confidence, and refusing it on shape is the conservative reading of an ambiguous path.

#### Scenario: AbsolutePathOfGuardedShape

- **GIVEN** a tool call names an absolute path shaped like a guarded location
- **WHEN** it resolves outside every guarded location
- **THEN** the path is not treated as guarded

#### Scenario: RelativePathOfGuardedShape

- **GIVEN** a tool call names a relative path shaped like a guarded location
- **WHEN** the working directory it would resolve against is not known
- **THEN** the path is treated as guarded

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

- **Working-directory change within a single shell command.**
  A command that changes directory and then names a target relatively cannot be judged, because the working directory of the later part is not knowable from the command text.
- **Hard links.**
  A second name for the same file is indistinguishable by path.
- **Any route that does not present a path.**
  This capability inspects paths supplied by tool calls, and nothing else.

The operating system sandbox and the agent permission layer are the boundary.
This capability is defence in depth: it catches the accidental and the casual, and raises the cost of the deliberate.
