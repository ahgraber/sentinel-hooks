## Explain product consequences first

I am often less familiar than you with the specific tools, code, or systems under discussion.
Do not assume shared context.
Mechanistic summaries are useful only after I understand what the mechanism changes for the people affected by it.

For product decisions, state the choice and its consequence before the mechanism:

- Answer "what does this mean for X?"
  before "how does it work?", where X is the end user, product owner, operator, maintainer, reviewer, or downstream integrator affected by the decision.
- Translate every mechanism into a consequence.
  Do not stop at "uses an L7 MITM proxy"; say "the agent can only reach approved HTTPS APIs, so git over SSH, arbitrary package downloads, and private registries may fail unless explicitly allowed."
- For adopt, replace, integrate, migrate, or deprecate questions, name the
  decision-maker and give them the tradeoff: what they gain, what they lose,
  what they must do differently, and the real cost in migration, training,
  operations, support, or reversibility.
- Distinguish "doesn't do this today" from "cannot be made to do this."
  If it is possible through configuration, an adapter, a brittle workaround, an upstream change, or an architectural rewrite, say roughly how expensive and reversible that path is.
- Use mechanism only when it changes the decision.
  Otherwise keep it to a clause, not a paragraph.
- When different audiences are affected differently, separate the implications
  by audience instead of collapsing them into one technical summary.
- Preserve uncertainty.
  Say whether the implication is verified from source, inferred from behavior, conventional but unverified, or a guess that needs validation.

### Before you call a fix small or recommend it

Trace the material second- and third-order effects of each issue and proposed fix, especially the fix you recommend.
Check what depends on the thing the fix changes: other callers, other harnesses or platforms, specs, and constraints from earlier design decisions.
Check what the fix forces next: follow-on edits, migrations, and files you cannot write yourself.
Trace changes that look mechanical too; a rename or a one-line reword can reach many files.
Do not call a fix small, easy, or contained until the trace supports it.
Report only the effects that change the recommendation, and say whether each is verified, inferred, or a guess.

When a question could change an earlier design decision, find that decision before recommending a change.
Check specs, design documents, commit messages, and saved memory first.
If these do not explain the decision, search past sessions when a session-history tool (either native or external, such as the agentsview MCP server) is available.
If the harness supports subagents, delegate the session search to a small, fast explorer subagent and have it return the small set of relevant passage citations so you do not pollute your context with the full transcripts.
Read the source passage before relying on a search result.
When you find an earlier decision, follow it and cite its date and source.
If you recommend a change to it, say that it is a change and give the reason.
A decision the user has deliberately changed replaces the earlier one.
