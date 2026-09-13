# Design: skill-script-exec-through

## Context

The tamper hook's Bash branch already classifies before it gates.
The read-through carve-out, added on 2026-09-02, splits a command into pipeline segments and asks whether every segment runs a utility that can neither write nor execute.
That machinery is where the run form belongs; a second classifier over the same command would give two answers to one question.

The classifier is defense in depth, not the boundary.
The OS sandbox and each agent's permission list gate writes to these paths regardless, and neither reads the manifest.
A run this hook permits is still subject to both.

The Pi security extension reads the manifest but implements neither carve-out, so it keeps gating skill reads and runs.
That divergence predates this change; the manifest tables it does not read are inert to it.

## Decisions

### Decision: SeparateExecThroughTable

**Chosen:** a second manifest table, `[exec-through]`, listing the same three skills roots as `[read-through]`.

**Rationale:** running a file held in a location is a wider grant than reading one, and the two lists will not stay identical.
Declaring them separately makes the wider grant an explicit act.

**Alternatives considered:**

- Widen `[read-through]` to mean read-and-run: every location a later change declares readable becomes runnable in the same edit, silently.
- Derive exec-through from the gated classes: the manifest would then carry no record of the decision, which is what `carve-outs-are-specified` exists to prevent.

### Decision: RecognizeTwoRunForms

**Chosen:** the script is the command itself, or the file argument to a named interpreter (`bash`, `sh`, `zsh`, `python`, `python3`, `uv`, `uvx`, `node`, `deno`, `ruby`, `perl`, `Rscript`).

**Rationale:** both forms appear in skill instructions.
An executable script is called directly; a `.py` under `uv run` and a `.cjs` under `node` are not.

**Alternatives considered:**

- Direct invocation only: `uv run <skill>/scripts/x.py` is the common form in installed skills, so this would leave the reported problem in place.
- Any command naming an exec-through path: `cp /tmp/x.py <skill>/scripts/x.py` names one too, and that is a write.

### Decision: ExistenceAndProgramShape

**Chosen:** the named file must exist after path resolution, and must carry the execute bit or a script suffix.

**Rationale:** a path the run would create is a write, so existence separates the two.
The execute bit alone misses `node server.cjs`, which ships without one; a suffix alone misses an extensionless script.
Requiring either keeps `uv run <skill>/SKILL.md` gated, which is a real entry in the test suite's rejected set.

**Alternatives considered:**

- Suffix only: rejects extensionless scripts that skills do ship.
- No shape test: any existing file under a skills directory becomes a run target, which makes the carve-out about location alone.

### Decision: InlineCodeOptionsDisqualify

**Chosen:** a segment carrying `-c`, `--command`, `-e`, `--eval`, or `--exec` is not a run, whatever else it names.

**Rationale:** these make the interpreter execute text from the command line.
A path matched beside one is a string the interpreter never opens, so recognizing the segment would grant the carve-out to arbitrary program text.

**Alternatives considered:**

- Parse the quoted program text and classify it too: a second shell parser inside the classifier, with the quoting bugs that implies.

### Decision: SubstitutedHomeInTests

**Chosen:** the run cases build a skills tree under a temporary home and pass it to the hook through `HOME`.

**Rationale:** existence is part of the contract, so the cases need files on disk.
Reading the running user's installed skills would make the suite pass or fail on what happens to be installed, and the `nix flake check` sandbox has no such home at all.

**Alternatives considered:**

- Point at the repository's own files: no skills directory exists inside the repo, and inventing one would guard a path nothing deploys.

## Architecture

```text
Bash tool call
  |
  v
command_protected_class(command) -----> not GATED ------> exit 0
  |
  GATED
  v
only_carved_out(command)  --- no ----> gate with the enforcement reason
  |
  yes
  v
is_read_only_command(command)  --- yes ---> exit 0
  |                                          ^
  no                                         |
  v                                          |
runs_exec_through_script(command) -- yes ----+
  |
  no
  v
gate with the unrecognized-form reason
```

`_segments` splits the command once; `is_read_only_command` and `runs_exec_through_script` both read that split.
A run command may carry recognized reads in its other segments, so `<skill>/scripts/x.sh | head -5` passes and `<skill>/scripts/x.sh; rm ...` does not.

## Risks

- **A skill script does whatever it does.**
  The hook judges the invocation.
  Mitigation: writes to skill content stay gated on every tool, so the script being run is one the user installed, and the sandbox and permission layers still gate what it touches.
- **The interpreter list goes stale.**
  A skill shipping a `.php` or `.lua` helper gates until the list grows.
  Mitigation: accepted — the failure is a prompt, not a refusal, and the prompt names the interpreters that would have proceeded.
- **`_exec_through_script` touches the filesystem on every Bash call that names a guarded path.**
  Mitigation: it runs only after `EXEC_THROUGH.contains` narrows the token set, and `os.path.isfile` on a resolved path is one `stat`.
