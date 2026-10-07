# Delta for hook-interface

## MODIFIED Requirements

### Requirement: BlockAIGuidance

> Previously: the retry form was for a command the classifier could not check, its opening stated only that cause, and every block-class refusal used the stop form.

Serves: a-refused-search-says-what-would-work

Every block response (exit 2) SHALL include a structured AI instruction section appended after the human explanation.

The section SHALL take one of two forms, and SHALL NOT combine them.
Whether the block message names an alternative the hook accepts SHALL decide which form.

A block whose message names no accepted alternative SHALL use the stop form.
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

A block whose message names an alternative the hook accepts SHALL use the retry form.
Two refusals name one.
A command the classifier could not check names the commands it can check.
A recursive read whose root holds a declared credential names a search whose roots hold none.
Forbidding the alternative would contradict the same message, which names what works and then bars it.

The search retry form is a narrower operation, not another route to the refused access.
It SHALL forbid reaching the refused credential by any other command, link, copy, or equivalent read, and SHALL NOT permit retrying an operation another layer denied.
A refusal of a word that names a block-class location SHALL keep the stop form, because no narrower form of that operation leaves the credential unread.

The retry form SHALL state why the call stopped, in terms of the refusal that stopped it, and SHALL quote the words that introduce the alternative.
"Not recognized" repeats the explanation above it and gives the agent no next step.
A pointer that says only "above" leaves the agent searching a paragraph of prose for the alternative.

For a command the classifier could not check:

```text
---
AI INSTRUCTIONS:
The classifier stopped this call because the command does not match any form it can check for writes. Reading this path is allowed; writing to it needs the user's approval.

If one of the commands listed above under "Recognized reads use" does what you need, run that instead.

If none of them does, stop and report the following to the user:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
```

For a recursive read or copy whose root holds a declared credential:

```text
---
AI INSTRUCTIONS:
The hook refused this recursive operation because its root includes the declared credential path named above under "Protected file". Reading or copying that file could expose credentials.

Search again only with roots that contain no declared credential path. An exclude flag does not change this verdict. Do NOT access the refused credential through another command, link, copy, or equivalent read. This instruction does not permit retrying an operation denied by another layer.

If your task requires credential access, another layer denies the operation, or no such search serves your task, stop and report the following to the user:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed
```

The four reporting points SHALL be identical in every form.
Each requests the same account of the same stopped call, so any difference between them is drift.

The retry form is no more permissive than the stop form.
The hooks judge the retried command as they judged the first.
Every command the classifier accepts reads, none writes, and none runs a program the command leaves unnamed.
The search retry form forbids the refused access itself, and a link beneath a narrower root stays a limit `sensitive-path-blocking` `BashReadBestEffort` states, with the OS sandbox as its boundary.
An AI that intended the refused effect therefore reaches the same four-point report by either route.

Where the agent's adapter, rather than the hook, turns an `Ask` into a refusal, the `Ask` SHALL carry the instruction section in its reason.
The hook cannot know whether that adapter will show the prompt, and a refusal the adapter builds from the reason is otherwise a refusal without the section.

#### Scenario: AskAnAdapterMayRefuse

- **GIVEN** a hook reaches `Ask` for an agent whose adapter decides per call whether a prompt can be shown
- **WHEN** the adapter refuses the call, because no prompt can be shown or the user declines it
- **THEN** the reason the AI receives carries the instruction section

#### Scenario: BlockMessageFormat

- **GIVEN** a hook exits 2 with a message naming no alternative the hook accepts
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation section followed by a `---` delimiter, `AI INSTRUCTIONS:` header, a prohibition on workaround-seeking, and the four-point reporting directive

#### Scenario: RetryMessageFormat

- **GIVEN** a hook exits 2 with a message naming commands the hook accepts
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation section followed by a `---` delimiter, `AI INSTRUCTIONS:` header, an instruction to run the command again in one of the named forms, and the four-point reporting directive for the case where none serves

#### Scenario: SearchRetryMessageFormat

- **GIVEN** a hook exits 2 because a recursive read or copy has a declared credential beneath its root
- **WHEN** the block message is written to stderr
- **THEN** it contains a human explanation naming the credential, a `---` delimiter, `AI INSTRUCTIONS:` header, the reason the root is protected, an instruction to search again only with roots that contain no declared credential, a statement that an exclude flag does not change the verdict, a prohibition on reaching the credential by another route or retrying an operation another layer denied, and the four-point reporting directive

#### Scenario: AIDoesNotSeekWorkaround

- **GIVEN** the AI receives a block response carrying the stop form
- **WHEN** the AI processes the tool result
- **THEN** the instruction directs it not to attempt alternative commands, equivalent operations, or any other substitutes for the blocked action

#### Scenario: AIRunsAnAcceptedCommand

- **GIVEN** the AI receives a block response carrying the retry form
- **WHEN** the AI processes the tool result
- **THEN** it may run the same operation as one of the commands the message named, and is not directed against doing so

#### Scenario: AIDoesNotReachTheRefusedCredential

- **GIVEN** the AI receives a block response carrying the search retry form
- **WHEN** the AI processes the tool result
- **THEN** it may search again with roots that hold no declared credential, and the instruction directs it not to reach the refused credential by any other route

#### Scenario: ACredentialBlockUsesTheStopForm

- **GIVEN** a block response for a word that names a location in the block class
- **WHEN** the block message is written to stderr
- **THEN** it carries the stop form, whether or not the hook could read the command

#### Scenario: AIReportsToUser

- **GIVEN** the AI receives a block response with an AI instruction section
- **WHEN** the AI presents the block to the user
- **THEN** the instruction directs its response to include: (1) what ongoing task it was performing, (2) what step it intended to take, (3) what was blocked and why, and (4) what the user could do manually and why they might want to
