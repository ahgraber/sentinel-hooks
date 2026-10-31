# Proposal: recursive-credential-read-refusal

## Intent

A recursive read of a directory prints every file beneath it, and the hooks judge only the directory the command names.
`grep -r x ~` and `grep -r x ~/.codex` each print `~/.codex/auth.json`, and every other file the manifest's block class declares, with no refusal from any hook.
The read property added in `security-posture-alignment` found this on its first run.

That change records the gap as a `BashReadBestEffort` limit, with the OS sandbox floor as the boundary.
This change closes the part of the gap the hooks can see: a known recursive reader, rooted at a directory that holds a declared credential.

## User Stories

- **a-declared-credential-is-not-read-by-its-parent** — As the operator of four agents, I want a recursive read that would reach a declared credential to be refused, so that the hooks hold the block class against a read that does not name the file, and not only the sandbox.
  (North star: "layers are independent"; each layer covers the others' blind spots, and none is trusted to be the only one.)
- **a-refused-search-says-what-would-work** — As the operator of an agent whose search was refused, I want the refusal to say why the directory is protected and how to search without reaching the credential, so that the agent completes the search and does not stop or work around the refusal.
  (North star: "response matches risk"; a search that does not reach the credential is ordinary work, and it should proceed.)

## Scope

**In scope:**

- `sensitive-path-blocking`: refuse a recursive read rooted at a directory that holds an existing block-class file, and narrow the recursive-read limit in `BashReadBestEffort` to what the refusal does not cover.
- `hook-interface`: let a refusal that names an accepted alternative state its own cause, so the search refusal can use the form that lists what works.
- A recursive-reader table shared by the hooks, beside the tamper hook's operand table.
- Verdict cases, and recursive forms added to the read property's command catalog.

**Out of scope:**

- A secret only the name rules recognize, such as a `.env` file beneath the root.
  Finding one needs a walk of the tree.
- A reader's own include and exclude flags (`--exclude-dir`, `--glob`, `find -name`).
  A root above a declared credential is refused whatever the flags select.
- A recursive reader missing from the table.
  The read property is the check that the table is complete.
- A copy now and a read in a later call.

## Approach

- One table maps each recursive reader to the condition that makes it recursive and to the roots it reads: `grep -r`, `rg`, `ag`, `find` with `-exec` running a known reader, `tar -c`, `cp -r`, `scp -r`, `rsync -r`, `zip -r`, and `ditto`.
  A reader with no root operand reads the current directory.
- The reader is identified with the shared helpers `credential-store-handoff` added, so a wrapper does not hide it: `bash_commands.invoked` for the program past `sudo`, `env`, `command`, and the rest, and `bash_commands.launched_arguments` for the command `find -exec` or `xargs` runs.
- Roots resolve against every directory the reader may run in, using the `cd` tracking `security-posture-alignment` moves into `shell_words`.
- A root is refused when a block-class declaration lies at or beneath it, whether or not the file exists yet, comparing every spelling of both paths.
- `rg` and `ag` are judged like `grep -r`, so `rg foo ~` is refused: a glob or an ignore-file whitelist makes them open hidden entries, and the hook cannot see every ignore file.
  A name-listing mode such as `rg --files` is not a recursive read.
- The refusal has no prompt, as for every block-class read.
  Its message names the credential beneath the root, says reading or copying it could expose credentials, tells the agent to search again only with roots that hold no declared credential, and forbids reaching the credential by another route.

## Dependencies

- `security-posture-alignment` adds the recursive-read limit to `BashReadBestEffort` and moves `cd` tracking into `shell_words`; this change narrows that limit and uses that tracking.
  Apply it after that change is synced.
- `credential-store-handoff` adds `bash_commands.invoked` and `launched_arguments`; apply this change after it.

## Open Questions

- Whether to declare `~/.config/op/` and `~/.kube/` in the manifest's `[block]` class.
  Every agent's sandbox denies both, but the manifest names neither, so this change would not refuse `grep -r x ~` for them, and the configuration assessment does not hold the surfaces to them.
  `credential-store-handoff` left the declaration for a separate decision because it changes what `block-sensitive-paths` refuses and requires entries on every surface.
  This change is where the declaration first pays off.
