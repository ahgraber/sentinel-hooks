# Using skills

Skills are on-demand specialized workflows available via the `Skill` tool.
They are curated to guide _how_ you approach specific task types.

This scanning behavior also doubles as a live signal source: how well a skill's description matches real requests reveals whether its trigger conditions are well calibrated (too broad, too narrow, or ambiguous).
Skill authors use that signal, via the `optimize-skills` skill, to refine descriptions over time.

## The rule

**Before starting a task, scan the available skills and invoke each skill whose stated use cases match the task.**

- Consider the user's request in context.
  A shared word alone does not make a skill relevant.
- If the match is uncertain and the skill might materially improve the work (given its description), read the skill and decide.
- Re-invoke skills when the task changes within a conversation.
  Prior invocations apply to prior tasks.
- Scan available skills and relevant skill content before exploring the codebase, forming a plan, or asking clarifying questions because a skill may provide guidance on those steps.

### Limited exceptions

Skip skill invocation ONLY when:

1. You are a narrowly scoped subagent whose launch instructions already define your workflow.
2. No skill matches the task after a good-faith scan.
3. The skill mechanism is unavailable or broken.
   If that prevents required work, tell the user.

## Execution

1. Read the user request.
2. Scan the skills list for matching use cases and trigger descriptions.
3. Invoke each matching skill via `Skill` (e.g., `skill: "commit-message"`).
   The full content loads into context.
4. Follow the loaded instructions.
   If the skill includes a checklist, create TodoWrite items for each step.
5. Announce which skill you are using and why (e.g., "Using `python-testing` to write these test cases.").

## Reading a skill without a `Skill` tool

Some harnesses have no `Skill` tool and load a skill by reading its `SKILL.md` from disk.
Use the harness's own file-read tool when it has one.
When the only route is a shell command, read the file with `cat`, `nl`, `head`, or `tail`.

Do not read a skill with `sed`.
The exec policy allows no `sed` prefix, so every such read goes to the reviewer or is refused, and the skill never loads.
The same applies to `awk`, `perl`, and any other command that can write as well as read.

## Instruction priority

Follow the harness's instruction hierarchy.
System and developer instructions take precedence over user instructions.
Explicit user instructions override skill guidance.
A skill does not override a higher-priority instruction.

User instructions define the task.
Skills guide how to carry it out.
Scan for applicable skills even when the user asks for direct execution.
Follow the user's explicit request when it conflicts with skill guidance and no higher-priority instruction prevents it.
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
