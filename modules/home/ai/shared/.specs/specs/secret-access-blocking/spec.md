# Spec: secret-access-blocking

## Purpose

Credentials can leave the machine inside a tool call, typed into a command, sent over the network, or read from a credential store, without any protected file being read.
These requirements cover which calls are scanned, how secret formats are recognized, and when a credential-store read or a send is refused or put to the user.

## Requirements

### Requirement: ToolScope

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

### Requirement: UniversalSecretScan

The system SHALL detect a secret in any field of `tool_input` on every tool call.

This catch-all ensures secrets are detected regardless of which tool or argument they appear in — a URL containing an API key in WebFetch, a grep pattern containing a private key header, or any future tool with arguments we haven't anticipated.

A finding from the universal scan is always `ask` mode, since without tool-specific context the hook cannot determine whether exfiltration is occurring.

#### Scenario: SecretInAnyToolArg

- **GIVEN** any tool call is intercepted
- **WHEN** a field of `tool_input` contains a string matching a known secret format
- **THEN** the hook exits 0 with `permissionDecision: "ask"`

#### Scenario: CleanToolInput

- **GIVEN** any tool call is intercepted
- **WHEN** no field of `tool_input` contains a known secret format
- **THEN** the hook exits 0 (allow)

### Requirement: RuleModes

Each detection rule SHALL be classified as `block` or `ask`.

**`block`** — the operation is an active exfiltration vector and is never permitted.
The hook exits 2 with an explanation.

**`ask`** — the operation involves secrets but may be legitimate (e.g., debugging, verifying configuration).
The hook exits 0 with `permissionDecision: "ask"` JSON (see `hook-interface`).

The user may be using Claude to debug authentication flows, inspect token validity, or troubleshoot credential configuration.
The `ask` path ensures they are not locked out of their own secrets while still requiring conscious confirmation.

### Requirement: BlockSecretExfiltration

The system SHALL block (deny) Bash commands that transmit secrets over the network.

A Bash command that carries a secret in a network-sending context SHALL be blocked.
Without that context, the hook asks the user about the same secret, per `UniversalSecretScan`.

This includes:

- A literal secret pattern in a command alongside a network-sending tool (`curl`, `wget`, `nc`, `ssh`, `scp`, `rsync`)
- Credential store reads (`security find-generic-password`, `.netrc`, token files) piped to network commands
- Environment variable dumps (`env`, `printenv`, `export -p`) piped to network commands
- Data encoded into DNS queries as a covert channel (`dig`, `nslookup`, `host` with subshell-constructed subdomains)

#### Scenario: ApiKeyInCurlHeader

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command contains a literal API key string in a `curl -H` argument
- **THEN** the hook exits 2 (block)

#### Scenario: EnvDumpToNetwork

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command pipes `env` or `printenv` output to a network-sending command
- **THEN** the hook exits 2 (block)

#### Scenario: DnsSubdomainExfil

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command constructs a DNS lookup with a subshell or variable expansion in the hostname
- **THEN** the hook exits 2 (block)

#### Scenario: LocalhostExemption

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a secret+network pattern is matched but the target is a loopback address (`127.0.0.1`, `localhost`, `::1`, `0.0.0.0`)
- **THEN** the hook exits 0 (local dev servers may require real credentials)

The localhost check SHALL cover all network tool patterns detected by the hook, including:

- URL-based tools: `curl`, `wget` — check for `http(s)://localhost` or loopback IP in the URL
- Connection-based tools: `nc`, `ncat` — check for loopback address as the host argument
- File transfer tools: `scp`, `rsync`, `ssh` — check for loopback address in the host argument (e.g., `scp file localhost:...`, `rsync ... localhost:...`)

A command SHALL NOT be classified as local merely because a loopback address appears anywhere in the command text.
The loopback address SHALL be checked in the host/destination position for the relevant network tool.

### Requirement: AskOnCredentialStoreRead

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

### Requirement: SecretFormats

Secret formats include API tokens, private key material, and certificates — anything that could be used to authenticate as or impersonate the user.

**API tokens:**

- Anthropic API keys (`sk-ant-`)
- OpenAI API keys (`sk-`)
- GitHub personal access tokens (`ghp_`, `github_pat_`)
- AWS access key IDs (`AKIA[0-9A-Z]{16}`)
- Slack tokens (`xoxb-`, `xoxp-`)
- Bearer token header values (`Authorization: Bearer ...`)

**Private key material and certificates:**

- PEM-encoded private keys (`-----BEGIN RSA PRIVATE KEY-----`, `-----BEGIN EC PRIVATE KEY-----`, `-----BEGIN OPENSSH PRIVATE KEY-----`, `-----BEGIN PRIVATE KEY-----`)
- GPG private key blocks (`-----BEGIN PGP PRIVATE KEY BLOCK-----`)
- Client certificate material (`-----BEGIN CERTIFICATE-----`)

The listed formats SHALL be detected on every tool call.
They SHALL be chosen so that a match is almost always a real secret.
`TieredSecretDetection` adds coverage on network sends.

### Requirement: TieredSecretDetection

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
