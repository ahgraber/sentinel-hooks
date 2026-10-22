# Delta for sensitive-path-blocking

## MODIFIED Requirements

### Requirement: BlockBashReadFromZeroAccessPath

> Previously: a value a loop passes to its body through the loop variable was judged only where a read utility stood in the loop's own header.

The system SHALL block `Bash` commands that read a zero-access path, so its contents cannot enter the agent's context.

This enforcement matters most on Linux, where the OS sandbox (bubblewrap) ignores glob deny rules such as `Read(**/.env)` and so does not stop a plain `cat ./project/.env`; on macOS the Seatbelt sandbox honors those globs.
The hook makes read blocking uniform across platforms.

This hook is a `shell-lexing` path hook.
When a command uses quoting, escapes, or words the shell rewrites, the hook SHALL judge the words bash would produce.
If the hook cannot work them out, it SHALL treat them as unresolvable.
It SHALL NOT judge them as written.

Where any word of a segment names a recognized read utility, every word in that segment SHALL be judged by the strong rules, whatever its kind: an extension, a credential directory, a key filename, a dotenv name, and a declared block path each name a file wherever they appear, so `-f.env`, `if=.env`, and `sudo -u root cat .env` all block.
An unresolvable word SHALL be judged by the paths it holds.
Input redirection targets SHALL be judged regardless of the command word.

The name heuristic, which guesses contents from a word in a name, SHALL be applied to a path candidate, as `shell-lexing` `APathCandidateDenotesAFile` defines it, to a redirection target, and in a segment that reads to an unresolvable word that may denote a file, and to no other word.
An unresolvable word may denote a file when the shell builds it from an expansion, when the segment's directory does not resolve, or when its spelling in a directory the segment may run in names an existing entry; that last test is the one a bare word already meets to be a path candidate.
A search pattern, a selector expression, and a commit subject are words a read utility receives that name no file, and refusing them stopped ordinary work over this module four times in one session.
A bare word that names an entry in the working directory is a path candidate, so the same word is refused the moment a file of that name exists.

The bias still prefers false positives over false negatives for every rule that recognizes a shape.
The name heuristic is the one rule that recognizes a word, and a word that denotes no file is outside what it can be right about.

Read-from-path forms in Bash include:

- A recognized read command (`cat`, `head`, `grep`, `sed`, `awk`, `jq`, `sort`, `source`, `openssl`, `tar`, `unzip`, `install`, an editor, ...) in a segment that also contains a zero-access word
- Input redirection (`<`, `0<`, `$(< file)`, `mapfile`/`read < file`) from a zero-access path
- `dd if=` a zero-access path
- A value a `for` or `select` loop passes to its body through the loop variable, whatever program the body runs

Serves: a-multi-line-command-is-read-line-by-line

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

#### Scenario: SearchPatternAfterADirectoryChange

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a search after a resolved `cd` carries a name-heuristic word that names no entry in any directory the search may run in (e.g. `cd sub && rg secret .`)
- **THEN** the hook exits 0

#### Scenario: NamedFileAfterADirectoryChange

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read after a `cd` names a file whose name carries a name-heuristic word, and the `cd` is unresolved or the file exists in a directory the read may run in (e.g. `X=~/.config; cd $X && cat mcp-secrets.env`, `if cd ~/.config; then cat mcp-secrets.env; fi`)
- **THEN** the hook exits 2

#### Scenario: NamedFileBehindAnExpansion

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a read names a file through an expansion carrying a name-heuristic word (e.g. `cat ${X:-mcp-secrets.env}`)
- **THEN** the hook exits 2

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
- **WHEN** a read command receives an unresolvable word that holds a zero-access path
- **THEN** the hook exits 2

#### Scenario: AZeroAccessPathALoopPassesToItsBody

- **GIVEN** a Bash tool call is intercepted
- **WHEN** a loop passes a zero-access path to its body through the loop variable (e.g. `for f in id_rsa; do cat "$f"; done`)
- **THEN** the hook exits 2

## ADDED Requirements

### Requirement: AMultiLineCommandReachesItsOneLineVerdict

A Bash command written across lines SHALL reach the same verdict as its one-line form.
If the hook cannot read the command as a whole, and any strong rule refuses a path anywhere in the text, the hook SHALL refuse the command.
No exemption applies.

Serves: a-multi-line-command-is-read-line-by-line

The hook judges the words of each segment.
So a command read across lines gets the same rules on the same words as its one-line form.
A placeholder dotenv file read on one line of a multi-line command therefore proceeds as it does alone, and a write to it is refused as it is alone.

A here-document is data, and names no file, only where `hook-tampering-blocking` `UnrecognizedCommandsAreGated` says so: where a recognized read or a named sink reads it.
A secret-looking name inside a data body is therefore not refused.
If any other program reads the body, the body is program text.
If any strong rule refuses a path anywhere in the body, the hook SHALL then refuse the command.
The hook treats the body as it treats a command it cannot read, because it does not know what that program does with the body.

If the hook cannot read a command as a whole, it cannot tell what the command reads, writes, or only mentions.
So no exemption applies.

#### Scenario: ASecretReadOnAnyLineIsRefused

- **GIVEN** a multi-line command one of whose lines reads a zero-access path
- **WHEN** the command is judged
- **THEN** it is refused, whichever line holds the read

#### Scenario: APlaceholderReadAcrossLinesProceeds

- **GIVEN** a multi-line command one of whose lines reads a declared placeholder with a recognized read
- **WHEN** the command is judged
- **THEN** the read proceeds, as it does alone

#### Scenario: ANameInsideAHereDocumentIsText

- **GIVEN** a here-document with a quoted delimiter, read by `cat` or `git commit -F -`
- **WHEN** its body names a zero-access path
- **THEN** the command is not refused for that name

#### Scenario: ANameInsideAProgramBodyIsRefused

- **GIVEN** a here-document read by `bash`, `xargs`, `sed -f -`, `cat` piped into a shell, or any program not named as a data reader
- **WHEN** its body names a zero-access path
- **THEN** the command is refused

#### Scenario: UnreadableTextIsJudgedPieceByPiece

- **GIVEN** a command that cannot be read as a whole, such as one with an unclosed quote
- **WHEN** any piece of its text names a zero-access path, a placeholder included
- **THEN** it is refused
