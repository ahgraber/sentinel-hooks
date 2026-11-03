# Delta for Secret Access Blocking

## MODIFIED Requirements

### Requirement: RefuseUserOnlyCredentialStores

> Previously: the store commands were found through the leak hook's own option tables for `op` and `kubectl`; the requirement did not state that a wrapper or a global option leaves the refusal in place.

The system SHALL block a Bash command that reads a secret from the 1Password CLI or from Kubernetes secrets, whether or not the command sends its output over the network.
The refusal reason SHALL state that the store is for the user alone, so that the agent asks the user to run the command.

The refusal SHALL hold whatever wrapper, path, or nesting carries the store command, and whatever global options precede its subcommand, as `program-catalog` `WrappersAreReadThrough` reads them.
Where the catalog cannot read the store command, because its entry is invalid or the reading ends before the subcommand, the system SHALL still refuse every store read it refuses today: under every spelling the shell decodes, in a Kubernetes resource list, and as the known command a launcher runs.
A text match over the raw command does not meet this on its own, because it does not decode the spelling or split a resource list.

A secret read into an agent's context reaches the model provider, so the read is itself an exfiltration vector in the sense of `RuleModes`.
Every agent's posture keeps these stores out of the agent's reach.
An ask cannot grant that access: on an agent whose sandbox denies the store's configuration, an approved read fails, and on an agent whose sandbox does not, approval would make that agent the exception.
A command that only checks the account or lists metadata reads no secret, and this requirement does not refuse it.

Serves: a-wrapper-read-once-holds-everywhere, unknown-reads-as-dangerous

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

#### Scenario: StoreReadUnderAWrapper

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs `op read 'op://vault/item/field'` under `env`, `nice`, `caffeinate -i`, or `/usr/bin/env`
- **THEN** the hook exits 2 (block)

#### Scenario: GlobalOptionsBeforeTheSubcommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `op --account work read 'op://vault/item/field'` or `kubectl --namespace prod get secret my-secret`
- **THEN** the hook exits 2 (block)

#### Scenario: StoreCommandWithAnInvalidEntry

- **GIVEN** the catalog entry for `op` is invalid
- **WHEN** the command is `op read 'op://vault/item/field'`
- **THEN** the hook exits 2 (block)

#### Scenario: ResourceListWithAnInvalidEntry

- **GIVEN** the catalog entry for `kubectl` is invalid
- **WHEN** the command is `kubectl get pods,secrets -o yaml`
- **THEN** the hook exits 2 (block)

#### Scenario: DecodedSpellingWithAnInvalidEntry

- **GIVEN** the catalog entry for `op` is invalid
- **WHEN** the command spells `op` in ANSI-C quoting, such as `$'o\x70' read 'op://vault/item/field'`
- **THEN** the hook exits 2 (block)

#### Scenario: StoreReadBuiltByALauncher

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `xargs kubectl get pods,secrets`
- **THEN** the hook exits 2 (block)
