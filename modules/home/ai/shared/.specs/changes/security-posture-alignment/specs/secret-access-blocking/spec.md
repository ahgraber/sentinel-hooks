# Delta for secret-access-blocking

## MODIFIED Requirements

### Requirement: ToolScope

> Previously: `Read`, `Write`, and `Edit` also carried file path heuristics for likely-secret files; those now belong to `sensitive-path-blocking` `SuggestiveNamesAsk`.

Serves: placeholder-files-are-readable

The system SHALL evaluate ALL tool calls, regardless of tool name.

Secrets can appear in any tool argument — a command string, file content, a URL, a grep pattern, a file path.
The hook SHALL check every field of `tool_input` on every call, so it detects a secret in any argument.
It does not list specific tools or fields.

Tool-specific handling is layered on top of the universal scan:

- `Bash`: additional context-aware analysis (network-sending detection, credential store reads, localhost exemption)
- `Write`/`Edit`: content payload scanning, through the universal scan
- All other tools: universal scan only

This hook does not judge a file path as a location.
Which paths hold credentials is `sensitive-path-blocking`'s judgment, made from the manifest, so a declared exception or placeholder holds for every hook.

### Requirement: AskOnCredentialStoreRead

> Previously: a Read of a credential store named under a differing letter case asked here; `sensitive-path-blocking` now refuses that path for every spelling.

Serves: placeholder-files-are-readable

The system SHALL ask (confirm) when a Bash command reads from a system credential store without piping the output to a network command.

This covers legitimate debugging: checking which credentials are stored, verifying a token value, or inspecting a credential helper.

#### Scenario: KeychainReadLocal

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain but does not pipe to a network command
- **THEN** the hook exits 0 with `permissionDecision: "ask"`

#### Scenario: KeychainReadAndSend

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain and pipes the result to a network command
- **THEN** the hook exits 2 (block — handled by `BlockSecretExfiltration`)

<!-- modified-removes: CaseVariantCredentialStore -->

### Requirement: TieredSecretDetection

> Previously: the scan-surface table named file path heuristics as an independent row, pointing at the removed `AskOnSecretFileAccess`.

Serves: placeholder-files-are-readable

The system SHALL detect the formats in `SecretFormats` in every tool call.
If a Bash command sends data to a non-local destination and `gitleaks` is on `PATH`, the system SHALL also detect every format the default `gitleaks` rules detect.
If `gitleaks` is not on `PATH`, detection in that case covers `SecretFormats` only, and the `SessionStart` hook warns the user (see `session-tool-checks`).

A secret missed in a network send can leak a credential to a remote host.
A secret missed elsewhere costs only a missed confirmation prompt.
So the wider coverage is required only where a leak is possible.

Coverage by context:

| Context                    | `SecretFormats` | `gitleaks` rules, where installed |
| -------------------------- | --------------- | --------------------------------- |
| Bash + network (non-local) | yes             | yes                               |
| Bash (local or no network) | yes             | not required                      |
| Read / Write / Edit        | yes             | not required                      |
| All other tools            | yes             | not required                      |

#### Scenario: GitleaksAvailableWithNetwork

- **GIVEN** a Bash tool call with a non-local network destination is intercepted
- **WHEN** `gitleaks` is found on `PATH`, and the command carries a secret in a format only the `gitleaks` rules detect
- **THEN** the hook detects the secret

#### Scenario: GitleaksAvailableWithoutNetwork

- **GIVEN** a non-network tool call is intercepted
- **WHEN** `gitleaks` is found on `PATH`, and the call carries a secret in a `SecretFormats` format
- **THEN** the hook detects the secret

#### Scenario: GitleaksMissing

- **GIVEN** a tool call is intercepted, a network send included
- **WHEN** `gitleaks` is not found on `PATH`, and the call carries a secret in a `SecretFormats` format
- **THEN** the hook detects the secret

#### Scenario: GitleaksFindsSecret

- **GIVEN** a Bash command that sends to a non-local destination, with `gitleaks` on `PATH`
- **WHEN** the command carries a secret the `gitleaks` rules detect
- **THEN** the hook exits 2 (block — exfiltration vector confirmed)

## REMOVED Requirements

### Requirement: AskOnSecretFileAccess

Removed because: it judged file paths as locations from a name list of its own, which never read the manifest.
A declared dotenv placeholder or name-heuristic exception that `sensitive-path-blocking` allows therefore still asked here, and was refused on every agent that cannot prompt.
The names `sensitive-path-blocking` already refuses (key and certificate files, SSH key names, `.env` files, `.netrc`, `.npmrc`, `.git-credentials`, the credential directories, and `secret` or `credentials` in a name) need no ask.
The names it did not judge move to `sensitive-path-blocking` `SuggestiveNamesAsk`, where the same exemptions and declarations apply.
