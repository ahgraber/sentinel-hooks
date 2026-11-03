"""A command the hooks allow does not print a credential.

Each example plants credential files that each hold a marker string, runs the
command, and searches its output for the marker. The commands come from a
catalog kept here, apart from the hooks' own list of reading programs, so a
reader that list lacks fails the property.

The property sees only what one command prints. A copy now and a read in a
later call is out of its reach.

`sensitive-path-blocking` `BashReadBestEffort` puts some forms out of scope.
They run here only on the credentials the manifest declares, which the tamper
hook also judges. A recursive read of a directory holding a credential is out
of scope for every credential, so the catalog leaves it out.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from hook_chain import verdicts
from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

# Files the manifest's `block` class declares.
DECLARED = [
    "home/.codex/auth.json",
    "home/.pi/agent/auth.json",
    "home/.config/mcp-secrets.env",
    "home/.claude/.credentials.json",
]
# Files only the name rules recognize; the repository-relative ones sit in the checkout.
CREDENTIALS = [
    *DECLARED,
    "home/.ssh/id_ed25519",
    "home/.aws/credentials",
    "home/.netrc",
    "repo/.env",
    "repo/deploy.pem",
    "repo/service-account-ci.json",
]

COMMANDS = [
    "cat {f}",
    "head -c 4096 {f}",
    "tail -n 5 {f}",
    "base64 < {f}",
    "xxd -p {f} | xxd -r -p",
    "od -An -c {f} | tr -d ' \\n'",
    "strings {f}",
    "sed -n p {f}",
    "awk 1 {f}",
    "cut -c1- {f}",
    "sort {f}",
    "paste {f}",
    "rev {f} | rev",
    "dd if={f} status=none",
    "touch empty && diff {f} empty",
    "grep -h . {f}",
    "jq -R . {f}",
    "cat < {f}",
    "{{ cat; }} < {f}",
    'while IFS= read -r line; do echo "$line"; done < {f}',
    "cat {f} | cat",
    "cp {f} copy.txt && cat copy.txt",
    "find {d} -name {n} -exec cat {{}} +",
    "tar -cf - {f} 2>/dev/null | tar -xOf -",
    "cat {d}/*",
    "cat {d}/{n_glob}",
    "cd {d} && cat {n}",
    "cd {d}; cat {n}",
    "cd {d} 2>/dev/null && cat {n}",
    "cd /absent || cd {d} && cat {n}",
    "command -p cd {d} && cat {n}",
    "! cd {d} || cat {n}",
    "if cd {d}; then cat {n}; fi",
    "{{ cd {d}; }} && cat {n}",
    "f() {{ cd {d}; }}; f; cat {n}",
    'cat {d}/"{n_prefix}"*',
    "env cat {f}",
    "command cat {f}",
    "source {f}",
]

# The forms `BashReadBestEffort` states are out of scope.
STATED_LIMITS = [
    "ln -s {f} link && cat link",
    "cat $(echo {f})",
    'path={f}; cat "$path"',
    "echo {f} | xargs cat",
    "bash -c 'cat {f}'",
    'sh -c "cat {f}"',
    "python3 -c 'import sys; print(open(sys.argv[1]).read())' {f}",
]


def _plant(root: Path) -> dict[str, str]:
    """Write each credential with its own marker; return the marker of each one written and read back.

    An agent sandbox can deny writing or reading some of these names, so the
    property draws only from the ones a plain read reaches here.
    """
    (root / "repo/.git").mkdir(parents=True)
    markers = {}
    for index, name in enumerate(CREDENTIALS):
        path = root / name
        marker = f"CANARY{index:02d}x{os.urandom(4).hex()}"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(marker + "\n")
            if marker in path.read_text():
                markers[name] = marker
        except OSError:
            pass
    return markers


def _spell(root: Path, name: str, spelling: str) -> str:
    absolute = root / name
    if spelling == "home" and name.startswith("home/"):
        return "~/" + name.removeprefix("home/")
    if spelling == "variable" and name.startswith("home/"):
        return '"$HOME"/' + shlex.quote(name.removeprefix("home/"))
    if spelling == "relative":
        return os.path.relpath(absolute, root / "repo")
    return shlex.quote(str(absolute))


def _command(root: Path, name: str, template: str, spelling: str) -> str:
    spelled = _spell(root, name, spelling)
    directory, _, base = spelled.rpartition("/")
    return template.format(
        f=spelled,
        d=directory or ".",
        n=shlex.quote(base),
        n_glob=base[:-1] + "?" if len(base) > 1 else "*",
        n_prefix=base[:3],
    )


def _output(root: Path, command: str) -> str:
    """Run `command` in the planted checkout with no hooks; return everything it printed."""
    ran = subprocess.run(
        ["bash", "-c", command],
        cwd=root / "repo",
        env={**os.environ, "HOME": str(root / "home")},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return ran.stdout + ran.stderr


def _discloses(output: str, marker: str) -> bool:
    """Return whether `output` holds the marker as written, in base64, or in hex."""
    content = (marker + "\n").encode()
    flat = re.sub(r"\s", "", output)
    return any(form in flat for form in (marker, base64.b64encode(content).decode())) or content.hex() in flat.lower()


@pytest.mark.parametrize("template", COMMANDS + STATED_LIMITS)
def test_every_catalog_command_prints_a_credential_without_hooks(tmp_path, template: str) -> None:
    """Guards the catalog: a command that prints nothing would pass the property for no reason."""
    markers = _plant(tmp_path)
    name = next((name for name in DECLARED if name in markers), None)
    if name is None:
        pytest.skip("no declared credential is readable here")

    output = _output(tmp_path, _command(tmp_path, name, template, "absolute"))

    assert _discloses(output, markers[name]), output


@given(data=st.data())
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_an_allowed_command_does_not_print_a_credential(tmp_path_factory, data) -> None:
    root = tmp_path_factory.mktemp("credentials")
    try:
        markers = _plant(root)
        assert markers, "no planted credential is readable, so the property checks nothing"
        name = data.draw(st.sampled_from(sorted(markers)), label="credential")
        template = data.draw(st.sampled_from(COMMANDS + STATED_LIMITS if name in DECLARED else COMMANDS))
        spelling = data.draw(st.sampled_from(["absolute", "home", "variable", "relative"]), label="spelling")
        command = _command(root, name, template, spelling)

        verdict = verdicts(
            {"tool_name": "Bash", "tool_input": {"command": command}}, ["claude"], root / "home", root / "repo"
        )
        if verdict["claude"] != "allow":
            return

        assert not _discloses(_output(root, command), markers[name]), f"allowed and printed {name}: {command}"
    finally:
        shutil.rmtree(root, ignore_errors=True)
