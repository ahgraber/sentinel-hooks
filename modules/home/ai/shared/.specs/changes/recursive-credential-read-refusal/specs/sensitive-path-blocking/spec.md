# Delta for sensitive-path-blocking

## ADDED Requirements

### Requirement: RecursiveReadAboveADeclaredCredential

Serves: a-declared-credential-is-not-read-by-its-parent, a-refused-search-says-what-would-work

A Bash command that reads or copies a directory recursively SHALL be refused, with no prompt and on every agent, when a path the block class declares lies at or beneath a root it reads.

A recursive read exposes the files beneath its root without naming them, so a check of the named words does not see the credential.
The block class has no prompt, because a credential that has been exposed cannot be taken back.

A declared path SHALL count whether or not a file exists there when the hook judges the command, so a credential the same command creates is covered.
A root and a declaration SHALL be compared through every spelling of each, so a link in either path, or a difference in letter case on a volume that ignores case, does not hide the declaration.
Each root SHALL be judged in every directory the reader may run in, and a recursive reader given no root SHALL be judged as reading that directory.
A flag or ignore file that selects or excludes files SHALL NOT change the verdict: the refusal is conservative about what the reader opens.
A mode that lists names without opening any file is not a recursive read.

The refusal SHALL name the declared path beneath the root, SHALL state that reading or copying it could expose credentials, and SHALL use the search retry form of `hook-interface` `BlockAIGuidance`.

A recursive reader the hooks do not recognize is a limit stated in `BashReadBestEffort`.

#### Scenario: RecursiveReadOfAnAncestorIsRefused

- **GIVEN** the block class declares `~/.codex/auth.json`
- **WHEN** a Bash command runs `grep -r token ~`
- **THEN** it is refused on every agent, and the message names `~/.codex/auth.json`

#### Scenario: RootIsTheCredentialsOwnDirectory

- **GIVEN** the block class declares `~/.config/mcp-secrets.env`
- **WHEN** a Bash command runs `grep -r x ~/.config`
- **THEN** it is refused

#### Scenario: RootHoldsNoDeclaredCredential

- **GIVEN** no declared path lies beneath the repository checkout
- **WHEN** a Bash command runs `grep -r x .` in that checkout
- **THEN** this requirement does not refuse it

#### Scenario: DeclaredCredentialDoesNotExistYet

- **GIVEN** no file exists at a declared path
- **WHEN** a Bash command recursively reads that path's parent directory
- **THEN** it is refused

#### Scenario: ReaderThatSkipsHiddenEntries

- **GIVEN** the block class declares `~/.codex/auth.json`
- **WHEN** a Bash command runs `rg foo ~` or `rg -g '**' foo ~`
- **THEN** it is refused, because a glob or an ignore-file entry can make the reader open hidden entries

#### Scenario: NameListingIsNotARecursiveRead

- **GIVEN** the block class declares `~/.codex/auth.json`
- **WHEN** a Bash command runs `rg --files ~`
- **THEN** this requirement does not refuse it

#### Scenario: RootAfterADirectoryChange

- **GIVEN** the block class declares a path beneath the home directory
- **WHEN** a Bash command runs `cd ~ && grep -r x .`
- **THEN** it is refused

#### Scenario: RootAfterADirectoryChangeThatMayFail

- **GIVEN** the command starts in the home directory, and the block class declares a path beneath it
- **WHEN** a Bash command runs `cd /absent || grep -r x .`
- **THEN** it is refused, because the reader runs in the home directory when the change fails

#### Scenario: ReaderGivenNoRoot

- **GIVEN** the block class declares a path beneath the home directory
- **WHEN** a Bash command runs `cd ~ && grep -r x`
- **THEN** it is refused

#### Scenario: DeclarationBeneathALinkedDirectory

- **GIVEN** `~/.config` is a link to another directory, and the block class declares `~/.config/mcp-secrets.env`
- **WHEN** a Bash command recursively reads the link's target directory
- **THEN** it is refused

#### Scenario: RootSpelledInAnotherCase

- **GIVEN** a volume that ignores letter case, and the block class declares `~/.codex/auth.json`
- **WHEN** a Bash command runs `grep -r x ~/.CODEX`
- **THEN** it is refused

#### Scenario: AnExcludeFlagDoesNotChangeTheVerdict

- **GIVEN** the block class declares `~/.codex/auth.json`
- **WHEN** a Bash command runs `grep -r --exclude-dir=.codex x ~`
- **THEN** it is refused

#### Scenario: RecursiveCopyOfAnAncestor

- **GIVEN** the block class declares `~/.config/mcp-secrets.env`
- **WHEN** a Bash command runs `cp -r ~/.config /tmp/backup` or `tar -czf backup.tgz ~`
- **THEN** it is refused, as a copy of the declared file itself is

## MODIFIED Requirements

### Requirement: BashReadBestEffort

> Previously: a recursive read of a directory holding a secret was out of scope whatever the secret and the reader.

Serves: a-declared-credential-is-not-read-by-its-parent

Bash read blocking is fail-safe but not a boundary: some ways of reading a file need real shell evaluation that command-text parsing cannot do.

The following are OUT OF SCOPE and SHALL NOT be relied upon:

- Interpreters that open the file in code (`python -c`, `node -e`, `perl`, `ruby`)
- Words hidden behind a variable, whether the command word (`c=cat; $c .env`) or the operand (`f=.env; cat "$f"`)
- Wrappers whose child is a nested command string (`bash -c '...'`, `eval`, backticks) or where the secret and the reader land in different pipeline segments (`echo .env | xargs cat`)
- Symlink indirection (`ln -s <secret> link`, then reading `link`), including a link beneath a recursive read's root
- A recursive read that `RecursiveReadAboveADeclaredCredential` does not refuse: one by a reader the hooks do not recognize, and one reaching a secret only the name rules recognize, such as a `.env` file beneath the root

For these, the boundary is the OS sandbox's denies, which `guarded-path-declarations` `ConfigurationSurfacesCoverTheDeclarations` holds to the block class on every agent, the network egress allowlist, and `block-secrets.py`.
A secret only the name rules recognize, such as a `.env` file, has no declaration for that floor to cover, so on an agent whose sandbox does not deny it by name, these forms reach it.

#### Scenario: RecursiveReadOfANameRuleSecret

- **GIVEN** a directory holding a `.env` file and no declared credential
- **WHEN** a Bash command reads the directory recursively
- **THEN** the hooks do not refuse it
