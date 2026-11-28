# Delta for guarded-surface

## ADDED Requirements

### Requirement: DotenvPlaceholdersAreDeclared

Serves: placeholder-files-are-readable

The manifest SHALL declare `.env.example`, `.env.sample`, `.env.template`, and `.env.op` as exceptions for the dotenv surface, each matching its file name in any directory.

These are the names projects commit to list the variables they expect, with placeholder values.
The values in `.env.op` are 1Password secret references, which name a vault, an item, and a field but hold no secret.
`.env.dist` is not declared.
`sensitive-path-blocking` `DotenvPlaceholderReadIsExcusedOnlyByDeclaration` excuses a read of a declared name and nothing else.

An agent's configuration MAY refuse a declared name more strictly than the declaration allows.
Codex has no way to reopen a file inside a deny glob, so its `**/.env.*` deny still refuses these names.

#### Scenario: EachPlaceholderNameIsDeclared

- **GIVEN** the shipped manifest
- **WHEN** its dotenv exceptions are read
- **THEN** they name exactly `.env.example`, `.env.sample`, `.env.template`, and `.env.op`

#### Scenario: ADotenvExceptionIsAFileName

- **GIVEN** a dotenv exception whose pattern is not `.env.` followed by a suffix, or holds a directory separator, home notation, whitespace, or a glob character
- **WHEN** the manifest is validated
- **THEN** validation fails, because the pattern is compared as one literal file name, and `.env` itself is the file the dotenv rule exists to refuse
