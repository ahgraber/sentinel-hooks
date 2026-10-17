# Change order

This file records the order in which active changes apply, and why.
A change not listed here has no ordering dependency on another active change.
Remove an entry when its change is archived.

## Sequence

1. `multi-line-command-lexing`
2. `single-command-rule-engine`

`multi-line-command-lexing` comes first.
With the lexer able to read newline commands, `single-command-rule-engine` reads every command through the lexer and drops its quote-splice rewrite.
In the other order, the rule engine keeps the rewrite for newline commands, and the lexing change has to retire it afterward.

A second sequence:

1. `program-semantics-table`
2. `recursive-credential-read-refusal`
3. `sensitive-path-word-narrowing` (stub)

`program-semantics-table` comes first.
Its catalog holds the recursive readers as rows, so `recursive-credential-read-refusal` adds rows instead of a fourth per-program table in `bash_commands.py`.
`sensitive-path-word-narrowing` needs the catalog's effect typing and the evidence its proposal names before it starts.

## Shared specs

These changes do not depend on each other, but their delta specs modify the same baseline spec.
The change that syncs second rebases its delta on the synced text.

- `sensitive-path-blocking`: `multi-line-command-lexing`, `recursive-credential-read-refusal`, and `program-semantics-table`.
- `dangerous-bash-blocking`: `single-command-rule-engine` and `program-semantics-table`.
  `program-semantics-table` owns the privilege-escalation rule; `single-command-rule-engine` does not add its own.
  Both replace or render from the program-reading helpers in `bash_commands.py`; the change that lands second builds on what the first left.

## Independent

- `pi-subagent-enforcement`
- `path-directory-guarding` (stub); it uses the host inventory `program-semantics-table` produces, but does not wait for that change.

## Satisfied prerequisites

`guarded-path-classes` and `security-posture-alignment` are archived (2026-10-13).
Every active change that named them as a prerequisite can start.
