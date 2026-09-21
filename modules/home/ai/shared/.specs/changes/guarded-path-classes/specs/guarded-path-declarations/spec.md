# Delta for guarded-path-declarations

## MODIFIED Requirements

### Requirement: SingleDeclarationSource

> Previously: the manifest declared the gated protected classes split into deployed and source lists, the agent credential class, the instruction layers, the location-only roots, and the secret-floor representatives, and the read-through and exec-through locations were declared with no requirement recording them.

The system SHALL declare the guarded surface in one manifest as one guarded list and the deltas to it: the block class, the exec-through class, the write-through class, and the declared exceptions.

Serves: one-list-then-deltas

Every enforcement implementation SHALL take these declarations from the manifest rather than carrying a copy.
A copy is a second authoring surface, and a second authoring surface is where one platform or one implementation gets left behind.

The manifest SHALL carry nothing that exists only to steer how an implementation matches.
A table that exempts an entry from one matcher, or that lists locations a read may proceed under, encodes the implementation rather than the policy, and an operator reading it cannot tell what was decided.

#### Scenario: TwoImplementationsOneSource

- **GIVEN** two implementations of the tamper policy in different languages
- **WHEN** each judges the same path
- **THEN** they reach the same verdict, because both read the same declarations

#### Scenario: AddedPathReachesEveryConsumer

- **GIVEN** a path is added to a manifest class
- **WHEN** any enforcement implementation next judges that path
- **THEN** the path is treated as a member of that class, with no edit to the implementation

#### Scenario: OnlyPolicyTablesExist

- **GIVEN** the manifest
- **WHEN** its tables are enumerated
- **THEN** each is one of the guarded list, the block class, the exec-through class, the write-through class, or the exceptions

### Requirement: ConfigurationSurfacesCoverTheDeclarations

> Previously: every configuration surface that gates by path had to cover every gated declaration and every credential declaration as a floor, including the editor's edit-approval globs over the repository sources.

Every configuration surface that refuses access by path SHALL refuse the block class as a floor: the per-user agent permission lists and the per-user OS sandbox lists.

Serves: floors-are-checked-where-a-miss-is-unrecoverable

A surface MAY refuse more than the block class.
What must not happen is the reverse, where the manifest blocks something no surface entry refuses, because then a hook is the only thing standing between an agent and a credential, and a credential read cannot be undone.

The guarded class is not held to a floor.
A guarded location asks rather than refuses, so its floor entry would be an ask rule, and the surfaces cannot express an ask with a carve-out beneath it.
A base declaration for a directory with a write-through directory inside it has no surface equivalent, and demanding one turns every manifest edit into a settings edit the surface cannot be given.
An unprompted edit to a guarded location is recoverable through version control, which is why the hook rather than the floor is where the ask lives.

Coverage SHALL be judged against concrete representative paths, not by comparing pattern text.
A pattern that looks right and does not match is the failure this requirement exists to catch.
The representatives SHALL include paths standing for the operating-system secret stores the block class does not enumerate, held beside the assessment that judges the surfaces rather than in the manifest, because they are evidence for the floor and not policy.
The judgment is an assessment of each agent's configuration against this requirement, not a test in the hooks package: the package is independent of any agent's configuration, per `security-posture-alignment`.

<!-- modified-removes: EditApprovalFloor -->

#### Scenario: AgentPermissionFloor

- **GIVEN** a per-user agent permission list
- **WHEN** it is checked against the block representatives
- **THEN** every representative is refused by a rule in that list

#### Scenario: SandboxFloor

- **GIVEN** a per-user OS sandbox configuration
- **WHEN** it is checked against the block representatives
- **THEN** every representative is refused by an entry in that configuration

#### Scenario: GuardedDeclarationWithNoFloorEntry

- **GIVEN** a guarded declaration no surface entry covers
- **WHEN** conformance is checked
- **THEN** the surface passes

### Requirement: LoadFailureIsReported

> Previously: every tool call proceeded when the manifest could not be loaded, with the failure reported, on the grounds that the sandbox and permission layers kept enforcing.

