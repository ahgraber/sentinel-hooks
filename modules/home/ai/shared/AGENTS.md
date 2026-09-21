# AGENTS.md for the shared agent security module

## What runs here

`hooks/` holds the hooks Claude Code, Codex, Copilot, and Pi run on every tool call.
The first three call these files through an adapter.
Pi reimplements them in TypeScript under `../pi/security/`.
Each agent registers them itself, in `users/*/home-manager/claude/settings.json`, `users/*/home-manager/codex/hooks.json`, `../copilot/hooks/`, and the Pi extension.

Editing a hook changes what every agent may do, including the one making the edit.

## The posture

`.specs/NORTH-STAR.md` states it in full.

**Response matches risk.**
Refuse credential access, exfiltration, privilege escalation, and persistence.
Ask the user about guardrail maintenance, destructive-but-legitimate operations, and anything reaching outside the project.
Let ordinary recoverable work through unprompted.

**A denial from any layer is final.**
The hooks, the OS sandbox, the agent permission lists, and the editor approval globs each cover gaps the others leave.
When one refuses, do not reach the same place through another.

**One policy covers every agent.**
An agent that can weaken another agent's guardrails has weakened its own.

**Degradation grants no more than the full encoding would.**
A prompt that cannot be shown becomes a refusal.

## Layout

- `hooks/` — the hooks, and the modules they share.
  A hyphenated file is a hook and runs; an underscored file is a module and is imported.
  `hook_response.py` encodes a decision per agent.
  `guarded_paths.py` decides whether a path is guarded.
  `shell_words.py` lexes a Bash command, `bash_commands.py` classifies what the lexed words do, and `apply_patch.py` reads the paths an `apply_patch` body names.
- `hooks/guarded-paths.toml` — the guarded surface.
  Every implementation reads it at invocation, and the conformance tests check the other surfaces against it.
- `hooks/instructions/` — prompt text injected at session start.
  An edit asks, as for any other file under `hooks/`: prompt text shapes what the agent does with every other guardrail.
- `tests/` — the suites, plus `guarded-path-cases.json` and `sensitive-path-cases.json`, which both languages read.
- `.specs/` — the specs for this module.

## Rules

Declare a guarded path in `guarded-paths.toml`, not in a hook.
A path spelled in code leaves the other implementations and platforms behind.
The enforcement floor is the exception: harness permission locations and the guard's own footprint are mechanics that a manifest grant cannot override.
Block outranks the floor; the floor requires approval for writes and runs, including exact grants, and does not restrict reads.
Grants remain effective outside the floor, including on instruction text.

Cover every `[block]` declaration in the permission lists and the sandbox lists.
A block path no surface refuses leaves one hook between an agent and a credential, and a credential read cannot be undone.
The guarded class is not held to a floor: the surfaces cannot express an ask with a carve-out beneath it, and an unprompted edit there is recoverable.

Declare a loosening in `[[exceptions]]`, with its surface, pattern, and reason.
Nothing downstream distinguishes an undeclared loosening from an accident.

Read `hook-interface` before changing an error path.
It states whether each hook fails open or closed, and why.

Change Pi in the same change.
It is a separate implementation, judged against the shared verdict tables rather than by reading its source.

## Specs

`.specs/specs/` holds baselines, `.specs/changes/` work in progress, `.specs/changes/archive/` the record.

Do not edit a baseline.
Sync produces them from a change.
A requirement that enters or leaves a baseline with no change behind it has no recorded reason, and nothing in the repository contradicts it.

`fba2187` replaced `RequireSignedCommits` with `RequireAgentCommitAlias` by editing the baseline, and `c7f3937` dropped two ripgrep redirects the same way.
Three requirements left the record with no account of why, eight weeks apart.

Use the skills: `sdd-propose`, implement, `sdd-verify`, `sdd-sync`, `sdd-archive`.

Write headings as `## Requirements`, then `### Requirement: Name`, then `#### Scenario: Name`.
`sdd-sync` and `check_modified_completeness.py` match `### Requirement:` only, so a requirement at `##` gets duplicated instead of replaced.

Write a MODIFIED block as the complete post-change requirement, every still-applicable scenario included.
Sync replaces the matched requirement wholesale and deletes whatever the block omits.

Changing behavior without changing a spec is drift, whether or not a test catches it.

## Validation

The shared lexer assumes Bash.
Pin Claude with `CLAUDE_CODE_SHELL=/run/current-system/sw/bin/bash`.
Use absolute paths in Bash commands.
Directory changes within a command are not tracked.
Hard links, links inside a declared directory, and routes that present no path remain limits; the sandbox and agent permissions are the boundary.

A recorder comparison on 2026-09-16 found these Bash/zsh differences:

- An unmatched `*.absent` stays literal in Bash; zsh starts no command.
- `=cat` stays literal in Bash; zsh expands it to the executable path.
- `**/*.md` does not match a top-level `a.md` in default Bash; zsh matches it.
- ANSI-C `\cA` and `\c?` produce control bytes in Bash; zsh passes `cA` and `c?`.
  The differential property reproduced this mismatch.

Quoted globs, matching `*.md`, brace expansion, ANSI-C octal escapes, home expansion, and backslash line continuation produced the same words in that sample.
The lexer refuses every newline, including backslash continuation, before either hook classifies the command.
The recorder reset `PATH` after shell startup because this host's zsh startup changes it.

- `just apps test shared` — this module.
  `just apps test all` — every agent's suite.
- `nix build .#checks.<system>.shared-hook-tests` — the same suite under the flake.
- `prek run --files <paths>` — scope it to what you touched.

Run the shared suite for any hook change, and the Pi suite for anything the verdict tables cover.
