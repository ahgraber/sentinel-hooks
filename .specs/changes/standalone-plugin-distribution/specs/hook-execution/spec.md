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
