# Delta: destructive-ops-blocking

## MODIFIED Requirements

### Requirement: ExternalPatternFile

> Previously: a missing or unreadable pattern file let every command proceed, and nothing stated what an invalid rule did; the hook skipped it without notice.

Serves: degradation-still-reaches-the-user, existing-guarantees-are-recorded

The system SHALL load rules from an external pattern file co-located with the hook.
Each rule SHALL contain at minimum:

- a regex pattern
- a `description` — plain-language explanation of what the matched operation does and its effect
- a `reason` — why it is blocked or flagged (the safety or security concern)
- a `mode` — `block` or `ask`

The `description` and `reason` fields are used together to construct the `ExplanationContract` message shown to the user (see `hook-interface`).
Rules SHOULD be grouped by category (e.g., git, filesystem, cloud, database).
The pattern file format is TOML, chosen because `tomllib` is available in the Python standard library from Python 3.11+, requiring no external dependencies.

The system SHALL use the pattern file only when every rule in it is valid.
A rule is invalid when it lacks one of the four fields, names a mode other than `block` or `ask`, or holds a pattern that does not compile.
When the file is missing, cannot be read or parsed, or holds an invalid rule, the hook SHALL reach `Ask` on every `Bash` call, as `hook-interface` `ErrorHandlingByDamagePotential` allows for a fault that recurs on every call.
The reason SHALL name the fault: the file that could not be used, or the invalid rule.
The system SHALL NOT judge by the valid remainder of a file that holds an invalid rule, because a rule dropped without notice is a protection removed without notice.

#### Scenario: PatternFileLoaded

- **GIVEN** the hook is invoked
- **WHEN** the pattern file exists, is readable, and every rule in it is valid
- **THEN** all rules from the file are active for the current evaluation

#### Scenario: PatternFileMissing

- **GIVEN** the hook is invoked
- **WHEN** the pattern file does not exist or cannot be read
- **THEN** the hook reaches `Ask`, and the reason names the pattern file

#### Scenario: PatternFileUnparsable

- **GIVEN** the hook is invoked
- **WHEN** the pattern file is not valid TOML
- **THEN** the hook reaches `Ask`, and the reason names the pattern file

#### Scenario: RuleIsInvalid

- **GIVEN** the pattern file holds a rule with `mode = "deny"`, a rule with no `reason`, or a rule whose pattern does not compile
- **WHEN** any `Bash` call is intercepted, whether or not it matches a valid rule
- **THEN** the hook reaches `Ask`, and the reason names the invalid rule

#### Scenario: UnusableFileWhereNoPromptCanBeShown

- **GIVEN** the pattern file cannot be used
- **WHEN** the invoking agent cannot express `Ask` for `Bash`
- **THEN** the hook reaches `Block`
