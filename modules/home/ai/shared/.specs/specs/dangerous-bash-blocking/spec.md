# Spec: dangerous-bash-blocking

## Requirements

### Requirement: ToolScope

The system SHALL only evaluate commands when `tool_name` is `Bash`.

### Requirement: BlockReverseSells

The system SHALL block commands containing reverse shell patterns.

Reverse shell patterns include:

- Interactive bash redirected to a network socket (`bash -i` combined with `>&` and `/dev/`)
- Netcat with program execution (`nc -e` or `nc -c`)
- Direct TCP device node connections (`/dev/tcp/`, `/dev/udp/`)
- Socat with shell execution (`socat` combined with `exec:` or `system:`)
- One-liner reverse shells using scripting languages (Python, Perl, Ruby, PHP) that open a socket and exec a shell

#### Scenario: BashReverseShell

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command contains `bash -i` redirected to a network socket
- **THEN** the hook exits 2 with a reason identifying the reverse shell pattern

#### Scenario: NetcatShell

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command contains `nc -e /bin/sh` or equivalent
- **THEN** the hook exits 2

#### Scenario: LocalhostExemption

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command matches a reverse shell pattern but the target address is a loopback address (`127.0.0.1`, `localhost`, `::1`, `0.0.0.0`)
- **THEN** the hook exits 0 (local development tooling is permitted)

The localhost exemption SHALL apply to all reverse shell pattern families, including scripting language one-liners (Python, Perl, Ruby, PHP).
For `/dev/tcp` and `nc` patterns, the loopback address SHALL be checked in positional context (the host argument) rather than anywhere in the command, to prevent trivial bypass via appended text.
For scripting language patterns, where the host is embedded inside a string argument, a broader check for loopback addresses anywhere in the command is acceptable since these patterns already require specific socket/exec structures that limit false exemptions.

### Requirement: BlockPipeToShell

The system SHALL block commands that download and execute code in a single pipeline.

Pipe-to-shell patterns include:

- `curl` or `wget` output piped to `sh`, `bash`, `zsh`, `python`, or `ruby`
- `fetch` output piped to a shell interpreter

#### Scenario: CurlPipeShell

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command matches `curl ... | sh` or equivalent
- **THEN** the hook exits 2

### Requirement: BlockObfuscatedExec

The system SHALL block commands that decode and execute content at runtime.

Obfuscated execution patterns include:

- Base64-decoded content piped to a shell (`base64 -d ... | sh`)
- `eval` of a command substitution (`eval $(...)` or `` eval `...` ``)
- Hex-decoded content piped to a shell interpreter

#### Scenario: Base64Exec

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command decodes a base64 string and pipes the result to a shell
- **THEN** the hook exits 2

### Requirement: BlockClipboardAccess

The system SHALL block commands that read from the system clipboard.

Clipboard read patterns include:

- macOS: `pbpaste`
- Linux (X11): `xclip -o`, `xclip --output`, `xsel --output`, `xsel -o`
- Linux (Wayland): `wl-paste`
- PowerShell clipboard access invoked from a shell

The clipboard may contain passwords, tokens, or other secrets the user has recently copied.
Blocking reads (not writes) is sufficient; writing to the clipboard poses no direct leakage risk.

#### Scenario: PbpasteRead

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command invokes `pbpaste`
- **THEN** the hook exits 2

#### Scenario: XclipRead

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command invokes `xclip -o` or `xsel --output`
- **THEN** the hook exits 2

### Requirement: BlockForkBombs

The system SHALL block the canonical fork bomb pattern: a function that calls itself, pipes to itself, and backgrounds the result (e.g., `:(){ :|:& };:`).

The detection pattern SHALL require self-reference (the function body invokes the function's own name).
A function definition that merely contains a pipe and a background operator is NOT a fork bomb and SHALL NOT be blocked.

#### Scenario: ForkBomb

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command contains the canonical fork bomb pattern (a function that recurses and forks itself)
- **THEN** the hook exits 2

#### Scenario: LegitimateBackgroundPipeline

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command defines a function that contains a pipe and a background operator but does NOT recursively call itself
- **THEN** the hook exits 0 (this is a legitimate function definition, not a fork bomb)

### Requirement: BlockCronInjection

The system SHALL block commands that install or replace cron jobs via piping content into `crontab`.

Cron injection patterns include:

- Content piped to `crontab` (`... | crontab`)
- `crontab` invoked with a file argument to replace the current crontab (`crontab myfile`)
- Direct crontab replacement from stdin (`crontab -`)

The pattern SHALL NOT match read-only crontab operations such as `crontab -l` (list).
The pattern SHALL NOT match the word "crontab" appearing in unrelated contexts (e.g., `echo "check the crontab docs"`).

#### Scenario: PipeToCrontab

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command pipes content into `crontab`
- **THEN** the hook exits 2

#### Scenario: CrontabListAllowed

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `crontab -l`
- **THEN** the hook exits 0

### Requirement: BlockSshKeyManipulation

The system SHALL block commands that inject or overwrite SSH authorized keys, which could establish persistent unauthorized access.

SSH key manipulation patterns include:

- Appending to or overwriting `~/.ssh/authorized_keys` via redirections
- Copying key files into `~/.ssh/`

#### Scenario: AppendToAuthorizedKeys

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command appends to `authorized_keys`
- **THEN** the hook exits 2

### Requirement: BlockPrivilegeEscalation

The system SHALL block commands that elevate to root or another user's privileges.

Privilege escalation patterns include:

- `sudo` at the start of a command or after a command separator
- `su` at the start of a command or after a command separator

Claude Code should operate within the current user's permissions.
Commands requiring elevated privileges should be delegated to the user to run manually.

#### Scenario: SudoCommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command invokes `sudo`
- **THEN** the hook exits 2

### Requirement: BlockDangerousMacOSInteraction

The system SHALL block commands that execute arbitrary AppleScript or modify system preferences.

Blocked macOS patterns include:

- `osascript` — executes arbitrary AppleScript, which can control any application, send keystrokes, or access accessibility features
- `defaults write` — modifies macOS system or application preferences, which can alter security settings or application behavior

The `open` command SHALL NOT be blocked by this hook.
While `open` can launch applications, it is a routine macOS development command (`open .`, `open README.md`, `open https://...`) and blocking it would be excessively disruptive.
If `open` control is desired, it should be an `ask`-mode rule in `destructive-ops-blocking` rather than a hard block here.

#### Scenario: OsascriptBlocked

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command invokes `osascript`
- **THEN** the hook exits 2

#### Scenario: DefaultsWriteBlocked

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command invokes `defaults write`
- **THEN** the hook exits 2

#### Scenario: OpenAllowed

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command invokes `open`
- **THEN** the hook exits 0 (not blocked by this hook)
