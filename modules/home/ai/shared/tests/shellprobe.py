"""Record the words the shell passes to each program of a command.

The read classifier decides from command text, lexing it with `shlex`. The shell
expands words after that lexing — braces, parameters, pathnames, tildes — so a
token the classifier judged as a filename can reach a program as an option.

This runs the same text through the real shell with every program replaced by a
recorder, which makes that divergence observable without running anything that
has an effect. The recorder is the only thing on `PATH`, so a generated command
cannot reach a real utility.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# The shim writes its own argv and exits. `$RANDOM` and `$$` together keep
# concurrent invocations inside one command from overwriting each other.
SHIM = """#!{bash}
printf '%s\\0' "$0" "$@" > "${{REC_DIR}}/rec.$$.${{RANDOM}}"
"""


@dataclass(frozen=True)
class Invocation:
    """One program the shell actually started, and the words it received."""

    program: str
    argv: tuple[str, ...]

    @property
    def words(self) -> tuple[str, ...]:
        """Program name followed by its arguments, matching a classifier segment."""
        return (self.program, *self.argv)


class ShellProbe:
    """A restricted world in which a command's real argument vectors are observable."""

    def __init__(self, root: Path, programs: set[str]) -> None:
        bash = shutil.which("bash")
        if bash is None:  # pragma: no cover - bash is a test dependency
            raise RuntimeError("bash is required to observe shell word expansion")

        # Kept as an absolute path: `bash` is itself a recorded program, so
        # invoking the shell through `PATH` would reach the shim instead.
        self.bash = bash
        self.root = root
        self.bin = root / "bin"
        self.records = root / "records"
        self.work = root / "work"
        # The real home, because the classifier expands `~` against it too, and a
        # substituted one would read as a divergence the shell did not cause.
        # Nothing under it is reachable: the shims are the whole of `PATH`.
        self.home = Path(os.path.expanduser("~"))
        for directory in (self.bin, self.records, self.work):
            directory.mkdir(parents=True, exist_ok=True)

        for program in programs:
            shim = self.bin / program
            shim.write_text(SHIM.format(bash=bash))
            shim.chmod(0o755)

    def clear(self) -> None:
        for record in self.records.iterdir():
            record.unlink()

    def run(self, command: str, timeout: float = 10.0) -> list[Invocation]:
        """Every program the shell started for `command`, with the words it received.

        A command naming a program with no shim simply starts nothing, which the
        caller reads as an empty result rather than as an error.
        """
        self.clear()
        env = {
            "PATH": str(self.bin),
            "REC_DIR": str(self.records),
            "HOME": str(self.home),
            "SHELL": "/bin/bash",
        }
        try:
            subprocess.run(
                [self.bash, "-c", command],
                cwd=self.work,
                env=env,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return []

        invocations = []
        for record in sorted(self.records.iterdir()):
            words = record.read_bytes().split(b"\0")
            if words and words[-1] == b"":
                words.pop()
            if not words:
                continue
            decoded = [word.decode("utf-8", "surrogateescape") for word in words]
            invocations.append(
                Invocation(os.path.basename(decoded[0]), tuple(decoded[1:]))
            )
        return invocations
