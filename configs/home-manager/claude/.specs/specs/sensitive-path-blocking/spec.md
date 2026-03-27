# Spec: sensitive-path-blocking

## Requirement: ToolScope

The system SHALL evaluate tool calls when `tool_name` is `Bash`, `Read`, `Write`, or `Edit`.

Because the hook handles a mix of sensitive tools (`Bash`, `Write`, `Edit`) and a read-only tool (`Read`), it cannot determine the tool type on a JSON parse failure.
The system SHALL exit 0 on parse failure (fail-open), per `hook-interface` `ErrorHandlingByDamagePotential`.

### Requirement: ZeroAccessPaths

The system SHALL define a set of zero-access paths that may never be written to or modified.

Zero-access paths include:

- Dot-env files: `.env`, `.env.*`, `.envrc`
- SSH directory and contents: `~/.ssh/**`
- AWS credentials directory: `~/.aws/**`
- Kubernetes config directory: `~/.kube/**`
- GPG directory: `~/.gnupg/**`
- Certificate and key files: `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.crt`, `*.cer`
- Terraform state files: `*.tfstate`, `*.tfstate.backup`
- Files whose name contains `credentials` or `secret` (case-insensitive), unless the path falls within a package or dependency directory (see `PackageDirExemption`)

### Requirement: PackageDirExemption

Name-based patterns (`credentials`, `secret`) SHALL NOT apply to paths within package or dependency directories, where these are valid module or source file names rather than credential stores.

Package and dependency directories include:

- `.venv/`, `venv/`, `env/` (Python virtual environments)
- `site-packages/` (anywhere in the path)
- `node_modules/`
- Any path segment matching a common package manager output directory

Path-based patterns (e.g., `~/.aws/**`, `~/.ssh/**`, `*.pem`) are not subject to this exemption and remain zero-access regardless of location.

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

#### Scenario: RedirectToEnvFile

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command contains `> .env` or `>> .env`
- **THEN** the hook exits 2

#### Scenario: CpToSshDir

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command copies a file into `~/.ssh/`
- **THEN** the hook exits 2
