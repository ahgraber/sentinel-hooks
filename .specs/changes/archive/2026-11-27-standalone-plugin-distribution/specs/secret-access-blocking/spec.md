# Delta for Secret Access Blocking

## MODIFIED Requirements

### Requirement: RefuseUserOnlyCredentialStores

> Previously: text nested past the hook's reading depth, and text the lexer cannot read, were judged by a text match that a reordered argument passed, the program was recognized only by the exact case of its name, a subcommand's option before the subcommand hid the read, and the requirement did not say what happens there.

The system SHALL block a Bash command that reads a secret from the 1Password CLI or from Kubernetes secrets, whether or not the command sends its output over the network.
The refusal reason SHALL state that the store is for the user alone, so that the agent asks the user to run the command.

A secret read into an agent's context reaches the model provider, so the read is itself an exfiltration vector in the sense of `RuleModes`.
Every agent's posture keeps these stores out of the agent's reach.
An ask cannot grant that access: on an agent whose sandbox denies the store's configuration, an approved read fails, and on an agent whose sandbox does not, approval would make that agent the exception.
A command that only checks the account or lists metadata reads no secret, and this requirement does not refuse it.
The store program SHALL be recognized whatever the case of its name, because macOS's default filesystem finds a program that way, so `OP read` runs `op read`.
An option before the subcommand SHALL NOT hide the read, whether it is a global option, one of the subcommand's own, or a wrapper's; a command in which an option's value is itself a subcommand word, as in `op item list --tags read`, is refused as well.
Text the lexer cannot read, such as a here-string or a process substitution, SHALL be judged command by command by the same rules, any word of a command taken as its program.
A command that nests program text or launchers deeper than the hook reads SHALL be refused when the unread text names `op` or `kubectl` as a word, whether or not it reads a secret; text the lexer gives up on because it nests deeper than the lexer reads counts as nested past the limit.
Text nested that deep does not occur in ordinary work, and refusing it there keeps one more level of nesting from hiding a store read.

Serves: no story of this change; the change answers findings of this change's verification, that a reordered argument, a program name in another case, and an option before the subcommand each hid a store read.

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

#### Scenario: StoreNamedPastTheNestingLimit

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command nests program text deeper than the hook reads, and the unread text names `kubectl`
- **THEN** the hook exits 2 (block)

#### Scenario: StoreReadTheLexerCannotRead

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a Kubernetes secret inside a process substitution, such as `diff <(kubectl get -o yaml secret a) b`
- **THEN** the hook exits 2 (block)

#### Scenario: StoreReadWithAnOptionBeforeItsSubcommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a secret with one of the subcommand's options before the subcommand, such as `kubectl -o yaml get secret a` or `op item --vault v get x`
- **THEN** the hook exits 2 (block)
