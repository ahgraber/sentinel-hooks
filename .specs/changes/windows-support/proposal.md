# Proposal: windows-support

Status: stub.
It has no delta specs, design, or tasks.

## Intent

Sentinel runs on macOS and Linux only.
On Windows, a supported agent runs without Sentinel's guardrails.

Four things tie Sentinel to macOS and Linux:

- The hooks need Bash.
  `bash-command-validator.sh`, `block-dangerous-bash.sh`, `git-baseline.sh`, and `session-tool-checks.sh` are Bash scripts; the Bash hooks read each tool call with `jq`, and `block-dangerous-bash.sh` matches commands with `perl`.
- Each path in `guarded-paths.toml` uses `/` as its separator, and none names a drive.
- Each settings file in `configuration-floor.toml` has its macOS or Linux path only.
  On Windows, VS Code 1.146.0 also reads Copilot's managed settings from `%ProgramFiles%\GitHubCopilot\managed-settings.json` and from the registry key `SOFTWARE\Policies\GitHubCopilot`; the session-start check reads neither.
- The hooks read shell commands as POSIX shell.
  An agent on Windows can also run PowerShell or `cmd.exe` commands, and no hook reads those.

## User Stories

### Story: guardrails-on-windows

As a user who runs a supported agent on Windows, I want Sentinel's hooks to run in my sessions and decide each tool call as they do on macOS and Linux.

North star: "response matches risk"; the same tool call gets the same decision on every platform Sentinel supports.

## Scope

**In scope:**

- Every hook running on Windows, with the Bash hooks ported or replaced.
- A Windows path for each declaration in `guarded-paths.toml` and each settings file in `configuration-floor.toml`, for each supported harness.
- Path matching for Windows paths: `\` as a separator, drive letters, and Windows case folding.
- A test run on Windows in CI.

**Out of scope:**

- Reading the Windows registry, until the open question about registry policy is settled.

## Open Questions

- Which harnesses run on Windows natively, and which only under WSL; a harness under WSL can already work as it does on Linux.
- Whether to port the Bash hooks to Python, or to require Git Bash or WSL.
- Which shells the hooks read on Windows: PowerShell, `cmd.exe`, or only the POSIX shells that Git Bash starts.
- Whether the session-start check reads managed policy from the registry.
  VS Code reads policy there; whether Copilot CLI does is unverified.
- The Windows path of each harness's home and settings files; each needs evidence, as `configuration-floor.toml` requires.
