"""A command the tamper hook allows leaves every declared file as it was.

Each example runs the command on a fresh tree and compares the declared file
before and after. The commands come from a catalog kept here, apart from the
hook's own program table, so a program the table lacks fails the property.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import bash_commands
from hypothesis import HealthCheck, given, settings, strategies as st

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
DECLARED = "modules/home/ai/shared/hooks/guard.py"
TARGETS = [
    ".",
    "modules",
    "modules/home/ai",
    "modules/home/ai/shared/hooks",
    DECLARED,
    "modules/home/ai/notes.md",
    "scratch",
]
COMMANDS = [
    "rm -rf {t}",
    "mv {t} {away}",
    "cp -R {src}/. {t}",
    "ln -sfn {src} {t}",
    "truncate -s 0 {t}",
    "chmod 000 {t}",
    "chmod -R a-w {t}",
    "find {t} -delete",
    "find {t} -type f -exec rm {{}} +",
    "tar -xf {archive} -C {t}",
    "cd {t} && tar -xf {archive}",
    "cd {parent} && rm -rf {base}",
    "ditto {src} {t}",
    "rsync -a --delete {src}/ {t}",
    "env rm -rf {t}",
    "FOO=1 rm -rf {t}",
]


def _load_gate():
    spec = importlib.util.spec_from_file_location("tamper_gate_tree", HOOKS_DIR / "block-hook-tampering.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def allows(command: str, cwd: str) -> bool:
    reading = bash_commands.read(command, cwd)
    return (
        gate.command_protected_class(command, cwd) is None
        and gate._destroyed_ancestor(reading, cwd) is None
        and gate._unanchored_operand(reading, cwd) is None
    )


def _build(root: Path, target: str) -> dict[str, Path]:
    repo = root / "repo"
    (repo / ".git").mkdir(parents=True)
    for name in (DECLARED, "modules/home/ai/notes.md", "scratch/a.txt"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(name)
    src = root / "src"
    (src / "shared/hooks").mkdir(parents=True)
    (src / "shared/hooks/guard.py").write_text("replaced")
    archive = root / "archive.tar"
    member = os.path.relpath(repo / DECLARED, repo / target) if not target.startswith(DECLARED) else "x"
    payload = root / "payload"
    payload.write_text("replaced")
    with tarfile.open(archive, "w") as tar:
        tar.add(payload, arcname=member)
    return {"repo": repo, "src": src, "archive": archive, "away": root / "away"}


def _state(repo: Path) -> tuple:
    declared = repo / DECLARED
    try:
        return (declared.read_text(), declared.stat().st_mode, (repo / DECLARED).parent.stat().st_mode)
    except OSError as error:
        return (type(error).__name__,)


def _cleanup(root: Path) -> None:
    subprocess.run(["chmod", "-R", "u+rwx", str(root)], check=False, capture_output=True)
    shutil.rmtree(root, ignore_errors=True)


@given(
    template=st.sampled_from(COMMANDS),
    target=st.sampled_from(TARGETS),
    spelling=st.sampled_from(["relative", "absolute", "dotted"]),
)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_an_allowed_command_leaves_the_declared_file_unchanged(
    tmp_path_factory, template: str, target: str, spelling: str
) -> None:
    root = tmp_path_factory.mktemp("tree")
    try:
        paths = _build(root, target)
        repo = paths["repo"]
        spelled = {"relative": target, "absolute": str(repo / target), "dotted": f"./{target}"}[spelling]
        command = template.format(
            t=spelled,
            src=paths["src"],
            archive=paths["archive"],
            away=paths["away"],
            parent=os.path.dirname(spelled) or ".",
            base=os.path.basename(spelled),
        )
        if not allows(command, str(repo)):
            return
        before = _state(repo)
        subprocess.run(["bash", "-c", command], cwd=repo, capture_output=True, timeout=30, check=False)
        assert _state(repo) == before, f"allowed and changed {DECLARED}: {command}"
    finally:
        _cleanup(root)
