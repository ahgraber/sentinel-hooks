"""Record the words the shell passes to each program of a command.

The read classifier decides from command text, lexing it with `shell_words`.
The shell expands words after that lexing (braces, parameters, pathnames,
tildes), so a token the classifier judged as a filename can reach a program as
an option.

This runs the same text through the real shell with every program replaced by a
recorder, which makes that divergence observable without running anything that
has an effect. The recorder is the only thing on `PATH`, so a generated command
cannot reach a real utility.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import signal
import subprocess

# The shim writes its own argv and the standard input it received, then exits.
# `$RANDOM` and `$$` together keep concurrent invocations inside one command from
# overwriting each other. `read -d ''` keeps every newline of the input, which
# a command substitution would strip from its end.
SHIM = """#!{bash}
id="$$.${{RANDOM}}"
IFS= read -r -d '' input
printf '%s' "${{input}}" > "${{REC_DIR}}/in.${{id}}"
printf '%s\\0' "$0" "$@" > "${{REC_DIR}}/rec.${{id}}"
"""

# Read through `BASH_ENV`, so the command text runs unchanged: bash calls this for
# any program not on `PATH`, which records programs no shim names.
MISSING_HANDLER = """command_not_found_handle() {
  printf '%s\\0' "$@" > "${REC_DIR}/rec.${BASHPID}.${RANDOM}"
  return 127
}
"""


@dataclass(frozen=True)
class Invocation:
    """One program the shell started or tried to start, the words it received, and its standard input."""

    program: str
    argv: tuple[str, ...]
    stdin: str = ""

    @property
    def words(self) -> tuple[str, ...]:
        """Program name followed by its arguments, matching a classifier segment."""
        return (self.program, *self.argv)


class ShellProbe:
    """A restricted world in which a command's real argument vectors are observable."""

    def __init__(self, root: Path, programs: set[str], *, record_missing: bool = False) -> None:
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
        self.bash_env: Path | None = None
        if record_missing:
            self.bash_env = root / "bash_env"
            self.bash_env.write_text(MISSING_HANDLER)

    def clear(self) -> None:
        for record in self.records.iterdir():
            record.unlink()

    def run(self, command: str, timeout: float = 10.0) -> list[Invocation]:
        """Every program the shell started for `command`, with the words it received, or `[]` past `timeout`.

        A program with no shim starts nothing and is left out, unless the probe
        records missing programs, in which case it appears with the words bash
        passed it.
        """
        self.clear()
        env = {
            "PATH": str(self.bin),
            "REC_DIR": str(self.records),
            "HOME": str(self.home),
            "SHELL": "/bin/bash",
        }
        if self.bash_env is not None:
            env["BASH_ENV"] = str(self.bash_env)
        # Standard input is empty, so a program given no other input reads none.
        # A session of its own keeps a `kill 0` in the command away from the caller,
        # and killing its process group stops a background job from recording into the next run.
        process = subprocess.Popen(
            [self.bash, "-c", command],
            cwd=self.work,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return []
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()

        invocations = []
        for record in sorted(self.records.glob("rec.*")):
            words = record.read_bytes().split(b"\0")
            if words and words[-1] == b"":
                words.pop()
            if not words:
                continue
            decoded = [word.decode("utf-8", "surrogateescape") for word in words]
            received = record.with_name("in." + record.name.removeprefix("rec."))
            stdin = received.read_bytes().decode("utf-8", "surrogateescape") if received.exists() else ""
            invocations.append(Invocation(os.path.basename(decoded[0]), tuple(decoded[1:]), stdin))
        return invocations
