# Proposal: Pi subagent enforcement

Status: draft.
The scope is incomplete, and this change has no specs, design, or tasks yet.
The proposal commit is the later commit that adds them, not the commit that first added this file.

## Intent

Pi's `subagent` tool is refused since 2026-10-11 (`security-posture-alignment` `PiSubagentsAreRefused`).
A foreground child runs inside the Pi process without the hooks or the sandbox, and a session can write an agent definition that opts any child out of them.
The tool's own parameters also act in the Pi process with no check: they run shell commands, write files at any path, upload the session, and choose a child directory whose project file can turn the sandbox off.
This change makes the posture hold inside every Pi subagent and around its launch, so that `subagent` can proceed again.

## User Stories

- **subagents-carry-the-posture**: As the operator of Pi, I want every subagent a session starts to run under the same hooks and sandbox as the session, so that delegating work does not also remove the guardrails.
  (North star: "the policy is written once and holds for every agent".)
- **the-launch-is-judged**: As the maintainer of these guardrails, I want each part of a subagent launch that acts outside the child to be judged before the launch, so that the tool that starts a checked child cannot do unchecked work itself.
  (North star: "layers are independent, and a denial from any layer is final".)
- **project-files-cannot-disable-the-sandbox**: As the operator of Pi, I want no project file to turn Pi's sandbox off or replace its deny list, so that opening a project does not remove a layer.
  (North star: "degradation keeps the user in control".)

## Scope

**In scope:**

- Load the hooks extension and the sandbox extension into every subagent child, foreground, background, nested, and resumed, in a way no agent definition, project setting, or launch parameter can remove.
- Refuse a launch when either extension cannot be loaded into the child.
- Judge the `subagent` call's parameters in a shared hook: the agent scope, inline agent configuration, workflow scripts, gate and acceptance commands, output paths, session sharing, machine placement, extension bindings, session directories, and the child's working directory, including inside `tasks` and `chain` items.
- Turn off the pi-subagents features that act in the Pi process unchecked, such as in-process agent management, through a configuration file this repository deploys.
- Stop the sandbox extension from reading a project's `.pi/sandbox.json`, in the parent session as well as in children.
- List `subagent` and the tools a child uses in the tool vocabulary again.
- Choose one set of MCP tools that run without asking, and express it in every agent: Claude `permissions.allow`, Codex `approval_mode`, and, for Pi, a shared-hook rule that asks on any other MCP tool in place of today's passthrough for every `mcp__*` tool.
  This closes the exception `security-posture-alignment` records against `NetworkReachIsUniformPerUser`.
- TODO (user): add the Pi follow-ups from `modules/home/ai/pi/TODO.md` to this scope.

**Out of scope:**

- A fork of pi-subagents.
  Version 0.75.0 already provides the host API this change needs.
- Prompts inside a child.
  A child has no UI, so a hook `Ask` there becomes a refusal, as it does for any headless Pi.
- Subagents of the other agents, which already run the hooks.

## Approach

pi-subagents 0.75.0 has a host API, `registerRequiredChildExtensions`, that appends named extensions to every child launch with final precedence, so agent defaults, overrides, and `extensions: []` cannot remove them.
With `requireForAllRunners`, it refuses external CLI runners and machine placement, and a child launch fails when a required extension fails to load.
The hooks extension, or a small guard extension beside it, would register `hooks/` and `sandbox/` as required on `session_start` and dispose the registration on `session_shutdown`.

The required extensions close the definition route but not the launch parameters, which act in the host process before any child exists.
A rule in a shared hook judges those parameters, because `cross-agent-capability-parity` holds that a harness extension carries no rule of its own about which calls proceed.

A deployed `~/.pi/agent/extensions/subagent/config.json` turns off `agent-management`, `workflow-scripts`, `gates`, `external-machines`, and `extension-bindings`.
The sandbox extension is copied at activation, so a small patch there can drop the project-file merge.

Evidence and line references are in `research.md` beside this proposal.

## Open Questions

- Does a second instance of the sandbox extension in a child share the parent's `SandboxManager`?
  If it does, a child's `session_shutdown` resets the parent's sandbox, and the design needs another route.
  This is the load-bearing assumption, and a live check settles it.
- Should a hook or sandbox extension that fails at child startup fail the launch, rather than continue unchecked as both do in a parent session today?
- The change name: it may widen once the `TODO.md` scope is added.
