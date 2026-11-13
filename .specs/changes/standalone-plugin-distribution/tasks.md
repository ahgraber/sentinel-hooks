# Tasks: standalone-plugin-distribution

## 1. Specs root

- [x] 1.1 Move `modules/home/ai/shared/.specs/` to `.specs/` with `git mv`, including this change directory.
- [x] 1.2 Move each capability in `modules/home/ai/pi/.specs/specs/` and the archived change in `modules/home/ai/pi/.specs/changes/archive/` into `.specs/`, and delete `modules/home/ai/pi/.specs/NORTH-STAR.md`.
- [x] 1.3 Rewrite every `modules/home/ai/` path in the active changes to its location in the new layout: `pi-subagent-enforcement/proposal.md`, `single-command-rule-engine/proposal.md`, and `program-semantics-table/{proposal.md,design.md,tasks.md,specs/hook-tampering-blocking/spec.md}`.
  Where `program-semantics-table/design.md` reasons from `hooks.nix` or a home-manager switch, add an `OPEN QUESTION` there for that change's apply step, and leave the reasoning unchanged.
- [x] 1.4 Update every file outside `.specs/` that names `modules/home/ai/shared/.specs/` or `modules/home/ai/pi/.specs/`, found with `git grep`.

## 2. Hooks outside the posture

- [x] 2.1 Delete `stop-precommit.sh` and its test `test_stop_precommit.py`.
- [x] 2.2 Delete `session-instructions.sh` and the `instructions/` directory.
- [x] 2.3 Delete `reload-skills-catalog.py`.
- [x] 2.4 Remove the deleted hooks from the Copilot adapter's hook table, from Pi's `hooks.json`, and from the capability and tooling records the capability coverage test reads.
- [x] 2.5 Remove `end-of-turn-precommit` from the capability kind record.
- [x] 2.6 Remove every remaining reference to the deleted files, found with `git grep`.
  The suites cannot collect until task 3.4, so task 3.8 runs them.

## 3. Plugin directory

- [x] 3.1 Move `modules/home/ai/shared/hooks/` to `plugins/sentinel/hooks/` with `git mv`.
- [x] 3.2 Remove the `REPO_ROOT` constant and the `repo_root` parameter from `guarded_paths.py`, resolve `<repo>/` declarations through `repo_root_of` on the supplied path, and take case folding from the home directory and the supplied path's volume.
  Rewrite each test that passes `repo_root` to build a checkout with a `.git` entry in its temporary directory.
- [x] 3.3 Add a test that a `<repo>/` declaration matches a path inside any checkout, with the hooks loaded from a directory that is not in a checkout and has fewer than five parent directories.
- [x] 3.4 Move the Copilot adapter to `plugins/sentinel/harnesses/copilot/`, and `git mv` `security-policy.json` to `plugins/sentinel/com.github.copilot/hooks/hooks.json`.
  Move the Pi extension to `plugins/sentinel/harnesses/pi/extension/`, and `hook-dispatch.py` and `hooks.json` to `plugins/sentinel/harnesses/pi/`.
- [x] 3.5 Move each agent's `tests/` to `tests/<agent>/`, the shared tests to `tests/shared/`, and the extension's `*.test.mjs` files to `tests/pi/`, and move `pyproject.toml` and `uv.lock` to the repository root.
- [x] 3.6 Replace every path a test builds from its own file's location (`parents[N]`, `.parent.parent`, `resolve(import.meta.dirname, ...)`) and every `flake.nix` lookup with a repository root found as the nearest directory above the test file that holds `.specs/`, and the plugin directory as `<root>/plugins/sentinel/`.
  Rewrite each fixture that recreates the `modules/home/ai/` layout in a temporary directory, such as the Copilot adapter path tests, to the plugin layout.
