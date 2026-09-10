# Spec: sensitive-path-blocking

## Requirement: ToolScope

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

A supplied path SHALL be judged in every form `path-matching` produces for it — as written, with home notation and traversal applied, and as resolved — so that home notation, traversal, and a symbolic link do not defeat the set.
The stated limits of `path-matching` apply here unchanged.

Membership itself SHALL NOT be decided by `path-matching`, and letter case SHALL NOT follow the volume here.

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

The exemption SHALL be declared once for the whole family, not per agent.
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

The system SHALL block `Bash` commands that read a zero-access path, so its contents cannot enter Claude's context.

This enforcement matters most on Linux, where the OS sandbox (bubblewrap) ignores glob deny rules such as `Read(**/.env)` and so does not stop a plain `cat ./project/.env`; on macOS the Seatbelt sandbox honors those globs.
The hook makes read blocking uniform across platforms.

The check SHALL be fail-safe rather than precise: the goal is to prevent operations over secrets, not to model shell grammar.
Commands SHALL be tokenised with `shlex` (quote- and operator-aware) so quoting and escapes resolve (`\cat`, `c""at`, `'cat'`) and quoted operators do not split the command.
If a command segment invokes a recognized read command, EVERY token in that segment SHALL be checked against the zero-access rules and any match SHALL block.
There SHALL be no option/operand modelling: a zero-access path that appears anywhere — as an operand, an attached option value (`-f.env`, `if=.env`), or behind a wrapper (`sudo -u root cat .env`) — SHALL block.
Input redirection targets (`<`, `0<`) SHALL be checked regardless of the command word.

This bias SHALL prefer false positives over false negatives: a zero-access-looking search pattern (e.g. `grep -r secret .`) SHALL block even though it names no file.

Read-from-path forms in Bash include:

- A recognized read command (`cat`, `head`, `grep`, `sed`, `awk`, `jq`, `sort`, `source`, `openssl`, `tar`, `unzip`, `install`, an editor, ...) in a segment that also contains a zero-access token
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
- **WHEN** a read command targets an extensionless credential file operand (e.g. `cat credentials`, `cat id_rsa`) outside a package directory
- **THEN** the hook exits 2

#### Scenario: SecretWordPatternOverDenies

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a search command uses a zero-access-looking token as its pattern, not a file (e.g. `grep -r secret .`, `jq '.credentials' config.json`)
- **THEN** the hook exits 2 (accepted over-deny; the fail-safe bias blocks rather than risk a miss)

### Requirement: BashReadBestEffort

Bash read blocking is fail-safe but not a boundary: some ways of reading a file need real shell evaluation that command-text parsing cannot do.

The following are OUT OF SCOPE and SHALL NOT be relied upon:

- Interpreters that open the file in code (`python -c`, `node -e`, `perl`, `ruby`)
- Command words hidden behind a variable (`c=cat; $c .env`)
- Wrappers whose child is a nested command string (`bash -c '...'`, `eval`, backticks) or where the secret and the reader land in different pipeline segments (`echo .env | xargs cat`)
- Symlink indirection (`ln -s <secret> link`, then reading `link`)

For these, the boundary is the OS sandbox's literal-prefix denies (which protect the home credential stores regardless of command), the network egress allowlist, and `block-secrets.py`.