Where an implementation cannot load the manifest, a call to a tool the implementation gates SHALL reach the user as an `Ask`, refused where the invoking agent honors no prompt, and a call to a tool it is registered for but does not gate, such as `Read`, SHALL proceed; in every case the failure SHALL be reported where the invoking agent can report it.

Serves: one-list-then-deltas

A manifest that is absent, that does not parse, or that lacks a required table leaves the implementation with no policy at all.
A mutation judged against no policy is a mutation nothing checked, and `hook-interface` `ErrorHandlingByDamagePotential` already requires that a sensitive tool not proceed on a failure to judge.
`Ask` rather than `Block` for the reason the tamper hook's `FailureMode` gives: most mutating calls reach nothing guarded, and a fault that recurs would otherwise refuse every mutation with no route left for the user.
The prompt is the pressure to repair the manifest, and the repair is made outside the agent; no approval grants unchecked operation beyond the one call it approves.

A read-only tool proceeds under the approved internal-error posture.
Independent strong rules continue to apply, and a valid block list remains usable when another part of the manifest fails validation.
An absent or unparsable manifest supplies no block declarations; the strong rules alone do not cover every declared credential path.
Where a harness has a sandbox read-deny floor, that floor remains in force.

It SHALL NOT be silent: a guard that quietly checks nothing is how the guarded surface disappears without anyone noticing.

#### Scenario: MissingManifest

- **GIVEN** the manifest file is absent
- **WHEN** a tool call is intercepted
- **THEN** a mutating call asks and a read proceeds, and the failure is reported where the agent can show it

#### Scenario: UnparsableManifest

- **GIVEN** the manifest file cannot be parsed
- **WHEN** a tool call is intercepted
- **THEN** a mutating call asks and a read proceeds, and the failure is reported where the agent can show it

#### Scenario: MissingRequiredTable

- **GIVEN** the manifest parses but lacks one of its required tables
- **WHEN** a mutating tool call is intercepted
- **THEN** the decision is `Ask`, refused where the agent honors no prompt, and the reason names the missing table

#### Scenario: MutationOnAnAgentThatCannotPrompt

- **GIVEN** the manifest cannot be loaded
- **WHEN** a mutating tool call is intercepted on an agent that honors no prompt
- **THEN** the call is refused, and the reason names the load failure

## ADDED Requirements

### Requirement: TheGuardedClassIsTheBase

A guarded declaration SHALL cover the declared location and everything beneath it, and within it a read SHALL proceed, while a write, a removal, a rename, or a run SHALL reach the user as an `Ask`, refused where the invoking agent honors no prompt.

Serves: one-list-then-deltas, reads-are-frictionless

A read of a guarded location carries no risk the ask would address.
The location holds enforcement an agent may inspect, instructions it is meant to load, and skills it is meant to use; the operating-system sandbox and the block class are what stand between an agent and material it must not see.
Every guarded location has therefore been readable in practice since 2026-09-02, and declaring it so is what lets the read-through table go.

#### Scenario: ReadOfAGuardedLocation

- **GIVEN** a location covered by a guarded declaration and by no block declaration
- **WHEN** a tool call reads a file there
- **THEN** the call proceeds on every agent

#### Scenario: WriteBeneathAGuardedLocation

- **GIVEN** a location covered by a guarded declaration
- **WHEN** a tool call writes a file beneath it
- **THEN** the decision is `Ask`, and the call is refused where the agent honors no prompt

#### Scenario: RunBeneathAGuardedLocation

- **GIVEN** a location covered by a guarded declaration and by no exec-through declaration
- **WHEN** a shell command runs a program held there
- **THEN** the decision is `Ask`

### Requirement: ADeltaClassChangesOneOutcome

Each delta class SHALL change exactly one outcome of the guarded base for the locations it declares: the block class refuses every operation, reads included, on every agent; the exec-through class lets a run of a program already held there proceed; the write-through class lets a write proceed.

An exec-through or write-through declaration SHALL also supply the guarded base for that location, even without a separate guarded declaration.
The operation-specific carve-out overrides this implicit base under `PrecedenceIsOneRule`.

