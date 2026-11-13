# Delta for sensitive-path-blocking

## MODIFIED Requirements

### Requirement: PackageDirExemption

> Previously: the exemption also covered the hook sources of a configuration checkout.

Name-based patterns (`credentials`, `secret`) SHALL NOT apply to paths within package or dependency directories, where these are valid module or source file names rather than credential stores.

Package and dependency directories include:

- `.venv/`, `venv/`, `env/` (Python virtual environments)
- `site-packages/` (anywhere in the path)
- `node_modules/`
- Any path segment matching a common package manager output directory

Path-based patterns (e.g., `~/.aws/**`, `~/.ssh/**`, `*.pem`) are not subject to this exemption and remain zero-access regardless of location.

The exemption SHALL NOT depend on a file that an agent can create without asking the user.
A file planted in a project would otherwise switch the name-based patterns off for every path beside it.

No file in this repository's plugin, extension, or test directories SHALL have a name that matches a name-based pattern.
Sentinel's own files are then reachable without any exemption, in a checkout and in every installed copy.

Serves: one-tree, protect-installed-copy

<!-- modified-removes: GuardrailSourceNamedForWhatItBlocks -->

#### Scenario: APlantedHookSourceDoesNotExempt

- **GIVEN** a directory holds a file at `hooks/guarded_paths.py`
- **WHEN** a Read, Write, or Edit tool call targets a file beside it whose name matches a name-based pattern
- **THEN** the hook exits 2

#### Scenario: NoSentinelFileMatchesANamePattern

- **GIVEN** the files under this repository's plugin, extension, and test directories
- **WHEN** each file name is checked against the name-based patterns
- **THEN** none matches

#### Scenario: CredentialsModuleInVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` but contains `.venv/` in the path
- **THEN** the hook exits 0 (library source, not a credential store)

#### Scenario: CredentialsFileOutsideVenv

- **GIVEN** a Write or Edit tool call is intercepted
- **WHEN** `tool_input.path` matches `*credentials*` and is not within a package directory
- **THEN** the hook exits 2
