# Delta Spec: hook-interface (deny-response-ai-guidance)

> Generated from requirement analysis on 2026-03-28
> Source files: modules/home/apps/claude/.specs/specs/hook-interface/spec.md

---

## MODIFIED Requirement: ExplanationContract

Every block or ask response SHALL include an explanation that contains:

1. **What the operation does** — a plain-language description of the matched command's or path's purpose and effect (e.g., "reads your SSH private key into Claude's context", "pipes your AWS credentials to a remote host")
2. **Why it is dangerous or suspicious** — the specific security risk this operation poses (e.g., "a private key in context can be incorporated into a subsequent command or network call without further confirmation", "credential files piped to remote hosts expose authentication material to third parties")

For `ask` responses, the explanation addresses the user only.

For `block` responses (exit 2), the stderr message SHALL contain two sections:

**Section 1 — Human explanation** (as above): addressed to the user, states what the operation would have done and why it was stopped.

**Section 2 — AI instruction block**: a delimited section that instructs the AI not to seek workarounds and directs it to surface a four-point report to the user.

The AI instruction block SHALL begin with the exact delimiter `---` on its own line, followed by `AI INSTRUCTIONS:` on the next line.

The AI instruction block SHALL include:

- A prohibition on workaround-seeking: the AI SHALL NOT attempt alternative commands, equivalent operations, broken-up steps, or any other substitutes for the blocked action
- A directive to immediately report four points to the user:
  1. **Ongoing task** — what the AI was working on when the block occurred
  2. **Intended step** — what specific action it was about to take and why
  3. **What was blocked** — the exact operation and the reason given by the hook
  4. **User action option** — how the user could run this operation manually on the AI's behalf, including the exact command or steps, and why the user might or might not want to

The explanation SHALL be written for the user, not for the hook implementer.
It SHALL NOT be a raw regex pattern or an internal rule identifier.
It SHALL name the specific file or command where possible, not a generic category.

---

### ADDED Requirement: BlockAIGuidance

Every block response (exit 2) SHALL include a structured AI instruction section appended after the human explanation.

The purpose of this section is to:

- Prevent the AI from silently pivoting to a workaround after receiving a block
- Ensure the user is given enough context to make an informed decision about completing the action themselves

The AI instruction section SHALL use this exact format:

```text
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
```

The placeholder text (items 1–4) is directive language instructing the AI how to construct its report; it is not literal output.

#### Scenario: BlockMessageFormat

- **GIVEN** a hook exits 2
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation section followed by a `---\nAI INSTRUCTIONS:` delimiter and the four-point reporting directive

#### Scenario: AIDoesNotSeekWorkaround

- **GIVEN** the AI receives a block response with an AI instruction section
- **WHEN** the AI processes the tool result
- **THEN** it does NOT attempt alternative commands, equivalent operations, or any other substitutes for the blocked action

#### Scenario: AIReportsToUser

- **GIVEN** the AI receives a block response with an AI instruction section
- **WHEN** the AI presents the block to the user
- **THEN** its response includes: (1) what ongoing task it was performing, (2) what step it intended to take, (3) what was blocked and why, and (4) what the user could do manually and why they might want to

#### Scenario: BlockExplanationForUser

- **GIVEN** a hook exits 2
- **WHEN** the user reads the stderr output
- **THEN** the human section (before the `---` delimiter) states what the command would have done and why it was stopped, including the specific downstream risk — the AI instruction section is additional content and does not replace the human explanation

---

### MODIFIED Scenario: BlockExplanation

- **GIVEN** a hook exits 2
- **WHEN** the user reads the stderr output
- **THEN** they understand both what the command would have done and why it was stopped, including the specific downstream risk; additionally, the AI receives explicit instruction not to seek workarounds and to surface the block context to the user
