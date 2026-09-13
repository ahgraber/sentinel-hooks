# Proposal: skill-script-exec-through

## Intent

A skill ships helper scripts and tells the agent to run them by path.
Those paths sit under `~/.claude/skills/`, `~/.codex/skills/`, and `~/.agents/skills/`, which the tamper hook guards.
A Bash call states no intent, so the hook gates any command naming a guarded path, and `uv run ~/.claude/skills/antislop-writing/scripts/prose_audit.py` reaches the user as an approval prompt or, on an agent that cannot prompt, a refusal.

The read-through carve-out added on 2026-09-02 solved half of this: a recognized read of a skill file proceeds.
It does not cover the other half, because a script run is not a read, and the skill directories hold scripts the skill's own instructions call for.
The result is a prompt on ordinary use of a skill the user installed, which is the habituation the north star's "response matches risk" clause exists to avoid.

That carve-out also shipped with no requirement in this specs root, so nothing recorded which command forms the classifier accepts.
This change adds the exec form and records both.

## User Stories

- **skill-scripts-run** — As the operator of these agents, I want a run of a script already held in a skills directory to proceed without a prompt, so that using an installed skill does not train me to approve prompts about my own tooling.
  (North star: "ordinary, recoverable work proceeds without friction".)
- **carve-outs-are-specified** — As the maintainer of these guardrails, I want every accepted command form under a carved-out location stated as a requirement, so that widening the carve-out is a spec change rather than a hook edit no artifact records.
  (North star: "what only the user may decide is put to the user"; a carve-out is a standing decision, and an unrecorded one cannot be reviewed.)

## Scope

**In scope:**

- `guarded-path-declarations`: the manifest gains an `exec-through` class, declared separately from `read-through`, and the enumeration of declared classes catches up with both.
- `hook-tampering-blocking`: a Bash command naming only carved-out locations is classified before it is gated, and a run of a script already held in an exec-through location proceeds alongside a recognized read.
- The three skills roots are declared exec-through.
- Tests over the accepted and rejected command forms, built on a substituted home so a case does not depend on which skills the running user has installed.

**Out of scope:**

- Writes to skill content.
  `Write`, `Edit`, and any command that is neither a recognized read nor a recognized run still gate.
- The Pi security extension.
  It implements neither carve-out, so a Pi session keeps gating skill reads and runs; closing that gap is its own change.
- The Claude permission lists, the OS sandboxes, and the VS Code approval globs.
  They gate writes to these paths and are unaffected by a classification the hook makes.
- A command that names the skills root with no trailing path component and no absolute spelling — `bash -c "touch ~/.agents/skills"` — reaches neither the text layer nor the path layer today.
  This predates the change and applies to every directory declaration, not to skills alone.

## Approach

Classify the command from its text, as the read-through carve-out already does, and add one accepted form rather than a second decision point.

The hook splits a command into pipeline segments once, then asks each segment whether it is a recognized read or a recognized script run.
A segment is a script run when the script is the command itself, or the file argument to a named interpreter.
The script must already exist, because a path a run would create is a write; it must look like a program, by execute bit or by suffix, because `uv run` on a `SKILL.md` is not what this carve-out is for.
Inline-code options (`-c`, `-e`) disqualify a segment: they make the interpreter run text the classifier never sees.

The existing outer rule is unchanged — one guarded path outside the carved-out locations gates the whole command.
