# Spec: destructive-ops-blocking

## Purpose

Some shell commands destroy work that cannot be recovered, and whether to run one is the user's decision, not the agent's.
These requirements cover which calls the rules judge, where the rules are declared and how they load, the outcome each rule gives, and how commands are matched.

## Requirements

### Requirement: ToolScope

The system SHALL only evaluate commands when `tool_name` is `Bash`.

### Requirement: ExternalPatternFile

The system SHALL load rules from an external pattern file co-located with the hook.
Each rule SHALL contain at minimum:

- a regex pattern
- a `description` — plain-language explanation of what the matched operation does and its effect
- a `reason` — why it is blocked or flagged (the safety or security concern)
- a `mode` — `block` or `ask`

The `description` and `reason` fields are used together to construct the `ExplanationContract` message shown to the user (see `hook-interface`).
Rules SHOULD be grouped by category (e.g., git, filesystem, cloud, database).
The pattern file format is TOML.

The system SHALL use the pattern file only when every rule in it is valid.
A rule is invalid when it lacks one of the four fields, names a mode other than `block` or `ask`, or holds a pattern that does not compile.
When the file is missing, cannot be read or parsed, or holds an invalid rule, the hook SHALL reach `Ask` on every `Bash` call, as `hook-interface` `ErrorHandlingByDamagePotential` allows for a fault that recurs on every call.
The reason SHALL name the fault: the file that could not be used, or the invalid rule.
The system SHALL NOT judge by the valid remainder of a file that holds an invalid rule, because a rule dropped without notice is a protection removed without notice.

#### Scenario: PatternFileLoaded

- **GIVEN** the hook is invoked
- **WHEN** the pattern file exists, is readable, and every rule in it is valid
- **THEN** all rules from the file are active for the current evaluation

#### Scenario: PatternFileMissing

- **GIVEN** the hook is invoked
- **WHEN** the pattern file does not exist or cannot be read
- **THEN** the hook reaches `Ask`, and the reason names the pattern file

#### Scenario: PatternFileUnparsable

- **GIVEN** the hook is invoked
- **WHEN** the pattern file is not valid TOML
- **THEN** the hook reaches `Ask`, and the reason names the pattern file

#### Scenario: RuleIsInvalid

- **GIVEN** the pattern file holds a rule with `mode = "deny"`, a rule with no `reason`, or a rule whose pattern does not compile
- **WHEN** any `Bash` call is intercepted, whether or not it matches a valid rule
- **THEN** the hook reaches `Ask`, and the reason names the invalid rule

#### Scenario: UnusableFileWhereNoPromptCanBeShown

- **GIVEN** the pattern file cannot be used
- **WHEN** the invoking agent cannot express `Ask` for `Bash`
- **THEN** the hook reaches `Block`

### Requirement: RuleModes

Each rule SHALL declare one of two modes:

**`block`** — the operation is never permitted.
The hook exits 2 with the rule description and no path to proceeding in the current invocation.

**`ask`** — the operation is potentially dangerous and requires explicit user confirmation.
The hook exits 0 and writes a `permissionDecision: "ask"` JSON object to stdout (see `hook-interface`).
Claude Code presents a permission dialog; the user may approve once, always allow, or deny.
If the user selects "always allow", that choice MAY be remembered so the user is not asked again.

#### Scenario: BlockModeMatch

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command matches a `block`-mode rule
- **THEN** the hook exits 2 with a message stating the operation is not permitted

#### Scenario: AskModeMatch

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command matches an `ask`-mode rule
- **THEN** the hook exits 0 and writes ask JSON to stdout; Claude Code shows the user a confirmation dialog

#### Scenario: AskApprovedOnce

- **GIVEN** the user is shown a confirmation dialog for an `ask`-mode rule
- **WHEN** the user selects "approve once"
- **THEN** the tool proceeds for this invocation; the next identical command will prompt again

#### Scenario: AskAlwaysAllow

- **GIVEN** the user is shown a confirmation dialog for an `ask`-mode rule
- **WHEN** the user selects "always allow"
- **THEN** the tool proceeds and the approval MAY be persisted to `settings.json`

#### Scenario: NoMatch

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command matches no rule in the pattern file
- **THEN** the hook exits 0

### Requirement: PatternCategories

The pattern file SHALL define rules covering at minimum the following operations, assigned to the indicated mode:

**Git:**

