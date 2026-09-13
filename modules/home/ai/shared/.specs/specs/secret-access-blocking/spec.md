# Spec: secret-access-blocking

## Requirements

### Requirement: ToolScope

The system SHALL evaluate ALL tool calls, regardless of tool name.

Secrets can appear in any tool argument — a command string, file content, a URL, a grep pattern, a file path.
Rather than enumerating specific tools and fields, the hook SHALL scan the serialized `tool_input` object for every invocation.

Tool-specific handling is layered on top of the universal scan:

- `Bash`: additional context-aware analysis (network-sending detection, credential store reads, localhost exemption)
- `Read`: file path heuristics for likely-secret files
- `Write`/`Edit`: file path heuristics (same as Read) plus content payload scanning
- All other tools: universal scan only

### Requirement: UniversalSecretScan

The system SHALL serialize `tool_input` to a string and scan it for secret patterns on every tool call.

This catch-all ensures secrets are detected regardless of which tool or argument they appear in — a URL containing an API key in WebFetch, a grep pattern containing a private key header, or any future tool with arguments we haven't anticipated.

A finding from the universal scan is always `ask` mode, since without tool-specific context the hook cannot determine whether exfiltration is occurring.

#### Scenario: SecretInAnyToolArg

- **GIVEN** any tool call is intercepted
- **WHEN** the serialized `tool_input` contains a string matching a known secret pattern
- **THEN** the hook exits 0 with `permissionDecision: "ask"`

#### Scenario: CleanToolInput

- **GIVEN** any tool call is intercepted
- **WHEN** no secret patterns are found in the serialized `tool_input`
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

This is a Bash-specific escalation: the universal scan finds the secret (ask), but if the Bash command also contains a network-sending context, the mode escalates to block.

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

Whether a supplied path denotes a credential store SHALL be determined according to `path-matching`.
A store reached by a differing letter case on a case-insensitive filesystem is the same store, and SHALL prompt.

#### Scenario: CaseVariantCredentialStore

- **GIVEN** a Read tool call is intercepted on a case-insensitive filesystem
- **WHEN** the target is a credential store named under a differing letter case
- **THEN** the hook asks

#### Scenario: KeychainReadLocal

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain but does not pipe to a network command
- **THEN** the hook exits 0 with `permissionDecision: "ask"`

#### Scenario: KeychainReadAndSend

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain and pipes the result to a network command
- **THEN** the hook exits 2 (block — handled by `BlockSecretExfiltration`)

### Requirement: AskOnSecretFileAccess

The system SHALL ask (confirm) when a `Read`, `Write`, or `Edit` tool call targets a file whose content is likely to contain secrets, **except** where `sensitive-path-blocking` has already hard-blocked the path.

Because `block-sensitive-paths.py` runs before this hook and hard-blocks `Read`, `Write`, and `Edit` to zero-access paths, paths such as `~/.ssh/id_ed25519` or `~/.aws/credentials` will never reach this hook's ask logic.
This hook's `ask` for credential-dir reads remains the protection layer for paths outside the zero-access list (e.g., `~/.netrc`) that are not hard-blocked by `block-sensitive-paths.py`.

