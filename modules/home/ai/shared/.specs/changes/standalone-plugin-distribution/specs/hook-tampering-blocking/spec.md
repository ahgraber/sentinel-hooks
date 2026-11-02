# Delta for hook-tampering-blocking

## ADDED Requirements

### Requirement: PluginMaintenanceReachesTheUser

The system SHALL gate a Bash command that runs a supported harness's own command line to disable, uninstall, update, or prune an installed plugin, or to remove or update the marketplace a plugin came from, or to write the harness's settings.

A harness switches a plugin off through its own records, so the command names no path a declaration covers, and the path gates never see it.
Sentinel is a plugin, so each of these commands can switch it off or replace it in one step.
Updating and removing a plugin is ordinary maintenance, so the user decides it in the moment rather than the hook refusing it.

The commands are identifiers the harnesses publish, so they are named here: `claude plugin` `disable`, `uninstall`, `remove`, `rm`, `update`, `prune`, and `autoremove`, and `claude plugin marketplace` `remove`, `rm`, and `update`; `codex plugin remove` and `codex plugin marketplace` `remove` and `upgrade`; `copilot plugin` `disable`, `uninstall`, `remove`, `rm`, and `update`, and `copilot plugin marketplace` `remove` and `update`, and `copilot config` given a value to set, which writes a settings file that can set `disableAllHooks`; and `pi` `remove`, `uninstall`, `update`, and `config`.
The harness's legacy aliases for `plugin`, `plugins` in Claude Code and Copilot CLI, are the same command.

The program is identified as `UnrecognizedCommandsAreGated` identifies it, through a wrapper known to run its operands unchanged, and in every segment of the command.
A command whose program word does not resolve, such as a variable, is not recognized as one of these and is judged by the other gates alone.

Serves: protect-installed-copy

#### Scenario: PluginIsDisabled

- **GIVEN** a Bash command `claude plugin disable sentinel@sentinel-hooks`
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: PluginIsRemovedInAnotherHarness

- **GIVEN** a Bash command in one harness's session that uninstalls a plugin through another harness's command line, such as `copilot plugin uninstall sentinel`
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: MarketplaceIsRemoved

- **GIVEN** a Bash command that removes the marketplace Sentinel was installed from
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: PluginCommandBehindAWrapper

- **GIVEN** a plugin command run under `timeout`, or as a later segment of a `&&` list
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: PluginIsListed

- **GIVEN** a Bash command that lists or inspects plugins, such as `claude plugin list`
- **WHEN** the command is intercepted
- **THEN** the hook exits 0

### Requirement: SessionsWithoutTheHooksAreRefused

The system SHALL refuse a Bash command that starts a supported harness's session with its hooks or plugins switched off, or with a plugin loaded in place of an installed one.

A session started that way runs the agent's work with no Sentinel hook, so it escapes every guardrail at once, for as long as it runs.
One approval would grant that for every call the session makes, so the decision is a refusal, as for privilege escalation; the user can still start such a session in their own terminal.

The switches are identifiers the harnesses publish, so they are named here: Claude Code's `--bare`, `--safe-mode`, `--restricted`, `--plugin-dir`, `--plugin-url`, a `--settings` value that sets `disableAllHooks`, and the environment variables `CLAUDE_CODE_SIMPLE` and `CLAUDE_CODE_PLUGIN_DIRS`; Codex's `--disable hooks`, `--disable plugins`, and a `-c` override of `features.hooks`, `features.plugins`, or a plugin's `enabled`; Copilot CLI's `--plugin-dir`, `--config-dir`, and the environment variable `COPILOT_HOME`; and Pi's `--no-extensions`, `-ne`, `--extension`, and `-e`.

The program is identified as `PluginMaintenanceReachesTheUser` identifies it, and an environment assignment before the program is part of the command.

Serves: protect-installed-copy

#### Scenario: NestedSessionWithHooksOff

- **GIVEN** a Bash command `claude --bare -p "fix the tests"`
- **WHEN** the command is intercepted
- **THEN** the hook refuses it on every agent

#### Scenario: NestedSessionThroughAnOverride

- **GIVEN** a Bash command `codex exec -c features.hooks=false "fix the tests"`
- **WHEN** the command is intercepted
- **THEN** the hook refuses it on every agent

#### Scenario: NestedSessionThroughAnEnvironmentAssignment

- **GIVEN** a Bash command `CLAUDE_CODE_SIMPLE=1 claude -p "fix the tests"`
- **WHEN** the command is intercepted
- **THEN** the hook refuses it on every agent

#### Scenario: ExtensionReplacedInPi

