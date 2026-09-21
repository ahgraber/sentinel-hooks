# Delta for bash-command-validator

## REMOVED Requirements

### Requirement: RedirectGrepToRipgrep

Removed because: the rule was retired by `c7f3937` (2026-07-28), which replaced this requirement in the baseline with `ReviewHeredocsForBangHistory`, `RejectZshExpansionHazards`, and `RejectRipgrepRecursiveFlag`.
A bare `grep` invocation is no longer redirected.
The retirement was made by editing the baseline directly, so no change recorded it until this one.

### Requirement: RedirectFindToRipgrep

Removed because: retired by `c7f3937` (2026-07-28) alongside `RedirectGrepToRipgrep`.
A `find <dir> -name` invocation is no longer redirected.

### Requirement: RequireSignedCommits

Removed because: superseded by `RequireAgentCommitAlias` in `fba2187` (2026-05-02), which replaced this requirement in the baseline rather than recording a rename.
Requiring the alias subsumes requiring a signing flag: the alias signs with the dedicated agent key, so a commit that satisfies `RequireAgentCommitAlias` is signed by construction.
