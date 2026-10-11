# Delta for sensitive-path-blocking

## ADDED Requirements

### Requirement: AMultiLineCommandReachesItsOneLineVerdict

A Bash command written across lines SHALL reach the verdict its one-line form reaches, as `shell-lexing` reads it, and the strong rules SHALL judge the unparsed text piece by piece only where the lexer reports the command unresolvable.

Serves: a-multi-line-command-is-read-line-by-line

The hook judges the words of each segment, so a command the lexer reads across lines is judged by the same rules on the same words as its one-line form.
A placeholder dotenv file read on one line of a multi-line command therefore proceeds as it does alone, and a write to it is refused as it is alone.

A here-document is data, and names no file, only where `hook-tampering-blocking` `UnrecognizedCommandsAreGated` says so: where a recognized read or a named sink reads it.
A secret-looking name inside a data body is therefore not refused.
A body any other program reads is program text, and each piece of it SHALL be judged by the strong rules, as the text of a command the lexer cannot read is, because the hook does not know what that program does with it.

Where the lexer cannot read a command, which it reports as a whole, the hook cannot tell what it reads, writes, or only mentions.
Each piece of the text between shell syntax is then judged by the strong rules with no exemption, because the rules anchor at the end of a name, and judging the whole text would see only its last line.

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

- **GIVEN** a here-document read by `bash`, `xargs`, `sed -f -`, or any program not named as a data reader
- **WHEN** its body names a zero-access path
- **THEN** the command is refused

#### Scenario: UnreadableTextIsJudgedPieceByPiece

- **GIVEN** a command the lexer reports as a whole as unresolvable
- **WHEN** any piece of its text names a zero-access path, a placeholder included
- **THEN** it is refused
