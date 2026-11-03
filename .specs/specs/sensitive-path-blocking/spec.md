# Spec: sensitive-path-blocking

## Purpose

An agent that reads a credential file holds the secret for the rest of the session, where any later call can disclose or use it.
These requirements cover which paths are zero-access, how each tool and shell form that reads or writes them is refused, the declared exceptions, and the limits of the shell checks.

## Requirements

### Requirement: ToolScope

The system SHALL evaluate tool calls when `tool_name` is `Bash`, `Read`, `Write`, `Edit`, or `apply_patch`.

The hook is shared (symlinked) between Claude Code and Codex, which send the same snake_case `{tool_name, tool_input}` PreToolUse payload.
`Read`/`Write`/`Edit` are Claude tools; `apply_patch` is the Codex edit tool; `Bash` is common (Codex's shell tool also reports `tool_name == "Bash"`).
A tool a given agent never emits is an inert branch there.

Because the hook handles a mix of sensitive tools (`Bash`, `Write`, `Edit`) and a read-only tool (`Read`), it cannot determine the tool type on a JSON parse failure.
The system SHALL exit 0 on parse failure (fail-open), per `hook-interface` `ErrorHandlingByDamagePotential`.

Failing open SHALL NOT extend to a path that cannot be resolved.
Such a path is judged from the path as written, per `path-matching` `UnresolvablePathIsGuarded`.

### Requirement: ZeroAccessPaths

The system SHALL define a set of zero-access paths that may never be written to or modified.

Zero-access paths include:

- Dot-env files: `.env`, `.env.*`, `.envrc` (case-insensitive; the `.env` forms also match shell globs such as `*.env` and `.env*`)
- Credential directories, matched wherever they appear in a path (not only under `~`): `.ssh/`, `.aws/`, `.kube/`, `.gnupg/`, `.azure/`
- SSH key filenames anywhere: `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*` (private and public)
- Credential config files anywhere: `.netrc`, `.npmrc`, `.pypirc`, `.git-credentials`, `.docker/config.json`, `service-account*.json`
- Certificate and key files: `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.crt`, `*.cer`
- Terraform state files: `*.tfstate`, `*.tfstate.backup`
- Shell history files: `.bash_history`, `.zsh_history`, `.sh_history`, `.node_repl_history`, `.python_history`
- Files whose name contains `credentials` or `secret` (case-insensitive), unless the path falls within a package or dependency directory (see `PackageDirExemption`)

A zero-access path SHALL be recognized whether it is supplied as written, with a home reference such as `~` or `$HOME`, with `..` components, or through a symbolic link.
The stated limits of `path-matching` apply here unchanged.

Letter case SHALL NOT follow the volume here.

This requirement asks a different question from a guarded location.
A guarded location asks whether a path _is_ a declared file, so two spellings are one file only where the volume says so, and `secret-access-blocking` `AskOnCredentialStoreRead` is decided that way.
This requirement asks whether a path _looks like_ it holds a secret, from its extension, its basename, and the directories it passes through.
On a volume that distinguishes case, `SECRET.PEM` is a different file from `secret.pem`, and it is equally a private key.
A name heuristic that stopped applying because a letter was capitalized would be defeated by capitalizing a letter.

Every pattern in this requirement therefore matches without regard to case, on every volume.
The error this admits is refusing a path that resembles a secret and is not one, which is the safe direction for a set whose members may never be read.

#### Scenario: CaseVariantCredentialDirectory

- **GIVEN** a Read, Write, or Edit tool call is intercepted
- **WHEN** the target lies within a credential directory named under a differing letter case
- **THEN** the hook exits 2, whether or not the filesystem folds case

### Requirement: PackageDirExemption

Name-based patterns (`credentials`, `secret`) SHALL NOT apply to paths within package or dependency directories, where these are valid module or source file names rather than credential stores.

Package and dependency directories include:

- `.venv/`, `venv/`, `env/` (Python virtual environments)
- `site-packages/` (anywhere in the path)
- `node_modules/`
- Any path segment matching a common package manager output directory

Path-based patterns (e.g., `~/.aws/**`, `~/.ssh/**`, `*.pem`) are not subject to this exemption and remain zero-access regardless of location.

The exemption SHALL cover the directories holding this repository's own hook sources, for every agent.
Those directories hold files whose names describe what they guard against, not what they contain.
Reaching one of them requires the name-based patterns not to apply, and an agent that cannot read or write its own guardrail source cannot maintain it.

The exemption SHALL cover the hook-source directory of every agent in this repository.
This includes a directory added or moved later, with no edit to the exemption.
Naming the agents one at a time leaves a directory uncovered whenever these modules move, making a guardrail source unreachable to the people responsible for it.

#### Scenario: GuardrailSourceNamedForWhatItBlocks

- **GIVEN** a Read, Write, or Edit tool call is intercepted
- **WHEN** the target is a hook source in this repository whose name matches a name-based pattern
- **THEN** the hook exits 0

#### Scenario: CredentialsModuleInVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` but contains `.venv/` in the path
- **THEN** the hook exits 0 (library source, not a credential store)

#### Scenario: CredentialsFileOutsideVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` and is not within a package directory
- **THEN** the hook exits 2

### Requirement: BlockWriteEditToZeroAccessPath

The system SHALL block `Write` and `Edit` tool calls targeting a zero-access path.

#### Scenario: WriteToEnvFile

- **GIVEN** a Write tool call is intercepted
- **WHEN** `tool_input.path` matches a zero-access path pattern
- **THEN** the hook exits 2

#### Scenario: EditSshKey

- **GIVEN** an Edit tool call is intercepted
- **WHEN** `tool_input.path` is within `~/.ssh/`
- **THEN** the hook exits 2

### Requirement: BlockApplyPatchToZeroAccessPath

The system SHALL block a Codex `apply_patch` tool call that adds, updates, deletes, or moves a zero-access path.

The `apply_patch` target paths SHALL be read from the command body (`*** Add File:`, `*** Update File:`, `*** Delete File:`, `*** Move to:` lines) in `tool_input.command`.

#### Scenario: ApplyPatchToEnvFile

- **GIVEN** an `apply_patch` tool call is intercepted
- **WHEN** the patch body names a zero-access path (e.g. `*** Add File: config/.env`)
- **THEN** the hook exits 2

### Requirement: BlockReadFromZeroAccessPath

The system SHALL block `Read` tool calls whose `file_path` matches any zero-access path pattern defined in `ZeroAccessPaths`.

Reading zero-access paths exposes secret material to Claude's context window.
A subsequent operation — network call, file write, or command — could then transmit that material without a further confirmation opportunity.
Hard-blocking the read prevents the secret from entering context at all.

#### Scenario: ReadSshKey

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` is within `~/.ssh/`
- **THEN** the hook exits 2

#### Scenario: ReadEnvFile

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` matches a dot-env pattern (`.env`, `.env.*`, `.envrc`)
- **THEN** the hook exits 2

#### Scenario: ReadPemFile

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` has a zero-access extension (`.pem`, `.key`, `.p12`, etc.)
- **THEN** the hook exits 2

#### Scenario: ReadCredentialNamedFile

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` basename matches `credentials` or `secret` (case-insensitive) and the path is not within a package directory
- **THEN** the hook exits 2

#### Scenario: ReadCredentialNamedFileInVenv

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.file_path` basename matches `credentials` or `secret` but the path contains `.venv/` or `site-packages/`
- **THEN** the hook exits 0 (package-dir exemption applies)

### Requirement: BlockBashWriteToZeroAccessPath

The system SHALL block `Bash` commands that write to or overwrite a zero-access path.

Write-to-path patterns in Bash include:

- Output redirection (`>`, `>>`) to a zero-access path
- `cp`, `mv`, `install`, `tee` with a zero-access path as the destination
- `chmod` or `chown` targeting a zero-access path
- `dd of=` a zero-access path

#### Scenario: RedirectToEnvFile

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command contains `> .env` or `>> .env`
- **THEN** the hook exits 2

#### Scenario: CpToSshDir

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command copies a file into `~/.ssh/`
- **THEN** the hook exits 2

### Requirement: BlockBashReadFromZeroAccessPath

The system SHALL block `Bash` commands that read a zero-access path, so its contents cannot enter the agent's context.

This enforcement matters most on Linux, where the OS sandbox (bubblewrap) ignores glob deny rules such as `Read(**/.env)` and so does not stop a plain `cat ./project/.env`; on macOS the Seatbelt sandbox honors those globs.
The hook makes read blocking uniform across platforms.

This hook is a `shell-lexing` path hook.
When a command uses quoting, escapes, or words the shell rewrites, the hook SHALL judge the words bash would produce.
If the hook cannot work them out, it SHALL treat them as unresolvable.
It SHALL NOT judge them as written.

Where any word of a segment names a recognized read utility, every word in that segment SHALL be judged by the strong rules, whatever its kind: an extension, a credential directory, a key filename, a dotenv name, and a declared block path each name a file wherever they appear, so `-f.env`, `if=.env`, and `sudo -u root cat .env` all block.
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
- **WHEN** a read after a `cd` names a file whose name carries a name-heuristic word, and the `cd` is unresolved or the file exists in a directory the read may run in (e.g. `X=~/.config; cd $X && cat mcp-secrets.env`, `if cd ~/.config; then cat mcp-secrets.env; fi`)
- **THEN** the hook exits 2

#### Scenario: NamedFileBehindAnExpansion

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read names a file through an expansion carrying a name-heuristic word (e.g. `cat ${X:-mcp-secrets.env}`)
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

### Requirement: SecretMaterialIsDeclaredRatherThanRecognized

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
