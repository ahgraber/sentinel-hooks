---
name: refresh-configuration-floor
description: Use on request to refresh Sentinel's configuration floor, when a supported harness ships a new build, renames or adds a setting that turns hooks or plugins off, changes a permission mode or a default, or when a value in `configuration-floor.toml` has old evidence.
---

# Refresh the configuration floor

`plugins/sentinel/hooks/configuration-floor.toml` names the settings, in each supported harness, that defeat Sentinel's hooks.
The session-start check reports each one it finds.
A harness changes its settings between builds, so the file goes stale.
This skill brings the file up to date with evidence for each value.

## When to Use

- The user asks to refresh, recheck, or update the configuration floor.
- A supported harness has a new build, and the file records an older `version`.
- A harness adds, renames, or removes a setting that turns hooks or plugins off, or changes a permission mode or a default.
- A value's `checked` date is old, or its `evidence` is `documentation` and a probe can now run.

## When Not to Use

- Judge a user's sandbox, permission mode, or network settings: the floor does not report them.
- Change what the session-start check reports in principle: that is a requirement change to `agent-configuration-floor`.
- Record the tool names or hook input a harness sends: `tool-vocabulary.toml` holds those.

## Invocation Notice

- Tell the user when this skill is running: `refresh-configuration-floor`.
  Skip the notice when the user asked for the skill by name or slash command; spelling and spacing need not match.
  A phrase from this skill's own trigger list is not a name — naming the work is not naming the skill.

## What the floor holds

A setting belongs in the floor only when it has one of two effects:

- It stops Sentinel's hooks from running: it turns off the harness's hooks, switches the Sentinel plugin off, or switches off one hook Sentinel registered.
- It lets a question a hook put to the user be answered without the user.

Every other setting stays out, however permissive its name is.
A mode in which a hook's `ask` reaches the user, or is refused because no user is present, is not a floor value.

## The evidence rule

List a value only when one of these shows its effect, and record which one in `evidence`:

- `probe`: a probe in `scripts/` ran against the current build.
- `source`: the harness's source at the build's tag.
- `documentation`: the harness's own documentation.

A mode's name or description is not evidence.
Claude Code's `bypassPermissions`, Copilot CLI's `allow-all`, and VS Code's autopilot each show the user a hook's `ask`, and each description says otherwise.
Prefer a probe; use documentation alone only when no probe can run.

## Workflow

01. Read `plugins/sentinel/hooks/configuration-floor.toml`, including the field notes at its top.
02. Read each installed harness's version: `claude --version`, `codex --version`, `copilot --version`, `code --version`, `pi --version`.
    Compare each with the `version` the file records.
03. For each harness whose build changed, read its settings reference and changelog for the two effects above.
    Check each recorded value still exists under the same name, and check each recorded default.
    Check the settings files and their merge order against the `files` list.
04. Decide which probes to run: read `references/probes.md`.
    Run a probe for each permission mode a harness adds or changes, and for each value whose evidence is `documentation` when a probe can show it.
05. Give the user each probe command to run, one at a time.
    Do not start a harness session yourself.
    A probe needs a signed-in harness, some need a person at the screen, and a session with every permission is the user's to start.
06. Save each probe's output under `evidence/` in the active change, with the harness version and the date.
07. Update `configuration-floor.toml`: add, change, or remove values, and set each value's `evidence`, `source`, and `checked`, and the harness `version`.
    Do not add a value without evidence.
08. Add or change a case in `tests/shared/test_configuration_floor.py` for each value that changed.
    A new `kind` of value needs code in `plugins/sentinel/hooks/configuration_floor.py` and its own tests.
09. Run `bash scripts/apps-test.sh shared` and the hooks in `.pre-commit-config.yaml` on the changed files.
10. Report what changed, what each probe showed, and which values still rest on documentation alone.

## What needs the user's decision

Stop and ask before any of these:

- A new effect, beyond the two above, that a setting has on Sentinel.
- A harness that no longer shows the user a session-start report by the route `session-policy-checks.py` uses.
- A probe result that contradicts a value the file lists.

## References

- `references/probes.md`: each probe, what it shows, how to read its output, and what it showed last.
- `scripts/`: the probes.
  Each builds its own throwaway plugin or project and changes no configuration.
