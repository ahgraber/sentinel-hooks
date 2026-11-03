# Delta for sensitive-path-blocking

## MODIFIED Requirements

### Requirement: PackageDirExemption

> Previously: the exemption covered the hook sources of a configuration checkout, and no installed copy.

Name-based patterns (`credentials`, `secret`) SHALL NOT apply to paths within package or dependency directories, where these are valid module or source file names rather than credential stores.

Package and dependency directories include:

- `.venv/`, `venv/`, `env/` (Python virtual environments)
- `site-packages/` (anywhere in the path)
- `node_modules/`
- Any path segment matching a common package manager output directory

Path-based patterns (e.g., `~/.aws/**`, `~/.ssh/**`, `*.pem`) are not subject to this exemption and remain zero-access regardless of location.

The exemption SHALL cover the directories holding Sentinel's own hook sources, for every agent, in a checkout of this repository and in every installed copy of the plugin, and the checkout's test directory.
Those directories hold files whose names describe what they guard against, not what they contain.
Reaching one of them requires the name-based patterns not to apply, and an agent that cannot read or write its own guardrail source cannot maintain it.

The exemption SHALL cover the hook-source directory of every harness Sentinel supports.
This includes a directory added or moved later, with no edit to the exemption.
Naming the harnesses one at a time leaves a directory uncovered whenever these modules move, making a guardrail source unreachable to the people responsible for it.

Serves: one-tree, protect-installed-copy

<!-- modified-removes: GuardrailSourceNamedForWhatItBlocks -->

#### Scenario: GuardrailSourceInACheckout

- **GIVEN** a Read, Write, or Edit tool call is intercepted
- **WHEN** the target is a hook source or a test in a checkout of this repository whose name matches a name-based pattern
- **THEN** the hook exits 0

#### Scenario: GuardrailSourceInAnInstalledCopy

- **GIVEN** a Read tool call is intercepted
- **WHEN** the target is a hook source in an installed copy of the plugin whose name matches a name-based pattern
- **THEN** the hook exits 0

#### Scenario: CredentialsModuleInVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` but contains `.venv/` in the path
- **THEN** the hook exits 0 (library source, not a credential store)

#### Scenario: CredentialsFileOutsideVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` and is not within a package directory
- **THEN** the hook exits 2
