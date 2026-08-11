#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Codex hook: run pre-commit/prek after apply_patch edits."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PATCH_FILE_RE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (?P<path>.+)$", re.MULTILINE
)


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for path in (current, *current.parents):
        if (path / ".git").exists():
            return path
    return current


def has_precommit_config(root: Path) -> bool:
    return (root / ".pre-commit-config.yaml").is_file() or (
        root / ".pre-commit-config.yml"
    ).is_file()


def extract_patch_paths(tool_input: object) -> list[str]:
    if not isinstance(tool_input, dict):
        return []
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return []
    return [match.group("path").strip() for match in PATCH_FILE_RE.finditer(command)]


def existing_repo_files(root: Path, paths: list[str]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()

    for raw in paths:
        if not raw or raw.startswith("/"):
            continue
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        rel = str(candidate.relative_to(root))
        if rel not in seen:
            seen.add(rel)
            files.append(rel)

    return files


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    if data.get("tool_name") != "apply_patch":
        sys.exit(0)

    cwd = Path(data.get("cwd") or os.getcwd())
    root = find_repo_root(cwd)
    if not has_precommit_config(root):
        sys.exit(0)

    files = existing_repo_files(root, extract_patch_paths(data.get("tool_input")))
    if not files:
        sys.exit(0)

    runner = "prek"
    if (
        subprocess.run(
            ["/usr/bin/env", "bash", "-lc", "command -v prek >/dev/null"],
            cwd=root,
            check=False,
        ).returncode
        != 0
    ):
        runner = "pre-commit"
        if (
            subprocess.run(
                ["/usr/bin/env", "bash", "-lc", "command -v pre-commit >/dev/null"],
                cwd=root,
                check=False,
            ).returncode
            != 0
        ):
            sys.exit(0)

    result = subprocess.run([runner, "run", "--files", *files], cwd=root, check=False)
    if result.returncode != 0:
        sys.stderr.write(f"{runner} failed for edited files: {', '.join(files)}\n")
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"codex-posttooluse-precommit failed: {exc}\n")
        sys.exit(0)
