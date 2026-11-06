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
import json
import os
from pathlib import Path
import shlex
import sys

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REGISTRATION = PLUGIN_ROOT / "harnesses" / "codex" / "hooks.json"
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


def read_hook_file(path: Path) -> dict:
    """Return the parsed hook file, or an empty one when it does not exist; exit when it cannot be used."""
    if not path.exists():
        return {"hooks": {}}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        sys.exit(f"Cannot read {path}: {error}. Fix or move it, then run this installer again.")
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        sys.exit(f"{path} has no `hooks` object. Fix or move it, then run this installer again.")
    return data


def without_sentinel(hooks: dict) -> dict:
    """Return `hooks` with every entry this installer wrote removed, and groups left empty dropped."""
    kept: dict = {}
    for event, groups in hooks.items():
        for group in groups:
            handlers = [h for h in group.get("hooks", []) if MISSING_HOOK_NOTICE not in h.get("command", "")]
            if handlers:
                kept.setdefault(event, []).append({**group, "hooks": handlers})
    return kept


def main() -> None:
    """Install or, with `--uninstall`, remove Sentinel's entries in the user's Codex hook file."""
    parser = argparse.ArgumentParser(description="Write Sentinel's Codex hooks into $CODEX_HOME/hooks.json.")
    parser.add_argument("--uninstall", action="store_true", help="remove Sentinel's entries and keep every other hook")
    uninstall = parser.parse_args().uninstall
    if "/plugins/cache/" not in PLUGIN_ROOT.as_posix():
        sys.exit(f"{PLUGIN_ROOT} is not a plugin install location. Run the installer from the copy Codex installed.")

    target = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "hooks.json"
    data = read_hook_file(target)
    hooks = without_sentinel(data.get("hooks", {}))
    if not uninstall:
        for event, groups in json.loads(REGISTRATION.read_text())["hooks"].items():
            for group in groups:
                handlers = [{**handler, "command": guarded(handler["command"])} for handler in group["hooks"]]
                hooks.setdefault(event, []).append({**group, "hooks": handlers})
    data["hooks"] = hooks

    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(f"{target.name}.tmp")
    staged.write_text(json.dumps(data, indent=2) + "\n")
    staged.replace(target)
    if uninstall:
        print(f"Removed Sentinel's hooks from {target}.")
    else:
        print(f"Wrote Sentinel's hooks to {target}. Start Codex and trust them in /hooks.")


if __name__ == "__main__":
    main()