- [x] 3.7 Make the Copilot adapter and `hook-dispatch.py` find the hooks as `../../hooks` from their own files, and remove the adapter's `REPO_ROOT`.
- [x] 3.8 Update `scripts/apps-test.sh` and `scripts/lib/common.sh` for the new test and project paths, keeping one pytest run per test directory.
- [x] 3.9 Record the `harness` kind in the capability coverage test, with artifacts found under `plugins/sentinel/harnesses/`, and record `hook-events`, `hook-execution`, and `hook-registration` as that kind with the extension files that implement each.
- [x] 3.10 Run the full suite, and record each failing test with the requirement or declaration it covers.
  Expected failures are the tests of the configuration-checkout declarations, which group 6 removes, and the tests of the hook-source exemption on the moved paths, which group 8 fixes; fix any other failure before continuing.
  Recorded failures:
  - `tests/shared/test_capability_coverage.py::test_every_capability_has_a_kind_and_existing_package_artifact`: the baseline still holds `end-of-turn-precommit`, which this change removes; `sdd-sync` deletes the baseline capability.
  - `tests/shared/test_guarded_surface.py::test_end_of_turn_hook_source_reaches_each_agent_gate`: `RepositorySourcesAreGuarded`, over a configuration-checkout source this repository never held; task 6.4 deletes it.
  - `tests/copilot/test_block_hook_tampering.py::TestPathResolution::test_write_through_symlink_to_repo_hook_asks`: the adapter in the checkout was covered by a `<repo>/modules/...` declaration; `RunningCopyLoadedInPlace` covers it after tasks 4.5 and 5.3.
- [x] 3.11 Add a test for `ThePluginIsSelfContained`: copy `plugins/sentinel/` to a temporary directory outside any checkout, and check that each hook reaches the same decision there as in the checkout for a set of tool calls.

## 4. Manifests and registrations

- [x] 4.1 Write `plugins/sentinel/harnesses/claude/hooks.json` with the events and matchers of the Claude registration, each command in the form `"${CLAUDE_PLUGIN_ROOT}/hooks/<hook>"`.
- [x] 4.2 Write `plugins/sentinel/harnesses/codex/hooks.json` in the same form, with `"${PLUGIN_ROOT}/hooks/<hook>"`.
- [x] 4.3 Rewrite `plugins/sentinel/com.github.copilot/hooks/hooks.json`, each command running the adapter as `"${PLUGIN_ROOT}/harnesses/copilot/copilot-vscode-hook-adapter.py"`, and update the Copilot tests that read the registration.
- [x] 4.4 Rewrite `plugins/sentinel/harnesses/pi/hooks.json` with the dispatcher command `AI_HOOK_AGENT=pi uv run --script "${PLUGIN_ROOT}/harnesses/pi/hook-dispatch.py"` and each shell hook as `AI_HOOK_AGENT=pi "${PLUGIN_ROOT}/hooks/<hook>"`.
- [x] 4.5 Write `plugins/sentinel/.claude-plugin/plugin.json`, naming `./harnesses/claude/hooks.json`, and `plugins/sentinel/plugin.json` with the Agent Plugins 1.0 `$schema` and `extensions.com.openai.hooks` naming `./harnesses/codex/hooks.json`.
- [x] 4.6 Install the plugin in VS Code from a local marketplace, and record which format it reads, which registration it runs, and where it installs the plugin from each catalog and from a local folder.
  Install it in Codex, and record whether Codex CLI lists and runs its hooks.
  Install it in Copilot CLI, and record which registration it runs.
- [x] 4.7 Write the catalogs `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`, and `.github/plugin/marketplace.json`, each with one relative-path entry for `plugins/sentinel`.
- [x] 4.8 Write the root `package.json` with the `pi-package` keyword, a `pi` key naming the extension, and `"*"` peer dependencies on the Pi packages the extension imports.
- [x] 4.9 Add a test for `EachHarnessRunsOnlyItsOwnRegistration`: the plugin holds no `hooks/hooks.json`, no root `hooks.json`, and no `.codex-plugin/`; the Claude manifest names `harnesses/claude/hooks.json`; the root manifest declares the Agent Plugins `$schema` and names `harnesses/codex/hooks.json`; and `com.github.copilot/hooks/hooks.json` runs only the Copilot adapter.
- [x] 4.10 Add a test for `HooksRunFromTheInstalledPlugin`: for each registration, run every command with the plugin-root variable set to a temporary copy of the plugin and the working directory set to an unrelated directory and then to a checkout of this repository, and check that each command starts the hook in the copy.
- [x] 4.11 Add a test for `OneVersionAcrossManifests`: every manifest, `package.json`, and catalog entry carries one version, and a fixture with one differing version fails.
- [x] 4.12 Run `claude plugin validate` on the plugin and on the Claude catalog, and fix every error it reports.

