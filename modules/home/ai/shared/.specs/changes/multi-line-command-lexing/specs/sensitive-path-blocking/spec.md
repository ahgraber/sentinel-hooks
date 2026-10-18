# Delta for sensitive-path-blocking

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
