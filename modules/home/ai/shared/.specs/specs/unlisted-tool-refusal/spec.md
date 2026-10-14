# unlisted-tool-refusal Specification

## Purpose

An agent can gain tools with each release, and a tool the shared vocabulary does not name passes the hooks with nothing judging it.
These requirements cover the refusal of a tool no table lists, and the refusal of every call when the vocabulary cannot be read.

## Requirements

### Requirement: UnlistedToolIsRefused

Where a harness sends its tool names to the shared hooks without an adapter, the system SHALL refuse a tool the tool vocabulary neither maps nor lists as passthrough for that harness, and SHALL let every other tool through to the hooks that judge it.

The shared hooks gate on the declared vocabulary and let any other tool proceed, so a tool a harness gains is judged by nothing until someone maps it.
An adapter closes that gap for the harness it serves, per `cross-agent-capability-parity` `AdapterNormalizationIsTotal`.
A harness with no adapter needs the same refusal from a hook it registers for every tool call.

A mapping counts as listed only where it maps a tool to its own name.
The hooks judge the name the harness sends, and only an adapter converts it, so a mapping to another name would let the tool past this hook and past every hook that judges it.

The refusal SHALL name the tool and the file that declares the vocabulary, so the person the agent reports to can map it, list it as passthrough, or leave it refused.
It SHALL end with the stop instruction, because the agent cannot list a tool itself: the vocabulary is a guarded file.

#### Scenario: MappedToolProceeds

- **GIVEN** a tool the vocabulary maps for the invoking harness
- **WHEN** the hook judges the call
- **THEN** the hook exits 0 and writes nothing

#### Scenario: PassthroughToolProceeds

- **GIVEN** a tool the vocabulary lists as passthrough for the invoking harness, by name or by pattern
- **WHEN** the hook judges the call
- **THEN** the hook exits 0 and writes nothing

#### Scenario: UnlistedToolRefused

- **GIVEN** a tool the vocabulary neither maps nor lists as passthrough for the invoking harness
- **WHEN** the hook judges the call
- **THEN** the call is refused with the stop instruction, and the refusal names the tool and the vocabulary file

#### Scenario: MappedToAnotherName

- **GIVEN** a tool the vocabulary maps to a different name for the invoking harness
- **WHEN** the hook judges the call
- **THEN** the call is refused, and the refusal names the tool and the name it is mapped to

#### Scenario: UnidentifiedHarness

- **GIVEN** a call from a harness the hook cannot name
- **WHEN** the hook judges the call
- **THEN** the call is refused, because no vocabulary table applies to it

### Requirement: UnreadableVocabularyRefusesEveryCall

Where the tool vocabulary cannot be read, parsed, or validated, the hook SHALL refuse every tool call, with the stop instruction, and the refusal SHALL name the file and the error.

This departs from `guarded-path-declarations` `LoadFailureIsReported` and from the read-only direction of `hook-interface` `ErrorHandlingByDamagePotential`.
Both rest on another layer that keeps enforcing: the sandbox and the permission lists do not read the manifest, so they still hold when it fails to load.
No other layer knows which tools exist, so an unreadable vocabulary would otherwise let every unlisted tool through, including one that writes.

The cost is that the agent cannot read or edit the file to repair it, so the person the agent reports to repairs it by hand.
The vocabulary is a guarded file, and its syntax is checked before a commit, so the case arises from an uncommitted edit in the checkout the agents run.

#### Scenario: MissingVocabulary

- **GIVEN** the vocabulary file is absent
- **WHEN** the hook judges any tool call
- **THEN** the call is refused with the stop instruction, and the refusal names the file

#### Scenario: InvalidVocabulary

- **GIVEN** the vocabulary file cannot be parsed, or fails validation
- **WHEN** the hook judges any tool call
- **THEN** the call is refused with the stop instruction, and the refusal names the file and the error
