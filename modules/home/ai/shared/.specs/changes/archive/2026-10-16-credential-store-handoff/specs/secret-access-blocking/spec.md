# Delta: secret-access-blocking

## ADDED Requirements

### Requirement: RefuseUserOnlyCredentialStores

The system SHALL block a Bash command that reads a secret from the 1Password CLI or from Kubernetes secrets, whether or not the command sends its output over the network.
The refusal reason SHALL state that the store is for the user alone, so that the agent asks the user to run the command.

A secret read into an agent's context reaches the model provider, so the read is itself an exfiltration vector in the sense of `RuleModes`.
Every agent's posture keeps these stores out of the agent's reach.
An ask cannot grant that access: on an agent whose sandbox denies the store's configuration, an approved read fails, and on an agent whose sandbox does not, approval would make that agent the exception.
A command that only checks the account or lists metadata reads no secret, and this requirement does not refuse it.

Serves: hand-off-not-dead-end, one-answer-per-store

#### Scenario: OnePasswordSecretRead

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a secret through the 1Password CLI, such as `op read 'op://vault/item/field'`
- **THEN** the hook exits 2 (block), and the reason states that the user must run the command

#### Scenario: OnePasswordSecretInjectedIntoCommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs another program with 1Password secrets in its environment, such as `op run --env-file .env.op -- pytest`
- **THEN** the hook exits 2 (block)

#### Scenario: KubernetesSecretRead

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a Kubernetes secret, such as `kubectl get secret my-secret -o yaml`
- **THEN** the hook exits 2 (block), and the reason states that the user must run the command

#### Scenario: UserOnlyStoreReadAndSend

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a 1Password secret and pipes the result to a non-local network command
- **THEN** the hook exits 2 (block)

#### Scenario: OnePasswordAccountCheck

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs a 1Password CLI command that reads no secret, such as `op whoami`
- **THEN** this requirement does not block the command

## MODIFIED Requirements

### Requirement: BlockSecretExfiltration

The system SHALL block (deny) Bash commands that transmit secrets over the network.

A Bash command that carries a secret in a network-sending context SHALL be blocked.
Without that context, the hook asks the user about the same secret, per `UniversalSecretScan`.

This includes:

- A literal secret pattern in a command alongside a network-sending tool (`curl`, `wget`, `nc`, `ssh`, `scp`, `rsync`)
- Credential store reads (`security find-generic-password`, `.netrc`, token files) piped to network commands
- Environment variable dumps (`env`, `printenv`, `export -p`) piped to network commands
- Data encoded into DNS queries as a covert channel (`dig`, `nslookup`, `host` with subshell-constructed subdomains)

> Previously: the loopback exemption applied to every command, including a read from a store `RefuseUserOnlyCredentialStores` covers.

Serves: one-answer-per-store

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

The exemption does not apply to a read from a store `RefuseUserOnlyCredentialStores` covers: the read places the secret in the agent's context, which reaches the model provider before any local destination does.

#### Scenario: UserOnlyStoreReadToLoopback

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a 1Password secret and pipes the result to a loopback address
- **THEN** the hook exits 2 (block — handled by `RefuseUserOnlyCredentialStores`)

### Requirement: AskOnCredentialStoreRead

The system SHALL ask (confirm) when a Bash command reads from a system credential store that `RefuseUserOnlyCredentialStores` does not cover, without piping the output to a network command.

This covers legitimate debugging: checking which credentials are stored, verifying a token value, or inspecting a credential helper.

> Previously: every credential-store read without a network send asked, including 1Password and Kubernetes secrets.

Serves: one-answer-per-store

#### Scenario: KeychainReadLocal

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain but does not pipe to a network command
- **THEN** the hook exits 0 with `permissionDecision: "ask"`

#### Scenario: KeychainReadAndSend

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain and pipes the result to a network command
- **THEN** the hook exits 2 (block — handled by `BlockSecretExfiltration`)