Serves: one-list-then-deltas, skill-scripts-run

A class that changed two outcomes at once would make every location a later change declares for one purpose also serve the other.
Running a file is a wider grant than reading it, and writing one is a different grant again, so each is declared on its own.

#### Scenario: BlockRefusesAReadAndAWrite

- **GIVEN** a location covered by a block declaration
- **WHEN** a tool call reads or writes it
- **THEN** the call is refused on every agent, with no prompt

#### Scenario: ExecThroughDoesNotMakeWritable

- **GIVEN** a location covered by an exec-through declaration
- **WHEN** a tool call writes a file there
- **THEN** the decision is `Ask`

#### Scenario: WriteThroughDoesNotMakeRunnable

- **GIVEN** a location covered by a write-through declaration and by no exec-through declaration
- **WHEN** a shell command runs a program held there
- **THEN** the decision is `Ask`

### Requirement: PrecedenceIsOneRule

For every hop in a supplied path's link chain, the system SHALL find the declarations covering that hop and reach a verdict there: block decides first; for writes and runs, the enforcement floor decides guarded next; otherwise the closest declaration decides.
The path's verdict SHALL be the strictest across its hops, and the order of declarations in the manifest SHALL NOT affect any verdict.

Serves: one-list-then-deltas

A hop is the path as written, each link along the way, and the final target, per `path-matching` `SpellingIndependence`.
The closest declaration is the one whose declared location lies the fewest path segments above the hop, measured in the spelling where it matched; a declaration naming the file itself is closest of all.
Where two declarations lie at the same distance in different classes, the delta class decides, because declaring a carve-out at exactly a guarded location is the intent of writing it.
This tie rule cannot override the enforcement floor.
Strictness runs block over guarded over carve-out over undeclared.

A write consults the write-through and guarded classes.
A run consults the exec-through and guarded classes.
A read consults the block class alone.
The guarded class includes the implicit base supplied by each exec-through and write-through declaration.
A removal, rename, or replacement is a write.

One rule covers restriction and permission alike.
A restriction holds when any hop reaches it, so a write through a link named under a carve-out still asks when the link leads to enforcement.
A permission holds only when every hop allows it, and a hop no declaration covers allows everything, so a link from a carve-out into undeclared space keeps the carve-out.
Fixing precedence this way is what lets a carve-out be written beneath a base and a base be restated beneath a carve-out.

#### Scenario: BlockBeneathWriteThrough

- **GIVEN** a block declaration for a file beneath a write-through directory
- **WHEN** a tool call writes that file
- **THEN** the call is refused

#### Scenario: WriteThroughBeneathGuarded

- **GIVEN** a write-through declaration for a directory beneath a guarded one
- **WHEN** a tool call writes a file in that directory
- **THEN** the call proceeds

#### Scenario: GuardedBeneathWriteThrough

- **GIVEN** a guarded declaration for a directory beneath a write-through one
- **WHEN** a tool call writes a file in that directory
- **THEN** the decision is `Ask`

#### Scenario: ExecThroughBeneathGuarded

- **GIVEN** an exec-through declaration for a directory beneath a guarded one
- **WHEN** a shell command runs a program held there
- **THEN** the call proceeds

#### Scenario: LinkFromACarveOutIntoAGuardedLocation

- **GIVEN** a link inside a write-through directory whose target lies under a guarded declaration with no write-through declaration of its own
- **WHEN** a tool call writes through the link
- **THEN** the decision is `Ask`, because the strictest hop decides

#### Scenario: LinkFromACarveOutIntoUndeclaredSpace

- **GIVEN** a link inside an exec-through directory whose target lies under no declaration
- **WHEN** a shell command runs a program through the link
- **THEN** the call proceeds, because an undeclared hop allows everything

#### Scenario: DeclarationsReordered

- **GIVEN** two manifests holding the same declarations in different orders
- **WHEN** each judges the same tool calls
- **THEN** every verdict is the same

### Requirement: EquivalentPoliciesReachEqualVerdicts

For any two manifests that assign every path the same class under `PrecedenceIsOneRule`, every implementation SHALL reach the same verdict for every tool call.