Every ask response produced by this requirement SHALL comply with the `ExplanationContract` defined in `hook-interface`: the `permissionDecisionReason` MUST state both what the operation would do (read/write a likely-secret file) and what the specific danger is (exposure of credentials to Claude's context window, enabling potential downstream exfiltration).
It SHALL name the specific file.

Location matching SHALL be determined according to `path-matching`.
Basename matching in this requirement applies case-insensitively and is unaffected.

Detection uses two independent heuristic checks:

**Check 1 — Credential file names:**

Files with names matching common credential file patterns:

- Key and certificate extensions: `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*.keystore`, `*.jks`
- SSH key names: `id_rsa`, `id_ed25519`, `id_ecdsa`, `id_dsa`
- Credential config files: `.npmrc`, `.netrc`, `.git-credentials`
- Files whose basename contains `token`, `password`, `passwd`, `api_key`, or `auth_key` (case-insensitive)
- Files whose basename contains `secret` or `credential` (case-insensitive), subject to the `PackageDirExemption` defined in `sensitive-path-blocking`

**Check 2 — Credential directory prefixes:**

Any file within well-known credential directories:

- `~/.ssh/` — SSH keys, known hosts, agent sockets
- `~/.aws/` — AWS credentials and config
- `~/.kube/` — Kubernetes cluster credentials
- `~/.gnupg/` — GPG keyrings and trust databases

Note: this requirement overlaps with `sensitive-path-blocking` and with sandbox `denyRead` rules.
Where `sensitive-path-blocking` hard-blocks a path (for Read, Write, or Edit), that takes precedence and this hook's ask logic is not reached for that path.
Where sandbox `denyRead` blocks reads to a directory, the sandbox block takes precedence.
This requirement applies `ask` to paths that are not already blocked by either mechanism but still likely to contain secrets — for example, `Read(~/.netrc)` is not in the zero-access list and not blocked by sandbox `denyRead`, so this hook's ask is the only protection.

#### Scenario: ReadSshPrivateKey

- **GIVEN** a Read tool call is intercepted by this hook
- **WHEN** `tool_input.file_path` matches `~/.ssh/id_*`
- **THEN** the hook exits 0 with `permissionDecision: "ask"` and a reason that names the file, describes that it likely contains a private key, and warns that reading it places the key in Claude's context where it could be incorporated into a subsequent command or network call

#### Scenario: ReadNetrcFile

- **GIVEN** a Read tool call is intercepted by this hook
- **WHEN** `tool_input.file_path` is `~/.netrc` (not in the zero-access list, so not blocked by `block-sensitive-paths.py`)
- **THEN** the hook exits 0 with `permissionDecision: "ask"` and a reason that names the file, describes that it contains plaintext usernames and passwords for remote hosts, and warns that reading it places those credentials in Claude's context where they could be incorporated into a subsequent command or network call

#### Scenario: ReadTokenFileInProject

- **GIVEN** a Read tool call is intercepted by this hook
- **WHEN** `tool_input.file_path` matches `*token*` in the project directory (not in a package dir)
- **THEN** the hook exits 0 with `permissionDecision: "ask"` and a reason that names the file, explains why its name suggests it may contain an access token, and notes that the token could be read into context and used in subsequent operations

#### Scenario: ReadSecretsJsonInProject

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.path` is `secrets.json` in the project directory (not in a package dir)
- **THEN** the hook exits 0 with `permissionDecision: "ask"`

#### Scenario: ReadCredentialsModuleInVenv

- **GIVEN** a Read tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` but contains `.venv/` in the path
- **THEN** the hook exits 0 silently (package-dir exemption applies)

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

The built-in pattern set SHALL be curated for high precision (minimizing false positives) rather than exhaustive coverage.
Gitleaks provides comprehensive coverage on the deep-scan path (see `TieredSecretDetection`).
The built-in patterns are a focused safety net, not a replication of the gitleaks corpus.

### Requirement: TieredSecretDetection

The system SHALL use a two-tier detection model that balances coverage against latency.

**Tier 1 — Built-in patterns (all tool calls):**

A set of high-precision regex patterns covering the most common secret formats (API keys, PEM headers, bearer tokens, cloud provider credentials).
These run on every tool call as part of the universal scan.
Latency is negligible (~microseconds).

Built-in patterns are the primary detection mechanism for non-exfiltration contexts (local Bash commands, Read, Write, Edit, and all other tools).
They are sufficient for the ask-mode use case, where the cost of a false negative is a missed confirmation prompt rather than a leaked secret.

**Tier 2 — Gitleaks deep scan (Bash + network context only):**

When a Bash command contains a network-sending context (and the target is not localhost), gitleaks is invoked for comprehensive scanning (~400+ rules).
This is the exfiltration detection path, where a missed secret could result in credential leakage to a remote host.

Gitleaks is NOT invoked on every tool call because:

- Its startup cost (~100ms+) would compound across every tool invocation
- The risk profile of non-network contexts (ask-mode prompts) does not justify the latency
- Built-in patterns cover the high-confidence formats that appear in tool arguments

When gitleaks is not available on `PATH`, the deep scan falls back to built-in patterns.
Coverage is reduced for the exfiltration path, but the `SessionStart` hook warns the user (see `session-tool-checks`).

Scan surfaces by tier:

| Context                    | Tier 1 (built-in)                         | Tier 2 (gitleaks) |
| -------------------------- | ----------------------------------------- | ----------------- |
| Bash + network (non-local) | yes                                       | yes               |
| Bash (local or no network) | yes                                       | no                |
| Read / Write / Edit        | yes                                       | no                |
| All other tools            | yes                                       | no                |
| File path heuristics       | independent (see `AskOnSecretFileAccess`) | n/a               |

#### Scenario: GitleaksAvailableWithNetwork

- **GIVEN** a Bash tool call with a non-local network destination is intercepted
- **WHEN** `gitleaks` is found on `PATH`
- **THEN** the hook invokes gitleaks for deep scanning in addition to built-in patterns

#### Scenario: GitleaksAvailableWithoutNetwork

- **GIVEN** a non-network tool call is intercepted
- **WHEN** `gitleaks` is found on `PATH`
- **THEN** the hook uses only built-in patterns (gitleaks is not invoked)

#### Scenario: GitleaksMissing

- **GIVEN** a tool call is intercepted
- **WHEN** `gitleaks` is not found on `PATH`
- **THEN** the hook uses built-in patterns for all contexts (deep scan is unavailable)

#### Scenario: GitleaksFindsSecret

- **GIVEN** gitleaks is invoked on a Bash command with network context
- **WHEN** gitleaks reports a finding
- **THEN** the hook exits 2 (block — exfiltration vector confirmed)
