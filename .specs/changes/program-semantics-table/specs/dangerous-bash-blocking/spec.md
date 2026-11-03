# Delta for Dangerous Bash Blocking

## MODIFIED Requirements

### Requirement: BlockPrivilegeEscalation

> Previously: the rule matched `sudo` and `su` as text at the start of a command or after a command separator, so a wrapper, a path, a leading space, an escape, and `doas` passed.

The system SHALL block every Bash command that runs a program as root or as another user, whatever wrapper, path, or nesting carries it.

A command runs a program as another user when any segment, or any command line or shell text read through it as `program-catalog` `WrappersAreReadThrough` requires, invokes a program the catalog states as changing the user it runs as: `sudo`, `su`, `doas`, `pkexec`, `run0`, `runuser`, `setpriv`, and the others the catalog lists.
A program is matched by its base name, so `/usr/bin/sudo` and a nix store `sudo` are `sudo`.
A command that only looks a privilege tool up, such as `command -v sudo`, does not run it.

Where the reading of a segment ends, the system SHALL block the command when a program the segment may run, as `program-catalog` `AnIncompleteReadingEndsRecognition` counts them, changes the user it runs as.
This covers a command line the lexer has not split, such as `env -S 'doas id'`, an invalid wrapper entry, an abbreviated option, and nesting beyond the bound.

The text match of `sudo` and `su` at the start of a command or after a command separator SHALL remain beside the reading, so no command it blocks today proceeds, including one whose reading ends before its program is known.
Whether a text match stops blocking a mention inside a quoted argument is decided by `single-command-rule-engine`, not here.

Agents operate within the current user's permissions.
Commands requiring elevated privileges are delegated to the user to run.

Serves: a-wrapper-read-once-holds-everywhere

#### Scenario: SudoCommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command invokes `sudo`
- **THEN** the hook exits 2

#### Scenario: PrivilegeUnderAWrapper

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs `sudo` under `env`, `nohup`, `timeout 5`, `nice`, or `command`
- **THEN** the command is blocked

#### Scenario: PrivilegeByPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs `/usr/bin/sudo` or a `sudo` held in the nix store
- **THEN** the command is blocked

#### Scenario: AnotherPrivilegeTool

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs `doas`, `pkexec`, or `run0`
- **THEN** the command is blocked

#### Scenario: PrivilegeInsideShellText

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command runs `bash -c 'sudo id'`
- **THEN** the command is blocked

#### Scenario: PrivilegeInAnUnsplitCommandLine

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `env -S 'doas id'`
- **THEN** the command is blocked

#### Scenario: PrivilegeQuotedInAnUnsplitCommandLine

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `env -S "'doas' id"`
- **THEN** the command is blocked

#### Scenario: PrivilegeSplitByTheWrappersOwnEscape

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `env -S 'doas\_id'`, which `env -S` splits into `doas` and `id`
- **THEN** the command is blocked

#### Scenario: PrivilegeBehindAnInvalidWrapperEntry

- **GIVEN** the catalog entry for `env` is invalid
- **WHEN** the command is `env doas id`
- **THEN** the command is blocked

#### Scenario: PrivilegeBeyondTheNestingBound

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command nests transparent wrappers beyond the bound before `doas`
- **THEN** the command is blocked

#### Scenario: ALookup

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `command -v sudo`
- **THEN** this requirement does not block the command
