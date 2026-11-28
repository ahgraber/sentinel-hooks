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
- `guarded-surface`: the guarded surface covers the installed plugins and the settings that switch a plugin off; a checkout a harness loads in place is covered only as the running copy.
- `hook-tampering-blocking`: tamper protection applies to the installed plugin; a command that disables, removes, or updates a plugin asks the user, and a command that starts a session without the hooks is refused.
- `agent-configuration-floor`: Sentinel reports, at session start, each harness setting that stops its hooks or answers a hook's `ask` without the user, and never writes a setting.
- `sensitive-path-blocking`: the name-heuristic exemption covers package directories only, and no Sentinel file has a name the heuristic matches.
  The shipped block class declares no file of one user's own configuration.
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
- 2026-11-04 Harness commands: the plugin command gate and the session check also read program text passed to a shell or `eval`, and the session check counts a listed variable assigned anywhere in the command, such as through `export`.
  Decided with the user.
- 2026-11-09 A missing package `harnesses/pi/hooks.json` is reported as an unusable file; a missing agent directory `hooks.json` stays silent.
  Decided with the user.
- 2026-11-06 Pi's hook runner lives in `extensions/pi/`, outside the plugin directory, and the floor covers the extensions an in-place Pi package names.
  Decided with the user.
- 2026-11-05 Codex install: the plugin ships a hook installer, the Codex install method until Codex loads hooks from an Agent Plugins manifest; `EachSupportedHarnessInstallsSentinel` stays unchanged, and `design.md` records the Codex gap as known noncompliance.
  Decided with the user.
- 2026-11-05 Scope: a repository skill, `refresh-configuration-floor` in `.agents/skills/`, keeps `configuration-floor.toml` current and replaces `assess-agent-configuration`.
  Decided with the user.
- 2026-11-10 Configuration floor: the session-start check reports only what defeats Sentinel, which is a setting that stops its hooks or lets a hook's `ask` be answered without the user; a value needs a probe, source, or documentation as evidence; `NetworkReachIsUniformPerUser` is removed; a configuration audit the user runs on request is a later change.
  Decided with the user.
- 2026-11-10 Session-start report: Pi's hook runner shows the user a hook's `systemMessage` (`ASystemMessageReachesTheUser`); where a harness shows no session hook output, the check hands the report to the model to pass on, and the README says where the report appears in each harness.
  Decided with the user.
- 2026-11-12 Scope: user documentation is a great-docs site published to GitHub Pages, with `README.md` as its home page and guide pages for installing, updating, and removing Sentinel, answering a question or a refusal, reading the session-start report, and the limits of the posture.
  Decided with the user.
- 2026-11-12 Versioning: the Pi extension has its own manifest, `extensions/pi/package.json`, and its own version, changelog, and `pi-v` tags; `OneVersionAcrossManifests` holds the plugin manifests, the root `package.json`, and the catalogs to the plugin version and excludes the extension manifest (`ExtensionVersionIsItsOwn`); `just` recipes cut each release.
  Decided with the user.
- 2026-11-12 `EachHarnessRunsOnlyItsOwnRegistration` rationale: Copilot in VS Code and Copilot CLI share one event vocabulary, not one tool vocabulary; one registration still serves both because it does not name any tools.
  Decided with the user.
- 2026-11-13 Name-heuristic exemption: it covers package directories only; Sentinel's own file names do not match a name-based pattern, so a file planted in a project cannot switch the heuristic off.
  Decided with the user.
- 2026-11-14 Plugin command gate and session check: they judge shell text wherever a command carries it, including through `xargs` and `find -exec`, and scan text the lexer cannot read; code in another language is not read, inline or in a file.
  Decided with the user.
- 2026-11-13 `PackageDirExemption`: `env/` is removed from the package directories, matching the code since 2026-08-19, because a directory named `env/` can hold real secrets; a virtual environment named `env/` stays covered through its `site-packages/`.
  Decided with the user.
- 2026-11-14 `EnforcementIsNeverCarvedOut`: runs are open inside the `skills/` directory of every plugin a harness installs or loads in place; the requirement does not list how those directories are found.
  Decided with the user.
- 2026-11-14 `PackageDirExemption`: a `.claude/` directory is not a package directory, so the name-based patterns apply inside it.
  Decided with the user.
- 2026-11-17 `UnusableRegistrationIsReportedForTheWholeSession`: the Pi runner reads event names and handler types without regard to case, so `pretooluse` registers `PreToolUse` hooks instead of making the file unusable.
  Decided with the user.
- 2026-11-17 `ExtensionCarriesItsOwnRule`: a rule an extension holds of its own is found by reviewing the extension's source, the check `assess-agent-configuration` made and `refresh-configuration-floor` does not.
  Decided with the user.
- 2026-11-17 `PluginMaintenanceReachesTheUser`: plugin commands are found in program text passed to a shell or to `eval`; the requirement names no other interpreter.
  Decided with the user.
