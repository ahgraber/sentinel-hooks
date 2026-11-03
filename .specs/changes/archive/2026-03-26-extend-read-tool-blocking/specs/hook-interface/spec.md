# Delta for hook-interface

## MODIFIED Requirements

### Requirement: ExplanationContract

Every block or ask response SHALL include an explanation that contains:

1. **What the operation does** — a plain-language description of the matched command's or path's purpose and effect (e.g., "reads your SSH private key into Claude's context", "pipes your AWS credentials to a remote host")
2. **Why it is dangerous or suspicious** — the specific security risk this operation poses (e.g., "a private key in context can be incorporated into a subsequent command or network call without further confirmation", "credential files piped to remote hosts expose authentication material to third parties")

(Previously: explanations were required to state what the operation does and why it was blocked or flagged, but with no requirement to make the downstream danger explicit.
In practice, ask-mode messages stated the path or pattern matched but did not describe the specific risk to the user.)

The explanation SHALL be written for the user, not for the hook implementer.
It SHALL NOT be a raw regex pattern or an internal rule identifier.
It SHALL name the specific file or command where possible, not a generic category.

#### Scenario: AskExplanation

- **GIVEN** a hook exits 0 with `permissionDecision: "ask"`
- **WHEN** the user reads the dialog reason
- **THEN** they understand (a) what operation Claude is attempting, (b) what specific file or command is involved, and (c) what harm could result if the operation proceeds unchecked (e.g., credentials entering context, data reaching a remote host)

#### Scenario: BlockExplanation

- **GIVEN** a hook exits 2
- **WHEN** the user reads the stderr output
- **THEN** they understand both what the command would have done and why it was stopped, including the specific downstream risk (unchanged from previous — block messages already met this standard; this scenario is retained for completeness)
