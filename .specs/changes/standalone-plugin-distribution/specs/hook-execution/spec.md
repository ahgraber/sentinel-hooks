# Delta for hook-execution

## ADDED Requirements

### Requirement: PackageHooksAreGivenThePackageDirectory

Every hook the package's registration file declares SHALL run with the environment variable `PLUGIN_ROOT` set to the absolute path of the installed plugin directory that holds the extension.
A hook the agent directory's registration file declares SHALL run without `PLUGIN_ROOT` set by the extension.

A hook command runs in the session's working directory, so a package hook cannot name its script by a path relative to the package.
`PLUGIN_ROOT` is the name Codex and Copilot set for the same purpose, so one command form serves every harness.
The value is wherever Pi installed the package, so no registration names a fixed install path.
A user's own hook belongs to no package, as a hook in a user's settings belongs to no plugin in Claude Code.

Serves: install-per-agent

#### Scenario: PackageHookReadsThePackageDirectory

- **GIVEN** a hook in the package's registration file that prints `PLUGIN_ROOT`
- **WHEN** it runs in a session started in a project directory
- **THEN** it prints the absolute path of the plugin directory inside the package Pi installed

#### Scenario: UserHookHasNoPackageDirectory

- **GIVEN** a hook in the agent directory's registration file that prints `PLUGIN_ROOT`, in a Pi process whose environment does not set it
- **WHEN** it runs
- **THEN** it prints nothing

### Requirement: ASystemMessageReachesTheUser

The extension SHALL show the user the `systemMessage` a hook's JSON reply carries, on every event and whatever the hook decides.

Claude Code and Codex show this field to the user, and a hook uses it for a report the user must see and the model need not act on.
The session-start check reports the settings that defeat the hooks this way, so the same reply reaches the user in Pi.
Where Pi has no UI, the message goes to standard error, as the extension's other reports do.

Serves: install-per-agent

#### Scenario: SessionHookReportsThroughASystemMessage

- **GIVEN** a `SessionStart` hook that exits 0 with a `systemMessage` on standard output
- **WHEN** a session starts
- **THEN** the user is shown the message, and the session proceeds

#### Scenario: SystemMessageBesideADecision

- **GIVEN** a `PreToolUse` hook whose JSON reply carries a `permissionDecision` and a `systemMessage`
- **WHEN** the agent makes a matching tool call
- **THEN** the user is shown the message, and the decision stands
