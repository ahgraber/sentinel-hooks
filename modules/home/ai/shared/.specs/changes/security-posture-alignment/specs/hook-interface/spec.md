# Delta for hook-interface

## MODIFIED Requirements

### Requirement: ErrorHandlingByDamagePotential

> Previously: the sensitive tools were `Bash`, `Write`, and `Edit`, an internal error on one required exit 2, and nothing separated a hook's registration from the tool a call named, so a hook covering reads as well had no stated direction.

Serves: degradation-still-reaches-the-user

The system SHALL handle internal errors differently based on the damage potential of the tool being evaluated.

**Sensitive tools** (`Bash`, `Write`, `Edit`, `apply_patch`) — tools that can modify state, destroy data, or transmit information.
On internal error, the hook SHALL reach a decision no more permissive than `Ask`.
An unhandled crash in a hook guarding a destructive tool must not silently allow the operation.

A hook whose subject is a class of path rather than a class of command MAY reach `Ask` rather than `Block`.
Such a hook runs on every call to a sensitive tool, most of which reach nothing it guards, so a fault that recurs would refuse every mutation the agent attempts with no route left for the user to say otherwise.
`Ask` grants nothing the full encoding would not: where the agent cannot show a prompt it degrades to the same refusal.
A hook that refuses a named class of command SHALL reach `Block` on an error judging one call.
When such a hook cannot load the rules it judges by, it SHALL reach `Ask`: that fault recurs on every call it judges, which is the ground on which a path hook reaches `Ask`.

**Read-only tools** (`Read`, `Glob`, `Grep`) — tools that cannot modify state.
On internal error, the hook SHALL reach a `Warn` decision: the tool proceeds and the reason is reported where the agent can report it.
Blocking a read on a hook crash is unnecessarily disruptive.

A hook registered for both SHALL choose the direction by the tool named in the payload rather than by its registration.
Where the payload does not name a tool — it did not parse, or naming the tool was itself the step that failed — the read-only direction applies, because a hook covering reads cannot refuse what it cannot identify.

The failure path SHALL NOT repeat a step that has already failed.
Naming the invoking agent is such a step, so it is recorded as the call is read rather than recomputed once the call has gone wrong.

This guarantee is conditional.
It holds only for errors the hook reaches and handles.

A failure that prevents the hook from running at all — an interpreter that cannot start, a script that is absent or unreadable — produces an outcome the agent encodes, not the hook.
At least one agent refuses the tool call on any such failure.
The stated fail-open posture therefore does not hold uniformly for startup failures, and SHALL NOT be represented as if it did.

A surface that runs several hooks in one process SHALL treat a hook that ends in an error it did not handle as a hook that gave no answer, and SHALL NOT read it as `Allow`.
Run alone, that hook would have exited with a status its agent refuses or reports; bundled, its failure is the surface's to encode.

#### Scenario: InternalErrorOnSensitiveTool

- **GIVEN** an unhandled error occurs inside the hook
- **WHEN** the tool being evaluated is `Bash`, `Write`, `Edit`, or `apply_patch`
- **THEN** the hook reaches `Ask` or `Block`, never `Allow`

#### Scenario: InternalErrorWhereNoPromptCanBeShown

- **GIVEN** an unhandled error occurs inside a hook judging a sensitive tool
- **WHEN** the invoking agent cannot express `Ask` for that tool
- **THEN** the hook reaches `Block`

#### Scenario: CommandHookCannotLoadItsRules

- **GIVEN** a hook that refuses a named class of command cannot load the rules it judges by
- **WHEN** a call to a sensitive tool it judges is intercepted
- **THEN** the hook reaches `Ask`, degrading to `Block` where the agent cannot express `Ask`

#### Scenario: InternalErrorOnReadOnlyTool

- **GIVEN** an unhandled error occurs inside the hook
- **WHEN** the tool being evaluated is `Read`, `Glob`, or `Grep`
- **THEN** the hook reaches `Warn` (fail-open — the tool proceeds, and the reason is reported where the agent can report it)

#### Scenario: InternalErrorBeforeTheToolIsNamed

- **GIVEN** a hook registered for both sensitive and read-only tools
- **WHEN** it fails before the payload names a tool
- **THEN** it reaches `Warn`

#### Scenario: HookFailsInsideASharedProcess

- **GIVEN** a surface that runs several hooks in one process, and one of them raises an error it does not handle
- **WHEN** a tool call is intercepted
- **THEN** the surface does not allow the call on that hook's account

#### Scenario: HookCannotStart

- **GIVEN** a hook is registered but cannot be executed
- **WHEN** a tool call is intercepted
- **THEN** the outcome is determined by the invoking agent, and may be either allow or deny depending on the agent

### Requirement: ExplanationContract

> Previously: section 2 of a block message was described as instructing the AI not to seek workarounds, which is one of the two forms `BlockAIGuidance` now defines.

Serves: a-refusal-says-what-would-work