Serves: one-list-then-deltas, posture-and-mechanism-are-separate

A policy is what the classes say about each path, not how the operator chose to write it.
A directory may be declared as one base entry with carve-outs beneath it, or as an enumeration of the enforcement it holds, and the hook cannot tell the difference.
Which to write is a posture choice, recorded in `guarded-surface`, and the manifest records it without the hook depending on it.

#### Scenario: BaseWithCarveOutsVersusEnumeration

- **GIVEN** one manifest declaring a directory guarded with a write-through directory beneath it, and another enumerating the guarded siblings of that directory
- **WHEN** each judges a write to the write-through directory and a write to a guarded sibling
- **THEN** both proceed the first and ask the second

### Requirement: OneGlobForm

A declaration MAY carry `*`, which SHALL match exactly one path segment in whichever component it appears, including the last; no other glob form SHALL be recognized; and a trailing `/` SHALL declare the directory and everything beneath it.

Serves: one-list-then-deltas

A directory entry already covers its subtree, which is what a recursive glob mostly says, and a broad name pattern is the name heuristic's job in `sensitive-path-blocking`.
One form keeps the question of what a declaration matches answerable by reading it.

A glob in the last component narrows a declaration to files of one shape directly within a directory.

#### Scenario: GlobInADirectoryComponent

- **GIVEN** a declaration with `*` in a directory component
- **WHEN** a path substitutes one segment for it
- **THEN** the path is covered

#### Scenario: GlobInTheLastComponent

- **GIVEN** a declaration with `*` in its last component
- **WHEN** a path matches it directly within the directory
- **THEN** the path is covered, and a path nested one directory deeper is not

#### Scenario: GlobDoesNotSpanSegments

- **GIVEN** a declaration with `*`
- **WHEN** a path would need `*` to span a separator to match
- **THEN** the path is not covered

### Requirement: EnforcementIsNeverCarvedOut

An exec-through or write-through declaration SHALL have no effect on writes and runs where it covers the enforcement floor, at any distance, including an exact tie.
Block SHALL outrank the floor, and the floor SHALL NOT restrict reads.
The grant SHALL remain effective outside the floor.
Every implementation SHALL report the floor paths to which a grant does not apply where the invoking agent can show the report; it SHALL NOT describe the entire grant as ignored.
At session start, only a grant lying at or inside the floor SHALL be reported, because such a grant has no effect at all; a broader grant keeps its effect outside the floor and is reported at gate time, on the call it does not reach.

Serves: one-list-then-deltas

The floor SHALL be derived independently of user declarations from the guard's implementation and launch locations and known harness enforcement locations.
It covers the manifest, hook implementations and dependencies, harness permission and settings files and their profile layers, their repository sources, project-local permission settings, and every hop of their link chains.
Instruction text is outside the floor.
A broad home or project grant permits content changes without permitting the permission rules themselves to be rewritten without approval.

#### Scenario: WriteThroughOverTheManifest

- **GIVEN** a write-through declaration covering the manifest
- **WHEN** a tool call writes the manifest
- **THEN** the decision is `Ask`, and the report names the manifest as a floor path to which the grant does not apply

#### Scenario: ExecThroughOverAHook

- **GIVEN** an exec-through declaration covering a hook implementation
- **WHEN** a shell command runs that hook
- **THEN** the decision is `Ask`, and the report names the hook as a floor path to which the grant does not apply

#### Scenario: CarveOutOverAHookSource

- **GIVEN** a write-through declaration covering the repository source a deployed hook resolves to
- **WHEN** a tool call writes that source
- **THEN** the decision is `Ask`, and the report names the source as a floor path to which the grant does not apply

#### Scenario: BroadGrantPreservesContentPermission

- **GIVEN** a write-through grant over an agent home or project
- **WHEN** a tool writes ordinary content or instruction text outside the floor
- **THEN** the grant remains effective

#### Scenario: BroadGrantIsSilentAtSessionStart

- **GIVEN** a write-through grant over an agent home that contains floor paths
- **WHEN** the manifest is validated at session start
- **THEN** no finding is reported for that grant