- 2026-11-17 Scope: `CodexHookInstallKeepsTheUsersHooks` is added; the Codex hook installer keeps the user's own hook entries and leaves a hook file it cannot read unchanged.
  Decided with the user.
- 2026-11-17 `ADestructiveOperationOnAnAncestorReachesTheUser`: the requirement states that a directory holding only a location found at runtime, an in-place plugin or a link target, is not gated; the behavior is unchanged.
  Decided with the user.
- 2026-11-17 Rationale in requirements: the history clause in `GuardrailEditsRouteToTheUser`, the permission-layer claim in `ADestructiveOperationOnAnAncestorReachesTheUser`, and the vendor claim in `PackageHooksAreGivenThePackageDirectory` leave the specs; `design.md` keeps the reasoning.
  Decided with the user.
- 2026-11-17 `SettingsThatDefeatTheHooksAreReported`: a settings file that does not parse is reported as unchecked, as its scenario and `design.md` already said.
  Decided with the user.
- 2026-11-17 `EnforcementIsNeverCarvedOut`: a declaration of a class other than the floor anchored at the working directory fails to load, as its scenario already said.
  Decided with the user.
- 2026-11-18 Scope: the shipped block class drops the file of one user's own configuration, and the specs and tests stop naming it; that user's own configuration protects the file until a later change adds a policy of the user's own.
  Decided with the user.
- 2026-11-18 `PackageDirExemption`: the listed directories are a floor, not a closed list, as decided with the user on 2026-11-17, and the exemption covers only directories a package manager creates and fills with installed code.
  `env/` and the catch-all for other package manager output leave the list: the code exempts neither, and `env/` also names a directory of environment settings, which can hold secrets.
  Decided with the user.
- 2026-11-18 `ThePluginIsSelfContained`: a copy outside a checkout decides as the checkout does except on a write to the running plugin directory or the Pi extensions its repository names; the running copy gates those, and another copy gates them only where a harness records the checkout as loaded in place.
  Decided with the user.
- 2026-11-20 Copies a harness loads in place: the floor covers the plugin install locations only, and a checkout only as the running copy; this replaces the 2026-11-02 decision to cover copies found from each harness's own records.
  Only a developer loads a checkout in place, and covering one also meant covering every catalog and package manifest that chooses what the harness loads.
  Decided with the user.
- 2026-11-23 `ConfigurationSurfacesCoverTheDeclarations` is removed: Sentinel neither sets nor reads a user's agent permission lists or OS sandbox; `BashReadBestEffort` says the user configures the layers that stop the read forms the hooks cannot see.
  Decided with the user.
- 2026-11-23 `SettingsThatDefeatTheHooksAreReported`: the report of an unset setting names the user settings file and a value to set, and a setting accepted in its place counts only in the files the harness accepts it from.
  Decided with the user.
- 2026-11-23 `CodexHookInstallKeepsTheUsersHooks`: the installer writes the file a linked hook file ends at and keeps the link and the file's permissions; a link to no file, a read-only file, a file it cannot write, and a file that names a key twice are reported and left unchanged.
  Decided with the user.
- 2026-11-23 `ASystemMessageReachesTheUser`: Pi shows a `systemMessage` whole, and shortens a long error report in the middle so its end, which holds the error, shows.
  Decided with the user.
- 2026-11-23 `PluginMaintenanceReachesTheUser`: program text and launchers are read up to a set depth of nesting, and a command that nests deeper is refused on every agent; `design.md` records the depth.
  Decided with the user.
- 2026-11-23 `RefuseUserOnlyCredentialStores`: a command nested past the leak hook's reading depth is refused when the unread text names `op` or `kubectl`, and a command substitution is read as a command, not matched as text.
  Decided with the user.
- 2026-11-23 `UnusableRegistrationIsReportedForTheWholeSession`: a registration file that names one key twice in an object is unusable and reported, instead of losing the first copy's hooks without a report.
  Decided with the user.
- 2026-11-23 `EnforcementIsNeverCarvedOut`: a covering declaration has no effect on a write or on any run inside the floor other than the open runs in a plugin's `skills/` directory, and the floor names the Pi extensions of the running copy's package.
  Decided with the user.
- 2026-11-24 `PluginMaintenanceReachesTheUser`: the nesting depth counts program text and launchers together in any mix, text too deep to lex is refused, and a program is recognized whatever the case of its name.
  Decided with the user.
- 2026-11-24 `PluginMaintenanceReachesTheUser`: the forms that carry shell text are a closed list of what the checks read, and `design.md`'s known limits name the class left out, a program that runs a command it takes as arguments, such as `flock`.
  Decided with the user.
- 2026-11-24 `PluginMaintenanceReachesTheUser`: the closed list adds `env -S`, whose argument becomes a command line, and a `git -c` key is read in any case git accepts.
  Decided with the user.
