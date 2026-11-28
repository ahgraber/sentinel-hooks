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
When Sentinel runs from `plugins/sentinel/` in a repository, the floor also covers the extensions that repository's `package.json` names, as it covers the running plugin directory.

**Rationale:** the runner gives Pi the hook engine Claude Code, Codex, and Copilot have built in.
It also runs the user's own hooks from Pi's agent directory, so it is host runtime that runs plugins, and no part of a plugin.
Inside the plugin directory, every harness that copies the plugin would carry it unused, and a second plugin would have to reach into Sentinel's directory to run on Pi.
Pi loads exactly the files `pi.extensions` names, so that list, and not the catalogs Pi never reads, says which files of the running copy's repository are in the floor.
Sentinel reads each entry as Pi does: a path or glob relative to the package, with or without `./`, and the conventional `extensions/` directory where the package names no extensions (Pi's `docs/packages.md`, read 2026-11-24).
A `!` entry is not applied, so the floor can cover more than Pi loads; decided with the user on 2026-11-24, after a verify run found that an entry rewritten without `./` took the runner out of the floor while Pi still loaded it.
Pi's other fallbacks, for a list that mixes text with other values and for an empty list under a settings filter, are not followed, so an extension Pi loads that way can be outside the floor; decided with the user on 2026-11-26.
A git or npm install is in the floor whole, so an agent cannot write either list into Sentinel's `package.json`, and an agent that can edit a local package's `package.json` can remove the runner from the list outright, which following the fallbacks would not prevent.
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

### Decision: EventNamesAndHandlerTypesIgnoreCase

**Chosen:** the runner compares a registration file's event names and handler types with the names it knows without regard to case.
`pretooluse` registers `PreToolUse` hooks, and a handler of type `Command` is a command handler.
Where two names in one file differ only in case, the groups of both are kept, in file order.
A file that writes one JSON key twice in an object is unusable, and the problem names the key and the line of its second occurrence, because a JSON parser keeps only the last value and would drop the hooks of the first without a sign; decided with the user on 2026-11-24.
Decided with the user on 2026-11-17.

**Rationale:** matchers already compare tool names without regard to case, so the same file reads the same way at every level.
Nobody writes `pretooluse` for a hook they mean not to run, so running it is the outcome the author intended.
Keeping both groups of a duplicated name drops no hook.

**Alternatives considered:**

- A case variant makes the file unusable: one typo stops every hook in the user's file, though the error stays in view.
- A case variant is skipped with a warning: the hook the user meant to run never runs, and the warning scrolls away.

**Known limits:** a misspelling that is not only a case difference, such as `PreToolUs`, still names no event and is skipped with a warning.
Claude Code's handling of a case variant is not checked, so a file Pi accepts can behave differently there; a user's Pi file is read only by Pi.

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

**Known limits:** a plugin installed as a link to a directory outside the install location, as a Claude Code local install can be, has skill runs that ask on every run.
The guard judges a run at the link's target, which no glob matches, and opening runs there would extend an exec-through to a directory the user chose, not one a harness installed.

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

### Decision: OnlyPluginInstallsAreCovered

**Chosen:** the floor covers the copies of Sentinel in the plugin install locations.
A checkout that a harness loads in place is in the floor only while Sentinel runs from it, as the running plugin directory (`TheRunningPluginDirectoryIsInTheFloor`).
The guard does not read the harness records that name local plugin locations.
Decided with the user on 2026-11-20.
This replaces the 2026-11-02 decision to cover every copy those records name.

**Rationale:** each install that the README and the install guide describe puts Sentinel in a plugin install location.
Claude Code, Codex, Copilot CLI, and VS Code install from the marketplace; Pi installs from git.
Only a developer loads a checkout in place.

To protect such a checkout, the guard also had to protect the files that choose which directory the harness loads: the catalog at the checkout's root, and a Pi package's `package.json`.
Without them, an agent could edit the catalog to point the harness at a directory outside the floor.
The harnesses read catalog and manifest paths that the guard did not, as their documentation and source showed on 2026-11-20, and each harness release can change those paths.
A catalog entry that named a missing directory also made the guard fail on every write.

**Known limits:** in a development setup, a session of another harness can write the checkout's plugin directory without asking.
A session of any harness can edit the checkout's catalog, and at its next start the harness loads the directory the catalog names.

**Alternatives considered:**

- Cover each in-place copy, its catalogs, and its Pi `package.json`, at every path each harness reads: it protects a setup only developers use, and its path lists must change with each harness release.

### Decision: FoundLocationsAreNotAncestors

**Chosen:** the destructive-operation ancestor check stays on the manifest's declarations.
The directories the guard finds at runtime (the running plugin directory and each link target in an install location) are in the floor as themselves, but a directory that encloses one is not an ancestor for that reason.
An ancestor holds no fragment of a declaration's text, so the gate finds one by resolving each path word, not by matching text.
Decided with the user on 2026-11-04.
`hook-tampering-blocking` `ADestructiveOperationOnAnAncestorReachesTheUser` states this limit, so a reader of the spec knows a directory above the running plugin directory or a link target is not gated; decided with the user on 2026-11-17.

**Rationale:** the ancestor gate is the only layer that asks before such a removal: guarded paths are declared `ask` rather than `deny` so the prompt can reach the user, so the permission layer permits the write.
A marketplace install puts the plugin under a declared install location, so each harness's configuration directory above it is already an ancestor.
The gap is limited to a running copy loaded in place, which is a checkout by definition, and to the directories above a link target.
Every enclosing directory up to the home directory would become an ancestor, including the directory that holds a user's checkouts; the gate already reads a filtered `find -delete`, an archive extraction, and a recursive `chmod` there as a destruction of that directory.

**Alternatives considered:**

- Every enclosing directory up to the home directory or the repository root, as for declarations: it closes the gap, at the friction above.
  It fits a later change that also narrows `find -delete` to the files it can reach.
- Enclosing directories up to the repository root that holds the found directory: it leaves the removal of the directory that holds the checkout ungated.

### Decision: TheFloorIsBuiltOncePerHookCall

**Chosen:** the walk and the floor itself are built once in each hook process that writes or runs, as the floor is now.

**Rationale:** a link target can change between calls, and a per-call build reads the current state with no cache to invalidate.

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

A Codex `-c` or `--config` override also counts when it sets a whole table as a TOML inline table that names the key: `features={hooks=false}`, or a `plugins` table whose value names `enabled`.
On 2026-11-19 the user confirmed that `codex -c 'features={hooks=false}'` starts a session with no hooks; the `plugins` table forms follow from the same TOML parsing and were not run.
A table that sets the key to `true` is refused too, since the pattern reads names, not values.

### Decision: HarnessCommandsAreFoundInProgramTextAndEarlierSegments

**Chosen:** the harness command checks also read the program text a command passes to a shell or to `eval`, and the text it pipes into a shell, nested up to four levels.
Code in another language is not read, as `SentinelReadsShellWhereverItAppears` decides.
The session check counts an assignment of a listed variable anywhere in the command, including the program text, except in the harness's own arguments.
Decided with the user on 2026-11-04.

A command that nests program text, or launchers such as `xargs`, more than four levels deep is refused on every agent; decided with the user on 2026-11-23.
Before, text nested deeper was not read and the command proceeded, so five nested `eval`s or command substitutions hid `claude plugin disable` or `claude --bare`.
On 2026-11-24 the user decided that the depth counts program text and launchers together, in any mix, and that text too deep to lex is refused as well.
One walker, `bash_commands.nesting`, reads every level for both the tamper hook and the leak hook, so the two hooks count depth the same way.
The tamper hook refuses whatever lies past four levels.
The leak hook refuses there only when the unread text names `op` or `kubectl`, because its refusal cannot be appealed and the tamper hook already refuses the rest.
Text the lexer cannot read, such as a here-string or a process substitution, has no reading to walk, so the walker splits it into the commands it may run and judges every word there at any depth.
Its nesting is therefore not counted: a count found no command the word scan misses, and counting parentheses refused a Python here-document with five nested calls; decided with the user on 2026-11-24.
The one depth case left is the lexer itself giving up because expansions nest past its own limit of 32 levels, far past the four the checks read, and that command is refused as nested past the limit.
The split removes quoting and breaks commands at operators even inside quotes, because a here-string body such as `'cd /srv;op read …'` is code; a quoted `;` inside an option value, as in `--account "w;x"`, therefore cuts `op` from `read`, a rare form accepted for that reason.
Words break at whitespace alone, so `--context=$CTX` stays one option, and `$'…'` quoting is decoded first, as the lexer decodes it.
No word of that text is dropped as a harness's own argument, because any word can look like a harness: `/tmp/claude` would otherwise claim the `CLAUDE_CODE_SIMPLE=1` after it.
Both hooks judge those commands by their normal rules, any word taken as the program: refusing every such command that names `kubectl` would also refuse `diff <(kubectl get deploy a -o yaml) <(kubectl get deploy b -o yaml)`, a read of no secret.

A program name is matched whatever its case wherever a match makes a check stricter, because macOS's default filesystem runs `CLAUDE` as `claude`; decided with the user on 2026-11-24.
The read-only check, which a match makes looser, keeps the exact name, because on a case-sensitive filesystem `CAT` can be another program.
`block-sensitive-paths.py` folds the case of the program a segment runs and of each program that `xargs` or `find -exec` launches, and counts a read utility's exact name in any other word; decided with the user on 2026-11-24.
Folding every word would refuse `git log HEAD -- deploy/.env.production`, because `HEAD` folds to `head`.
A read utility in another case behind a program the hooks do not unwrap, one that takes its command as arguments, is not recognized; `BashReadBestEffort` lists that form.

**Rationale:** `bash -c 'claude --bare'` and `export CLAUDE_CODE_SIMPLE=1; claude` start the same session as the forms the requirements named, and the lexer already extracts the text and the words both need.
Claude Code reads `CLAUDE_CODE_SAFE_MODE` and `CLAUDE_CODE_RESTRICTED` beside `CLAUDE_CODE_SIMPLE` as the modes `--safe-mode` and `--restricted` set (Claude Code 2.1.330 bundle, read 2026-11-25).
`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `HOME` move a harness's home, the names `configuration-floor.toml` records, so a session started with one reads a configuration in which Sentinel need not be installed.
A `--settings` value that sets Sentinel's `enabledPlugins` entry to false switches the plugin off, as `disableAllHooks` switches every hook off.
Claude Code reads `enabledPlugins` only from the settings sources it loads, and `--setting-sources` chooses them beside the managed and `--settings` sources, so a list without `user` starts a session in which a plugin turned on in user settings alone is off (Claude Code 2.1.330 bundle, read 2026-11-26).
`codex features disable hooks` and `codex features disable plugins` write `features.hooks = false` or `features.plugins = false` to `config.toml` (`codex features --help`, codex-cli 0.171.0, read 2026-11-24), so they ask, as the other maintenance commands do.
Decided with the user on 2026-11-25.
Order is not tracked, and an assignment that is not exported still counts: the over-refusal is limited to a variable named in the same command as a harness.

**Alternatives considered:**

- Assignments on the harness's own segment only: it leaves the `export` form open.

### Decision: SentinelReadsShellWhereverItAppears

**Chosen:** the plugin command gate and the session check judge shell text wherever a command carries it: at the top level, in program text passed to a shell or `eval`, in the command `xargs` or `find -exec` runs, in text piped into a shell, and inside a `$(…)` or backquote substitution, including one inside `${…}` or `$((…))`.
Where the lexer cannot read a command, as for a here-string or a here-document a shell reads, both checks scan its words for a harness program and judge the words after it.
Code in another language is not read, whether the command passes it inline or in a file.
Decided with the user on 2026-11-14.

A shell's code is the first word after the options that follow `-c`, because `bash`, `sh`, `zsh`, and `dash` all read options there: `bash -c -x '<code>'`, `bash -c -o errexit '<code>'`, and `bash -c -- '<code>'` run the code.
The word after an `-o` or `-O` there is read as code too: `bash -O` takes a name, but `zsh -O` does not and runs that word, so reading both misses neither.
A word after `-c` that is not `-` or `+` followed by letters is read as code; a shell rejects such a word as an option, so reading it can only add a prompt.
An interpreter's code is the word right after its code option, because `python -c`, `node -e`, and `perl -e` take that word even when it starts with `-`.
The shells read are `bash`, `sh`, `zsh`, `dash`, `ksh`, `mksh`, `yash`, `fish`, `csh`, and `tcsh`; only the first three also count as running a script, so adding the others reads more code and opens no run.
`csh` and `tcsh` text is read with the same lexer, and text it cannot read is scanned word by word, so a harness command in it is still found.
`env -S` and `--split-string` turn their argument into a command line, so that argument is read as shell text; `-S` is found in a group of short options such as `-iS`, and a group whose last option takes a value, such as BSD `env -P <path>`, takes the next word.
`eval --` runs the text after the `--`.
Git reads a `-c` section and variable name in any case, so `Core.Pager` sets the pager.
Decided with the user on 2026-11-24, after a verify run found `eval -- 'claude plugin disable sentinel'`, `env -iS 'claude --bare -p x'`, `env -P /usr/local/bin claude --bare -p x`, and `tcsh -c 'claude plugin disable sentinel'` passing every gate.
Decided with the user on 2026-11-19, after a verify run found `bash -c -- 'claude --bare -p x'` and `dash -c '<write to a settings file>'` passing every gate.

A wrapper's or launcher's options are not trusted to be read exactly, because a group of short options (`sudo -iu root`), an abbreviation (`env --un X`), or an option missing from a list (`sudo -T 10`) makes the option's value look like the program.
For a command behind `sudo`, `doas`, `env`, `nice`, `exec`, `nohup`, `time`, `timeout`, `stdbuf`, `setsid`, `xargs`, or `watch`, the checks a match makes stricter also judge, as the start of the command, each word that can be an option's value and the first word after those, which no option can take.
A later word is an argument, so `timeout 5 git log HEAD -- <path>` does not read `HEAD` as `head`.
A false match needs an option value that is itself a harness command or a read utility, as in `xargs -I claude echo claude --bare`; on 2026-11-25, 216 commands from the tests and a list of everyday wrapper commands kept every verdict.
The read-only check, which a match makes looser, keeps the exact reading.
`env -S` text is read as `env`'s own arguments, so `-S'-i claude'` holds an option and a program, and `--s` is the shortest abbreviation of `--split-string` GNU `env` accepts.
Complete option lists for each wrapper would read the program exactly, but each list goes stale as its program adds options, which is how these forms passed.
Decided with the user on 2026-11-25, after a verify run found `sudo -iu root claude --bare -p x`, `xargs -0n 1 claude --bare -p x`, `sudo -T 10 claude plugin disable sentinel`, and `env -- CLAUDE_CODE_SIMPLE=1 claude -p x` passing every gate.

`block-leaks.py` judges what `bash_commands.nesting` finds, the walk the tamper checks use, so `secret-access-blocking` has a delta: text the lexer cannot read is judged command by command, text the walker reads past the limit is refused when it names `op` or `kubectl`, and the store program is recognized whatever the case of its name.
The global options of `op` and `kubectl` that take a value come from `op --help` and `kubectl options`, so an option value before the subcommand, such as `kubectl --profile none get secret x`, does not hide the read.
A subcommand's own option can stand before the subcommand too, and its value is in no global list, so `kubectl` counts `get` anywhere among its operands with a secret resource after it, and `op` counts `read`, `run`, or `inject` anywhere, or `item` or `document` with `get` after it.
An option value equal to one of those words, as in `op item list --tags read`, refuses; decided with the user on 2026-11-25.

**Rationale:** Sentinel judges command text, not what a process does.
A script file that an agent writes and runs can switch Sentinel off, and a subprocess can write a harness settings file directly, and neither shows in the command text.
Reading inline code in other languages would close one form of indirect execution and leave the file form open, so inline and file code are treated the same.
The agent's sandbox is the boundary for indirect execution, as `user_guide/limits.qmd` tells the user.
Scanning unreadable text favors a match over a miss, as the path gates do for text they cannot read.

**Alternatives considered:**

- Ask when code for a non-shell interpreter names a harness program: it covered inline code only, needed per-interpreter option tables, and widened shared interpreter detection that one exemption relied on (verify run, 2026-11-13).
- Refuse every command the lexer cannot read: here-documents are common, as in `git commit`, so the cost is high.
- Inspect script files, or compare protected files before and after each tool call: a later proposal, if any; a script can have a valid reason to read what such a check would flag.

**Known limits:** code in another language, inline or in a file; a program name or an argument assembled at run time or read from a file or a variable, such as `a=--bare; claude $a`, `$(echo --bare)`, `"$@"`, or a `--settings` value that names a file; text that a program other than `echo` or `printf` pipes into a shell; code given to a program the lists above do not name, such as `script -c` or a copy of `bash` under another name; and a command run by a program, other than the wrappers and launchers named, that takes the command as its arguments, such as `flock` or `parallel`.

### Decision: SentinelFilesDoNotNeedANameExemption

**Chosen:** the name-heuristic exemption covers package directories only.
No file in the plugin, the Pi extension, or the tests has a name that matches a name-based pattern, and a test keeps it so.
The harness-named directory pattern is removed.

**Rationale:** an exemption found from a file's presence or contents can be planted.
An agent creates `hooks/guarded_paths.py` in a project without a prompt, and the name heuristic stops applying to every file beside it; a copied file carries the same hash or marker as the genuine one.
On 2026-11-12, no tracked file in those directories had a matching name, so the exemption did not cover any file.
Sentinel's files then do not need an exemption in a checkout or in any installed copy.

**Alternatives considered:**

- A directory whose `hooks/` holds `guarded_paths.py`: planted with one empty file (found by the verify run on 2026-11-12).
- That marker only inside the enforcement floor, where a write asks the user: sound, but more code for an exemption that does not cover any file, and the checkout loses it anyway.
- A path pattern per install layout: it needs an edit for each harness and each layout change, and a project can create the same path.

Decided with the user on 2026-11-13.

### Decision: EveryPluginSkillsDirectoryOpensRuns

**Chosen:** `EnforcementIsNeverCarvedOut` states one rule for skills: runs are open inside the `skills/` directory of every plugin in a plugin install location.
How each directory is found stays in design: the install-location globs in `TheFloorCoversWholeInstallLocations`.
Decided with the user on 2026-11-14.
`PrecedenceIsOneRule` excepts the runs this decision opens from the floor's guarded verdict, so the two requirements agree after sync; decided with the user on 2026-11-24, after a verify run found the baseline rule still gave every run inside the floor a guarded verdict.
The closest declaration decides these runs, so a guarded declaration of one skill inside a plugin's `skills/` directory makes that skill ask, as it does in a skills root; decided with the user on 2026-11-27, after a verify run found that the code let the plugin's declaration decide before any closer one.

**Rationale:** the requirement named one source of open runs, the exec-through declaration in the manifest, while the code also opens the `skills/` directory of an in-place plugin, so the text and the code disagreed (verify run, 2026-11-13).
The user's outcome is the same for both: a plugin's skill scripts run without a prompt, and nothing else in the floor does.
`~/.agents/skills/` is declared beside the per-agent skills roots because those roots hold links into it, and a declaration does not follow the links inside the directory it names.

**Alternatives considered:**

- List each source in the requirement: it states mechanism, and a new source would break the text again.

### Decision: OnlyASkillScriptRefusalOffersAnotherForm

**Chosen:** where an agent cannot be asked, a refusal of a command Sentinel cannot read halts and tells the agent to report to the user, unless the protected path it touches is a script a skills directory lets run.
For such a script, the refusal names the reads and the script runs Sentinel recognizes, so the agent can run the skill in a form that proceeds.
The prompt a user reads where the agent can be asked still names those forms, and a refusal that asks for relative paths to be restated absolutely is unchanged.
Decided with the user on 2026-11-19.

**Rationale:** `GuardrailEditsRouteToTheUser` forbids a refusal of a guardrail edit to name another way to make it.
The forms included script runs, and Sentinel does not read a script's contents, so after a refused write to a settings file the list read as advice to write a script and run it.
An unreadable command on a protected file and an unrecognized run of a skill script are different cases that reached one message; only the second has a rewrite that proceeds without reaching a guarded file another way.
A skill script is in a protected skills directory, so the agent cannot plant one there without the user.

**Alternatives considered:**

- Name scripts in skills directories only, in every refusal: an agent refused a settings edit still gets a list of forms instead of an instruction to stop.
- Leave the message and record the finding: the message keeps pointing at the script route.

**Known limits:** an agent can still write a script outside the floor and run it; Sentinel does not read script contents, as `SentinelReadsShellWhereverItAppears` records.

### Decision: EnvIsNotAPackageDirectory

**Chosen:** `PackageDirExemption` lists `.venv/` and `venv/` as Python virtual environments, and `env/` is removed from the list.

**Rationale:** the code has refused name matches under `env/` since commit `2b3f5fa` (2026-08-19), because a directory named `env/` can hold real secrets; that commit left the spec list unchanged, so the spec and the code disagreed.
A virtual environment named `env/` keeps its libraries under `site-packages/`, which the exemption covers wherever it appears, so its library files stay reachable.
Only a file outside `site-packages/` whose name matches a name-based pattern, such as `env/bin/credentials-helper`, is refused, which is the safe side.

**Alternatives considered:**

- Exempt `env/` only where it holds `pyvenv.cfg`: an agent can create that file without a prompt, so a planted file would switch the name heuristic off for a real `env/` secrets directory, as a planted `hooks/guarded_paths.py` did.

Decided with the user on 2026-11-13.

### Decision: PackageDirectoriesHaveACeilingAndAFloor

**Chosen:** `PackageDirExemption` covers only directories a package manager creates and fills with installed code, and covers at least `.venv/`, `venv/`, `site-packages/`, and `node_modules/`.
The catch-all for any common package manager output directory leaves the list.
The floor was decided with the user on 2026-11-17, and the ceiling on 2026-11-18.

**Rationale:** the code exempts exactly the four listed names, so the catch-all promised exemptions the code never made.
The floor lets a later change add a name such as `vendor/` or `target/` without changing the requirement.
The ceiling bounds the exemption, which loosens a check: with a floor alone, exempting `config/` would comply, and every file there would skip the name heuristic.
A name that commonly means something else, as `env/` also names a directory of environment settings, does not meet the ceiling.

**Alternatives considered:**

- A floor with no ceiling: it states no bound on a loosening.
- A closed list: every added name becomes a requirement change.

**Known limits:** whether a directory meets the ceiling is a reviewer's judgment; no test checks it.

### Decision: OnlyTheFloorUsesTheProjectAnchor

**Chosen:** `EnforcementIsNeverCarvedOut` states that a declaration of a class other than the floor, anchored at the working directory and every directory above it, fails to load.
Decided with the user on 2026-11-17.

**Rationale:** the requirement said no other class uses the anchor, and only its scenario said what happens when one does; `test_project_anchor_outside_the_floor_does_not_load` tests that outcome.
The anchor reaches every directory above the session, so an exception or a loosening class anchored there would apply far outside the project that declared it.
The behavior is unchanged.

### Decision: TheSessionCheckReadsAllHarnessSettings

**Chosen:** `session-policy-checks.py` reads, at each session start, the user, project, and managed settings files of every supported harness.
It reports each value `configuration-floor.toml` names, each unset setting whose current default is a reported value, and each file it cannot parse.
The data file, beside the hooks, holds for each harness its settings files in merge order and its reported values.
Each value carries its evidence, the harness version, and the date, as the harness commands in `tool-vocabulary.toml` carry `source` and `checked`.
It reads JSON with comments and trailing commas for VS Code and Copilot CLI, and TOML through `tomllib` for Codex.
The check writes no file.
It sends its report by the route each harness shows the user.
Claude Code and Codex show a session hook's `systemMessage` field and do not show its standard error on exit 0 (`evidence/claude-code-hook-ask-by-mode.txt`, `evidence/codex-session-start-output.txt`), so the check returns that field there.
Codex runs its session hooks when the first prompt is sent.
Pi shows nothing of a session hook by itself, so the extension that runs Pi's hooks shows the user a reply's `systemMessage`, and the check returns the field there too.
The extension passes text a hook wrote, its reasons, `additionalContext`, and `systemMessage`, unchanged, and shortens only text it builds itself: a hook's name, an error report, a refusal for a hook that gave no answer, and the call summary in a question; decided with the user on 2026-11-24.
Every text the extension shortens is cut in the middle by one function: it keeps a quarter of the limit from the start and three quarters from the end, and puts `… N characters left out …` between them, N counting code points, so the reader sees how a command starts and how its error ends; decided with the user on 2026-11-24.
Claude Code caps `additionalContext`, `systemMessage`, and plain output at 10,000 characters and saves a longer one to a file (code.claude.com/docs/en/hooks, read 2026-11-24); the extension does not, because Sentinel's own messages stay far under that cap.
Copilot CLI shows the user none of a session hook's output, and VS Code logs it only in its "GitHub Copilot Chat Hooks" output channel.
VS Code gives the model a session hook's `additionalContext`, so there the check returns the report in that field with a request to tell the user.
Copilot CLI gives the model neither that field nor the hook's plain output, from a session-start hook or from a hook that runs when a prompt is sent, and shows the user none of it, so a Copilot CLI session reports nothing (`evidence/copilot-cli-hook-ask-by-mode.txt`).
A session in another harness reports Copilot CLI's settings.
The README says where the report appears in each harness.
The shell warning names no install path: it reports a `CLAUDE_CODE_SHELL` that is not a bash.

**Rationale:** a harness whose hooks are off runs no check, so only another harness's session can report it.
The values are vendor identifiers, so they are data, with a version, beside the code that reads them.

**Known limits:** when `guarded-paths.toml` fails to load, the check reports that failure and stops, so it reports no harness setting.
Deferred with the user on 2026-11-19 to the change that adds a policy of the user's own, because that change adds a second policy file that can fail to load.

### Decision: TheFloorReportsOnlyWhatDefeatsSentinel

**Chosen:** the session-start check reports a setting only when it stops Sentinel's hooks from running or lets a hook's `ask` be answered without the user.
A value enters the data file only with a probe, the harness's source, or the harness's documentation as evidence.
A mode's name or description is not evidence.
The values the data file starts with:

| Harness             | Value                                                                                                                      | Effect                         | Evidence                                                                                                                    |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Claude Code 2.1.318 | `disableAllHooks` of `true`                                                                                                | hooks off                      | settings reference                                                                                                          |
| Claude Code 2.1.318 | `enabledPlugins` entry for Sentinel of `false`                                                                             | plugin off                     | settings reference                                                                                                          |
| Codex 0.167.0       | `features.hooks = false`, `features.plugins = false`                                                                       | hooks off, plugins off         | source, `features/src/lib.rs`                                                                                               |
| Codex 0.167.0       | `[plugins."<plugin>@<marketplace>"] enabled = false` for Sentinel, `[plugins._default] enabled = false`                    | plugin off                     | source, `PluginConfig`                                                                                                      |
| Codex 0.167.0       | `[hooks.state."<key>"] enabled = false` for a hook Sentinel registered                                                     | one hook off                   | source, `config/src/hook_config.rs`                                                                                         |
| Copilot CLI 1.0.108 | `disableAllHooks` of `true`, `enabledPlugins` entry for Sentinel of `false`                                                | hooks off, plugin off          | configuration reference                                                                                                     |
| Copilot CLI 1.0.108 | `defaultPermissionMode` of `assisted`, or unset                                                                            | a model answers a hook's `ask` | probe, `evidence/copilot-cli-hook-ask-by-mode.txt`; the reference says an unset mode "can start in manual or assisted mode" |
| VS Code 1.145.2     | `chat.useHooks` of `false`, `chat.plugins.enabled` of `false`, `chat.plugins.enabledPlugins` entry for Sentinel of `false` | hooks off, plugin off          | setting declarations in the build                                                                                           |
| Pi 1.4.0            | a `packages` entry for Sentinel whose `extensions` list is empty or holds a path with a `-` prefix                         | extension unloaded             | probe, `evidence/pi-extension-switched-off.txt`; Pi's `docs/packages.md` for the empty list                                 |

Added on 2026-11-20, after the third verify run found them missing:

| Harness             | Value                                                                                                            | Effect                                      | Evidence                                                           |
| ------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------ |
| Claude Code 2.1.323 | `allowManagedHooksOnly` of `true` in managed settings                                                            | hooks off unless force-enabled              | settings reference                                                 |
| Copilot CLI 1.0.114 | `allowManagedHooksOnly` of `true` in managed settings                                                            | hooks off unless required by managed policy | configuration directory reference                                  |
| VS Code 1.146.0     | `allowManagedHooksOnly` of `true` in Copilot's managed settings files (the `chat.hooks.allowManagedOnly` policy) | hooks off unless force-enabled              | the policy's declaration, and the code that reads it, in the build |

In all three harnesses, the hooks of a plugin that managed settings force-enable keep running.
The report therefore says that Sentinel's hooks stop unless managed settings force-enable Sentinel.

VS Code reads the key from Copilot's managed settings files: `/Library/Application Support/GitHubCopilot/managed-settings.json` on macOS and `/etc/github-copilot/managed-settings.json` on Linux.
A value in one of those files is reported twice, once for Copilot CLI and once for VS Code.
Both harnesses can also take the policy from native MDM or from GitHub's server, and the check reads neither.

OPEN QUESTION: does VS Code honor `chat.hooks.allowManagedOnly` in a user `settings.json`?
The setting is application-scoped and does not appear in the Settings editor, and no probe has tested it.

Probes showed that a hook's `ask` reaches the user, or is refused, in each of these modes, so the check reports none of them: Claude Code's manual, `auto`, and `bypassPermissions`; Copilot CLI's `allow-all` and `autopilot`; and VS Code's default approvals, allow all, and autopilot (`evidence/vscode-hook-ask-by-mode.txt`).
VS Code's assisted approvals are not in the data file: the account the probe ran on does not offer them.
A Codex profile file, `<name>.config.toml`, applies only when the user selects it, so the check judges each one over the other files and names the file.
A file nested too deeply for its parser is unreadable, as a file that does not parse is, so the rest of the report still reaches the user; every file Sentinel parses, its own records and the Codex hook file included, is read that way; decided with the user on 2026-11-25.
Every JSON reader in Sentinel, in the hooks, the Codex installer, the Pi dispatcher, and the Pi extension, applies one rule: text that is not valid UTF-8, holds `NaN` or `Infinity`, holds a number outside the range of a double, or is nested too deeply does not parse.
A file that fails the rule is reported as unreadable, and hook input or a hook's reply that fails it takes the path of one that does not parse; decided with the user on 2026-11-26, after a verify run found the Codex installer writing `Infinity` back into a file Codex rejects and the Pi extension reading a registration that was not UTF-8.
A strict reader rejects each such value, so Sentinel judges no value its harness may not read; the cost is that a settings file holding `1e400`, which Claude Code, VS Code, and Pi read as infinity, is reported as unreadable.
The Pi dispatcher, which decodes the replies of Sentinel's Python hooks inside one process, refuses a call whose reply begins as a JSON object and does not parse, as the extension does, so both decoders keep `AHookThatCannotAnswerBeforeAToolCallRefusesIt`; decided with the user on 2026-11-27.
The session check names a Codex hook file that it cannot read when a hook state switches off a hook in that file, because the hook may be one Sentinel registered; decided with the user on 2026-11-27.
The Copilot adapter passes a payload that does not parse to the hook unchanged, and each hook keeps its own answer for such a payload, so Copilot gets the answer every other harness gets; decided with the user on 2026-11-27, in place of refusing at the adapter, which would make Copilot refuse where three hooks only warn.
A repeated key is outside the rule: the Codex installer and the Pi extension report a hook file that repeats one, because the rewrite or the read would lose one copy's hooks, and the settings readers take the last value, as the harnesses do.
A report on an unset setting names the user settings file it is missing from, the value the harness can then start with, and the value to set there, `set-to`; where more than one value has the effect, it says the harness can start with a value that has it.
A setting that takes the unset one's place, `unset-unless`, counts only in the file scopes `unset-unless-scopes` names, because Copilot CLI lets a managed `permissions.defaultMode` override `defaultPermissionMode` and no other file; decided with the user on 2026-11-24.
The check does not read these, and reports nothing from them:

- Copilot's managed preferences that device management delivers, the `com.github.copilot` domain on macOS; it reads the managed settings file.
  No example of those preferences was found: a computer whose organization applies a Copilot policy held neither the file nor the preferences.
- Copilot settings that GitHub's servers deliver, which that computer's policy uses and which are in no file the check can read.
- A Pi `extensions` filter that excludes by pattern, written with a `!` prefix.

**Rationale:** Sentinel is installed into configurations it does not own.
A report on a user's permission mode, sandbox, or network settings appears in every session of a typical setup, and a report that always appears is ignored, including the one that says the hooks are off.
Two inferences from a mode's description were wrong: `bypassPermissions` and `allow-all` both show the user a hook's `ask`.
The requirement therefore names effects, and the data file names values with their evidence.

**Alternatives considered:**

- Report every value that weakens a harness's permission layer or sandbox: that judges settings Sentinel does not own, and each harness renames and adds such settings often.
- Name each reported value in the requirement: every refresh of the data file would then change a requirement.

A configuration audit the user runs on request is a later change.
It inherits what this check leaves out: sandbox state and its escape settings, Codex's `danger-full-access`, the permission modes above, VS Code's terminal, edit, and URL approvals, the comparison of each harness's allowed hosts, and Claude Code mods, which its documentation says can approve a call a hook refused.
A second later change can make a hook refuse where the settings select a mode that answers its `ask`.

Decided with the user.

### Decision: AMaintainerSkillKeepsTheFloorCurrent

**Chosen:** a repository skill, `refresh-configuration-floor`, checks each harness's current build and documentation for settings that stop the hooks or answer a hook's `ask`, and for changed defaults, and updates `configuration-floor.toml`.
Its directory holds the probes: a hook that answers `ask` for one file, and a script per command-line harness that runs one permission mode against it in a separate home.
A probe needs a signed-in harness, and an interactive one needs a person, so the skill runs them and no test does.
It lives in `.agents/skills/`, and `.claude/skills/` holds a relative link to it.
The plugin does not ship it.
It replaces `assess-agent-configuration`, which assessed a configuration repository's agent settings.

**Rationale:** the capability test now checks each registration, and the session-start check reports the values that defeat the hooks, so each check the assessment made runs in one of them or waits for the configuration audit.
The exception is its review of extension and adapter source for a rule of their own, which moves to source review of the same code (`cross-agent-capability-parity` `ExtensionCarriesItsOwnRule`); decided with the user on 2026-11-17.
A vendor default that becomes unsafe is reported only after the floor records it, and a person makes that record by reading each harness's new builds and documentation.
Codex reads project skills from `.agents/skills/`, and Claude Code reads only `.claude/skills/`, so one copy with a link serves both.
A relative link works in every clone.

**Alternatives considered:**

- Keep the assessment: every check it makes now belongs to a test or to the session-start report.
- Ship the skill in the plugin: it maintains this repository, not a user's session.

Decided with the user.

### Decision: TheUsersSandboxIsNotARequirement

**Chosen:** `guarded-path-declarations` `ConfigurationSurfacesCoverTheDeclarations` is removed.
`sensitive-path-blocking` `BashReadBestEffort` says the user configures the sandbox and the egress allowlist that stop the read forms the hooks cannot see, and that Sentinel neither sets nor checks them.

**Rationale:** the requirement held each agent's permission lists and OS sandbox to refuse the block class.
`assess-agent-configuration` judged it against the repository that generated that configuration, and this change replaces that skill.
A standalone plugin neither sets nor reads those surfaces, so the requirement would stay in the specs with nothing to make it true or to check it.
`BashReadBestEffort` cited it as the reason the read forms the hooks cannot see are safe; it now states the gap.

**Alternatives considered:**

- Keep it as a requirement: the specs would claim a protection that holds only for a user who configured a sandbox.
- Keep it as advice to the user: advice belongs in the user documentation, not in a requirement.

The configuration audit, a later change, can judge a user's own configuration against the block class.
Decided with the user on 2026-11-23.

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

### Decision: TheCodexInstallerKeepsTheUsersHooks

**Chosen:** `plugin-distribution` `CodexHookInstallKeepsTheUsersHooks` states what the installer preserves: the user's own entries through install and uninstall, and an unreadable hook file unchanged.
How it finds Sentinel's entries, and the missing-file guard on each entry, stay in `CodexHooksComeFromAnInstaller`.
Decided with the user on 2026-11-17.

**Rationale:** the installer writes into a file the user owns, so a defect in it can delete hooks the user wrote; a requirement lets verification report that as noncompliance.
`EachSupportedHarnessInstallsSentinel` is unchanged, and the installer stays known noncompliance with it.

**Alternatives considered:**

- Keep the installer in design only: a change that drops the user's hooks fails a test but is not a spec violation.

A linked hook file is written at the file the link ends at, by the same write-and-rename, and the written file keeps its permissions; decided with the user on 2026-11-23.
Writing in place follows a link too, but an interrupted write leaves a file Codex cannot parse, and Codex then runs no hook at all.
The rename's temporary file gets a new hidden name of its own beside the file the link ends at, which can be inside the user's dotfile repository, and the installer removes it however the write ends; only a run killed outright leaves it there.
A fixed name would follow or replace a file already at that name.
The temporary file starts owner-only, so a file the installer creates is set to the umask's mode, as a plain write gave it before.
The written file keeps the permission bits of the file it replaces, and the owner, group, access control lists, and extended attributes are not carried over, because the permission bits decide who can read and write the file, and carrying the rest over needs calls that differ by platform and, for another owner, privileges the installer does not have; decided with the user on 2026-11-24.
A run whose result equals the file writes nothing, so `--uninstall` succeeds on a read-only file that holds no Sentinel entry, and an uninstall with no hook file creates none.
An event list the user left empty is kept, because removing Sentinel's entries must not change anything else in the file.
An install compares Sentinel's hook definitions, not their place in each event's list, the order of their groups, or the order of the hooks within a group, with what it would write; when they match it leaves the file alone, because removing and re-adding them would move them to the end and change the order the user's hooks run in; decided with the user on 2026-11-24.
A read-only hook file is refused even where its directory allows the rename, and a hook file that names a key twice in an object is refused, because the rewrite would keep only one copy.

**Known limits:** when Codex loads hooks from an Agent Plugins manifest and the installer is removed, this requirement is removed with it.

### Decision: TheShippedManifestDeclaresNoUsersOwnFiles

**Chosen:** the block class Sentinel ships declares only files a harness itself writes.
The file of one user's own configuration leaves the manifest, and the specs and tests that named it use a file the manifest still declares or a made-up name.
Decided with the user on 2026-11-18.

**Rationale:** the plugin is installed by users whose machines hold no such file, so the entry protects nothing for them and publishes the name of a file on one machine.
`SecretMaterialIsDeclaredRatherThanRecognized` still holds: a user declares such a file in a policy of their own, which a later change adds.

**Known limits:** until that change lands, the plugin does not protect the removed file; the user's own configuration protects it.

### Decision: EachCopyGatesOnlyItsOwnDirectory

**Chosen:** `plugin-distribution` `ThePluginIsSelfContained` holds a copy outside a checkout to the checkout's decisions except on a write to the running plugin directory or the Pi extensions its repository names.
The running copy gates those writes for itself.
It does not gate a checkout it does not run from, as `OnlyPluginInstallsAreCovered` records.
Decided with the user on 2026-11-18.

**Rationale:** the requirement exists so that no hook depends on a file an installed copy lacks.
Which directory the running hooks protect follows from `TheRunningPluginDirectoryIsInTheFloor` and `ThePiHookRunnerIsHostRuntime`: an agent cannot edit the code that guards its session, and a maintainer running an installed copy edits a checkout without a prompt on each write.
A user has no checkout, so the exception changes nothing for them.

**Alternatives considered:**

- Every copy gates every checkout's plugin directory: a maintainer is prompted on each source edit while running an installed copy, and users gain nothing.

### Decision: OneVersionIsCheckedNotGenerated

**Chosen:** each manifest, `package.json`, and catalog entry carries the version as a literal.
A conformance test fails when they differ.

**Rationale:** four files with one field each is less machinery than a generator, and the test catches every drift the generator would prevent.

### Decision: ThePluginAndThePiExtensionAreReleasedSeparately

**Chosen:** the plugin and the Pi extension each have a version, a Keep a Changelog file, and an annotated tag prefix.
The plugin version is in each plugin manifest, the root `package.json`, and each catalog's Sentinel entry, and `CHANGELOG.md` and `plugin-v<X.Y.Z>` tags record it.
The extension version is in its own manifest, `extensions/pi/package.json`, and `extensions/pi/CHANGELOG.md` and `pi-v<X.Y.Z>` tags record it.
`scripts/release.sh`, run through `just release-plugin` or `just release-pi`, sets the version, promotes `[Unreleased]`, commits, and tags.
Changelog entries are written by hand with the `changelog` skill, as `AGENTS.md` directs.

**Rationale:** the root `package.json` is the manifest Pi reads for the whole package, which runs the plugin's hooks, so it carries the plugin version, and every harness reports one plugin version.
The extension is a separate component, the runner inside that package, and its own manifest gives its version a place a reader can find.
The repository has no Python package, so `uv-ship` and `pyproject.toml` versioning do not apply.
Commit subjects name mechanisms, and changelog entries describe what a user notices, so generated entries would be rewritten anyway.
An extension release does not change the plugin version.
If `pi update` compares the root `package.json` version before it pulls, an extension-only release reaches Pi users with the next plugin release; this is unverified, and the user accepted it to keep the two versions independent.

**Alternatives considered:**

- One version for the plugin and the extension: an extension-only change would bump every harness's plugin version.
- The root `package.json` carries the extension version: Pi users would see the runner's version and not the plugin version they run.
- The extension version only in its changelog and tags: no manifest would name the extension's version.
- Entries generated from commits with `git-cliff`: see the rationale.

Decided with the user.

### Decision: UserDocumentationIsAGreatDocsSite

**Chosen:** the user documentation is a great-docs site whose home page is `README.md`, with one guide page in `user_guide/` for each task a user does and a limits page.
A GitHub Actions workflow builds it and publishes it to GitHub Pages at `https://ahgraber.github.io/sentinel-hooks/`.
The README carries the categories of action, the posture on refusal, the prerequisites, and one install table, and links to the guide pages for detail.

**Rationale:** each harness installs Sentinel differently, Codex needs an extra step, and the session-start report appears in a different place in each harness, so a user needs more than a README can hold without hiding the install steps.
great-docs builds a site from a README and guide pages alone, so the site needs no Python package.

**Alternatives considered:**

- README only: the per-harness install, update, and removal steps and the finding-by-finding report guide push the install table far down the page.
- Docs as Markdown files in the repository, with no site: the same pages, but a user reads them only by browsing the repository.

Decided with the user.

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
- **Copilot CLI's tool input is not documented field by field**: a recorded probe shows it sends Claude Code's tool names, `Bash` with `command`, `Read` with an absolute `path`, and its `apply_patch` tool as `Edit` with the patch text as the whole `tool_input`.
  The adapter judges a file tool with a text input as `apply_patch`.
  The file tools depend on the model.
  A GPT model has only `apply_patch`, and creates files with it as `*** Add File:`.
  A Claude model has `create` and `edit`, sent as `Write` with `path` and `file_text` and as `Edit` with `path`, `old_str`, and `new_str`.
- **A session-start report may not reach the user**: each harness shows a session hook's output differently.
  Claude Code and Codex show the `systemMessage` field.
  The extension that runs Pi's hooks shows it too.
  VS Code logs a session hook's output only in its "GitHub Copilot Chat Hooks" output channel, and Copilot CLI shows none of it (`evidence/vscode-hook-ask-by-mode.txt`, `evidence/copilot-cli-hook-ask-by-mode.txt`).
  A report the model is asked to pass on reaches the user only when the model does so.
  A session in Claude Code, Codex, or Pi reports every harness's settings, so the report reaches a user who runs one of them.
  The install evidence records where each harness shows it.
- **A harness home moved by an environment variable is not declared**: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `VSCODE_AGENT_PLUGINS` move a harness's home and install location, and the manifest declares only the default paths.
  OPEN QUESTION: the manifest's home paths should probably honor these variables; a later change decides how, because the change touches every home declaration.
  `scripts/isolated-harness.sh` sets them to run a harness in `tmp/homes/`, where payload capture works but the floor does not cover the install.
- **Removing a directory above a found plugin location does not ask**: `rm -rf plugins` in a checkout loaded in place, or above a link target, is not an ancestor removal.
  The found location itself stays in the floor; a marketplace install sits under a declared location and is not affected.
- **A program name the command text hides**: `$X plugin disable` names no program the gate can find, so it passes the plugin command gate; the path gates still judge it.
- **A variable the command text does not set**: `source ./env.sh; claude` sets `CLAUDE_CODE_SIMPLE` in a file the session check does not read.
- **A checkout loaded in place**: the floor covers it only as the running copy, so another session can write it; `OnlyPluginInstallsAreCovered` records the decision.
- **VS Code's install from a local folder**: whether it copies the folder or loads it in place is not documented; task 4.6 records it.
- **A harness changes its install layout**: a skill directory the globs miss asks before each run, and the floor declarations are at the install root, so protection holds.
- **Codex trust**: a fresh install or an update runs no Sentinel hook until the user trusts it in `/hooks`.
  Sentinel cannot detect this from inside Codex, because its own session check is one of the hooks that does not run.
- **The active changes name `modules/home/ai/` paths**: the path rewrite updates them.
  A missed path makes that change's tasks name a file that does not exist, which its apply step detects.

## Spec Changes

- `plugin-distribution` `EachHarnessRunsOnlyItsOwnRegistration` rationale: Copilot in VS Code and Copilot CLI share one event vocabulary; the claim of one tool vocabulary is removed.
  The registration names no tools, so one registration still serves both.
  Source: the recorded Copilot CLI payloads.
  **Approved by:** user **Recorded:** 2026-11-12
- `plugin-distribution` `ReinstallKeepsTheOrderOfTheHooks`: the GIVEN adds Sentinel's hooks standing in another order than the installer writes them, within an event and within a group, so the scenario checks the order among Sentinel's own hooks as the requirement states it.
  **Approved by:** user **Recorded:** 2026-11-25
- `secret-access-blocking` `StoreReadWithAnOptionBeforeItsSubcommand`: a new scenario for a store read whose subcommand follows one of its options, which the requirement now refuses.
  **Approved by:** user **Recorded:** 2026-11-25
- `agent-configuration-floor` `HookSwitchedOffInAHookFileThatCannotBeRead`: a new scenario for a switch that turns off a hook in a Codex hook file that does not parse, which the requirement now reports.
  **Approved by:** user **Recorded:** 2026-11-27
- `hook-execution` `ReplyWithANumberOutsideTheRangeOfADouble`: a new scenario in a MODIFIED copy of the baseline requirement, for a reply that the parse rule now rejects.
  **Approved by:** user **Recorded:** 2026-11-27
- `guarded-path-declarations` `GuardedDeclarationInsideAPluginSkillDirectory`: a new scenario for a guarded declaration closer to a plugin skill script than the declaration that opens the plugin's `skills/` directory.
  **Approved by:** user **Recorded:** 2026-11-27
- `cross-agent-capability-parity` `PayloadThatDoesNotParseReachesTheHook`: a new scenario in a MODIFIED copy of the baseline requirement, for a payload an adapter cannot parse.
  **Approved by:** user **Recorded:** 2026-11-27

## Dropped Scenarios

- `guarded-path-declarations` `CarveOutOverAHookSource`: no hook resolves to a repository source once each harness runs an installed copy; `CarveOutOverAnInstalledCopy` covers the same grant over the copy a harness runs.
- `sensitive-path-blocking` `GuardrailSourceNamedForWhatItBlocks`: Sentinel's file names do not match a name-based pattern (`NoSentinelFileMatchesANamePattern`), so Sentinel's files do not need an exemption.
- `hook-registration` `EventNameDiffersOnlyInCase`: an event name in another case now registers that event's hooks (`EventNamesAndHandlerTypesIgnoreCase`); `EventNameInAnotherCase` states the new outcome.
- `hook-registration` `ToolCallsProceed`: with two registration files, an unusable file no longer means that no hook runs; `UnusableUserFileLeavesThePackageHooks` and `UnusablePackageFileLeavesTheUserHooks` state what runs.
- `agent-configuration-floor` `AuthorizedGuardrailEdit` and `UnauthorizedGuardrailEdit`: they bound a harness's own review surface, which is that harness's configuration and which Sentinel neither sets nor can judge.

## Known Noncompliance

- **Requirement:** `plugin-distribution` `EachSupportedHarnessInstallsSentinel`, scenario `CodexInstall` **Reason:** Codex skips the hooks of any plugin whose root manifest is an Agent Plugins manifest (openai/codex#39895, #47925, #59516), so Codex needs a step outside its own install mechanism: `harnesses/codex/install-hooks.py`.
  A Codex user who skips the installer runs every Codex session without Sentinel's hooks, and without any warning.
  **Exit condition:** when a Codex release loads `extensions.com.openai.hooks` from an Agent Plugins manifest, delete the installer and its tests, return the README's Codex row to the plugin install alone, and tell installed users to run `install-hooks.py --uninstall` so each hook does not run twice.
  **Approved by:** user, as `proposal.md` records on 2026-11-05 ("Codex install: the plugin ships a hook installer") **Recorded:** 2026-11-05
- **Requirement:** `agent-configuration-floor` `SettingsThatDefeatTheHooksAreReported`, for a session in Copilot CLI **Reason:** Copilot CLI does not show a session hook's output to the user, and does not pass it to the model, from a session-start hook or from a hook that runs when a prompt is sent (`evidence/copilot-cli-hook-ask-by-mode.txt`).
  A Copilot CLI session therefore does not report anything; a session in Claude Code, Codex, or Pi reports Copilot CLI's settings.
  **Exit condition:** when a Copilot CLI release shows a session hook's output to the user or passes it to the model, return the report by that route and delete this entry.
  **Approved by:** user **Recorded:** 2026-11-13
- **Requirement:** `agent-configuration-floor` `SettingsThatDefeatTheHooksAreReported`, when `guarded-paths.toml` fails to load **Reason:** `session-policy-checks.py` reports the load failure and then stops, before it reads any harness setting.
  A session whose `guarded-paths.toml` does not load therefore reports no setting that turns the hooks off (`TheSessionCheckReadsAllHarnessSettings` Known limits).
  **Exit condition:** the check reports each harness setting even when a policy file fails to load.
  The change that adds a policy of the user's own makes that fix, because it adds a second policy file that can fail to load; then delete this entry.
  **Approved by:** user, deferred on 2026-11-19 ("defer it; i think it could be included in the user-policy scope") **Recorded:** 2026-11-20

## Verification Waivers

- **Requirement:** `plugin-distribution` `EachSupportedHarnessInstallsSentinel` **Reason:** each scenario needs the harness's own install command against a published repository, and Codex, VS Code, Copilot CLI, and Pi need a signed-in session; the test suite checks the manifests and catalogs statically.
  **Manual evidence:** `evidence/install-claude.txt`, `evidence/install-codex.txt`, `evidence/install-vscode.txt`, `evidence/install-copilot-cli.txt`, and `evidence/install-pi.txt` in this change directory, captured during apply.
  **Recorded:** 2026-11-01
- **Requirement:** `plugin-distribution` `EachHarnessRunsOnlyItsOwnRegistration` **Reason:** which registration a harness loads is decided inside the harness; the test suite checks that no default registration file exists and that each manifest names its own file.
  **Manual evidence:** in each `evidence/install-<harness>.txt`, the `/hooks` listing in Claude Code and Codex; in VS Code, Copilot CLI, and Pi, which have no listing command, the decision a Sentinel hook returns on a tool call that only its own registration matches.
  **Recorded:** 2026-11-01
- **Requirement:** `hook-registration` `RegistrationsAreReadFromThePackageAndTheAgentDirectory`, `hook-execution` `PackageHooksAreGivenThePackageDirectory`, and `cross-agent-capability-parity` `EveryAgentImplementsEveryCapability`, for the two directories the Pi entry point, `extensions/pi/index.ts`, passes to the hook runner **Reason:** Pi's `getAgentDir` decides the agent directory inside Pi, and the entry point loads Pi's package, which the test suite runs without; the tests pass both directories in and test the plugin directory the extension finds.
  **Manual evidence:** `evidence/install-pi.txt`: the install run, where a hook from the package's `harnesses/pi/hooks.json`, whose commands start through `${PLUGIN_ROOT}`, refuses `sudo -n true` with no agent-directory hooks present, and "Hooks from the agent directory".
  **Approved by:** user **Recorded:** 2026-11-13
- **Requirement:** `cross-agent-capability-parity` `EveryAgentImplementsEveryCapability`, the clause that an extension holding its own pattern, path list, or rule for which tool calls proceed SHALL NOT be written, scenario `ExtensionCarriesItsOwnRule` **Reason:** a test checks only the calls it sends, so it cannot show that the extension has no rule for some other call.
  The scenario is a source review, as decided with the user on 2026-11-17 (`AMaintainerSkillKeepsTheFloorCurrent`).
  The test "with no hooks registered, every tool call proceeds", in `tests/pi/extension.test.mjs`, sends five calls that Sentinel's hooks refuse and checks that the extension lets each one proceed.
  It fails when the extension refuses `sudo` by a rule of its own.
  **Manual evidence:** on 2026-11-27, a search of the nine files `extensions/pi/*.ts` for `block: true`, regular expressions, string tests, and known paths and commands found nine lines, and none is a rule for which calls proceed.
  Lines 192, 194, and 197 of `extension.ts` return a block only from the decision that `run` combines from the hooks' answers.
  Line 61 of `decode.ts` checks whether a hook's output is JSON.
  Lines 25, 38, and 45 of `matcher.ts` compile and apply the matcher a registration supplies.
  Line 72 of `registration.ts` finds a repeated key in a registration file.
  Line 73 of `runner.ts` sets the environment a hook runs in, and matches the search only because of the text `.env`.
  `json.ts` has no matching line.
  **Recorded:** 2026-11-27

## Verification Overrides

- **Finding:** CRITICAL failing test `tests/shared/test_capability_coverage.py::test_every_capability_has_a_kind_and_existing_package_artifact` (`capabilities have no recorded kind: ['end-of-turn-precommit']`).
  **Stage:** verify **Reason:** the baseline `.specs/specs/end-of-turn-precommit/` still exists, and only `sdd-sync` deletes it; this change removes the capability from the kind record (task 2.5), and task 3.10 recorded the failure as expected.
  **Constraints:** no other test may fail; the test is not changed, skipped, or marked `xfail`; the verify run is diagnostic only and is not a clean pass; `sdd-sync` may proceed under this override only.
  **Follow-up task:** tasks.md 14.4 "After `sdd-sync` removes the `end-of-turn-precommit` requirements, delete the emptied `.specs/specs/end-of-turn-precommit/` directory, then run the full test suite and confirm that `tests/shared/test_capability_coverage.py::test_every_capability_has_a_kind_and_existing_package_artifact` passes."
  **Approved by:** user **Recorded:** 2026-11-12
