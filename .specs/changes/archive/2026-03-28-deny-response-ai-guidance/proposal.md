# Proposal: deny-response-ai-guidance

## Intent

When a hook blocks an operation (exits 2), the block response currently addresses only the human user.
The AI receives the stderr output as a tool result but has no explicit instruction about what to do next.
In practice, the AI may attempt to find workarounds, retry with alternative commands, or silently continue — none of which is appropriate when a hard block was intentional.

This change adds a structured AI instruction block to every block response.
The instruction block forbids workaround-seeking and directs the AI to surface a four-point report to the user so the user can make an informed decision about completing the action manually.

## Scope

- `hook-interface`: add `BlockAIGuidance` requirement; modify `ExplanationContract` and `BlockExplanation` to cover the dual-audience block message format
- All hook implementations that produce block (exit 2) responses must adopt the new format

Out of scope: `ask`-mode responses (those already surface context via the permission dialog).

## Approach

Append a delimited AI instruction section to every block stderr message.
The section:

1. Forbids workaround-seeking in unambiguous directive language
2. Prompts the AI to report four points to the user: current task, intended step, what was blocked, and how/why the user might complete it manually

The human explanation (what and why) precedes the AI section and is unchanged in intent.
The delimiter (`---\nAI INSTRUCTIONS`) is recognizable and consistent across all hooks.
