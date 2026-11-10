# Design: standalone-plugin-distribution

## Context

The hooks are stdlib-only Python and Bash scripts in one flat directory.
A hook imports its sibling modules from its own directory, so the directory ships as one unit.
Every harness runs the same hooks; the harnesses differ only in where they install a plugin and in how a registration names the hooks.

Facts from the harness documentation and source, gathered 2026-10-31 and checked again 2026-11-02:

- Every harness sets a plugin-root environment variable for a plugin's hook commands: `CLAUDE_PLUGIN_ROOT` (Claude Code), `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` (Codex), `PLUGIN_ROOT` and `COPILOT_PLUGIN_ROOT` (Copilot CLI), and `CLAUDE_PLUGIN_ROOT` or `PLUGIN_ROOT` by manifest format (VS Code).
- Hook commands run in the session's working directory, not in the plugin directory.
- Claude Code reads `.claude-plugin/plugin.json`, and always loads `hooks/hooks.json` when the file exists, in addition to the file its manifest names.
- Codex treats a root `plugin.json` that declares the Agent Plugins `$schema` as the canonical manifest, and reads hook settings from its `extensions.com.openai` object.
  `.codex-plugin/plugin.json` is a compatibility fallback that applies only when that object is absent.
  Codex's loader then skips the plugin's hooks, because it loads hooks only for the older manifest format (`codex-rs/core-plugins/src/loader.rs`, Codex 0.166.0; openai/codex#47925).
  Codex loads user hooks from `$CODEX_HOME/hooks.json`, runs each hook command as `$SHELL -lc`, and removes a plugin's other version directories when a version installs.
  An explicit `hooks` value replaces the default discovery of `hooks/hooks.json`.
  The Codex documentation says lifecycle hooks "are supported for plugins installed manually in Codex desktop", and does not say whether Codex CLI runs them.
- VS Code picks a plugin's format from its marker files: a root `plugin.json` with the Agent Plugins `$schema` is Agent Plugins 1.0, `.claude-plugin/plugin.json` is the Claude format, and the Copilot format applies only when no other marker is found.
  Each format reads its hooks from one fixed file: `com.github.copilot/hooks/hooks.json` (Agent Plugins 1.0), `hooks/hooks.json` (Claude), and a root `hooks.json` (Copilot).
- Install locations: `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`, `~/.copilot/installed-plugins/<marketplace>/<plugin>/`, `~/.vscode/agent-plugins/<host>/<owner>/<repo>/<path>/`, `~/.pi/agent/git/<host>/<owner>/<repo>/` and `~/.pi/agent/npm/node_modules/<name>/`.
  The Pi layouts are read from Pi's source, not from its documentation.
- Some plugins load in place, with no copy in an install location: Claude Code loads a `--plugin-dir` plugin and a relative-path plugin from a marketplace added from a local path in place, and a link-mode plugin through links to each top-level entry in its cache entry; Pi loads a local package from its path; VS Code loads a directory named in `chat.pluginLocations`.
  Claude Code forbids a top-level link that points outside a link-mode plugin, and allows links below the top level.
- Codex copies a local plugin into `~/.codex/plugins/cache/<marketplace>/<plugin>/local/` and loads that copy; its copy function skips symlinks (`codex-rs/core-plugins/src/store.rs`).
  VS Code and Pi clone git installs, which keep the links a plugin's repository commits.
- Copilot CLI gives a root Agent Plugins `plugin.json` precedence over `.claude-plugin/plugin.json`, and reads an Agent Plugins plugin's hooks from `com.github.copilot/hooks/hooks.json` only; the manifest cannot name another file.
- VS Code's Copilot harness and Copilot CLI share one hook runtime and format.
  A PascalCase event such as `PreToolUse` receives snake_case fields, `tool_name` and `tool_input`; the adapter reads that form today.
  VS Code's older Local harness has its own format, and Sentinel does not register for it.
- Copilot CLI sets `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, and `CLAUDE_PLUGIN_ROOT` for plugin hooks.
  Its own tool names are `bash`, `view`, `create`, `edit`, `str_replace_editor`, and `apply_patch`; the PascalCase form can report Claude's names instead.
  A non-zero exit from a `preToolUse` hook denies the call, a hook that times out lets the call proceed, and `ask` becomes a denial in autopilot mode.
  Its documentation names no approval step for plugin hooks.
- The harnesses switch a plugin or its hooks off through their own command lines and settings, with no path a declaration covers: `claude plugin disable`, `codex plugin remove`, `copilot plugin disable`, `copilot config`, `pi remove`, `disableAllHooks`, `enabledPlugins`, and Codex's `features.hooks`.
  Each can also start a nested session without the hooks, such as `claude --bare` or `codex -c features.hooks=false`.
- Codex runs a plugin hook only after the user trusts it in `/hooks`, and the trust is tied to a hash of the hook definition, so each update needs a new approval.
- A Claude Code plugin cannot set permissions, the sandbox, or `defaultMode`.
- Pi has no plugin hooks and no subdirectory install; `pi install git:` installs the whole repository.
  An extension finds its own file through `import.meta.url`.

Agent detection reads `/.claude/`, `/.codex/`, or `/.copilot/` in the hook's path, and an adapter or registration names its agent through `AI_HOOK_AGENT`.
The Claude Code, Codex, and Copilot CLI install locations carry their marker.
VS Code and Copilot CLI reach the hooks through the Copilot adapter, which names its agent `copilot`; one agent name serves both, because they share the tool vocabulary.
Pi reaches them through `hook-dispatch.py` with `AI_HOOK_AGENT=pi`; the Pi install locations carry no marker.

## Decisions

### Decision: OnePluginDirectoryIsTheSource

**Chosen:** `plugins/sentinel/` holds the hooks, every harness's manifest, registration, and adapter, and nothing else.
The tests stay outside it, at the repository root.

```text
sentinel-hooks/
├── .claude-plugin/marketplace.json
├── .agents/plugins/marketplace.json
├── .github/plugin/marketplace.json
├── package.json                    # Pi: whole-repository git install
├── extensions/pi/                  # Pi's hook runner, the extension package.json names
├── pyproject.toml                  # test tools
├── .specs/
├── tests/                          # shared/, claude/, codex/, copilot/, pi/
└── plugins/sentinel/
    ├── .claude-plugin/plugin.json  # Claude Code; hooks: ./harnesses/claude/hooks.json
    ├── plugin.json                 # Agent Plugins 1.0; extensions.com.openai.hooks: ./harnesses/codex/hooks.json
    ├── com.github.copilot/hooks/hooks.json   # VS Code and Copilot CLI registration, at the path Agent Plugins 1.0 fixes
    ├── hooks/                      # hooks, modules, guarded-paths.toml, tool-vocabulary.toml
    └── harnesses/
        ├── claude/hooks.json
        ├── codex/hooks.json
        ├── copilot/                # copilot-vscode-hook-adapter.py
        └── pi/                     # hooks.json, hook-dispatch.py
```

**Rationale:** with one plugin, every harness can share one hooks directory, so no build step copies files and the installed copy is the tested tree.
The `plugins/` level leaves room for other plugins in the same catalogs.
Tests outside the plugin keep the corpus and the fixtures out of every installed copy.

**Alternatives considered:**

- A generator that writes a plugin directory per harness from a canonical source: it solves copying shared files into many plugins, and this repository has one plugin.
- The repository root as the plugin: it conflicts with Pi's root `package.json` and with a later second plugin.
- A Python package as the canonical form, with registrations that call an installed command: a hook call then depends on a package on `PATH` or a network fetch.

### Decision: ManifestsFollowEachHarnessesFormatDetection

**Chosen:** two manifests.
`.claude-plugin/plugin.json` serves Claude Code.
A root `plugin.json` that declares the Agent Plugins 1.0 `$schema` serves Codex, through `extensions.com.openai.hooks`, and VS Code and Copilot CLI, through the fixed `com.github.copilot/hooks/hooks.json`.
The plugin holds no `.codex-plugin/` directory.

**Rationale:** VS Code reads `.claude-plugin/plugin.json` as a format marker, so a Copilot-format root manifest beside it is never read, and VS Code would run the Claude registration with Claude tool names.
The Agent Plugins `$schema` is the marker that outranks the Claude one.
Codex reads its hooks from that same root manifest; a `.codex-plugin/plugin.json` beside it would be ignored, and a second place to edit the Codex hooks is a place for them to drift.

**Alternatives considered:**

- A Copilot-format root `plugin.json`: VS Code reads the Claude marker instead.
- Keeping `.codex-plugin/plugin.json` as the Codex manifest: Codex applies it only when the root manifest has no `extensions.com.openai` object.

### Decision: NoDefaultHooksFile

**Chosen:** the plugin holds no `hooks/hooks.json`, and no `hooks.json` at its root.
Each harness's registration is at a path only that harness reads.

**Rationale:** Claude Code loads `hooks/hooks.json` whatever its manifest says, Codex discovers it when no explicit value is set, and VS Code reads it for a Claude-format plugin and a root `hooks.json` for a Copilot-format one.
A file at either path would run one harness's registration in another.

**Alternatives considered:**

- Renaming the scripts directory away from `hooks/`: it removes no risk, because the rule is about the registration file, not the directory name.

### Decision: CommandsStartFromThePluginRoot

**Chosen:** every registration command names its script as `"${PLUGIN_ROOT}/hooks/<hook>"` in double quotes, or as `"${CLAUDE_PLUGIN_ROOT}/hooks/<hook>"` where a harness sets only that name.
The shell expands the variable, so the form works whether or not a harness substitutes it in the command text.
The VS Code registration runs the Copilot adapter as `"${PLUGIN_ROOT}/harnesses/copilot/copilot-vscode-hook-adapter.py"`, and the Pi registration runs its dispatcher as `AI_HOOK_AGENT=pi uv run --script "${PLUGIN_ROOT}/harnesses/pi/hook-dispatch.py"` and its shell hooks as `AI_HOOK_AGENT=pi "${PLUGIN_ROOT}/hooks/<hook>"`.
The adapter and the dispatcher find the hooks relative to their own files.

**Rationale:** commands run in the session's working directory, so a relative path finds nothing, and a fixed home path names one install layout.
The Pi install locations carry no agent marker, so the Pi registration names its agent.

### Decision: PiInstallsTheRepository

**Chosen:** a root `package.json` with a `pi` key names the extension at `extensions/pi/`, and declares the Pi packages the extension imports as `"*"` peer dependencies.
The extension reads `harnesses/pi/hooks.json` from `plugins/sentinel/` in the repository that holds it, and `hooks.json` from Pi's agent directory.
It sets `PLUGIN_ROOT` to that plugin directory for the package's hooks only.

**Rationale:** Pi has no subdirectory install, so a git install takes the whole repository.
Setting `PLUGIN_ROOT` to the plugin directory, not to the repository root, gives Pi the same command form as the other harnesses.

### Decision: ThePiHookRunnerIsHostRuntime

**Chosen:** Pi's hook runner lives in `extensions/pi/`, outside the plugin directory.
`plugins/sentinel/harnesses/pi/` keeps Sentinel's Pi registration and `hook-dispatch.py`.
For a Pi package loaded in place, the floor covers the directory of each extension its `package.json` names under `pi.extensions`, beside the plugin directories its catalogs name.
When Sentinel runs from `plugins/sentinel/` in a repository, the floor also covers the extensions that repository's `package.json` names, as it covers the running plugin directory.

**Rationale:** the runner gives Pi the hook engine Claude Code, Codex, and Copilot have built in.
It also runs the user's own hooks from Pi's agent directory, so it is host runtime that runs plugins, and no part of a plugin.
Inside the plugin directory, every harness that copies the plugin would carry it unused, and a second plugin would have to reach into Sentinel's directory to run on Pi.
Pi loads exactly the files `pi.extensions` names, so that list, and not the catalogs Pi never reads, says which files of an in-place package must be in the floor.
A git install is in the floor whole, under `~/.pi/agent/git/`.

**Alternatives considered:**

- The runner under `plugins/sentinel/harnesses/pi/`: the floor covered it through the catalog-named plugin directory, with no change to the guard, but it ties the runner to one plugin.

Decided with the user.

### Decision: AMissingPackageRegistrationIsUnusable

**Chosen:** the runner reports a missing `harnesses/pi/hooks.json` in the package as an unusable file.
A missing `hooks.json` in Pi's agent directory stays silent.

**Rationale:** the package always ships its file, so a missing one means a broken install or a runner that looks in the wrong place.
Read as no registrations, either one stops every Sentinel hook under Pi with no report.
Most users write no hooks of their own, so a missing agent directory file is the usual case.

**Alternatives considered:**

- A missing file is no registrations for both sources: the requirement's earlier wording, which let Sentinel's hooks stop in silence.

Decided with the user.

### Decision: TheRunningPluginDirectoryIsInTheFloor

**Chosen:** the floor's fixed directories gain the plugin directory that holds the running hooks: the parent of the module's own directory, when that parent holds `.claude-plugin/plugin.json`.

**Rationale:** the module's and the launcher's directories are `hooks/`, so without this a copy loaded in place, such as a checkout added as a local marketplace, leaves its registrations, manifests, and adapters grantable.
The manifest marker keeps a hooks directory outside a plugin, as in a test fixture, from adding its parent.
A maintainer who loads Sentinel in place from the checkout they edit gets a prompt on every write to the plugin directory; installing from the git URL instead keeps the checkout outside the floor.

### Decision: TheFloorCoversWholeInstallLocations

**Chosen:** the manifest declares in the enforcement floor `~/.claude/plugins/`, `~/.codex/plugins/`, `~/.copilot/installed-plugins/`, `~/.vscode/agent-plugins/`, `~/.pi/agent/git/`, and `~/.pi/agent/npm/`.
It declares exec-through the skill directories inside them, with one-component globs per layout:

- `~/.claude/plugins/cache/*/*/*/skills/`
- `~/.codex/plugins/cache/*/*/*/skills/`
- `~/.copilot/installed-plugins/*/*/skills/`
- `~/.vscode/agent-plugins/*/*/*/skills/` and `~/.vscode/agent-plugins/*/*/*/plugins/*/skills/`
- `~/.pi/agent/git/*/*/*/skills/`, `~/.pi/agent/npm/node_modules/*/skills/`, and `~/.pi/agent/npm/node_modules/@*/*/skills/`

The guard applies an exec-through for runs inside the floor only where the declaration ends in a `skills/` component under one of these locations.
Session-start reporting leaves these declarations out, because they keep their effect on runs.

**Rationale:** every installed plugin's hooks run in its harness, and any of them can allow a tool call, so every file there is enforcement against writes.
No parser is needed for each harness's registration format, and no marker identifies Sentinel's copies.
Opening runs under skill directories keeps plugin skills working, and the floor still refuses an unapproved write to any script there.
A skill directory a glob misses asks before each run, so a layout the globs do not know fails toward a prompt, never toward a silent pass.

**Alternatives considered:**

- Sentinel's own files only, found by a path glob or a marker string: it leaves other plugins' hooks grantable, and it needs a marker scan or a glob per layout anyway.
- The floor over hook registrations and the scripts each one names: it needs a parser for each harness format in every hook call, and it protects fewer files.

### Decision: InstallLocationsDeclareTheirLinks

**Chosen:** the floor does not list the files under a plugin install location.
It walks each install location with `os.scandir`, following directory links once under the inode guard `_enforcement_files` already uses, and declares each link it finds: as a tree when the link's target is a directory, as a file otherwise.
The install location's own declaration covers every other path under it by prefix.
The hook-source trees keep the file listing.

**Rationale:** a floor tree's declaration already matches every path under it.
The listing adds a declaration for each file, and each declaration's link chain is what puts a link's target in the floor; nothing else depends on it.
Building those declarations is the cost: on 2026-11-02, with the real `~/.claude/plugins/cache/` (672 files, no links) declared, a hook call that writes took 201 ms with the listing and 26 ms without the cache declared, while the walk alone took 8 to 15 ms. On 2026-11-04, with the walk implemented, all six install locations declared, and the in-place records read, a floor build on the same machine took 88 ms at the median, against 33 ms with the install locations left out.
The install locations then held about 2,000 entries under `~/.claude/plugins/` alone, plus Codex, VS Code, and Pi npm plugins, and no in-place record; the walk scanned about 980 directories per build and accounts for most of the difference.
Only a write or a run builds the floor; a read does not.
Declaring each link keeps every hop of its chain in the floor, and a tree declaration over a linked directory also covers a file created there later, which the listing misses.

**Alternatives considered:**

- The full listing: it protects the same targets at about 200 ms per call, growing with each plugin, and misses new files behind a link.
- Prefix match alone: a write to a link's target proceeds, and Claude Code's link-mode plugins run from those targets.
- Only the top-level entries of each plugin directory: Claude Code forbids only top-level links that point outside the plugin, a `*` glob skips hidden entries, and the VS Code layout has no fixed depth.

### Decision: InstallLocationsAreMarkedInTheManifest

**Chosen:** an enforcement-floor record marks a plugin install location with `plugins = true`.
The guard walks a marked location for links instead of listing its files, and applies an exec-through declaration ending in `skills/` under it to runs inside the floor.
The flag is valid only on an enforcement-floor directory.
Decided with the user on 2026-11-03.

**Rationale:** the install locations are vendor paths, so they stay in the manifest beside the other per-harness declarations, in one list.
A location that loses its flag stays in the floor; its files are listed again, and its plugin skill scripts ask before each run.

**Alternatives considered:**

- A separate manifest table: a sixth declaration class, which every requirement that lists the classes would have to name.
- A list in `guarded_paths.py`: a second copy of the vendor paths, which can drift from the manifest.

### Decision: InPlaceCopiesComeFromHarnessRecords

**Chosen:** the floor covers the plugin directories the supported harnesses' user-level records name as loaded in place:

- Claude Code: each `known_marketplaces.json` entry with a `directory` or `file` source, at its `installLocation`.
- VS Code: each key of `chat.pluginLocations` in the user `settings.json`, at `~/Library/Application Support/Code/User/settings.json` on macOS and `~/.config/Code/User/settings.json` on Linux.
- Pi: each local path in the `packages` list of `~/.pi/agent/settings.json`, resolved from that file's directory.
- Copilot CLI: each `extraKnownMarketplaces` entry with a `directory` source in `~/.copilot/settings.json`.

For each location, the floor covers the location when it holds a plugin manifest, or else each relative-path plugin its catalog names, or else the whole location.
Each covered plugin's `skills/` directory is run-only, as in the install locations.
A record that is missing or does not parse adds nothing.

**Rationale:** Codex copies every plugin it installs, but Claude Code, VS Code, Copilot CLI, and Pi run a local plugin where it is, so a copy one harness runs in place is outside every install location.
Each harness writes the location to its own records, so the guard reads a few small files instead of searching the disk.
The records are in the floor: `~/.pi/agent/settings.json` and both VS Code user `settings.json` paths by declaration, `known_marketplaces.json` under `~/.claude/plugins/`, and `~/.copilot/settings.json` through `guarded-surface` `PluginSwitchesAreInTheFloor`, so an agent cannot drop a copy's coverage by editing its record.
Covering the plugin directories, not the whole checkout, keeps a checkout's tests and specs writable when a harness loads its plugin in place.
A record the harness itself cannot parse loads no plugin, so it has no running copy to cover.
The guard reads VS Code's `settings.json` as JSON with comments and trailing commas, as VS Code does, so a file VS Code accepts never reads as broken here.

**Alternatives considered:**

- A README note to load Sentinel in place in at most one harness: it leaves the gap to the user.

### Decision: FoundLocationsAreNotAncestors

**Chosen:** the destructive-operation ancestor check stays on the manifest's declarations.
The directories the guard finds at runtime (the running plugin directory, each plugin directory a harness loads in place, and each link target in an install location) are in the floor as themselves, but a directory that encloses one is not an ancestor for that reason.
Decided with the user on 2026-11-04.

**Rationale:** a marketplace install puts the plugin under a declared install location, so each harness's configuration directory above it is already an ancestor.
The gap is limited to a plugin loaded in place, which is a checkout by definition, and to the directories above a link target.
Every enclosing directory up to the home directory would become an ancestor, including the directory that holds a user's checkouts; the gate already reads a filtered `find -delete`, an archive extraction, and a recursive `chmod` there as a destruction of that directory.

**Alternatives considered:**

- Every enclosing directory up to the home directory or the repository root, as for declarations: it closes the gap, at the friction above.
  It fits a later change that also narrows `find -delete` to the files it can reach.
- Enclosing directories up to the repository root that holds the found directory: it leaves the removal of the directory that holds the checkout ungated.

### Decision: TheFloorIsBuiltOncePerHookCall

**Chosen:** the walk, the record reads, and the floor itself are built once in each hook process that writes or runs, as the floor is now.

**Rationale:** a link target or an in-place record can change between calls, and a per-call build reads the current state with no cache to invalidate.

### Decision: RepositoryRootFollowsThePath

**Chosen:** `guarded_paths.py` drops the module constant `REPO_ROOT`, the fifth parent of its own file, and the `repo_root` parameter it feeds.
A `<repo>/` declaration resolves against the repository that contains the supplied path, through `repo_root_of`, as `path-matching` `RepositoryContainment` requires.
Case-folding detection uses the home directory and the supplied path's volume.
A test that passed `repo_root` builds a checkout in its temporary directory instead, with a `.git` entry `repo_root_of` finds.

**Rationale:** in a plugin cache the fifth parent is an arbitrary cache directory, and an install path with fewer than five parent directories raises an error at import.
The per-path lookup already exists for every `<repo>/` match.

### Decision: TestsFindTheirTreeFromTheirOwnFile

**Chosen:** a test locates the plugin directory as `<repository root>/plugins/sentinel/`, with the repository root found as the nearest directory above the test file that holds `.specs/`.
No test reads a `flake.nix` marker or a `modules/home/ai/` path.
Each test directory runs as its own pytest run, as `scripts/apps-test.sh` runs them now, because several directories hold test files with the same name.

**Rationale:** the marker names a repository this one is not.
`.specs/` is at the root of this repository and nowhere else in it.

### Decision: HarnessCommandsAreATable

**Chosen:** `tool-vocabulary.toml` gains a table of each supported harness's program name, its plugin maintenance subcommands, and its switches that start a session without the hooks, including the environment variables.
`block-hook-tampering.py` reads the command through `shell-lexing`, finds the program in each segment through the known wrappers, and gates or refuses by the table: `Ask` for a maintenance subcommand, `Block` for a switch.

**Rationale:** the commands name no path, so they need a rule of their own, and they are vendor identifiers that change between releases, so they live in data beside the other per-harness names, with a source and a date.
The `program-semantics-table` change builds a catalog of programs; when it lands, these rows move into it.

### Decision: HarnessCommandsAreFoundInProgramTextAndEarlierSegments

**Chosen:** the harness command checks also read the program text a command passes to a shell, to `eval`, or to an interpreter's inline code option, and the text it pipes into a shell, nested up to four levels.
The session check counts an assignment of a listed variable anywhere in the command, including the program text, except in the harness's own arguments.
Decided with the user on 2026-11-04.

**Rationale:** `bash -c 'claude --bare'` and `export CLAUDE_CODE_SIMPLE=1; claude` start the same session as the forms the requirements named, and the lexer already extracts the text and the words both need.
Order is not tracked, and an assignment that is not exported still counts: the over-refusal is limited to a variable named in the same command as a harness.

**Alternatives considered:**

- Assignments on the harness's own segment only: it leaves the `export` form open.

### Decision: SentinelSourcesAreFoundByTheirContents

**Chosen:** the name-heuristic exemption covers a directory whose `hooks/` holds `guarded_paths.py`, and the `tests/` directory of a directory whose `plugins/*/hooks/` holds it.
The harness-named directory pattern is removed.

**Rationale:** the plugin runs from an installed copy, not from the checkout, so the running hook's own location does not find the checkout, and each harness installs copies at a different path.
A file the plugin ships is present in every copy and moves with the plugin, so no edit follows a new harness or a move.
The check reads the file system only after a file name matches the heuristic.

**Alternatives considered:**

- A path pattern per install layout: it needs an edit for each harness and each layout change, which the requirement rules out.
- The running plugin directory from the floor: it misses the checkout and every other harness's copy.

### Decision: TheSessionCheckReadsAllHarnessSettings

**Chosen:** `session-policy-checks.py` reads, at each session start, the user, project, and managed settings files of every supported harness, and reports each forbidden value, each unset setting whose current default is forbidden, each file it cannot parse, and each difference between the harnesses' allowed hosts.
A data file, `configuration-floor.toml` beside the hooks, holds for each harness its settings files, the forbidden values, the unsafe defaults with the harness version they were read from, and the host-list settings.
It reads JSON with comments and trailing commas for VS Code and Copilot CLI, and TOML through `tomllib` for Codex.
The check writes no file, and its report is the hook's standard error, as the session checks report now.
The shell warning names no install path: it reports a `CLAUDE_CODE_SHELL` that is not a bash.

**Rationale:** a harness whose hooks are off runs no check, so only another harness's session can report it.
The values are vendor identifiers, so they are data, with a version, beside the code that reads them.

### Decision: CodexHooksComeFromAnInstaller

**Chosen:** the plugin ships `harnesses/codex/install-hooks.py`, which writes the entries of `harnesses/codex/hooks.json` into `$CODEX_HOME/hooks.json` with `${PLUGIN_ROOT}` replaced by the installed copy it runs from.
It keeps the user's other hooks, replaces entries from an earlier Sentinel install, removes Sentinel's entries with `--uninstall`, and refuses to run outside a plugin install location.
Each entry runs its hook through `sh -c`, which exits 2 with the installer's command when the hook file is missing.
The README installs Codex this way, and every other harness through its own plugin install.

**Rationale:** Codex skips the hooks of a plugin with an Agent Plugins root manifest, and VS Code and Copilot CLI need that manifest.
The installer reads the registration the plugin ships, so the registration stays the one source and the parity test still covers it.
An update removes the old version directory, so an entry from the earlier install names a missing file.
Codex lets a call proceed when its hook fails.
Each entry therefore checks for its file and exits 2 when the file is missing, which refuses the call and prints the repair.
`sh -c` keeps the guard working under any login shell, including fish.

**Alternatives considered:**

- Codex installs the repository root with a `.codex-plugin/plugin.json`: Codex copies `.git` into the hook trust bundle of a root install (openai/codex#56793).
- Install scripts for every harness: a second registration beside a plugin whose hooks already run, and each hook would run twice.
- Wait for the Codex fix: until it ships, Codex skips every Sentinel hook.

Decided with the user.

### Decision: OneVersionIsCheckedNotGenerated

**Chosen:** each manifest, `package.json`, and catalog entry carries the version as a literal.
A conformance test fails when they differ.

**Rationale:** four files with one field each is less machinery than a generator, and the test catches every drift the generator would prevent.

## Architecture

```text
harness event
  └─ harness reads its own manifest
       └─ Claude Code: .claude-plugin/plugin.json ──> harnesses/claude/hooks.json ──> "${CLAUDE_PLUGIN_ROOT}/hooks/<hook>"
       └─ Codex: plugin.json extensions.com.openai ──> harnesses/codex/hooks.json ──> "${PLUGIN_ROOT}/hooks/<hook>"
       └─ VS Code, Copilot CLI: plugin.json $schema ──> com.github.copilot/hooks/hooks.json ──> harnesses/copilot/copilot-vscode-hook-adapter.py
       └─ Pi extension ──> harnesses/pi/hooks.json + ~/.pi/agent/hooks.json, PLUGIN_ROOT set ──> harnesses/pi/hook-dispatch.py
            └─ hooks/<hook> reads hooks/guarded-paths.toml and hooks/tool-vocabulary.toml
```

## Risks

- **VS Code loads a Claude-format plugin from `~/.claude/plugins/`**: the path marker then names Claude while VS Code runs the hook, and the path decides over the adapter's name.
  A task checks where VS Code installs from each catalog.
- **Codex CLI may not run plugin hooks**: the Codex documentation names Codex desktop for plugin lifecycle hooks.
  The Codex install evidence records whether Codex CLI lists and runs them; if it does not, Codex CLI users need the hooks in their own configuration until it does.
- **Copilot CLI lets a call proceed when a hook times out**: a hook that runs past its registration's timeout does not refuse.
  The registration's timeouts stay at the values the VS Code registration uses, and the install evidence records a hook's run time on Copilot CLI.
- **Copilot CLI's tool input is not documented field by field**: the adapter reads `command` and the path fields VS Code sends.
  A task records a payload for each of Copilot CLI's tools before the vocabulary and the adapter change.
- **A session-start report may not reach the user**: each harness shows a session hook's standard error differently.
  The install evidence records where each harness shows it.
- **A harness home moved by an environment variable is not declared**: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `VSCODE_AGENT_PLUGINS` move a harness's home and install location, and the manifest declares only the default paths.
  OPEN QUESTION: the manifest's home paths should probably honor these variables; a later change decides how, because the change touches every home declaration.
  `scripts/isolated-harness.sh` sets them to run a harness in `tmp/homes/`, where payload capture works but the floor does not cover the install.
- **Removing a directory above a found plugin location does not ask**: `rm -rf plugins` in a checkout loaded in place, or above a link target, is not an ancestor removal.
  The found location itself stays in the floor; a marketplace install sits under a declared location and is not affected.
- **A planted hook source**: a file named `hooks/guarded_paths.py` exempts its directory from the name heuristic, so an agent can create one to read a file named `secrets.txt` beside it.
  Path-based patterns and declarations still refuse, and the harness-named pattern this replaces could be planted the same way.
- **A program name the command text hides**: `$X plugin disable` names no program the gate can find, so it passes the plugin command gate; the path gates still judge it.
- **A variable the command text does not set**: `source ./env.sh; claude` sets `CLAUDE_CODE_SIMPLE` in a file the session check does not read, and program text nested more than four levels deep is not read.
- **In-place loads with no user-level record**: a `--plugin-dir` session, `CLAUDE_CODE_PLUGIN_DIRS`, a Pi project's `.pi/settings.json`, and VS Code workspace settings name an in-place plugin only for one session or one project.
  Another harness's session cannot see them, so a copy loaded only that way is covered only by its own running sessions.
- **VS Code's install from a local folder**: whether it copies the folder or loads it in place is not documented; task 4.6 records it.
- **A harness changes its install layout**: a skill directory the globs miss asks before each run, and the floor declarations are at the install root, so protection holds.
- **Codex trust**: a fresh install or an update runs no Sentinel hook until the user trusts it in `/hooks`.
  Sentinel cannot detect this from inside Codex, because its own session check is one of the hooks that does not run.
- **The active changes name `modules/home/ai/` paths**: the path rewrite updates them.
  A missed path makes that change's tasks name a file that does not exist, which its apply step detects.

## Dropped Scenarios

- `guarded-path-declarations` `CarveOutOverAHookSource`: no hook resolves to a repository source once each harness runs an installed copy; `CarveOutOverAnInstalledCopy` covers the same grant over the copy a harness runs.
- `sensitive-path-blocking` `GuardrailSourceNamedForWhatItBlocks`: it named the hook sources of one repository; `GuardrailSourceInACheckout` and `GuardrailSourceInAnInstalledCopy` cover a checkout and each installed copy.
- `hook-registration` `ToolCallsProceed`: with two registration files, an unusable file no longer means that no hook runs; `UnusableUserFileLeavesThePackageHooks` and `UnusablePackageFileLeavesTheUserHooks` state what runs.
- `agent-configuration-floor` `AuthorizedGuardrailEdit` and `UnauthorizedGuardrailEdit`: they bound a harness's own review surface, which is that harness's configuration and which Sentinel neither sets nor can judge.

## Known Noncompliance

- **Requirement:** `plugin-distribution` `EachSupportedHarnessInstallsSentinel`, scenario `CodexInstall` **Reason:** Codex skips the hooks of any plugin whose root manifest is an Agent Plugins manifest (openai/codex#39895, #47925, #59516), so Codex needs a step outside its own install mechanism: `harnesses/codex/install-hooks.py`.
  A Codex user who skips the installer runs every Codex session without Sentinel's hooks, and without any warning.
  **Exit condition:** when a Codex release loads `extensions.com.openai.hooks` from an Agent Plugins manifest, delete the installer and its tests, return the README's Codex row to the plugin install alone, and tell installed users to run `install-hooks.py --uninstall` so each hook does not run twice.
  **Recorded:** 2026-11-05

## Verification Waivers

- **Requirement:** `plugin-distribution` `EachSupportedHarnessInstallsSentinel` **Reason:** each scenario needs the harness's own install command against a published repository, and Codex, VS Code, Copilot CLI, and Pi need a signed-in session; the test suite checks the manifests and catalogs statically.
  **Manual evidence:** `evidence/install-claude.txt`, `evidence/install-codex.txt`, `evidence/install-vscode.txt`, `evidence/install-copilot-cli.txt`, and `evidence/install-pi.txt` in this change directory, captured during apply.
  **Recorded:** 2026-11-01
- **Requirement:** `plugin-distribution` `EachHarnessRunsOnlyItsOwnRegistration` **Reason:** which registration a harness loads is decided inside the harness; the test suite checks that no default registration file exists and that each manifest names its own file.
  **Manual evidence:** in each `evidence/install-<harness>.txt`, the `/hooks` listing in Claude Code and Codex; in VS Code, Copilot CLI, and Pi, which have no listing command, the decision a Sentinel hook returns on a tool call that only its own registration matches.
  **Recorded:** 2026-11-01