## 5. guarded-path-declarations

- [x] 5.1 For each plugin install location in the floor, replace the file listing with a walk that declares each link it finds, as a tree when the target is a directory, following directory links once under the inode guard; keep the file listing for the hook-source trees.
- [x] 5.2 Add tests for `NewFileBehindALinkInAnInstallLocation`, a link below a plugin's top level, a hidden top-level link, and a link to a link whose middle hop is written.
- [x] 5.3 Add to the floor's fixed directories the parent of the module's own directory when it holds `.claude-plugin/plugin.json`, with tests for `RunningCopyLoadedInPlace` and for a hooks directory whose parent holds no manifest.
- [x] 5.4 Apply an exec-through declaration to runs inside the floor where it names a `skills/` directory under a plugin install location, and to nothing else inside the floor, and leave those declarations out of `restricted_grants`.
- [x] 5.5 Add tests for `CarveOutOverAnInstalledCopy`, `PluginSkillScriptRunsInsideTheFloor`, and `PluginSkillScriptWriteInsideTheFloor`, and a test that session-start validation reports no finding for a plugin skill exec-through declaration.
- [x] 5.6 Add a test that an exec-through declaration naming a non-skill directory under a plugin install location has no effect on a run there.

## 6. guarded-surface

- [x] 6.1 Remove the `<repo>/modules/...`, `<repo>/users/...`, and `<repo>/modules/home/apps/...` declarations, the `<repo>/scripts/mcp-secrets.sh` exception, and the `~/.pi/agent/shared-hooks/` floor entry from `guarded-paths.toml`.
- [x] 6.2 Declare `~/.claude/plugins/`, `~/.codex/plugins/`, `~/.copilot/installed-plugins/`, `~/.pi/agent/git/`, and `~/.pi/agent/npm/` in the enforcement floor, beside the existing `~/.vscode/agent-plugins/` entry.
- [x] 6.3 Declare exec-through the plugin skill directories listed in `design.md` `TheFloorCoversWholeInstallLocations`, and remove `<repo>/modules/home/ai/shared/skills/`.
- [x] 6.4 Delete the tests that cover `RepositorySourcesAreGuarded` and the removed declarations, from the list task 3.10 recorded, and rewrite each remaining test fixture that names a `modules/home/ai/` or `users/*/home-manager/` path to a path the manifest still declares.
- [x] 6.5 Add tests for `AnotherHarnessesCopyIsWritten`, `AnotherPluginsFileIsWritten`, `PluginSkillScriptRuns`, and `InstalledCopyIsRead`.
- [x] 6.6 Add a test for `SkillsRootsAreRunnable` `SkillScriptRun` with a script under a plugin skill directory in each harness layout.
- [x] 6.7 Add to the floor the plugin directories the records in `design.md` `InPlaceCopiesComeFromHarnessRecords` name, with each one's `skills/` directory run-only, reading VS Code's `settings.json` as JSON with comments and trailing commas.
- [x] 6.8 Add tests for `AnotherHarnessesInPlaceCopyIsWritten` and `CheckoutOutsideThePluginDirectory` with a record of each harness, a Pi record with a relative path, a VS Code record with comments and a trailing comma, and a missing record.
- [x] 6.9 Measure the floor build time per hook call with the real plugin cache and the in-place records declared, and record it in `design.md` `InstallLocationsDeclareTheirLinks`.
- [x] 6.10 Declare in the enforcement floor `~/.copilot/settings.json`, `~/.copilot/config.json`, and `<project>/.github/copilot/settings*.json`, and add tests for `CopilotSettingsDisableTheHooks` and `ProjectCopilotSettingsAreWritten`.

