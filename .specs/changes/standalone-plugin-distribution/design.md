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
        └── pi/                     # hooks.json, hook-dispatch.py, extension/
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

**Chosen:** a root `package.json` with a `pi` key names the extension at `plugins/sentinel/harnesses/pi/extension/`, and declares the Pi packages the extension imports as `"*"` peer dependencies.
The extension reads `harnesses/pi/hooks.json` from the plugin directory and `hooks.json` from Pi's agent directory.
It sets `PLUGIN_ROOT` to the plugin directory, found from its own file, for the package's hooks only.

**Rationale:** Pi has no subdirectory install, so a git install takes the whole repository.
Setting `PLUGIN_ROOT` to the plugin directory, not to the repository root, gives Pi the same command form as the other harnesses.
An npm package published from `plugins/sentinel/` can follow later without a change to the registration.

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
Building those declarations is the cost: on 2026-11-02, with the real `~/.claude/plugins/cache/` (672 files, no links) declared, a hook call that writes took 201 ms with the listing and 26 ms without the cache declared, while the walk alone took 8 to 15 ms. Declaring each link keeps every hop of its chain in the floor, and a tree declaration over a linked directory also covers a file created there later, which the listing misses.

**Alternatives considered:**

- The full listing: it protects the same targets at about 200 ms per call, growing with each plugin, and misses new files behind a link.
- Prefix match alone: a write to a link's target proceeds, and Claude Code's link-mode plugins run from those targets.
- Only the top-level entries of each plugin directory: Claude Code forbids only top-level links that point outside the plugin, a `*` glob skips hidden entries, and the VS Code layout has no fixed depth.

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

### Decision: TheSessionCheckReadsAllHarnessSettings

**Chosen:** `session-policy-checks.py` reads, at each session start, the user, project, and managed settings files of every supported harness, and reports each forbidden value, each unset setting whose current default is forbidden, each file it cannot parse, and each difference between the harnesses' allowed hosts.
A data file, `configuration-floor.toml` beside the hooks, holds for each harness its settings files, the forbidden values, the unsafe defaults with the harness version they were read from, and the host-list settings.
It reads JSON with comments and trailing commas for VS Code and Copilot CLI, and TOML through `tomllib` for Codex.
The check writes no file, and its report is the hook's standard error, as the session checks report now.
The shell warning names no install path: it reports a `CLAUDE_CODE_SHELL` that is not a bash.

**Rationale:** a harness whose hooks are off runs no check, so only another harness's session can report it.
The values are vendor identifiers, so they are data, with a version, beside the code that reads them.

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
- **A program name the command text hides**: `$X plugin disable` names no program the gate can find, so it passes the plugin command gate; the path gates still judge it.
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

## Verification Waivers

- **Requirement:** `plugin-distribution` `EachSupportedHarnessInstallsSentinel` **Reason:** each scenario needs the harness's own install command against a published repository, and Codex, VS Code, Copilot CLI, and Pi need a signed-in session; the test suite checks the manifests and catalogs statically.
  **Manual evidence:** `evidence/install-claude.txt`, `evidence/install-codex.txt`, `evidence/install-vscode.txt`, `evidence/install-copilot-cli.txt`, and `evidence/install-pi.txt` in this change directory, captured during apply.
  **Recorded:** 2026-11-01
- **Requirement:** `plugin-distribution` `EachHarnessRunsOnlyItsOwnRegistration` **Reason:** which registration a harness loads is decided inside the harness; the test suite checks that no default registration file exists and that each manifest names its own file.
  **Manual evidence:** in each `evidence/install-<harness>.txt`, the `/hooks` listing in Claude Code and Codex; in VS Code, Copilot CLI, and Pi, which have no listing command, the decision a Sentinel hook returns on a tool call that only its own registration matches.
  **Recorded:** 2026-11-01
