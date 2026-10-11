# Delta for secret-access-blocking

## MODIFIED Requirements

### Requirement: ToolScope

> Previously: `Read`, `Write`, and `Edit` also carried file path heuristics for likely-secret files; those now belong to `sensitive-path-blocking` `SuggestiveNamesAsk`.

Serves: placeholder-files-are-readable

The system SHALL evaluate ALL tool calls, regardless of tool name.

Secrets can appear in any tool argument — a command string, file content, a URL, a grep pattern, a file path.
Rather than enumerating specific tools and fields, the hook SHALL scan the serialized `tool_input` object for every invocation.

Tool-specific handling is layered on top of the universal scan:

- `Bash`: additional context-aware analysis (network-sending detection, credential store reads, localhost exemption)
- `Write`/`Edit`: content payload scanning, through the universal scan
- All other tools: universal scan only

This hook does not judge a file path as a location.
Which paths hold credentials is `sensitive-path-blocking`'s judgment, made from the manifest, so a declared exception or placeholder holds for every hook.

### Requirement: AskOnCredentialStoreRead

> Previously: a Read of a credential store named under a differing letter case asked here; `sensitive-path-blocking` now refuses that path for every spelling.

Serves: placeholder-files-are-readable

The system SHALL ask (confirm) when a Bash command reads from a system credential store without piping the output to a network command.

This covers legitimate debugging: checking which credentials are stored, verifying a token value, or inspecting a credential helper.

#### Scenario: KeychainReadLocal

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain but does not pipe to a network command
- **THEN** the hook exits 0 with `permissionDecision: "ask"`

#### Scenario: KeychainReadAndSend

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads from the macOS Keychain and pipes the result to a network command
- **THEN** the hook exits 2 (block — handled by `BlockSecretExfiltration`)

<!-- modified-removes: CaseVariantCredentialStore -->

### Requirement: TieredSecretDetection

> Previously: the scan-surface table named file path heuristics as an independent row, pointing at the removed `AskOnSecretFileAccess`.

Serves: placeholder-files-are-readable

The system SHALL use a two-tier detection model that balances coverage against latency.

**Tier 1 — Built-in patterns (all tool calls):**

A set of high-precision regex patterns covering the most common secret formats (API keys, PEM headers, bearer tokens, cloud provider credentials).
These run on every tool call as part of the universal scan.
Latency is negligible (~microseconds).

Built-in patterns are the primary detection mechanism for non-exfiltration contexts (local Bash commands, Read, Write, Edit, and all other tools).
They are sufficient for the ask-mode use case, where the cost of a false negative is a missed confirmation prompt rather than a leaked secret.

**Tier 2 — Gitleaks deep scan (Bash + network context only):**

When a Bash command contains a network-sending context (and the target is not localhost), gitleaks is invoked for comprehensive scanning (~400+ rules).
This is the exfiltration detection path, where a missed secret could result in credential leakage to a remote host.

Gitleaks is NOT invoked on every tool call because:

- Its startup cost (~100ms+) would compound across every tool invocation
- The risk profile of non-network contexts (ask-mode prompts) does not justify the latency
- Built-in patterns cover the high-confidence formats that appear in tool arguments

When gitleaks is not available on `PATH`, the deep scan falls back to built-in patterns.
Coverage is reduced for the exfiltration path, but the `SessionStart` hook warns the user (see `session-tool-checks`).

Scan surfaces by tier:

| Context                    | Tier 1 (built-in) | Tier 2 (gitleaks) |
| -------------------------- | ----------------- | ----------------- |
| Bash + network (non-local) | yes               | yes               |
| Bash (local or no network) | yes               | no                |
| Read / Write / Edit        | yes               | no                |
| All other tools            | yes               | no                |

#### Scenario: GitleaksAvailableWithNetwork

- **GIVEN** a Bash tool call with a non-local network destination is intercepted
- **WHEN** `gitleaks` is found on `PATH`
- **THEN** the hook invokes gitleaks for deep scanning in addition to built-in patterns

#### Scenario: GitleaksAvailableWithoutNetwork

- **GIVEN** a non-network tool call is intercepted
- **WHEN** `gitleaks` is found on `PATH`
- **THEN** the hook uses only built-in patterns (gitleaks is not invoked)

#### Scenario: GitleaksMissing

- **GIVEN** a tool call is intercepted
- **WHEN** `gitleaks` is not found on `PATH`
- **THEN** the hook uses built-in patterns for all contexts (deep scan is unavailable)

#### Scenario: GitleaksFindsSecret

- **GIVEN** gitleaks is invoked on a Bash command with network context
- **WHEN** gitleaks reports a finding
- **THEN** the hook exits 2 (block — exfiltration vector confirmed)

## REMOVED Requirements

### Requirement: AskOnSecretFileAccess

Removed because: it judged file paths as locations from a name list of its own, which never read the manifest.
A declared dotenv placeholder or name-heuristic exception that `sensitive-path-blocking` allows therefore still asked here, and was refused on every agent that cannot prompt.
The names `sensitive-path-blocking` already refuses (key and certificate files, SSH key names, `.env` files, `.netrc`, `.npmrc`, `.git-credentials`, the credential directories, and `secret` or `credentials` in a name) need no ask.
The names it did not judge move to `sensitive-path-blocking` `SuggestiveNamesAsk`, where the same exemptions and declarations apply.
