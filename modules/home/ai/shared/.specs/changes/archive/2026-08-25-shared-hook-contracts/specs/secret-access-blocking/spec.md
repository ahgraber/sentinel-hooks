# Delta Spec: secret-access-blocking (shared-hook-contracts)

> Source files: modules/home/ai/shared/.specs/specs/secret-access-blocking/spec.md

---

## MODIFIED Requirements

### Requirement: AskOnCredentialStoreRead

The system SHALL ask before a read of a credential store.

The set of credential stores is unchanged.

Whether a supplied path denotes a credential store SHALL be determined according to `path-matching`.
A store reached by a differing letter case on a case-insensitive filesystem is the same store, and SHALL prompt.

#### Scenario: CaseVariantCredentialStore

- **GIVEN** a Read tool call is intercepted on a case-insensitive filesystem
- **WHEN** the target is a credential store named under a differing letter case
- **THEN** the hook asks

---

### Requirement: AskOnSecretFileAccess

The system SHALL ask before access to a file whose location marks it as secret-bearing.

The set of such locations is unchanged.

Location matching SHALL be determined according to `path-matching`.
Basename matching in this requirement already applies case-insensitively and is unaffected.
