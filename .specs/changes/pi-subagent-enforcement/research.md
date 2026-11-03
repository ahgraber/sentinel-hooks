# Research: enforcing the posture inside Pi subagents

Read from installed sources on 2026-10-11: Pi 1.0.0, pi-subagents 0.75.0, pi-intercom 0.16.0.
Line numbers refer to those builds.

## Established

- A foreground child loads none of the parent's extensions (`pi-subagents` `child-launch.js:199`, `child-session.js:349`, `docs/agents.md:457`).
  Live, 2026-10-11: a foreground `worker` child ran `python3 -c 'print(42)'` and found `~/.config/mcp-secrets.env` readable.
- Each `AgentSession` owns its extension runtime (Pi `docs/sdk.md:28`), so the parent's `tool_call` handlers never see a child's calls.
  Pi 1.0 has no process-wide hook or policy.
- `subagents.defaultSubagentOnlyExtensions` is a default: an agent's frontmatter (`[]` included) and project `agentOverrides` replace it (`docs/models.md:163`).
  A session can write an agent definition through `subagent` `create`/`update` (`agents/agent-management.js:175-280, 495-505`), in-process with no hook, or through a plain write to a project `.pi/agents/*.md`.
- Project agent and settings discovery does not consult Pi project trust (no trust check in `src/agents/`).

## Host API that forces extensions

- `registerRequiredChildExtensions({sessionId, extensions: [{id, path}], requireForAllRunners: true})`, exported as `pi-subagents/required-child-extensions` (`package.json:96-99`), since 0.68.0 and hardened in 0.75.0 (`CHANGELOG.md:19, 31, 330`).
- Required paths are appended with final precedence, so definitions, overrides, and `extensions: []` cannot remove them (`src/runs/shared/child-tool-plan.js:298-299`).
- Covers foreground (`child-launch.js:78`), background, nested, resumed, and recovered launches (`docs/agents.md:384-390`).
- The launch fails when a required extension fails to load (`child-session.js:384-389`) or its `session_start` handler throws.
- `requireForAllRunners` refuses external CLI runners and machine placement (`shared/required-child-extensions.js:82-89`).
- The registry is process-global, keyed by `Symbol.for(...)` (`:46-58`); a duplicate registration throws, so register on `session_start` and dispose on every `session_shutdown`.

## Launch parameters that act in the host process

- `gate` and `acceptance.verify[].command` run `spawn(..., {shell: true})` (`src/runs/shared/acceptance.js:1375-1378`); an agent's default acceptance can carry one (`subagent-executor.js:4471`).
- `output` accepts absolute paths, and the host writes the child's text there (`single-output.js:74, 218`).
- `share: true` runs `gh gist create` (`subagent-runner.js:305`).
- `cwd`: the sandbox extension merges `<cwd>/.pi/sandbox.json` over the user config (`~/.pi/agent/extensions/sandbox/index.ts` `loadConfig`/`deepMerge`); `enabled: false` turns the sandbox off, and a `filesystem` key replaces `denyRead`.
- `workflow` reads its script file at run time.
- Per-call `agentScope: "user"` drops project agents, packages, and project `agentOverrides` (`src/agents/agents.js:2505-2508, 2522-2525`).

## Configuration

- `~/.pi/agent/extensions/subagent/config.json` `disabledFeatures` (`docs/configuration.md:113-139`): `agent-management` removes in-process create/update/config; `gates` removes only the `gate` shorthand, not `acceptance`.
- No setting forces the agent scope.
- `forceTopLevelAsync` applies at depth 0 only (`docs/configuration.md:329`), and background children still honor a definition's `extensions`.

## Not enforcement

- Capability ceiling (`registerSubagentCapabilityCeiling`, `docs/extension-api.md:356-388`) narrows tools and can deny extensions, but cannot force one in.
- `registerPermissionGate` (`subagent-prompt-runtime.js:327`) is per-tool-name, agents override it, and bash passes through (`docs/watchdog.md:179-183`).

## Not determined

- Whether a child's sandbox extension instance shares the parent's `SandboxManager`.
  Pi loads extensions with jiti `moduleCache: false`, which suggests a fresh instance per load.
- Whether `@anthropic-ai/sandbox-runtime` `initialize` changes process-global state.
- How `requireForAllRunners` behaves for herdr pane placement.
- Whether `agentScope` restricts discovery for chain and parallel items and scheduled runs.

## Remaining gaps with required extensions

- A hook `Ask` becomes a refusal in a child, which has no UI.
- Both extensions continue unchecked when they fail at startup; throwing in `session_start` would fail the launch instead.
- The sandbox extension runs bash in `process.cwd()`, not the child's `cwd`.
- Same-process code, such as a trusted project extension, can dispose the registration.
