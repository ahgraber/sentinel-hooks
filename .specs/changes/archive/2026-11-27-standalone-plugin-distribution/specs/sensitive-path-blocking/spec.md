# Delta for sensitive-path-blocking

## MODIFIED Requirements

### Requirement: PackageDirExemption

> Previously: the exemption also covered the hook sources of a configuration checkout, listed `env/`, and ended with any segment matching a common package manager output directory.

Name-based patterns (`credentials`, `secret`) SHALL NOT apply to paths within package or dependency directories, where these are valid module or source file names rather than credential stores.

The exemption SHALL cover only directories a package manager creates and fills with installed code, and SHALL cover at least:

- `.venv/`, `venv/` (Python virtual environments)
- `site-packages/` (anywhere in the path)
- `node_modules/`

Path-based patterns (e.g., `~/.aws/**`, `~/.ssh/**`, `*.pem`) are not subject to this exemption and remain zero-access regardless of location.

The exemption SHALL NOT depend on a file that an agent can create without asking the user.
A file planted in a project would otherwise switch the name-based patterns off for every path beside it.

No file in this repository's plugin, extension, or test directories SHALL have a name that matches a name-based pattern.
Sentinel's own files are then reachable without any exemption, in a checkout and in every installed copy.

Serves: one-tree, protect-installed-copy

<!-- modified-removes: GuardrailSourceNamedForWhatItBlocks -->

#### Scenario: APlantedHookSourceDoesNotExempt

- **GIVEN** a directory holds a file at `hooks/guarded_paths.py`
- **WHEN** a Read, Write, or Edit tool call targets a file beside it whose name matches a name-based pattern
- **THEN** the hook exits 2

#### Scenario: NoSentinelFileMatchesANamePattern

- **GIVEN** the files under this repository's plugin, extension, and test directories
- **WHEN** each file name is checked against the name-based patterns
- **THEN** none matches

#### Scenario: CredentialsModuleInVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` but contains `.venv/` in the path
- **THEN** the hook exits 0 (library source, not a credential store)

#### Scenario: CredentialsFileOutsideVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` and is not within a package directory
- **THEN** the hook exits 2

### Requirement: BlockBashReadFromZeroAccessPath

> Previously: two scenario examples named a file of one user's own configuration, and a read utility was recognized only by the exact case of its name.

The system SHALL block `Bash` commands that read a zero-access path, so its contents cannot enter the agent's context.

This enforcement matters most on Linux, where the OS sandbox (bubblewrap) ignores glob deny rules such as `Read(**/.env)` and so does not stop a plain `cat ./project/.env`; on macOS the Seatbelt sandbox honors those globs.
The hook makes read blocking uniform across platforms.

This hook is a `shell-lexing` path hook.
When a command uses quoting, escapes, or words the shell rewrites, the hook SHALL judge the words bash would produce.
If the hook cannot work them out, it SHALL treat them as unresolvable.
It SHALL NOT judge them as written.

Where any word of a segment names a recognized read utility, every word in that segment SHALL be judged by the strong rules, whatever its kind: an extension, a credential directory, a key filename, a dotenv name, and a declared block path each name a file wherever they appear, so `-f.env`, `if=.env`, and `sudo -u root cat .env` all block.
A read utility SHALL be recognized here by its exact name in any word, and whatever the case of its name where it is the program a segment runs or a program that `xargs` or `find -exec` launches, because macOS's default filesystem finds a program that way, so `CAT .env` runs `cat`.
An unresolvable word SHALL be judged by the paths it holds.
Input redirection targets SHALL be judged regardless of the command word.

The name heuristic, which guesses contents from a word in a name, SHALL be applied to a path candidate, as `shell-lexing` `APathCandidateDenotesAFile` defines it, to a redirection target, and in a segment that reads to an unresolvable word that may denote a file, and to no other word.
An unresolvable word may denote a file when the shell builds it from an expansion, when the segment's directory does not resolve, or when its spelling in a directory the segment may run in names an existing entry; that last test is the one a bare word already meets to be a path candidate.
A search pattern, a selector expression, and a commit subject are words a read utility receives that name no file, and refusing them stopped ordinary work over this module four times in one session.
A bare word that names an entry in the working directory is a path candidate, so the same word is refused the moment a file of that name exists.

The bias still prefers false positives over false negatives for every rule that recognizes a shape.
The name heuristic is the one rule that recognizes a word, and a word that denotes no file is outside what it can be right about.

Read-from-path forms in Bash include:

- A recognized read command (`cat`, `head`, `grep`, `sed`, `awk`, `jq`, `sort`, `source`, `openssl`, `tar`, `unzip`, `install`, an editor, ...) in a segment that also contains a zero-access word
- Input redirection (`<`, `0<`, `$(< file)`, `mapfile`/`read < file`) from a zero-access path
- `dd if=` a zero-access path

Serves: install-per-agent

#### Scenario: CatEnvFile

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a zero-access path (e.g. `cat ./project/.env`)
- **THEN** the hook exits 2

