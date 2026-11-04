# Proposal: standalone-plugin-distribution

## Intent

Sentinel hooks give coding agents defense in depth.
No one can install them yet: the hooks, their policy, and their tests assume one fixed checkout layout.
This change makes the set of Sentinel hooks deployable as a plugin that each supported agent installs, and makes the guardrails protect the copy each agent runs.

## User Stories

### Story: install-per-agent

As a developer who runs several coding agents, I want to install Sentinel in each of them, so that every agent I run gets the same protection.

### Story: protect-installed-copy

As a Sentinel user, I want the guardrails to protect the copy of Sentinel each agent runs, so that an agent cannot weaken its own protection by editing its installed plugin.

### Story: one-tree

As the Sentinel maintainer, I want the source tree to be the installed plugin, so that what I test is what users install.

## Scope

**In scope:**

- One specs root at `.specs/`, which takes in every active change.
- Removal of the hooks outside the security posture, with the `end-of-turn-precommit` capability.
  This removal serves no story; it adds no behavior.
- `plugin-distribution` (new): Claude Code, Codex, Copilot in VS Code, Copilot CLI, and Pi install Sentinel from this repository.
- `guarded-path-declarations`: the enforcement floor covers the locations harnesses install plugins into, and plugin skill scripts run there.
- `guarded-surface`: the guarded surface covers the installed plugins, the copies a harness loads in place, and the settings that switch a plugin off, not a source checkout that no harness runs.
- `hook-tampering-blocking`: tamper protection applies to the installed plugin; a command that disables, removes, or updates a plugin asks the user, and a command that starts a session without the hooks is refused.
- `agent-configuration-floor`: Sentinel reports, at session start, each harness setting that weakens a layer, and never writes a setting.
- `sensitive-path-blocking`: the hook-source exemption covers the Sentinel plugin.
- `cross-agent-capability-parity`: parity holds across the harnesses Sentinel supports, checked over the registrations the plugin ships.
- `hook-registration` and `hook-execution` (Pi): the Pi runner runs the hooks shipped in the Sentinel package and the user's own hooks.

**Out of scope:**

- A PyPI package and a shell installer.
- `bash-command-validator`: unchanged.

## Approach

One plugin directory is both the source tree and the installed plugin.
Each harness gets its own manifest and hook registration in that directory, and every registration runs the same hooks.
The policy's self-protection names the directories where each harness installs plugins.

## Resolved Questions

- 2026-10-31 Distribution: one security plugin for every harness.
  Decided with the user.
- 2026-10-31 Self-protection: the enforcement floor covers the installed plugin directories, not a source checkout.
  Decided with the user.
- 2026-10-31 Preference hooks: `bash-command-validator` stays; the other preference hooks leave this repository.
  Decided with the user.
- 2026-10-31 Configuration floor: Sentinel checks the user's agent settings and does not write them.
  Decided with the user.
- 2026-10-31 Copilot CLI is a supported harness.
  Decided with the user.
- 2026-10-31 Specs root: one root at `.specs/`; this change lands before every other active change.
  Decided with the user.
- 2026-11-02 Links in plugin install locations: the floor walks each install location for links and covers each link and its target, instead of listing every file.
  Decided with the user.
- 2026-11-02 Copies a harness loads in place: this change covers them, found from each harness's own records.
  Decided with the user.
- 2026-11-02 One change: the configuration check, the plugin command gate, and Copilot CLI are part of this change, because the change makes the whole of the former configuration code a multi-harness plugin.
  Decided with the user.
- 2026-11-02 Configuration check: an unset boundary setting is reported only while its current default is unsafe, and the check keeps only the hook half of `GuardrailEditsRouteToTheUser`.
  Decided with the user.
- 2026-11-02 A command that starts a harness session with the hooks or plugins off is refused, not asked.
  Decided with the user.
- 2026-11-03 Plugin install locations: an enforcement-floor record marks one with `plugins = true`, so the manifest stays the one list of vendor paths.
  Decided with the user.
