# Delta for sensitive-path-blocking

## ADDED Requirements

### Requirement: SecretMaterialIsDeclaredRatherThanRecognized

Serves: existing-guarantees-are-recorded

A file holding live credentials SHALL be refused because the manifest declares it, and SHALL NOT rest on the name heuristic alone.

The strong rules here recognize a shape: an extension, a credential directory, a file called `.env`.
The name heuristic recognizes nothing; it guesses contents from a word in a name, and it is the weakest thing in this capability.
A credential whose only refusal comes from that guess is protected by what it is called, so renaming it withdraws the protection and nothing reports that anything changed.

`~/.config/mcp-secrets.env` was such a file.
It holds the API keys the MCP servers start with, rendered from a 1Password template at home activation.
The dotenv rule requires `.env` at a path boundary, so a `*.env` suffix reaches no strong rule, and no deny entry in any agent's configuration covered it.

A declared path SHALL also be covered on every enforcement surface, as `ConfigurationSurfacesCoverTheDeclarations` already requires of the block class.

#### Scenario: DeclaredCredentialIsRefused

- **GIVEN** a path declared in the manifest's block class
- **WHEN** a tool call would read it
- **THEN** it is refused on every agent

#### Scenario: RenamingDoesNotWithdrawTheRefusal

- **GIVEN** a declared credential path
- **WHEN** its name carries no term the name heuristic recognizes
- **THEN** it is still refused, because the declaration rather than the name is what refuses it

### Requirement: TheNameHeuristicIsExcusedOnlyByDeclaration

Serves: existing-guarantees-are-recorded

Where a file's name is the only signal against it, the system SHALL excuse it only where the manifest declares an exception for this surface, and SHALL judge that exception against one spelling at a time.

A name describes its subject, which is not always its contents.
A program that renders a secret file is named for the file it renders, and a guardrail source is named for what it guards against; both read as data to a rule that sees only the name.
The strong rules are unaffected, because each recognizes a shape rather than a word.

The exception is declared rather than written into the rule so that the reason travels with it, which is what this module already requires of every loosening.
An entry no implementation reads records an intention and changes nothing, so each implementation SHALL build its exemption from the declaration.

Judging one spelling at a time is what keeps the exemption with the file it was written for.
A link whose own name triggers the heuristic SHALL be refused even where its target is excused on this surface.
A declaration for a different surface MAY excuse a link by its verified target, where it states the conditions the link must meet; `guarded-surface` `NameHeuristicExceptionIsDeclared` declares one for a Home Manager store wrapper, and the strong rules still apply to every hop.

#### Scenario: DeclaredExceptionIsReadable

- **GIVEN** a file whose name is the only signal against it
- **WHEN** the manifest declares an exception covering it for this surface
- **THEN** the read proceeds

#### Scenario: UndeclaredNeighborIsRefused

- **GIVEN** a file beside a declared exception, with a name carrying the same term
- **WHEN** it is read
- **THEN** it is refused, because an exception covers what it names and nothing more

#### Scenario: ExceptionDoesNotTravelAlongALink

- **GIVEN** a link whose own name carries a term the heuristic recognizes
- **WHEN** its target is covered by an exception declared for the name-heuristic surface
- **THEN** the read is refused, because the spelling that triggered the heuristic is not the spelling the exception covers

## MODIFIED Requirements

### Requirement: BashReadBestEffort

> Previously: the limits named a command word hidden behind a variable but not an operand, did not name a recursive read, and named the OS sandbox's literal-prefix denies as the boundary without naming the requirement that holds them.

Serves: existing-guarantees-are-recorded

Bash read blocking is fail-safe but not a boundary: some ways of reading a file need real shell evaluation that command-text parsing cannot do.

The following are OUT OF SCOPE and SHALL NOT be relied upon:

- Interpreters that open the file in code (`python -c`, `node -e`, `perl`, `ruby`)
- Words hidden behind a variable, whether the command word (`c=cat; $c .env`) or the operand (`f=.env; cat "$f"`)
- Wrappers whose child is a nested command string (`bash -c '...'`, `eval`, backticks) or where the secret and the reader land in different pipeline segments (`echo .env | xargs cat`)
- Symlink indirection (`ln -s <secret> link`, then reading `link`)
- A recursive read of a directory holding a secret (`grep -r x ~`, `rg --hidden x ~`, `tar -c ~`, `cp -r ~/.config dest`), which reaches the files beneath the directory without naming them

For these, the boundary is the OS sandbox's denies, which `guarded-path-declarations` `ConfigurationSurfacesCoverTheDeclarations` holds to the block class on every agent, the network egress allowlist, and `block-secrets.py`.
A secret only the name rules recognize, such as a `.env` file, has no declaration for that floor to cover, so on an agent whose sandbox does not deny it by name, these forms reach it.

#### Scenario: RecursiveReadOfADeclaredCredential

- **GIVEN** a directory holding a file the block class declares
- **WHEN** a Bash command reads the directory recursively
- **THEN** the hooks do not refuse it, and the agent's OS sandbox denies the read of the declared file
