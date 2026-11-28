#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write Sentinel's Codex hooks into the user's Codex hook file.

Codex skips the hooks of a plugin whose root manifest is an Agent Plugins
manifest (openai/codex#47925), and VS Code and Copilot CLI require that
manifest. This installer writes the Codex registration the plugin ships,
`harnesses/codex/hooks.json`, into `$CODEX_HOME/hooks.json`, pointed at the
installed copy it runs from. Delete it once a Codex release loads
`extensions.com.openai.hooks`, and tell installed users to run it with
`--uninstall` so each hook does not run twice.

Run it from the installed plugin after each install or update, then trust the
hooks in Codex's `/hooks` screen. Once an update removes the copy an entry
names, that entry refuses every call and prints this installer's command.
"""

import argparse
import contextlib
import errno
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import sys
import tempfile

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REGISTRATION = PLUGIN_ROOT / "harnesses" / "codex" / "hooks.json"
# The shared hooks directory holds the JSON reader every Sentinel reader uses.
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
from json_records import parse_json  # noqa: E402

# Every entry this installer writes contains this text; a later run finds its entries by it.
MISSING_HOOK_NOTICE = "Sentinel: $0 is missing. Run:"


def installer_command() -> str:
    """Return the installer's path with the version directory as a glob, so it names whichever copy is installed."""
    return str(PLUGIN_ROOT.parent / "*" / "harnesses" / "codex" / Path(__file__).name)


def guarded(command: str) -> str:
    """Return `command` run through `sh -c`, exiting 2 with the installer's command when its hook file is missing.

    Codex runs a hook command through the user's login shell, which may not be a
    POSIX shell; `sh -c` keeps the guard working under any of them.
    """
    hook, *arguments = shlex.split(command.replace("${PLUGIN_ROOT}", str(PLUGIN_ROOT)))
    script = (
        f'test -x "$0" || {{ echo "{MISSING_HOOK_NOTICE}" {shlex.quote(installer_command())} >&2; exit 2; }}; '
        'exec "$0" "$@"'
    )
    return shlex.join(["sh", "-c", script, hook, *arguments])


def linked_file(path: Path) -> Path:
    """Return the file a linked hook file ends at, so a link a dotfile manager keeps stays a link; exit when it ends at no file."""
    try:
        if not stat.S_ISLNK(path.lstat().st_mode):
            return path
    except FileNotFoundError:
        return path
    except OSError as error:
        sys.exit(f"Cannot reach {path}: {error}. Make its directory readable, then run this installer again.")
    fix = "Fix the link, then run this installer again."
    try:
        return path.resolve(strict=True)
    except (RuntimeError, OSError) as error:
        # Python before 3.13 raises RuntimeError for a loop; 3.13 raises OSError with ELOOP.
        if isinstance(error, RuntimeError) or error.errno == errno.ELOOP:
            sys.exit(f"{path} links to {path.readlink()}, and its links form a loop. {fix}")
        if error.errno == errno.ENOENT:
            sys.exit(f"{path} links to {_link_end(path)}, which does not exist. {fix}")
        sys.exit(f"{path} is a link, and following it fails: {error}. {fix}")


def _link_end(path: Path) -> Path:
    """Return the path a chain of links ends at, each relative target read from its link's directory."""
    seen = set()
    while path.is_symlink() and path not in seen:
        seen.add(path)
        path = path.parent / path.readlink()
    return path


def _default_mode() -> int:
    """Return the mode a new file gets from the process umask."""
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def write_hook_file(path: Path, data: dict, advice: str) -> None:
    """Replace `path` with `data` in one rename, keeping its permissions; exit with `advice` when it cannot be written.

    The rename means Codex never reads a half-written file. The staged file gets a
    new name of its own, so no file already beside `path` is followed or replaced,
    and it is removed however the write ends. A new file gets the umask's mode.
    A read-only `path` is left alone, though its directory would allow the rename.
    """
    unwritable = f"Cannot write {path}"
    if path.exists() and not os.access(path, os.W_OK):
        sys.exit(f"{unwritable}: it is read-only. {advice}")
    staged: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        staged = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2) + "\n")
        if path.exists():
            shutil.copymode(path, staged)
        else:
            staged.chmod(_default_mode())
        staged.replace(path)
        staged = None
    except OSError as error:
        sys.exit(f"{unwritable}: {error}. {advice}")
    finally:
        if staged is not None:
            with contextlib.suppress(OSError):
                staged.unlink()


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    """Build an object, raising `ValueError` on a repeated key, whose first value the rewrite would drop."""
    data: dict = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"it names {key!r} twice in one object")
        data[key] = value
    return data


