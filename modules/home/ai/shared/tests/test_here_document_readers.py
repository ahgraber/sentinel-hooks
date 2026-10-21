"""A here-document is read only where a recognized read or a record sink keeps it as data."""

from __future__ import annotations

import bash_commands
import pytest
import shell_words

BODY = "rm /guarded/file\n"


def _here(reader: str, after: str = "") -> str:
    return f"{reader} <<'EOF'{after}\n{BODY}EOF"


@pytest.mark.parametrize(
    "reader",
    [
        "cat",
        "cat -",
        "cat /a",
        "head",
        "tr a b",
        "wc -l",
        "grep -f - /a",
        "git commit -F -",
        "git commit --file=-",
        "git commit --file -",
        "git commit -m subject -F -",
        "git -C /repo commit -F -",
        "git tag -a v1 -F -",
        "gh pr create --body-file -",
        "gh issue comment 1 --body-file=-",
        "tee out",
        "tee -a out",
    ],
)
def test_a_data_reader_keeps_the_body_as_data(reader):
    reading = bash_commands.read(_here(reader))

    assert reading.unlexable is None
    assert [segment.programs for segment in reading.segments] == [()]
    assert reading.segments[0].read_only == (reader.split()[0] in bash_commands.READ_ONLY_UTILITIES)


@pytest.mark.parametrize("after", ["", " > /out", "; head /a", " && head /a"])
def test_cat_keeps_its_body_as_data_beside_redirections_and_later_commands(after):
    assert bash_commands.read(_here("cat", after)).unlexable is None


@pytest.mark.parametrize(
    ("reader", "after"),
    [
        # Programs that may act on their input.
        ("bash", ""),
        ("python3 -", ""),
        ("uv run python -", ""),
        ("xargs rm", ""),
        ("sudo sh", ""),
        ("source /dev/stdin", ""),
        ("awk -f -", ""),
        ("sed -f -", ""),
        ("git apply", ""),
        ("crontab -", ""),
        ("unknown-program", ""),
        # A read that takes the names of the files it reads from its input.
        ("sort --files0-from=-", ""),
        ("wc --files0-from -", ""),
        ("file -f -", ""),
        ("find . -files0-from -", ""),
        ("sha256sum -c", ""),
        ("md5sum --check", ""),
        # A record reader whose output goes to another program.
        ("cat", " | sh"),
        ("cat", " | xargs rm"),
        ("tee /tmp/o", " | bash"),
        # A wrapper or an assignment before the reader may pick another program.
        ("env -S'sh -s' tee", ""),
        ("timeout 5 tee out", ""),
        ("command cat", ""),
        ("PATH=/tmp/x tee out", ""),
        ("GIT_EDITOR=sh git commit -F -", ""),
        ("/usr/bin/tee out", ""),
        # A git or gh form that may run the message, or names no record.
        ("git agent-commit -F -", ""),
        ("git commit", ""),
        ("git -c core.editor=sh commit -F -", ""),
        ("git commit -e -F -", ""),
        ("git commit --edit -F -", ""),
        ("git commit --ed -F -", ""),
        ("git commit -veF -", ""),
        ("git commit -c HEAD -F -", ""),
        ("git commit --reedit-message=HEAD -F -", ""),
        ("git --exec-path=/tmp commit -F -", ""),
        ("git -C", ""),
        ("gh pr create", ""),
        ("gh myalias --body-file -", ""),
        ("gh api --body-file -", ""),
    ],
)
def test_a_here_document_any_other_reader_takes_leaves_no_reading(reader, after):
    reading = bash_commands.read(_here(reader, after))

    assert reading.segments == ()
    assert reading.stopping_syntax() == bash_commands.UNREAD_HERE_DOCUMENT


@pytest.mark.parametrize("reader", ["cat", "git commit -F -", "tee /tmp/out"])
def test_an_assignment_shaped_body_names_no_path(reader):
    reading = bash_commands.read(f"{reader} <<'EOF'\nPATH=/guarded/file fix\nEOF")

    assert [
        path
        for segment in reading.segments
        for word in segment.words
        for path in bash_commands.word_paths(word, "/tmp")
    ] == (["/tmp/out"] if reader.startswith("tee") else [])


@pytest.mark.parametrize("shell", ["bash", "sh", "zsh -e"])
def test_a_shell_reads_its_here_document_as_its_program(shell):
    segments = shell_words.lex(_here(shell), "/tmp")

    assert bash_commands.reads_stdin_program(segments[0])


def test_a_body_bash_expands_is_unresolvable_for_cat():
    reading = bash_commands.read(f"cat <<EOF\n$X {BODY}EOF")

    assert reading.unlexable is None
    assert not reading.segments[0].read_only


def test_a_data_body_does_not_hide_the_readers_other_words():
    reading = bash_commands.read(f"cat <<'EOF' > /out\n{BODY}EOF")

    assert reading.segments[0].read_only
    assert [word.value for word in reading.segments[0].words if bash_commands.redirect_writes(word)] == ["/out"]