Every block or ask response SHALL include an explanation that contains:

1. **What the operation does** — a plain-language description of the matched command's or path's purpose and effect (e.g., "reads your SSH private key into Claude's context", "pipes your AWS credentials to a remote host")
2. **Why it is dangerous or suspicious** — the specific security risk this operation poses (e.g., "a private key in context can be incorporated into a subsequent command or network call without further confirmation", "credential files piped to remote hosts expose authentication material to third parties")

For `ask` responses, the explanation addresses the user only, except where an adapter may refuse the `Ask`: there it also carries the instruction section, per `AskAnAdapterMayRefuse`.

For `block` responses (exit 2), the stderr message SHALL contain two sections:

**Section 1 — Human explanation** (as above): addressed to the user, states what the operation would have done and why it was stopped.

**Section 2 — AI instruction block**: a delimited section addressed to the AI, in whichever of the two forms `BlockAIGuidance` selects for that refusal.

The AI instruction block SHALL begin with the exact delimiter `---` on its own line, followed by `AI INSTRUCTIONS:` on the next line.

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
- **THEN** they understand both what the command would have done and why it was stopped, including the specific downstream risk; additionally, the AI receives the instruction `BlockAIGuidance` selects for that refusal

#### Scenario: Allow

- **GIVEN** no blocking or ask condition is matched
- **WHEN** the hook finishes evaluation
- **THEN** the hook exits 0 with no stdout output

#### Scenario: Block

- **GIVEN** a hard-block condition is matched
- **WHEN** the hook finishes evaluation
- **THEN** the hook exits 2 and writes a human-readable reason to stderr

#### Scenario: Ask

- **GIVEN** a confirmation-required condition is matched
- **WHEN** the hook finishes evaluation
- **THEN** the hook exits 0 and writes the ask JSON to stdout; Claude Code presents a permission dialog to the user

### Requirement: BlockAIGuidance

> Previously: every block response carried one instruction section, and that section always prohibited seeking an alternative command.

Serves: a-refusal-says-what-would-work, degradation-still-reaches-the-user

Every block response (exit 2) SHALL include a structured AI instruction section appended after the human explanation.

The section SHALL take one of three forms, and SHALL NOT combine them.
What the block message offers the agent SHALL decide which form: commands the hook accepts, the restatement of relative paths as absolute paths, or nothing.

A block whose message offers nothing SHALL use the stop form.
It directs the AI to abandon the operation rather than rewrite it, and to give the user what they need to decide whether to run it themselves.

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

A block whose message names commands the hook accepts SHALL use the retry form.
The hook matched no rule against the operation itself; it refused a command the classifier could not check.
The listed commands are the ones it can check, so forbidding them would contradict the same message, which lists the commands that work and then bars them.

The retry form SHALL state why the call stopped, and SHALL quote the words that introduce the list.
"Not recognized" repeats the explanation above it and gives the agent no next step.
A pointer that says only "above" leaves the agent searching a paragraph of prose for the list.

The retry form is shared by every hook that refuses a command its classifier could not check, so it SHALL state nothing that holds for one hook alone.
What a write would need differs by hook: the tamper hook puts a write to its user, and the sensitive-path hook refuses one.
Each hook's own explanation SHALL say what happens to a write.

```text
---
AI INSTRUCTIONS:
The classifier stopped this call because the command does not match any form it can check. Reading this path is allowed with the commands listed above.

If one of the commands listed above under "Recognized reads use" does what you need, run that instead.

If none of them does, stop and report the following to the user:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
```

A block whose classifier stopped only on relative paths in a directory the hook cannot determine SHALL use the absolute-path form.
The stop is on the paths, not on what the command does: the same command with every path absolute is one the classifier can judge.
The form SHALL direct the agent to restate every relative path as an absolute path and run the command again.

```text
---
AI INSTRUCTIONS:
This call names a relative path in a directory the hook cannot determine, so it could not check which file the path reaches. Restate every relative path in the command as an absolute path and run the command again; the restated command is checked in full.

If the restated command is refused too, stop and report the following to the user:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
```

The four reporting points SHALL be identical in every form.
Each requests the same account of the same stopped call, so any difference between them is drift.

The retry form is no more permissive than the stop form.
Every command the hook accepts reads.
None writes, and none runs a program the command leaves unnamed.
An AI that intended to write therefore reaches the same four-point report by either route.

The absolute-path form is no more permissive than the stop form.
The restated command is judged in full, so a write it makes meets the gate it would have met had the agent written it absolutely the first time.

Where the agent's adapter, rather than the hook, turns an `Ask` into a refusal, the `Ask` SHALL carry the instruction section in its reason.
The hook cannot know whether that adapter will show the prompt, and a refusal the adapter builds from the reason is otherwise a refusal without the section.

#### Scenario: AskAnAdapterMayRefuse

