"""Validates: OneVersionAcrossManifests, at the release script that writes each component's version.

`scripts/release.sh` runs in a scratch repository holding copies of the files it
edits. `prek` and `uv` are stubbed: they check the result, and the test checks it
here instead.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from hermetic import REPO_ROOT
import pytest

PLUGIN_FILES = (
    "plugins/sentinel/.claude-plugin/plugin.json",
    "plugins/sentinel/plugin.json",
    "package.json",
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
    ".github/plugin/marketplace.json",
)
PI_FILES = ("extensions/pi/package.json",)
COPIED = (
    "scripts/release.sh",
    "scripts/lib/common.sh",
    "CHANGELOG.md",
    "extensions/pi/CHANGELOG.md",
    *PLUGIN_FILES,
    *PI_FILES,
)
COMPONENTS = {
    "plugin": ("plugin-v", "CHANGELOG.md", PLUGIN_FILES, PI_FILES),
    "pi": ("pi-v", "extensions/pi/CHANGELOG.md", PI_FILES, PLUGIN_FILES),
}


def version_of(repo: Path, file: str) -> str:
    data = json.loads((repo / file).read_text())
    if file.endswith("marketplace.json"):
        return next(plugin["version"] for plugin in data["plugins"] if plugin["name"] == "sentinel")
    return data["version"]


@pytest.fixture
def scratch(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    for file in COPIED:
        (repo / file).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / file, repo / file)
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name in ("prek", "uv"):
        (stubs / name).write_text("#!/bin/sh\nexit 0\n")
        (stubs / name).chmod(0o755)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Release Test\n\temail = release@example.invalid\n")
    env = {
        **os.environ,
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True)
    return repo, env


@pytest.mark.parametrize("component", COMPONENTS)
def test_a_release_sets_one_components_version_and_tags_it(scratch, component) -> None:
    repo, env = scratch
    prefix, changelog, owned, other = COMPONENTS[component]
    others_before = {file: version_of(repo, file) for file in other}

    subprocess.run(["bash", "scripts/release.sh", component, "9.8.7"], cwd=repo, env=env, check=True, timeout=60)

    assert {file: version_of(repo, file) for file in owned} == dict.fromkeys(owned, "9.8.7")
    assert {file: version_of(repo, file) for file in other} == others_before
    text = (repo / changelog).read_text()
    assert re.search(r"^## \[Unreleased\]\n\n## \[9\.8\.7\] - \d{4}-\d{2}-\d{2}$", text, re.MULTILINE)
    assert f"[Unreleased]: https://github.com/ahgraber/sentinel-hooks/compare/{prefix}9.8.7...HEAD" in text
    assert f"[9.8.7]: https://github.com/ahgraber/sentinel-hooks/releases/tag/{prefix}9.8.7" in text

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True).stdout

    assert git("status", "--porcelain") == ""
    assert git("cat-file", "-t", f"{prefix}9.8.7").strip() == "tag"
    assert git("rev-parse", f"{prefix}9.8.7^{{commit}}") == git("rev-parse", "HEAD")