## 7. hook-tampering-blocking

- [x] 7.1 Add a test for `ADestructiveOperationOnAnAncestorReachesTheUser` with `rm -rf ~/.pi`, which removes the declared `~/.pi/agent/`.
- [x] 7.2 Add the harness command table `design.md` `HarnessCommandsAreATable` describes to `tool-vocabulary.toml`, with the commands and switches the two new requirements name, and a source and date for each harness.
- [x] 7.3 Gate a plugin maintenance command and refuse a session switch in `block-hook-tampering.py`, finding the program in every segment through the known wrappers and reading an environment assignment before it.
- [x] 7.4 Add tests for `PluginIsDisabled`, `PluginIsRemovedInAnotherHarness`, `MarketplaceIsRemoved`, `PluginCommandBehindAWrapper`, and `PluginIsListed`, and a test that each subcommand in the table is gated.
- [x] 7.5 Add tests for `NestedSessionWithHooksOff`, `NestedSessionThroughAnOverride`, `NestedSessionThroughAnEnvironmentAssignment`, `ExtensionReplacedInPi`, and `NestedSessionWithHooksOn`, and a test that each switch in the table is refused.
- [x] 7.6 Read harness commands in program text and listed variables assigned anywhere in the command, as `design.md` `HarnessCommandsAreFoundInProgramTextAndEarlierSegments` describes, and add tests for `PluginCommandInProgramText`, `NestedSessionThroughAnExport`, and `NestedSessionInProgramText`.
- [x] 7.7 Find a harness that `xargs`, `find -exec`, or `watch` runs, and a short switch with its value attached, such as `pi -e./runner.ts`, with tests for both.

## 8. sensitive-path-blocking

- [x] 8.1 Extend the hook-source exemption to the Sentinel plugin directory in a checkout and in every installed copy, and to the checkout's `tests/` directory.
- [x] 8.2 Rewrite the entries in `sensitive-path-cases.json` that name `modules/home/ai/` or `users/*/home-manager/` paths.
- [x] 8.3 Add tests for `GuardrailSourceInACheckout`, with a hook source and a test file, and `GuardrailSourceInAnInstalledCopy`.
- [x] 8.4 Remove the hook-source exemption, so the name heuristic exempts package directories only, and replace the 8.3 tests with tests for `APlantedHookSourceDoesNotExempt` and `NoSentinelFileMatchesANamePattern`.

## 9. cross-agent-capability-parity

- [x] 9.1 Extend the capability coverage test to read each registration the plugin ships, `harnesses/*/hooks.json` and `com.github.copilot/hooks/hooks.json`, and fail when one does not run a hook of the enforcement kind, directly or through an adapter.
- [x] 9.2 Add a fixture registration that omits one enforcement hook, and check that the test fails on it.
- [x] 9.3 Remove the `configuration` kind from the capability coverage test, and record `agent-configuration-floor` as the enforcement kind with `session-policy-checks.py`.

## 10. Copilot CLI

- [x] 10.1 Install the plugin in Copilot CLI, and record the `PreToolUse` payload for each of its shell, read, create, and edit tools, and the environment a plugin hook receives.
- [x] 10.2 Make the adapter judge a Copilot CLI file tool whose input is patch text as `apply_patch`, since Copilot CLI sends Claude Code's tool names and its `apply_patch` tool as `Edit`.
- [x] 10.3 Add adapter tests that replay each recorded Copilot CLI payload and reach the same decision as the matching VS Code payload.
- [x] 10.4 Add a test that a hook under `~/.copilot/installed-plugins/` is detected as the `copilot` agent.

## 11. agent-configuration-floor

- [x] 11.1 Write `configuration-floor.toml` with each supported harness's settings files in merge order and the values `SettingsThatDefeatTheHooksAreReported` reports, each with its evidence, harness version, and date.
  Add `configuration-floor.toml` to the `agent-configuration-floor` record and to the hook data files in the capability coverage test.