def read_hook_file(path: Path) -> dict:
    """Return the parsed hook file, or an empty one when it does not exist; exit when it cannot be used."""
    if not path.exists():
        return {"hooks": {}}
    try:
        data = parse_json(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except (OSError, ValueError) as error:
        sys.exit(f"Cannot read {path}: {error}. Fix or move it, then run this installer again.")
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        sys.exit(f"{path} has no `hooks` object. Fix or move it, then run this installer again.")
    if not all(_is_group_list(groups) for groups in data.get("hooks", {}).values()):
        sys.exit(
            f"{path} has an event whose hook groups cannot be read. Fix or move it, then run this installer again."
        )
    return data


def _is_group_list(groups: object) -> bool:
    """Whether `groups` is a list of objects whose `hooks`, where present, is a list of handler objects."""
    if not isinstance(groups, list):
        return False
    for group in groups:
        if not isinstance(group, dict):
            return False
        handlers = group.get("hooks", [])
        if not isinstance(handlers, list) or not all(_is_handler(handler) for handler in handlers):
            return False
    return True


def _is_handler(handler: object) -> bool:
    """Whether `handler` is an object whose `command`, where present, is text."""
    return isinstance(handler, dict) and isinstance(handler.get("command", ""), str)


def without_sentinel(hooks: dict) -> dict:
    """Return `hooks` with every entry this installer wrote removed, and the groups and events that removal empties dropped.

    A group or an event that was already empty is the user's, so it is kept.
    """
    kept: dict = {}
    for event, groups in hooks.items():
        kept_groups = []
        for group in groups:
            existing = group.get("hooks", [])
            handlers = [handler for handler in existing if not _written_here(handler)]
            if handlers or not existing:
                kept_groups.append({**group, "hooks": handlers} if handlers else group)
        if kept_groups or not groups:
            kept[event] = kept_groups
    return kept


def _written_here(handler: dict) -> bool:
    """Whether a hook entry is one this installer wrote, which every guarded command marks."""
    return MISSING_HOOK_NOTICE in handler.get("command", "")


def sentinel_registration() -> dict:
    """Return the plugin's Codex registration, each command pointed at this copy and guarded; exit when it cannot be used."""
    try:
        return {
            event: [
                {**group, "hooks": [{**handler, "command": guarded(handler["command"])} for handler in group["hooks"]]}
                for group in groups
            ]
            for event, groups in parse_json(REGISTRATION.read_text(encoding="utf-8"))["hooks"].items()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        sys.exit(f"Cannot read {REGISTRATION}: {error!r}. Reinstall the plugin, then run this installer again.")


def sentinel_groups(hooks: dict) -> dict:
    """Return, for each event, the groups in `hooks` that hold an entry this installer wrote, in their order.

    Each group holds only the entries this installer wrote, so a user's hook placed in a group is not compared.
    """
    found: dict = {}
    for event, groups in hooks.items():
        for group in groups:
            written = [handler for handler in group.get("hooks", []) if _written_here(handler)]
            if written:
                found.setdefault(event, []).append({**group, "hooks": written})
    return found


def _unordered(groups_by_event: dict) -> dict:
    """Return each event's groups, and each group's handlers, in a canonical order.

    Two lists that hold the same groups of the same handlers then compare equal, in any order.
    """
    return {
        event: sorted(
            json.dumps(
                {
                    **group,
                    "hooks": sorted(group.get("hooks", []), key=lambda handler: json.dumps(handler, sort_keys=True)),
                },
                sort_keys=True,
            )
            for group in groups
        )
        for event, groups in groups_by_event.items()
    }


def installed(hooks: dict) -> dict:
    """Return `hooks` with this copy's registration in it.

    A file whose Sentinel groups already hold the registration's groups is returned as it is, in any
    order and wherever they sit, so a reinstall from the same copy keeps the order the user gave the hooks.
    Otherwise Sentinel's old groups are removed and the registration is added at the end of each event.
    """
    registration = sentinel_registration()
    if _unordered(sentinel_groups(hooks)) == _unordered(registration):
        return hooks
    kept = without_sentinel(hooks)
    for event, groups in registration.items():
        kept.setdefault(event, []).extend(groups)
    return kept


def main() -> None:
    """Install or, with `--uninstall`, remove Sentinel's entries in the user's Codex hook file."""
    parser = argparse.ArgumentParser(description="Write Sentinel's Codex hooks into $CODEX_HOME/hooks.json.")
    parser.add_argument("--uninstall", action="store_true", help="remove Sentinel's entries and keep every other hook")
    uninstall = parser.parse_args().uninstall
    if "/plugins/cache/" not in PLUGIN_ROOT.as_posix():
        sys.exit(f"{PLUGIN_ROOT} is not a plugin install location. Run the installer from the copy Codex installed.")

    hook_file = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "hooks.json"
    target = linked_file(hook_file)
    data = read_hook_file(target)
    current = data.get("hooks", {})
    hooks = without_sentinel(current) if uninstall else installed(current)
    where = str(target) if target == hook_file else f"{target}, which {hook_file} links to"
    # A run that changes nothing does not write, so it succeeds on a file it may not write
    # and creates no file the user never had.
    unchanged = hooks == current if target.exists() else not hooks
    if unchanged:
        print(f"{where} already holds {'none of ' if uninstall else ''}Sentinel's hooks. Nothing changed.")
        return
    data["hooks"] = hooks

    verb = "remove" if uninstall else "add"
    write_hook_file(target, data, f"Make it writable, or {verb} Sentinel's hooks where that file is managed.")
    if uninstall:
        print(f"Removed Sentinel's hooks from {where}.")
    else:
        print(f"Wrote Sentinel's hooks to {where}. Start Codex and trust them in /hooks.")


if __name__ == "__main__":
    main()
