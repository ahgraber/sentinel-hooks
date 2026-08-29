# Delta Spec: sensitive-path-blocking (shared-hook-contracts)

> Source files: modules/home/ai/shared/.specs/specs/sensitive-path-blocking/spec.md

---

## MODIFIED Requirement: ZeroAccessPaths

The system SHALL define a set of zero-access paths that may never be written to or modified.

The set is unchanged.

A supplied path SHALL be judged in every form `path-matching` produces for it — as written, with home notation and traversal applied, and as resolved — so that home notation, traversal, and a symbolic link do not defeat the set.
The stated limits of `path-matching` apply here unchanged.

Membership itself SHALL NOT be decided by `path-matching`, and letter case SHALL NOT follow the volume here.

This requirement asks a different question from a guarded location.
A guarded location asks whether a path _is_ a declared file, so two spellings are one file only where the volume says so, and `secret-access-blocking` `AskOnCredentialStoreRead` is decided that way.
This requirement asks whether a path _looks like_ it holds a secret, from its extension, its basename, and the directories it passes through.
On a volume that distinguishes case, `SECRET.PEM` is a different file from `secret.pem`, and it is equally a private key.
A name heuristic that stopped applying because a letter was capitalised would be defeated by capitalising a letter.

Every pattern in this requirement therefore matches without regard to case, on every volume.
The error this admits is refusing a path that resembles a secret and is not one, which is the safe direction for a set whose members may never be read.

### Scenario: CaseVariantCredentialDirectory

- **GIVEN** a Read, Write, or Edit tool call is intercepted
- **WHEN** the target lies within a credential directory named under a differing letter case
- **THEN** the hook exits 2, whether or not the filesystem folds case

---

## MODIFIED Requirement: PackageDirExemption

The exemption SHALL cover the directories holding this repository's own hook sources, for every agent.

Those directories hold files whose names describe what they guard against, not what they contain.
Reaching one of them requires the name-based patterns not to apply, and an agent that cannot read or write its own guardrail source cannot maintain it.

The exemption SHALL be declared once for the whole family, not per agent.
Naming the agents one at a time is what left the shared directory uncovered when these modules moved, making a guardrail source unreachable to the people responsible for it.

### Scenario: GuardrailSourceNamedForWhatItBlocks

- **GIVEN** a Read, Write, or Edit tool call is intercepted
- **WHEN** the target is a hook source in this repository whose name matches a name-based pattern
- **THEN** the hook exits 0

---

## MODIFIED Requirement: ToolScope

The system SHALL evaluate tool calls when `tool_name` is `Bash`, `Read`, `Write`, `Edit`, or `apply_patch`.

The system SHALL exit 0 on parse failure (fail-open), per `hook-interface` `ErrorHandlingByDamagePotential`.

Failing open SHALL NOT extend to a path that cannot be resolved.
Such a path is judged from the path as written, per `path-matching` `UnresolvablePathIsGuarded`.