- [x] 11.2 Make `session-policy-checks.py` read every supported harness's settings, report as `SettingsThatDefeatTheHooksAreReported` requires, write no file, and report a `CLAUDE_CODE_SHELL` that is not a bash without naming an install path.
- [x] 11.3 Add tests for each scenario of `SettingsThatDefeatTheHooksAreReported`, with a fixture settings file per harness, a VS Code file with comments and a trailing comma, a file that does not parse, and a check that no file changes.
- [x] 11.4 Make the check send its report by the route each harness shows the user: the `systemMessage` field in Claude Code, Codex, and Pi, with the Pi hook runner showing that field as `ASystemMessageReachesTheUser` requires and a test for each of its scenarios.
  In Copilot CLI and VS Code, hand the report to the model as session context with a request to tell the user, by the form a probe shows each one passes on.
- [x] 11.5 Add a test for `RegistrationsRouteTheVocabulary` over each registration the plugin ships, and a fixture registration that misses one spelling.
- [x] 11.6 Add tests for `GuardrailEditsRouteToTheUser` `WholesaleBypassRequested` and `NoSurfaceSeesTheRefusal` on the refusal text `hook_response.py` gives.
- [x] 11.7 Write the repository skill `refresh-configuration-floor` in `.agents/skills/`, which checks each harness's current build and documentation for settings that stop the hooks or answer a hook's `ask`, and for changed defaults, and updates `configuration-floor.toml`.
  Put the probes in its directory: the hook that answers `ask`, and a script per command-line harness that runs one permission mode against it.
  Track `.agents/skills/` and `.claude/skills/` in `.gitignore`, ask the user to link `.claude/skills/refresh-configuration-floor` to `../../.agents/skills/refresh-configuration-floor` and to remove the `assess-agent-configuration` link, and describe the skill in `AGENTS.md`.

## 12. Pi hook runner

- [x] 12.1 Read the package's `harnesses/pi/hooks.json` from the plugin directory, found from the extension's own file, and the agent directory's `hooks.json`, and run the hooks of both.
- [x] 12.2 Report an unusable file by its own path, and keep running the other file's hooks.
- [x] 12.3 Set `PLUGIN_ROOT` to the plugin directory for the package's hooks only.
- [x] 12.4 Add `node --test` cases for `PackageHookRuns`, `UserHookRuns`, `BothFilesMatchOneCall`, `ProjectFileIsIgnored`, and `NoUserFile`.
- [x] 12.5 Add `node --test` cases for `UnusableUserFileLeavesThePackageHooks` and `UnusablePackageFileLeavesTheUserHooks`, and update the other unusable-file cases to name the file they break.
- [x] 12.6 Add `node --test` cases for `PackageHookReadsThePackageDirectory` and `UserHookHasNoPackageDirectory`.
- [x] 12.7 Move the extension to `extensions/pi/`, point `package.json` at it, and find the plugin directory as `plugins/sentinel/` in the repository that holds it.
- [x] 12.8 Put in the floor the directory of each extension that an in-place Pi package, or the repository holding the running plugin directory, names under `pi.extensions` in its `package.json`, and add the floor and tamper cases for it.
- [x] 12.9 Report a missing package `harnesses/pi/hooks.json` as an unusable file, and add a `node --test` case for `MissingPackageFileIsReported`.

## 13. Codex hook installer

- [x] 13.1 Add tests for `harnesses/codex/install-hooks.py`: it writes each entry of `harnesses/codex/hooks.json` with `${PLUGIN_ROOT}` replaced by its installed copy, keeps the user's other hooks, replaces an earlier Sentinel install's entries, removes them with `--uninstall`, and refuses to run outside a plugin install location.
- [x] 13.2 Add a test that a written entry exits 2 with the installer's command when its hook file is missing, and runs the hook when it is present.
- [x] 13.3 Write `harnesses/codex/install-hooks.py` with a `uv` script shebang, and state in its docstring the Codex defect it works around and when to remove it.
- [x] 13.4 Install the plugin and run the installer in an isolated Codex home through `scripts/isolated-harness.sh`, trust the hooks, and record that a read of a `.env` file is refused.

## 14. Install evidence and documentation

