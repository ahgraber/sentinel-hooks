# Proposal: shared-hook-contracts

## Intent

Five hooks decide whether a path denotes a guarded location, and each answers differently.
Two use one name for opposite behaviour: one follows symbolic links, the other does not.
The divergence has produced a live bypass on case-insensitive filesystems, inconsistent handling of unresolvable paths, and three copies of tamper blocking that corrections reach one at a time.

This change defines path matching as a single capability with one contract, and adopts it in every hook that makes the judgement.

## Scope

- `path-matching`: new capability.
  Defines what it means for a path to denote a guarded location, the spellings that must not defeat it, and the limits that are accepted.
- `hook-tampering-blocking`: adopt the contract.
  Coverage stops varying by agent.
- `sensitive-path-blocking`, `secret-access-blocking`: adopt the contract for their path-shaped rules.
- `hook-interface`: outcomes become canonical decisions and their encoding becomes agent-specific.
  Included because the same investigation found that the three agents assign incompatible meanings to the same exit code, which is why a hook cannot currently report anything without either staying silent or refusing the call.

Out of scope: the name-pattern and glob rules in `sensitive-path-blocking` and `secret-access-blocking`, which are policy rather than path resolution; the command-pattern rules in `dangerous-bash-blocking` and `destructive-ops-blocking`, which do not resolve paths.

## Approach

State the contract as a property of the decision, not of an implementation: a guarded location is guarded regardless of the spelling used to reach it, subject to limits that are named rather than implied.

Accept the limits that cannot be closed by path inspection — a working-directory change inside a single shell command, and hard links — and record them in the spec so no reader mistakes this layer for the boundary.

Close the two that can be: letter case, and failure to resolve.

Consolidate the three tamper implementations into one.
The existing per-agent test suites are the evidence that no per-agent expectation was dropped; all of them continue to run against the consolidated hook.

## Risk

Consolidation widens coverage: an agent that previously enforced only its own protected set will enforce every agent's.
This removes no protection and adds some, but it changes which operations are refused, and refusals are visible to the user.

The case-insensitivity fix will refuse spellings that are accepted today.
On a case-sensitive filesystem those spellings address different files, so the rule must compare case-insensitively only where the filesystem does.
