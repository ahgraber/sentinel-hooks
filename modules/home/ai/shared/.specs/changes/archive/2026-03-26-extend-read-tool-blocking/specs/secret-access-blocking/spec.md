# Delta for secret-access-blocking

## MODIFIED Requirements

### Requirement: AskOnSecretFileAccess

The system SHALL ask (confirm) when a `Read`, `Write`, or `Edit` tool call targets a file
whose content is likely to contain secrets, **except** where `sensitive-path-blocking`
has already hard-blocked the path. (Previously: no explicit layering note; zero-access
paths were protected only by sandbox `denyRead`, which does not enforce against the Read
tool.)

Because `block-sensitive-paths.py` now runs before this hook (per hook execution order) and hard-blocks `Read`, `Write`, and `Edit` to zero-access paths, paths such as `~/.ssh/id_ed25519` or `~/.aws/credentials` will never reach this hook's ask logic.
This hook's `ask` for credential-dir reads remains the protection layer for paths outside the zero-access list (e.g., `~/.netrc`) that are not hard-blocked by `block-sensitive-paths.py`.

Every ask response produced by this requirement SHALL comply with the strengthened
`ExplanationContract` defined in `hook-interface`: the `permissionDecisionReason` MUST
state both what the operation would do (read/write a likely-secret file) and what the
specific danger is (exposure of credentials to Claude's context window, enabling potential
downstream exfiltration).

#### Scenario: ReadSshPrivateKey

- **GIVEN** a Read tool call is intercepted by this hook
- **WHEN** `tool_input.file_path` matches `~/.ssh/id_*`
- **THEN** the hook exits 0 with `permissionDecision: "ask"` and a reason that names the
  file, describes that it likely contains a private key, and warns that reading it places
  the key in Claude's context where it could be incorporated into a subsequent command or
  network call

#### Scenario: ReadNetrcFile

- **GIVEN** a Read tool call is intercepted by this hook
- **WHEN** `tool_input.file_path` is `~/.netrc` (not in the zero-access list, so not
  blocked by `block-sensitive-paths.py`)
- **THEN** the hook exits 0 with `permissionDecision: "ask"` and a reason that names the
  file, describes that it contains plaintext usernames and passwords for remote hosts,
  and warns that reading it places those credentials in Claude's context where they could
  be incorporated into a subsequent command or network call

#### Scenario: ReadTokenFileInProject

- **GIVEN** a Read tool call is intercepted by this hook
- **WHEN** `tool_input.file_path` matches `*token*` in the project directory (not in a
  package dir)
- **THEN** the hook exits 0 with `permissionDecision: "ask"` and a reason that names the
  file, explains why its name suggests it may contain an access token, and notes that the
  token could be read into context and used in subsequent operations