- [x] 14.1 Install Sentinel in Claude Code, Codex, VS Code, Copilot CLI, and Pi from the repository's git URL, and save each transcript, with the evidence `design.md` names for each harness, where the harness shows the session-start report, and a hook's run time on Copilot CLI, to `evidence/install-<harness>.txt`.
- [x] 14.2 Write the user documentation as a great-docs site whose home page is `README.md`.
  The reader is a developer who runs one or more of the supported agents and wants to install Sentinel and use it.
  The reader does not need to understand the code.
  Keep exit codes, command-parsing rules, file inventories, and maintainer material such as the `refresh-configuration-floor` skill out of the user documentation.
  Write in plain language in the voice of a professional technical writer, following ASD-STE100.
  - [x] 14.2.1 Confirm that great-docs builds a site from `README.md` and guide pages alone, because Sentinel ships no importable Python package.
    If it does not build, stop and give the user the options before writing pages.
  - [x] 14.2.2 Add `great-docs` and `quarto-cli` in a `docs` dependency group, and add `great-docs.yml` at the repository root.
    Build with `uv run --group docs great-docs build`, and add the build output to `.gitignore`.
    Exempt `great-docs.yml` from the `forbid-yml` hook, because great-docs reads only that file name.
  - [x] 14.2.3 Show the user the outline of the README and of each guide page, and get approval before writing prose.
  - [x] 14.2.4 Write `README.md` in this order: what Sentinel does and which agents it supports; which categories of action proceed, which ask the user, and which are refused, with one to three examples for each category; what happens when an action is refused, at a high level and in terms of the security posture; the install steps as one table with one install method per harness, including the programs `session-tool-checks` requires; what the session-start report is, at a high level; links to the guide pages.
    The guide pages carry the detail of a refusal and of the session-start report.
  - [x] 14.2.5 Write one guide page for each task a user does, each answering "how do I X": install, update, and remove Sentinel in each harness, with the Codex hook installer; read the session-start report, where it appears, and how to clear each finding; respond to an `ask` or a refusal, with what the user sees and what the agent is told.
  - [x] 14.2.6 Write a limits page about the limits of the security posture, each with what the user does about it.
    It says that Sentinel judges command text, so a command that hides its effect gets past it; that one agent setting can remove the sandbox and permission boundary Sentinel depends on; that harnesses differ in what Sentinel can enforce, and Sentinel refuses where a harness cannot ask; and that Sentinel cannot check Copilot policy the server delivers or a Claude Code mod that approves a refused call.
  - [x] 14.2.7 Add a GitHub Actions workflow that builds the site and publishes it to GitHub Pages at `https://ahgraber.github.io/sentinel-hooks/`, and set `site_url` in `great-docs.yml` to that address.
    The README links to the site.
  - [x] 14.2.8 Check each page against the proposal's user stories: it answers the questions a reader of that story asks, and it says nothing more.
- [ ] 14.3 Run the full test suite and every hook in `.pre-commit-config.yaml` on the changed files.
- [ ] 14.4 After `sdd-sync` deletes the `end-of-turn-precommit` baseline, run the full test suite and confirm that `tests/shared/test_capability_coverage.py::test_every_capability_has_a_kind_and_existing_package_artifact` passes.

## 15. Versioning and releases

- [x] 15.1 Give the Pi extension its own manifest, `extensions/pi/package.json`, with its own version, and narrow `OneVersionAcrossManifests` to exclude it (`ExtensionVersionIsItsOwn`), with a test.
- [x] 15.2 Add `CHANGELOG.md` for the plugin and `extensions/pi/CHANGELOG.md` for the extension, in Keep a Changelog format, with the first release under `[Unreleased]`.
- [x] 15.3 Add `scripts/release.sh` and the `just release-plugin` and `just release-pi` recipes, and try each in a throwaway clone: a first release, a second release, a dirty working tree, and an empty `[Unreleased]`.
- [x] 15.4 Add the versioning and changelog procedure to `AGENTS.md`.
- [ ] 15.5 Cut `plugin-v0.1.0` and `pi-v0.1.0` after the branch reaches `main`.