#### Scenario: RedirectReadWithoutCommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a zero-access path is read via input redirection with no external command (e.g. `mapfile -t a < .env`, `x=$(< .env)`)
- **THEN** the hook exits 2

#### Scenario: BareCredentialFilename

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command targets an extensionless key filename (e.g. `cat id_rsa`) outside a package directory
- **THEN** the hook exits 2, whether or not the file exists

#### Scenario: SearchPatternIsNotAPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a search command's pattern carries a name-heuristic word and names no entry in the working directory (e.g. `grep -r secret .`)
- **THEN** the hook exits 0

#### Scenario: SearchPatternAfterADirectoryChange

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a search after a resolved `cd` carries a name-heuristic word that names no entry in any directory the search may run in (e.g. `cd sub && rg secret .`)
- **THEN** the hook exits 0

#### Scenario: NamedFileAfterADirectoryChange

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read after a `cd` names a file whose name carries a name-heuristic word, and the `cd` is unresolved or the file exists in a directory the read may run in (e.g. `X=~/.config; cd $X && cat deploy-secrets.env`, `if cd ~/.config; then cat deploy-secrets.env; fi`)
- **THEN** the hook exits 2

#### Scenario: NamedFileBehindAnExpansion

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read names a file through an expansion carrying a name-heuristic word (e.g. `cat ${X:-deploy-secrets.env}`)
- **THEN** the hook exits 2

#### Scenario: SearchPatternNamingAnExistingEntry

- **GIVEN** a Bash tool call is intercepted, and an entry named by a name-heuristic word exists in the working directory
- **WHEN** a read command receives that bare word
- **THEN** the hook exits 2

#### Scenario: NameHeuristicWordWithASeparator

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command receives a word carrying a separator and a name-heuristic word, whether or not the file exists
- **THEN** the hook exits 2

#### Scenario: AQuotedZeroAccessPathIsResolved

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command receives a zero-access path in a quoting form, ANSI-C quoting included
- **THEN** the hook exits 2

#### Scenario: AZeroAccessPathInsideAnUnresolvableWord

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command receives an unresolvable word that holds a zero-access path
- **THEN** the hook exits 2

### Requirement: BashReadBestEffort

> Previously: the requirement said `ConfigurationSurfacesCoverTheDeclarations` held the sandbox denies to the block class, and its scenario said the agent's OS sandbox denies the read.

Bash read blocking is fail-safe but not a boundary: some ways of reading a file need real shell evaluation that command-text parsing cannot do.

The following are OUT OF SCOPE and SHALL NOT be relied upon:

- Interpreters that open the file in code (`python -c`, `node -e`, `perl`, `ruby`)
- Words hidden behind a variable, whether the command word (`c=cat; $c .env`) or the operand (`f=.env; cat "$f"`)
- Wrappers whose child is a nested command string (`bash -c '...'`, `eval`, backticks) or where the secret and the reader land in different pipeline segments (`echo .env | xargs cat`)
- Symlink indirection (`ln -s <secret> link`, then reading `link`)
- A recursive read of a directory holding a secret (`grep -r x ~`, `rg --hidden x ~`, `tar -c ~`, `cp -r ~/.config dest`), which reaches the files beneath the directory without naming them
- A read utility named in another case and run by a program the hooks do not unwrap, one that takes the command it runs as its arguments

For these forms, three other layers are the boundary: the OS sandbox's denies, the network egress allowlist, and `secret-access-blocking`.
The user configures the sandbox and the egress allowlist, and Sentinel neither sets nor checks them, so on an agent whose sandbox does not deny a secret, these forms reach it.

Serves: no story of this change; the text changes to stay true once `ConfigurationSurfacesCoverTheDeclarations` no longer holds the sandbox denies.

#### Scenario: RecursiveReadOfADeclaredCredential

- **GIVEN** a directory holding a file the block class declares
- **WHEN** a Bash command reads the directory recursively
- **THEN** the hooks do not refuse it

### Requirement: SecretMaterialIsDeclaredRatherThanRecognized

> Previously: the rationale named a file of one user's own configuration as its example, and a declared path was also required to be covered on every enforcement surface.

A file holding live credentials SHALL be refused because the manifest declares it, and SHALL NOT rest on the name heuristic alone.

The strong rules here recognize a shape: an extension, a credential directory, a file called `.env`.
The name heuristic recognizes nothing; it guesses contents from a word in a name, and it is the weakest thing in this capability.
A credential whose only refusal comes from that guess is protected by what it is called, so renaming it withdraws the protection and nothing reports that anything changed.

An environment file rendered at login, such as `~/.config/deploy-secrets.env`, is such a file.
The dotenv rule requires `.env` at a path boundary, so a `*.env` suffix reaches no strong rule.

Serves: install-per-agent

#### Scenario: DeclaredCredentialIsRefused

- **GIVEN** a path declared in the manifest's block class
- **WHEN** a tool call would read it
- **THEN** it is refused on every agent

#### Scenario: RenamingDoesNotWithdrawTheRefusal

- **GIVEN** a declared credential path
- **WHEN** its name carries no term the name heuristic recognizes
- **THEN** it is still refused, because the declaration rather than the name is what refuses it