- 2026-11-24 `ASystemMessageReachesTheUser`: every text the Pi extension shortens, not only an error report, is shortened the same way, keeping its start and end and counting the characters left out.
  Decided with the user.
- 2026-11-24 `CodexHookInstallKeepsTheUsersHooks`: the installer keeps a file's permission bits, and the owner, group, access control lists, and extended attributes are not carried over.
  Decided with the user.
- 2026-11-24 `CodexHookInstallKeepsTheUsersHooks`: an install whose hook definitions already stand in the file leaves it as it is, wherever they stand in each event's list.
  Decided with the user.
- 2026-11-24 `ASystemMessageReachesTheUser`: the Pi extension passes text a hook wrote unchanged and shortens only text it builds itself.
  Decided with the user.
- 2026-11-24 `RefuseUserOnlyCredentialStores`: text the lexer cannot read is judged command by command by the same rules, the nesting of such text is not counted, text the lexer gives up on because of its depth counts as nested past the limit, and the store program is recognized whatever the case of its name.
  Decided with the user.
- 2026-11-24 `BlockBashReadFromZeroAccessPath`: a read utility is recognized whatever the case of its name.
  Decided with the user.
- 2026-11-24 `BlockBashReadFromZeroAccessPath` and `BashReadBestEffort`: the case of a read utility's name is ignored where it is the program a segment runs or a program `xargs` or `find -exec` launches, and a reader in another case behind a program the hooks do not unwrap is out of scope.
  Decided with the user.
- 2026-11-24 `PrecedenceIsOneRule`: the floor's guarded verdict for runs excepts the runs `EnforcementIsNeverCarvedOut` opens in a plugin's `skills/` directory.
  Decided with the user.
- 2026-11-24 `CodexHookInstallKeepsTheUsersHooks` and `UnusableRegistrationIsReportedForTheWholeSession`: each requirement states the class of file it reports, one it cannot read, can read only by dropping part of it, or cannot reach or write, and its scenarios name the instances, such as a key written twice; the installer gives a new hook file the user's default permissions and writes nothing when a run changes nothing.
  Decided with the user.
- 2026-11-25 `SessionsWithoutTheHooksAreRefused`: the named switches add Claude Code's `CLAUDE_CODE_SAFE_MODE`, `CLAUDE_CODE_RESTRICTED`, and `CLAUDE_CONFIG_DIR`, a `--settings` value that switches the Sentinel plugin off, Codex's `CODEX_HOME`, Pi's `PI_CODING_AGENT_DIR`, and `HOME` for every harness.
  Decided with the user.
- 2026-11-26 `SessionsWithoutTheHooksAreRefused`: the named switches add a Claude Code `--setting-sources` list that leaves out `user`.
  Decided with the user.
- 2026-11-25 `PluginMaintenanceReachesTheUser`: a wrapper's or launcher's options do not hide the program it runs, a word that can be an option's value or the program is judged both ways, `env -S` text is read as `env`'s own arguments, and the Codex commands add `codex features disable hooks` and `plugins`.
  Decided with the user.
- 2026-11-25 `RefuseUserOnlyCredentialStores`: an option before the subcommand does not hide the read, and an option value equal to a subcommand word refuses.
  Decided with the user.
- 2026-11-25 `CodexHookInstallKeepsTheUsersHooks`: an install whose hook definitions already stand in the file leaves it as it is in any order of the hooks within a group as well.
  Decided with the user.
- 2026-11-25 `EnforcementIsNeverCarvedOut`: the floor names each directory from which Pi loads an extension of the running copy's package, not the entries `package.json` writes.
  Decided with the user.
- 2026-11-26 `EnforcementIsNeverCarvedOut`: an extension Pi loads only by its fallback for a mixed or empty `extensions` list is outside the floor.
  Decided with the user.
- 2026-11-27 `SettingsThatDefeatTheHooksAreReported`, `UnusableRegistrationIsReportedForTheWholeSession`, `CodexHookInstallKeepsTheUsersHooks`, and `AHookThatCannotAnswerBeforeAToolCallRefusesIt`: text that is not valid UTF-8, or holds `NaN`, `Infinity`, or a number outside the range of a double, does not parse.
  Decided with the user.
- 2026-11-27 `SettingsThatDefeatTheHooksAreReported`: a switch that turns off a hook in a hook file that cannot be read is reported, naming the hook file as unreadable.
  Decided with the user.
- 2026-11-27 `CodexHookInstallKeepsTheUsersHooks`: a registration in the installed copy that cannot be read is reported, and the hook file is left unchanged.
  Decided with the user.
- 2026-11-27 `EnforcementIsNeverCarvedOut`: `PrecedenceIsOneRule` decides a run in a plugin's `skills/` directory, so a closer guarded declaration makes it ask.
  Decided with the user.
- 2026-11-27 `AdapterNormalizationIsTotal`: an adapter passes a payload that does not parse to the hook unchanged, so the hook answers it as on a harness that sends payloads directly.
  Decided with the user.