- **GIVEN** a Bash command `pi -ne -e ./runner.ts`
- **WHEN** the command is intercepted
- **THEN** the hook refuses it on every agent

#### Scenario: NestedSessionWithHooksOn

- **GIVEN** a Bash command that starts a harness's session with none of these switches, such as `claude -p "fix the tests"`
- **WHEN** the command is intercepted
- **THEN** this requirement does not apply

## MODIFIED Requirements

### Requirement: Purpose

> Previously: the requirement named the guardrails of a configuration repository.

The system SHALL ensure that the files constraining an agent's behavior — its own or any other agent's — change only with the user's approval.

Every other guardrail Sentinel applies depends on this one.
A hook script, a permission rule, or a hook registration file is enforcement.
An edit to enforcement is not a routine edit: it removes or reshapes a constraint, and whether that happens is the user's decision alone.

The system SHALL put that decision to the user in the moment, where the invoking agent can prompt, and SHALL refuse the edit where it cannot.
A guard that can only refuse is a guard that gets disabled instead of consulted; maintenance that can be approved in-session stays inside the guardrails while it happens.

Agent credentials are the exception and SHALL be refused without a prompt.
No legitimate flow maintains a credential in-session, so a prompt there gains nothing and trains approval of the one request that should never come.

Serves: protect-installed-copy

### Requirement: ADestructiveOperationOnAnAncestorReachesTheUser

> Previously: the examples named directories of a configuration checkout.

The system SHALL gate an operation that removes, renames, or replaces a directory holding a declared location, or changes its permissions, owner, or attributes.

A declaration names a directory and protects what is inside it.
It does not protect the path to it, so `rm -rf ~/.pi` takes away the declared `~/.pi/agent/` while no word equals or falls inside any declaration.
No other layer closes this: guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, which means the permission layer permits the write by design.

The gate covers those operations alone.
Reading, searching, and creating files beneath an ancestor are ordinary work and SHALL stay unprompted.
Gating every command naming a prefix of a declaration reaches the home directory and the repository root.

A removal, a rename, or a replacement is a write under `guarded-path-declarations` `PrecedenceIsOneRule`; this gate reaches the ancestor that rule finds no declaration for.

An ancestor carries no declaration fragment, so it is found by resolving the path rather than by matching text.
A relative spelling resolves against the working directory the tool call supplies, moved by any earlier `cd` in the command.
Where no directory is supplied, or a `cd` names one the hook cannot resolve, the word is unresolvable, per `path-matching` `TextMatchingIsForTextThatMayHoldNoPath`.
The system SHALL refuse a removal, rename, or replacement of such a word on every agent, with the absolute-path instruction of `hook-interface` `BlockAIGuidance`.
It cannot be judged by its text: a `*` in a declaration matches almost any word, so judging its shape would refuse ordinary commands.
It is not put to the user either, because the user has no more to place it by than the hook.
The same command with the path written absolutely can be judged.

The gate knows the operation from the program, so a program it does not list passes on an ancestor.
So does a command assembled at run time, such as one `xargs` builds, and a branch switch, which changes every tracked file.

Serves: protect-installed-copy

#### Scenario: AnAncestorIsRemoved

- **GIVEN** a command that removes a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies, though the command names no declaration

#### Scenario: AnAncestorIsReplaced

- **GIVEN** a command that renames a directory over such a directory, or copies over it
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: AnAncestorsPermissionsChange

- **GIVEN** a command that changes the mode, owner, or attributes of a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: AnAncestorIsReachedThroughACd

- **GIVEN** a command that changes directory and then removes a relative path that resolves to a directory holding a declared location
- **WHEN** the command is intercepted
- **THEN** the gate applies

#### Scenario: OrdinaryWorkBeneathAnAncestor

- **GIVEN** a command that reads, searches, or creates a file beneath such a directory
- **WHEN** the command is intercepted
- **THEN** the hook exits 0

#### Scenario: ASiblingNamedLikeAnAncestor

- **GIVEN** a directory whose name begins with an ancestor's name but is not that directory
- **WHEN** a command removes it
- **THEN** the hook exits 0

#### Scenario: ARelativeOperandWithNoWorkingDirectory

- **GIVEN** a tool call that supplies no working directory
- **WHEN** its command removes, renames, or replaces a relative path
- **THEN** the hook refuses it on every agent with the absolute-path instruction

#### Scenario: AnAbsoluteOperandWithNoWorkingDirectory

- **GIVEN** a tool call that supplies no working directory
- **WHEN** its command removes an absolute path
- **THEN** the path is judged as it would be with a working directory
