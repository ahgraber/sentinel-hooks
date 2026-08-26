# Using Skills

Skills are on-demand specialized workflows available via the `Skill` tool.
They are curated to guide _how_ you approach specific task types.

This scanning behavior also doubles as a live signal source: how well a skill's description matches real requests reveals whether its trigger conditions are well calibrated (too broad, too narrow, or ambiguous).
Skill authors use that signal, via the `optimize-skills` skill, to refine descriptions over time.

## The Rule

**Before any response or action, scan the available skills list and invoke every plausibly relevant skill.**

- If the skill's description shares any concept with the task at hand — the user's current request understood in the full context of the conversation — it is plausibly relevant.
- Err toward invoking — the cost is near zero; skipping means missing established workflows.
  If unsure whether a skill applies, invoke it; do not require a perfect match.
- Re-invoke skills when the task changes within a conversation.
  Prior invocations apply to prior tasks.
- Skill invocation must precede all other cognitive work on the task.
  Read the request to understand what is being asked, then immediately scan and invoke — before analyzing the problem, forming an approach, or reasoning about implementation.
- Do not explore the codebase, gather context, or ask clarifying questions before checking skills — skills often define how to do those things.

### Limited Exceptions

Skip skill invocation ONLY when:

1. You are a narrowly scoped subagent whose launch instructions already define your workflow.
2. No skill is plausibly relevant after a good-faith scan.
   List the 2-3 closest candidate skills and why each was ruled out.
3. The skill mechanism is unavailable or broken.
   State this explicitly.

## Execution

1. Read the user request.
2. Scan the skills list (shown in system reminders) for matching names and trigger descriptions.
3. Invoke every plausibly relevant skill via `Skill` (e.g., `skill: "commit-message"`).
   The full content loads into context.
4. Follow the loaded instructions.
   If the skill includes a checklist, create TodoWrite items for each step.
5. Announce which skill you are using and why (e.g., "Using `python-testing` to write these test cases.").

## Instruction priority

1. Highest priority: **User instructions** always take precedence, even over skill guidance.
2. **Skills** guide default behavior via specialized knowledge.
3. **Public directives** (CLAUDE.md, AGENTS.md) and system defaults are lowest priority.

User instructions define _what_ to do.
Skills define _how_.
A user instruction is not permission to skip the skill check — always scan and invoke first, then follow user intent within the loaded workflow.
Inferred urgency or simplicity is not an explicit user instruction; only skip skill steps when the user directly and specifically tells you to skip them.

## Ordering

When multiple skills apply, invoke in this order:

1. **Process skills** (brainstorming, code-review, receiving-feedback) — shape your approach.
2. **Implementation skills** (python-\*, api-design, shell-scripts) — guide execution details.

## Skill types

- **Rigid**: the skill contains a numbered sequential workflow or checklist.
  Follow each step in order.
  Do not skip, reorder, or abbreviate.
- **Flexible**: the skill provides principles, heuristics, or reference routing.
  Adapt the guidance to the specific context.

When ambiguous, treat the skill as rigid.