| Operation                               | Mode  |
| --------------------------------------- | ----- |
| `git filter-branch`, `git filter-repo`  | block |
| `git reflog expire`                     | block |
| Force push without `--force-with-lease` | block |
| `gh repo delete`                        | block |
| Force push with `--force-with-lease`    | ask   |
| `git push --delete`                     | ask   |
| `git reset --hard`                      | ask   |
| `git clean -f` / `-fd` / `-fdx`         | ask   |
| `git stash drop` / `git stash clear`    | ask   |
| `git branch -D`                         | ask   |
| `git checkout .` / `git restore .`      | ask   |
| `git add .` / `git add -A`              | ask   |

**Filesystem:**

| Operation                                                        | Mode  |
| ---------------------------------------------------------------- | ----- |
| `rm -rf` / `rm -fr` targeting home, root, or root-adjacent paths | block |
| `mkfs.*`                                                         | block |
| `dd` writing to a disk device (`of=/dev/sd*`, `of=/dev/hd*`)     | block |
| `chmod 777` on a system path                                     | block |
| `rm -r` (general recursive delete)                               | ask   |
| `chmod -R` / `chown -R`                                          | ask   |
| `history -c`                                                     | ask   |

**Process management:**

| Operation | Mode |
| --------- | ---- |
| `killall` | ask  |
| `pkill`   | ask  |
| `kill -9` | ask  |

**Cloud CLIs:**

| Operation                                       | Mode |
| ----------------------------------------------- | ---- |
| `aws s3 rm --recursive`, `aws s3 sync --delete` | ask  |
| `gcloud` with `delete` or `destroy` subcommands | ask  |
| `firebase` with `delete` or `projects:delete`   | ask  |
| `vercel` with `projects rm` or `remove`         | ask  |
| `netlify` with `sites:delete` or `delete`       | ask  |
| `wrangler` with `delete` or `destroy`           | ask  |
| `heroku apps:destroy`                           | ask  |
| `fly apps destroy`                              | ask  |
| `doctl` with `delete` or `destroy`              | ask  |
| `supabase` with `projects delete` or `db reset` | ask  |

**Infrastructure tools:**

| Operation                                           | Mode  |
| --------------------------------------------------- | ----- |
| `kubectl delete` with `--all` or `--all-namespaces` | block |
| `terraform destroy` / `tofu destroy`                | ask   |
| `pulumi destroy`                                    | ask   |
| `serverless remove` / `sls remove`                  | ask   |
| `sam delete`                                        | ask   |
| `kubectl delete namespace`                          | ask   |
| `docker system prune -a`                            | ask   |
| `docker rm -f` / `docker rmi -f`                    | ask   |
| `docker volume rm` / `docker volume prune`          | ask   |
| `helm uninstall` / `helm delete`                    | ask   |
| `helm install` / `helm upgrade`                     | ask   |

**Databases:**

| Operation                                    | Mode  |
| -------------------------------------------- | ----- |
| Redis `FLUSHALL`, `FLUSHDB`                  | block |
| `redis-cli` with `FLUSH` commands            | block |
| MongoDB `dropDatabase`, `drop()`             | block |
| MongoDB CLI eval with `drop`                 | block |
| `dropdb` (PostgreSQL)                        | block |
| `mysqladmin drop`                            | block |
| `DROP TABLE`, `DROP DATABASE`, `DROP SCHEMA` | block |
| `DELETE FROM <table>` without `WHERE`        | block |
| `TRUNCATE TABLE`                             | ask   |

**Publishing:**

| Operation                                       | Mode |
| ----------------------------------------------- | ---- |
| `npm publish` / `yarn publish` / `pnpm publish` | ask  |
| `npm unpublish`                                 | ask  |
| `docker push`                                   | ask  |
| `uv publish`                                    | ask  |

**Package management:**

| Operation                    | Mode |
| ---------------------------- | ---- |
| `uv remove` / `uv uninstall` | ask  |

**Network access:**

| Operation                                                            | Mode |
| -------------------------------------------------------------------- | ---- |
| `ssh` (direct invocations only, not `ssh-keygen`, `ssh-agent`, etc.) | ask  |
| `scp`                                                                | ask  |
| `rsync`                                                              | ask  |

Note: the `ssh` pattern SHALL match the `ssh` command invocation (followed by whitespace) but SHALL NOT match compound command names like `ssh-keygen`, `ssh-agent`, or `ssh-copy-id`.

The pattern file SHALL NOT include overly broad patterns that match common words in non-command contexts.
A command that mentions `deploy` SHALL NOT match unless it runs a vendor deploy command, such as `firebase deploy` or `vercel deploy`.
A filename, a log message, or documentation that contains the word is not a deployment.

### Requirement: CaseSensitivity

SQL keyword patterns SHALL match case-insensitively.
Shell command patterns SHALL match case-sensitively.
