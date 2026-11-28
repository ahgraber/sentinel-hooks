# North star

> Ratified by the maintainer 2026-10-31.

Sentinel adds a layer of oversight to coding agents, beyond each harness's built-in sandbox, permissions, and approval settings.

The posture:

- The response matches the risk.
  Sentinel refuses credential access, exfiltration, privilege escalation, and persistence.
  It asks the user before guardrail maintenance, destructive but legitimate operations, and work that reaches past the project.
  Ordinary, recoverable work proceeds without friction.
- A denial from any layer is final.
  Each layer covers gaps the others leave, and no layer offers a way around another.
- One policy holds for every agent.
  An agent that can weaken another agent's guardrails has weakened its own.
  Supporting a new agent means expressing the same policy in that agent's terms.
- Degradation never grants more than the full encoding would.
  Where an agent cannot show a prompt, the prompt becomes a refusal.
