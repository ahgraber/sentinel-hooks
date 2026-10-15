# Delta: secret-access-blocking

## ADDED Requirements

### Requirement: RefuseUserOnlyCredentialStores

The system SHALL block a Bash command that reads a secret from the 1Password CLI or from Kubernetes secrets, whether or not the command sends its output over the network.
The refusal reason SHALL state that the store is for the user alone, so that the agent asks the user to run the command.

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
