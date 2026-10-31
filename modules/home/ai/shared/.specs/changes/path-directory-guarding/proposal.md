# Proposal: path-directory-guarding

Status: stub.
It has no delta specs, design, or tasks.

## Intent

The agent's `PATH` holds directories the user owns ahead of the system ones.
On the maintainer's Mac on 2026-10-17, `~/.cargo/bin` stood at position 11 and `/usr/bin` at position 19, and Claude Code's sandbox let a tool call create a file in `~/.cargo/bin`.
A program placed there under the name of an admitted reader, such as `column`, then runs for a bare `column` that the read classifier admits with no prompt.

Denying those directories in the OS sandbox would stop `cargo install`, `uv tool install`, `go install`, and `bun add -g`, a friction that would push users to turn the guardrails off.
Declaring them guarded in `guarded-paths.toml` gates only a command that names one of them, so a native installer, whose command does not name the directory, runs as before, and a hand-placed binary is put to the user.

## User Stories

### Story: binaries-arrive-through-installers

As the operator of four agents, I want a program to reach a directory on my `PATH` only through its installer or with my approval, so that an agent cannot place a program under the name of a utility the hooks trust without my seeing it.

North star: "response matches risk"; installing a tool is ordinary work, and placing a binary by hand where a trusted name resolves is a change only the user may approve.

## Scope

**In scope:**

- Guarded declarations for the user-owned directories on each agent's `PATH`: `~/.cargo/bin`, `~/.local/bin`, `~/go/bin`, `~/.bun/bin`, and the `fnm` directories, with others the host inventory of `program-semantics-table` finds.
- Verdict cases: a native install proceeds; a copy, link, or Write tool call into one of the directories is gated.

**Out of scope:**

- Sandbox denies on these directories.
- A program that writes into one of these directories from inside its own code; the hooks see only the command text.

## Open Questions

- Whether the declarations are per host, since each host's `PATH` differs.