- **GIVEN** a hook reaches `Ask` for an agent whose adapter decides per call whether a prompt can be shown
- **WHEN** the adapter refuses the call, because no prompt can be shown or the user declines it
- **THEN** the reason the AI receives carries the instruction section

#### Scenario: BlockMessageFormat

- **GIVEN** a hook exits 2 with a message naming no command the hook accepts
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation section followed by a `---` delimiter, `AI INSTRUCTIONS:` header, a prohibition on workaround-seeking, and the four-point reporting directive

#### Scenario: RetryMessageFormat

- **GIVEN** a hook exits 2 with a message naming commands the hook accepts
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation section followed by a `---` delimiter, `AI INSTRUCTIONS:` header, an instruction to run the command again in one of the named forms, and the four-point reporting directive for the case where none serves

#### Scenario: AbsolutePathMessageFormat

- **GIVEN** a hook exits 2 because its classifier stopped only on relative paths in a directory it cannot determine
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation section followed by a `---` delimiter, `AI INSTRUCTIONS:` header, an instruction to restate every relative path absolutely and run the command again, and the four-point reporting directive for the case where the restated command is refused

#### Scenario: AIDoesNotSeekWorkaround

- **GIVEN** the AI receives a block response carrying the stop form
- **WHEN** the AI processes the tool result
- **THEN** the instruction directs it not to attempt alternative commands, equivalent operations, or any other substitutes for the blocked action

#### Scenario: AIRunsAnAcceptedCommand

- **GIVEN** the AI receives a block response carrying the retry form
- **WHEN** the AI processes the tool result
- **THEN** it may run the same operation as one of the commands the message named, and is not directed against doing so

#### Scenario: ACredentialBlockUsesTheStopForm

- **GIVEN** a block response for a location in the block class
- **WHEN** the block message is written to stderr
- **THEN** it carries the stop form, whether or not the hook could read the command

#### Scenario: AIReportsToUser

- **GIVEN** the AI receives a block response with an AI instruction section
- **WHEN** the AI presents the block to the user
- **THEN** the instruction directs its response to include: (1) what ongoing task it was performing, (2) what step it intended to take, (3) what was blocked and why, and (4) what the user could do manually and why they might want to

## ADDED Requirements

### Requirement: OutcomesAreDecodedInFull

Serves: every-agent-carries-the-policy, degradation-still-reaches-the-user

A surface that consumes a hook's outcome SHALL decode the whole encoding that `ExitCodes` defines for the invoking agent, and SHALL NOT infer a decision from the exit status alone.

`Allow` and `Ask` share an exit status, and only the hook's standard output separates them.
A consumer that reads the status alone therefore turns every `Ask` into an `Allow`, which is the one degradation direction `ExitCodes` forbids, and it does so silently: the user is never prompted, and nothing records that a prompt was due.

Where a surface runs more than one hook for a single tool call, it SHALL run every hook rather than stop at the first that does not allow, and it SHALL combine their decisions so that `Block` outranks `Ask` and `Ask` outranks `Allow`.
Stopping early would let an approval of one gate skip the hooks behind it, and a decision that is not the most restrictive of those reached would grant more than some hook allowed.

#### Scenario: AskIsNotReadAsAllow

- **GIVEN** a hook that reaches `Ask` for an agent that can express it
- **WHEN** a consuming surface decodes the outcome
- **THEN** it reaches `Ask`, and does not treat the exit status it shares with `Allow` as an allow

#### Scenario: BlockOutranksAsk

- **GIVEN** one hook reaching `Ask` and another reaching `Block` for the same tool call
- **WHEN** the surface combines them
- **THEN** the tool call is refused

#### Scenario: EveryHookRunsAfterAnAsk

- **GIVEN** a hook that reaches `Ask` for a tool call
- **WHEN** the surface continues through the remaining hooks
- **THEN** each of them judges the same call, and a refusal from any of them still decides it

### Requirement: AdaptedInvocationsCarryTheAgentName

Serves: every-agent-carries-the-policy

An agent that reaches these hooks through an adapter SHALL name itself to them, and the name it gives SHALL be one the shared implementation recognizes.

`AgentIdentification` resolves an agent from the invocation path, which holds only where the hook runs from that agent's own directory.
An adapter dispatches from outside it, so the path names nothing and the agent falls back to the one that supports neither warning nor prompting.
An unrecognized name degrades the same way as no name at all, so a misspelled or undeclared agent silently loses the prompt it was entitled to and refuses instead.

#### Scenario: AdapterNamesARecognizedAgent

- **GIVEN** a hook invoked through an adapter
- **WHEN** the hook resolves the invoking agent
- **THEN** it resolves the agent the adapter named, and applies that agent's encoding

#### Scenario: AdapterNamesNothingOrSomethingUnknown

- **GIVEN** a hook invoked through an adapter that names no agent, or names one the shared implementation does not recognize
- **WHEN** the hook reaches a decision that needs a prompt
- **THEN** the tool call is refused rather than allowed unprompted
