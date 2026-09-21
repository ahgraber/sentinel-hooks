# Delta for sensitive-path-blocking

## MODIFIED Requirements

### Requirement: BlockBashReadFromZeroAccessPath

> Previously: the command was tokenized with `shlex` inside this hook, every token of a read segment was judged by every rule with no option or operand modelling, and a search pattern carrying a sensitive word was refused as an accepted over-deny.

The system SHALL block `Bash` commands that read a zero-access path, so its contents cannot enter the agent's context.

Serves: one-lexer, reads-are-frictionless

This enforcement matters most on Linux, where the OS sandbox (bubblewrap) ignores glob deny rules such as `Read(**/.env)` and so does not stop a plain `cat ./project/.env`; on macOS the Seatbelt sandbox honors those globs.
The hook makes read blocking uniform across platforms.

The command SHALL be read through `shell-lexing`, so that quoting, escapes, and a word the shell would rewrite reach this hook resolved or reported, and never as written.

Where any word of a segment names a recognized read utility, every word in that segment SHALL be judged by the strong rules, whatever its kind: an extension, a credential directory, a key filename, a dotenv name, and a declared block path each name a file wherever they appear, so `-f.env`, `if=.env`, and `sudo -u root cat .env` all block.
An unresolvable word SHALL be judged by the paths it holds.
Input redirection targets SHALL be judged regardless of the command word.

The name heuristic, which guesses contents from a word in a name, SHALL be applied to a path candidate, as `shell-lexing` `APathCandidateDenotesAFile` defines it, and to a redirection target, and to no other word.
A search pattern, a selector expression, and a commit subject are words a read utility receives that name no file, and refusing them stopped ordinary work over this module four times in one session.
A bare word that names an entry in the working directory is a path candidate, so the same word is refused the moment a file of that name exists.

The bias still prefers false positives over false negatives for every rule that recognizes a shape.
The name heuristic is the one rule that recognizes a word, and a word that denotes no file is outside what it can be right about.

Read-from-path forms in Bash include:

- A recognized read command (`cat`, `head`, `grep`, `sed`, `awk`, `jq`, `sort`, `source`, `openssl`, `tar`, `unzip`, `install`, an editor, ...) in a segment that also contains a zero-access word
- Input redirection (`<`, `0<`, `$(< file)`, `mapfile`/`read < file`) from a zero-access path
- `dd if=` a zero-access path

<!-- modified-removes: SecretWordPatternOverDenies -->

#### Scenario: CatEnvFile

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command reads a zero-access path (e.g. `cat ./project/.env`)
- **THEN** the hook exits 2

#### Scenario: RedirectReadWithoutCommand

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a zero-access path is read via input redirection with no external command (e.g. `mapfile -t a < .env`, `x=$(< .env)`)
- **THEN** the hook exits 2

#### Scenario: BareCredentialFilename

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command targets an extensionless key filename (e.g. `cat id_rsa`) outside a package directory
- **THEN** the hook exits 2, whether or not the file exists

#### Scenario: SearchPatternIsNotAPath

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a search command's pattern carries a name-heuristic word and names no entry in the working directory (e.g. `grep -r secret .`)
- **THEN** the hook exits 0

#### Scenario: SearchPatternNamingAnExistingEntry

- **GIVEN** a Bash tool call is intercepted, and an entry named by a name-heuristic word exists in the working directory
- **WHEN** a read command receives that bare word
- **THEN** the hook exits 2

#### Scenario: NameHeuristicWordWithASeparator

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command receives a word carrying a separator and a name-heuristic word, whether or not the file exists
- **THEN** the hook exits 2

#### Scenario: AQuotedZeroAccessPathIsResolved

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command receives a zero-access path in a quoting form, ANSI-C quoting included
- **THEN** the hook exits 2

#### Scenario: AZeroAccessPathInsideAnUnresolvableWord

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read command receives a word the lexer cannot resolve that holds a zero-access path
- **THEN** the hook exits 2
