# North star

> Candidate drafted 2026-08-27; ratified by the maintainer before first use.

One security posture governs every coding agent on this machine, however many surfaces it takes to express it.
The shared hooks in this module are one such surface; the OS sandboxes, the agent permission lists, the exec policies, and the reviewer policies in each agent's settings are the others.
A rule found in any of them is an expression of this posture, and is justified by it.

The posture:

- **Response matches risk.**
  What must stay secure, private, or confidential is refused: credential material, exfiltration, privilege escalation, persistence.
  What only the user may decide is put to the user: maintaining the guardrails themselves, destructive-but-legitimate operations, reaching past the project's blast radius.
  Ordinary, recoverable work proceeds without friction.
- **Layers are independent, and a denial from any layer is final.**
  Each layer covers the others' blind spots; none is trusted to be the only one.
  No layer offers a legitimate workaround for another.
- **The policy is written once and holds for every agent.**
  An agent that could weaken another agent's guardrails has weakened its own.
  Onboarding an agent means expressing this same posture in that agent's vocabulary, not writing a new one.
- **Degradation keeps the user in control.**
  Where a surface cannot express an outcome, the fallback never grants the agent more than the full encoding would: a prompt that cannot be shown becomes a refusal, and a warning that cannot be shown lets the call proceed no further than it already could.
