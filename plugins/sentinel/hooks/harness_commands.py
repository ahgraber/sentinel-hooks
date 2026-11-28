"""Find a supported harness's own plugin commands and session switches in a Bash command.

A harness switches a plugin off through its own records, so these commands name
no path a declaration covers. `tool-vocabulary.toml` names them per harness.
The program is found wherever `bash_commands.nesting` finds a command: in every
segment, past the wrappers `bash_commands.invoked` knows, in the commands
`xargs`, `find`, and `watch` run, and in program text the command passes to a
shell or `eval`, up to `bash_commands.NESTING_LIMIT` levels deep. Code in
another language, such as `python3 -c`, is not read. A program word that does
not resolve, such as a variable, is not found. In text that has no reading,
such as a here-string, each harness program among the words is found.
"""

from __future__ import annotations

from collections.abc import Iterator
import os

import bash_commands
from guarded_paths import TOOL_VOCABULARY, HarnessCommands
import shell_words
from shell_words import Word

# A settings file larger than this is read in part.
_SETTINGS_READ_LIMIT = 1_000_000


def _harness_runs(found: bash_commands.Nesting) -> Iterator[tuple[HarnessCommands, list[Word]]]:
    """Yield each run of a harness: its table and the arguments after the program.

    In a command that has no reading, every word can be the program, and the words after it are its arguments.
    """
    for words in found.invocations:
        if (table := _harness(words[0])) is not None:
            yield table, words[1:]
    for command in found.unread:
        for index, word in enumerate(command):
            if (table := _harness(word)) is not None:
                yield table, command[index + 1 :]


def _harness(word: Word) -> HarnessCommands | None:
    """Return the table of the harness `word` names as its program, if it names one."""
    name = bash_commands.program_name(word.value)
    return next((table for table in TOOL_VOCABULARY.harness_commands.values() if name == table.program), None)


def plugin_maintenance(found: bash_commands.Nesting) -> str | None:
    """Return the harness command `found` runs that can switch off, remove, or replace a plugin.

    A sequence matches anywhere after the program, so an option value before the
    subcommand does not hide it; a false match asks, and asking is the safe side.
    """
    for table, arguments in _harness_runs(found):
        values = [table.aliases.get(word.value, word.value) for word in arguments]
        for sequence in table.maintenance:
            window = _window(sequence, values)
            if window is not None:
                return " ".join((table.program, *window))
    return None


def _window(sequence: tuple[str, ...], values: list[str]) -> list[str] | None:
    """Return the run of `values` that `sequence` matches, a `*` matching any one word."""
    for start in range(len(values) - len(sequence) + 1):
        window = values[start : start + len(sequence)]
        if all(expected in {"*", value} for expected, value in zip(sequence, window, strict=True)):
            return window
    return None


def session_switch(found: bash_commands.Nesting, cwd: str | None) -> str | None:
    """Return the switch with which `found` starts a harness session without its hooks.

    An assignment anywhere in the command counts, including an `export` or a
    bare assignment in an earlier segment; the harness's own arguments do not.
    """
    runs = list(_harness_runs(found))
    harness_word_ids = {id(word) for _, harness_arguments in runs for word in harness_arguments}
    words = [
        word
        for each in found.readings
        for segment in each.segments
        for word in segment.words
        if id(word) not in harness_word_ids
    ]
    # In text with no reading any word can be a harness, so a path such as `/tmp/claude` would claim the
    # assignment after it as its own argument; no word there is dropped, and a false match refuses.
    words += [word for command in found.unread for word in command]
    for table, harness_arguments in runs:
        switch = _assigned(table, words) or _switched(table, harness_arguments, cwd)
        if switch is not None:
            return switch
    return None


def _assigned(table: HarnessCommands, words: list[Word]) -> str | None:
    """Return an assignment among `words` of a variable that switches the hooks off."""
    for word in words:
        if shell_words.is_assignment(word.value) and word.value.partition("=")[0].rstrip("+") in table.environment:
            return word.value
    return None


def _switched(table: HarnessCommands, arguments: list[Word], cwd: str | None) -> str | None:
    """Return an option among the arguments that switches the hooks off, up to a `--`."""
    for index, word in enumerate(arguments):
        if word.value == "--":
            break
        switch = _switch_named(table, word.value) or _switch_with_value(table, arguments, index, cwd)
        if switch is not None:
            return switch
    return None


def _switch_named(table: HarnessCommands, word: str) -> str | None:
    """Return the switch `word` names, alone or with a value attached."""
    for switch in table.switches:
        if word == switch or _attached_value(switch, word) is not None:
            return switch
    return None


def _switch_with_value(table: HarnessCommands, arguments: list[Word], index: int, cwd: str | None) -> str | None:
    """Return the value switch at `arguments[index]` whose value, or the file it names, switches the hooks off."""
    for switch, pattern in table.value_switches.items():
        value = _switch_value(switch, arguments, index)
        if value is not None and (pattern.search(value) or pattern.search(_file_text(value, cwd))):
            return f"{switch} {value}"
    return None


def _switch_value(switch: str, arguments: list[Word], index: int) -> str | None:
    """Return the value `arguments[index]` gives `switch`: the next word, after `=`, or attached to a short option."""
    word = arguments[index].value
    if word == switch:
        return arguments[index + 1].value if index + 1 < len(arguments) else None
    return _attached_value(switch, word)


def _attached_value(switch: str, word: str) -> str | None:
    """Return the value `word` attaches to `switch`: after `=` on a long option, or after a short option's letter."""
    if switch.startswith("--"):
        return word[len(switch) + 1 :] if word.startswith(f"{switch}=") else None
    if len(switch) == 2 and word.startswith(switch) and len(word) > 2:
        return word[2:]
    return None


def _file_text(value: str, cwd: str | None) -> str:
    """Return the text of the file a switch value names, or `""` where it names none the hook can read."""
    path = os.path.expanduser(value)
    if not os.path.isabs(path):
        if cwd is None:
            return ""
        path = os.path.join(cwd, path)
    # A device or a pipe could block the read, so only a regular file is opened.
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(_SETTINGS_READ_LIMIT)
    except OSError:
        return ""
