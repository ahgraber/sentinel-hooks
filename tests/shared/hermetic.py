"""Build the temporary world a path case needs, and bind a policy into a hook.

A case that depends on what exists on the machine is a case that passes or fails
for reasons it does not state. Every existence-dependent case builds its world
here instead: a temporary home, a temporary repository, and a substituted
manifest, with `HOME` pinned to the temporary home so a supplied `~` path and a
declaration resolve against the same root.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".specs").is_dir())
HOOKS_DIR = REPO_ROOT / "plugins" / "sentinel" / "hooks"


def load_hook(name: str):
    """Import a hook by location; its filename is not a valid identifier."""
    spec = importlib.util.spec_from_file_location(name, HOOKS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec.loader.exec_module(module)
    return module


def build_home(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Create an empty temporary home and repository; pin `HOME` to the home.

    The repository holds nothing but its `.git` marker, so a case that lists or
    globs it sees only what the case itself puts there.
    """
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    home.mkdir()
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return home, repo


def build_world(tmp_path: Path, monkeypatch, hooks_relative: str = "hooks") -> tuple[Path, Path, Path]:
    """Create a temporary home and repository holding a manifest; return the three.

    `hooks_relative` places the manifest inside the repository. The loader walks
    its parent to find the enforcement set, so a case that judges a declared
    hook tree has to put the manifest where that tree can be told from it.
    """
    home, repo = build_home(tmp_path, monkeypatch)
    hooks = repo / hooks_relative
    hooks.mkdir(parents=True)
    manifest = hooks / "guarded-paths.toml"
    manifest.touch()
    return home, repo, manifest


def manifest_floor() -> list[str]:
    """The enforcement floor the repository's manifest declares."""
    import guarded_paths  # importable only after conftest or load_hook puts the hooks directory on sys.path

    return list(guarded_paths.load_manifest()["enforcement-floor"]["paths"])


def policy(world, guarded=(), block=(), run=(), write=(), floor=None):
    """A policy over `world` declaring the given paths in each class, with no exceptions.

    The floor defaults to the one the repository's manifest declares.
    """
    import guarded_paths

    home, _, manifest = world
    data = {
        "guarded": {"paths": list(guarded)},
        "enforcement-floor": {"paths": manifest_floor() if floor is None else list(floor)},
        "block": {"paths": list(block)},
        "exec-through": {"paths": list(run)},
        "write-through": {"paths": list(write)},
        "exceptions": [],
    }
    return guarded_paths.PathPolicy(data, home=str(home), manifest_path=manifest)


def install_policy(monkeypatch, hook, policy) -> None:
    """Bind `policy` into the one global a hook reads for the manifest."""
    monkeypatch.setattr(hook, "POLICY", policy, raising=False)


def _quote(value: str) -> str:
    """A TOML basic string. An exception's `reason` is prose and may carry quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def dump_manifest(data: dict) -> str:
    """Serialize a loaded manifest back to its record form. No stdlib TOML writer exists."""
    lines = []
    for section, value in data.items():
        if section == "exceptions":
            for table in value:
                lines.append("[[exceptions]]")
                lines.extend(f"{key} = {_quote(val)}" for key, val in table.items())
            continue
        lines.append(f"[{section}]")
        for path in value["paths"]:
            lines += [f"[[{section}.paths]]", f"path = {_quote(path)}", 'reason = "test"']
    return "\n".join(lines) + "\n"
