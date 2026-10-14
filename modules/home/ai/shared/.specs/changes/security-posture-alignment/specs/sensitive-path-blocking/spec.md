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
A declared exception that no implementation applies records an intention but has no effect.
So a declared exception SHALL take effect in every implementation, with no other edit.

Judging one spelling at a time is what keeps the exemption with the file it was written for.
A link whose own name triggers the heuristic SHALL be refused even where its target is excused.

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
- **WHEN** its target is covered by a declared exception
- **THEN** the read is refused, because the spelling that triggered the heuristic is not the spelling the exception covers

### Requirement: DotenvPlaceholderReadIsExcusedOnlyByDeclaration

Serves: placeholder-files-are-readable

A read of a file the dotenv rule refuses SHALL proceed only where the manifest declares an exception for the dotenv surface whose file name matches the file's name, without regard to case.
Such an exception SHALL excuse reads only; a write SHALL still be refused.
The exception SHALL allow a read only if every spelling of the path carries a declared name: the path as written, and each path its links resolve through.
So a link with a placeholder name is refused if the dotenv rule refuses its target.

A project commits a file such as `.env.example` to list the variables it expects, with placeholder values.
The dotenv rule recognizes `.env` followed by any suffix, so it refuses these files along with `.env.local` and `.env.production`, which hold live values.
A refused placeholder stops routine work that reads it, and holds nothing a refusal protects.

The exception names a file name rather than a path, because a placeholder sits wherever its project keeps one.
It excuses only the dotenv rule: a placeholder inside a credential directory is still refused by that rule.
A write stays refused because the hazard is the reverse of a read: an agent can copy a live value into a placeholder that is then committed.

A shell command reads a placeholder only where the read classifier recognizes its segment as a read, by the criterion `hook-tampering-blocking` `ReadClassifierAdmitsOnlySelfDescribingUtilities` sets.
The rules that refuse take the broad set of programs that may read a file; an exemption takes the narrow set of utilities that only read their arguments.
`sed`, `awk`, and an editor can write the file they name, and the hook recognizes no in-place write, so a placeholder named to one of them stays refused.
A redirection's target is judged by its direction, as `UnrecognizedCommandsAreGated` judges it: an input target as a read, and an output target as a write.

A placeholder read refused only because its command is not recognized as a read SHALL carry the retry form of `hook-interface` `BlockAIGuidance`, with the recognized reads listed and a statement that writing to the placeholder is refused.
The policy permits the read, so the stop form would tell the agent to abandon work a different command completes.
A refusal any other rule makes SHALL keep the stop form, including a placeholder whose resolved form the dotenv rule refuses.

#### Scenario: DeclaredPlaceholderIsReadable

- **GIVEN** the manifest declares `.env.example` for the dotenv surface
- **WHEN** a tool call reads `apps/web/.env.example`
- **THEN** the read proceeds

#### Scenario: PlaceholderWriteIsRefused

- **GIVEN** a declared placeholder name
- **WHEN** a tool call writes a file of that name
- **THEN** the write is refused

#### Scenario: UndeclaredVariantIsRefused

- **GIVEN** the declared placeholder names
- **WHEN** a tool call reads `.env.local` or `.env.example.local`
- **THEN** the read is refused, because neither name is declared

#### Scenario: PlaceholderLinkToSecretIsRefused

- **GIVEN** a link named `.env.example` whose target is `.env`
- **WHEN** a tool call reads the link
- **THEN** the read is refused, because the resolved form is a name the dotenv rule refuses

#### Scenario: GlobIsJudgedByItsMatches

- **GIVEN** the declared placeholder names
- **WHEN** a shell command reads `.env.*`
- **THEN** the read proceeds only if every current match is a declared placeholder; if any match is a refused name, or nothing matches, the read is refused

#### Scenario: PlaceholderReadThroughARedirection

- **GIVEN** a declared placeholder name
- **WHEN** a recognized read takes it as an input redirection target, or writes its output to a file the policy permits
- **THEN** the read proceeds

#### Scenario: UnrecognizedPlaceholderReadNamesTheReadsThatProceed

- **GIVEN** a declared placeholder name
- **WHEN** a shell command reads it with a program the classifier does not recognize as a read
- **THEN** the refusal carries the retry form, lists the recognized reads, and states that writing to the placeholder is refused

### Requirement: SuggestiveNamesAsk

Serves: placeholder-files-are-readable, existing-guarantees-are-recorded

A `Read`, `Write`, `Edit`, or `apply_patch` call SHALL reach `Ask` when a spelling of a target path it names is suggestive and no rule in this capability refuses the target.
A name is suggestive when its basename contains `token`, `password`, `passwd`, `api_key`, `api-key`, `apikey`, `auth_key`, or `credential`, or ends in `.keystore` or `.jks`, matched without regard to letter case.
The package-directory exemption and the declared name-heuristic exceptions SHALL excuse a suggestive name exactly as they excuse the name heuristic.
A name that identifies a credential store rather than suggesting one, such as `.credentials.json`, SHALL reach `Ask` inside a package directory too.

These names suggest a credential without proving one, so the user decides rather than the hook refusing.
They sit in this capability because it owns the judgment of which paths hold credentials, and it reads the manifest: one declaration then holds for every rule.

The ask SHALL name the file and satisfy `hook-interface` `ExplanationContract`.
An agent that cannot show a prompt for the tool SHALL receive a refusal whose explanation does not ask anyone to approve.
A Bash command naming such a file is judged by the Bash read rules alone.

#### Scenario: SuggestiveNameAsks

- **GIVEN** a `Read` tool call targets `/project/auth_token.json`
- **WHEN** the hook judges it
- **THEN** the decision is `Ask`, and the reason names the file

#### Scenario: SuggestiveNameInAPackageDirectory

- **GIVEN** a `Read` tool call targets `token.py` inside a `.venv` package directory
- **WHEN** the hook judges it
- **THEN** the hook exits 0

#### Scenario: OAuthStoreInAPackageDirectory

- **GIVEN** a `Read` tool call targets `.credentials.json` inside a `.venv` package directory
- **WHEN** the hook judges it
- **THEN** the decision is `Ask`

#### Scenario: DeclaredReadsReachNoAsk

- **GIVEN** a `Read` tool call targets a declared dotenv placeholder or a declared name-heuristic exception
- **WHEN** the hook judges it
- **THEN** the hook exits 0

#### Scenario: AgentThatCannotPrompt

- **GIVEN** an agent that cannot show a prompt for the tool
- **WHEN** a call reaches this ask
- **THEN** the call is refused, and the explanation asks no one to approve

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

For these forms, three other layers are the boundary: the OS sandbox's denies, the network egress allowlist, and `secret-access-blocking`.
`guarded-path-declarations` `ConfigurationSurfacesCoverTheDeclarations` holds the sandbox denies to the block class on every agent.
A secret only the name rules recognize, such as a `.env` file, has no declaration for that floor to cover, so on an agent whose sandbox does not deny it by name, these forms reach it.

#### Scenario: RecursiveReadOfADeclaredCredential

- **GIVEN** a directory holding a file the block class declares
- **WHEN** a Bash command reads the directory recursively
- **THEN** the hooks do not refuse it, and the agent's OS sandbox denies the read of the declared file
