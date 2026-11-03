# Delta for Sensitive Path Blocking

## MODIFIED Requirements

### Requirement: BlockBashWriteToZeroAccessPath

> Previously: the write targets were the last word of `cp`, `mv`, and `install`, the operands of `tee` and `truncate`, and the operands after the mode of `chmod` and `chown`, found with every word that begins with `-` set aside; `cp -t <dest> <src>` named `<src>` as the destination.

The system SHALL block `Bash` commands that write to or overwrite a zero-access path.

Write-to-path patterns in Bash include:

- Output redirection (`>`, `>>`) to a zero-access path
- `cp`, `mv`, `install`, `tee` with a zero-access path as the destination
- `chmod` or `chown` targeting a zero-access path
- `dd of=` a zero-access path
- Any word the reading `program-catalog` gives types as written, deleted, or changed in permissions, owner, or times, through every wrapper, as `cp -t <dest>`, `sed -i`, `tar -x -C <dir>`, and `rsync` destinations are

Where a segment's reading ends, a zero-access path the segment names SHALL be judged as a write target of each program the segment may run, as `program-catalog` `AnIncompleteReadingEndsRecognition` counts them, whose entry states a write, delete, or permission effect.

The forms listed by program name SHALL apply in every case, beside the targets the reading gives, so a reading that is complete but wrong cannot remove a target those forms name, and no command blocked today proceeds.

Serves: every-argument-has-a-stated-effect, a-wrapper-read-once-holds-everywhere

#### Scenario: RedirectToEnvFile

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command contains `> .env` or `>> .env`
- **THEN** the hook exits 2

#### Scenario: CpToSshDir

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command copies a file into `~/.ssh/`
- **THEN** the hook exits 2

#### Scenario: CopyWithATargetDirectoryOption

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `cp -t ~/.ssh/ /project/key.pub`
- **THEN** the hook exits 2

#### Scenario: InPlaceEditUnderAWrapper

- **GIVEN** a Bash tool call is intercepted
- **WHEN** the command is `env sed -i 's/a/b/' /project/.env`
- **THEN** the hook exits 2