#### Scenario: GrantInsideTheFloorIsReportedAtSessionStart

- **GIVEN** a write-through grant naming a hook directory or a file inside one
- **WHEN** the manifest is validated at session start
- **THEN** the grant is reported with the floor paths it does not apply to

#### Scenario: ExactGrantCannotOverrideTheFloor

- **GIVEN** a grant naming a floor file exactly
- **WHEN** a tool writes or runs that file
- **THEN** the decision is `Ask`, regardless of declaration order

#### Scenario: ProjectPermissionSettingsAreEnforcement

- **GIVEN** a broad project grant and project-local permission settings
- **WHEN** a tool writes those settings
- **THEN** the decision is `Ask`, even if the manifest declares no guarded paths

### Requirement: ConflictingDeclarationsAreReported

The system SHALL report a declaration that conflicts with another: one location declared in the block class and in a carve-out class, or a link held directly inside a carve-out directory whose target lands under a stricter declaration with no carve-out of the same class.

A block declaration nested beneath a carve-out directory is not a conflict.
`PrecedenceIsOneRule` resolves it, block wins, and the layout is a valid way to write a policy.

Serves: one-list-then-deltas

A declaration names a location and not the entries beneath it, so a link inside a carve-out directory is followed by the path's chain and not by the declaration's.
Under `PrecedenceIsOneRule` the target hop then decides, and the carve-out the operator wrote has no effect on operations through that link.
An operator who wrote the carve-out expected it to work, so silence is the wrong answer, and the report names the target that would need a declaration of its own.

Computing the carve-out for the target from the carve-out on the link is refused.
Creating a link inside a write-through directory is itself a permitted write, so inheritance would let an agent widen its own permissions in one unprompted step.

Reporting is at session start, where an agent can show it, and in the manifest test suite, where a change that introduces a conflict fails.
The runtime verdict is unaffected: the block class wins, and the strictest hop decides.

#### Scenario: OneLocationInBlockAndACarveOut

- **GIVEN** the same location declared in the block class and in the write-through class
- **WHEN** the manifest is validated
- **THEN** the conflict is reported, naming both declarations

#### Scenario: BlockNestedBeneathACarveOut

- **GIVEN** a block declaration for a file beneath a write-through directory
- **WHEN** the manifest is validated
- **THEN** no conflict is reported

#### Scenario: LinkInsideACarveOutLeadingToAStricterLocation

- **GIVEN** a link held directly inside an exec-through directory whose target lies under a guarded declaration with no exec-through declaration of its own
- **WHEN** the manifest is validated
- **THEN** the link is reported, naming the target it would need declared

#### Scenario: LinkInsideACarveOutLeadingToUndeclaredSpace

- **GIVEN** a link held directly inside an exec-through directory whose target lies under no declaration
- **WHEN** the manifest is validated
- **THEN** no conflict is reported

#### Scenario: LinkInsideACarveOutLeadingToACarveOut

- **GIVEN** a link held directly inside an exec-through directory whose target lies under another exec-through declaration
- **WHEN** the manifest is validated
- **THEN** no conflict is reported

### Requirement: RunRequiresAnExecThroughDeclaration

A program held in a guarded location SHALL be runnable without a prompt only where an exec-through declaration covers it.

Serves: skill-scripts-run

Permission to run a file held in a location is wider than permission to read one: the hook judges the invocation, not what the program then does.
The reads that proceed under every guarded location do not make its programs runnable, and a location a later change declares guarded does not become runnable with it.

#### Scenario: GuardedLocationIsNotRunnable

- **GIVEN** a location covered by a guarded declaration and by no exec-through declaration
- **WHEN** a shell command runs a program held there
- **THEN** the decision is `Ask`

#### Scenario: ExecThroughLocationIsRunnable

- **GIVEN** a location covered by an exec-through declaration
- **WHEN** a shell command runs a program already held there
- **THEN** the call proceeds

#### Scenario: ExecThroughLocationStaysReadable

- **GIVEN** a location covered by an exec-through declaration
- **WHEN** a tool call reads a file held there
- **THEN** the call proceeds
