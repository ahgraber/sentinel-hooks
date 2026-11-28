# Proposal: script-content-judging

Status: stub.
It has no delta specs, design, or tasks.

## Intent

The hooks judge the text of a Bash command, and running a script file that is not guarded is ordinary work.
So a command that writes a program and then runs it is judged only by its words: `cat > /tmp/x.sh <<'EOF'` followed by `sh /tmp/x.sh` proceeds when the body deletes a guarded file, and so does `echo '<command>' > x.sh; sh x.sh`.
Verification of `multi-line-command-lexing` on 2026-10-22 confirmed both against bash 5.3.

A hook judges one tool call at a time, so a rule that links a write to a run inside one command misses the same script written in one call and run in the next.
The script's text is on disk by the time a later call runs it, and the hook can read it then.

## User Stories

### Story: a-script-is-judged-by-what-it-does

As the operator of four agents, I want a script an agent writes and then runs judged by the commands it holds, whether it runs in the same tool call or a later one, so that a guarded path changed from inside a script reaches me as it would written inline.

North star: "response matches risk"; writing and running a script is ordinary work, and a script that changes a guarded path is a change only the user may approve.

## Scope

**In scope:**

- A script a command runs that exists when the hook runs: its text, read and judged as program text in that script's language, by the rules the hooks apply to inline program text.
- A script the same command writes before running it: the written text, from a here-document, `echo`, `printf`, or `tee`, judged in its place.
- Verdict cases for both, across `sh`, `bash`, `source`, `.`, and the interpreters `program-semantics-table` catalogs.

**Out of scope:**

- A program a script starts that is not itself a script the command names.
- A compiled program; its behavior is not in readable text.
- Placing a program under a trusted name in a `PATH` directory; `path-directory-guarding` covers that.

## Dependencies

- `program-semantics-table`: its catalog says which word of a command each interpreter runs as a script.

## Open Questions

- How many of the scripts agents run name a guarded path only in comments or test data, such as this module's own tests, and so would ask without changing one.
- Whether a script larger than a set size is judged as unreadable text rather than read in full.
