"""A user's agents must reach the same set of hosts without asking.

Claude Code and Codex each carry their own automatic network allowlist, in
different files and different notation. When the two drift, the same fetch
succeeds silently under one agent and stops for approval under the other, which
reads as a broken tool rather than as a policy difference.

Parity is asserted per user, not repository-wide: a work profile allows the
package registries that profile needs, and holding it to a personal profile's
list would assert the wrong thing. A user with no Codex configuration is
unconstrained here.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest
import tomllib
from conformance import CLAUDE_SETTINGS, CODEX_CONFIGS, REPO_ROOT


def owner(path: Path) -> str:
    """The user directory a settings file belongs to."""
    return path.parents[2].name


def claude_domains(settings_path: Path) -> set[str]:
    settings = json.loads(settings_path.read_text())
    return set(settings.get("sandbox", {}).get("network", {}).get("allowedDomains", []))


def codex_domains(config_path: Path) -> set[str]:
    config = tomllib.loads(config_path.read_text())
    domains = config["permissions"]["guarded_workspace"]["network"]["domains"]
    return {domain for domain, mode in domains.items() if mode == "allow"}


def by_owner(paths: list[Path]) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        grouped[owner(path)].append(path)
    return grouped


CLAUDE_BY_OWNER = by_owner(CLAUDE_SETTINGS)
CODEX_BY_OWNER = by_owner(CODEX_CONFIGS)
PAIRED_OWNERS = sorted(CLAUDE_BY_OWNER.keys() & CODEX_BY_OWNER.keys())


def test_paired_owners_are_discovered() -> None:
    """Guards the pairing: an empty set would make every test below vacuous."""
    assert PAIRED_OWNERS, "found no user with both Claude and Codex configuration"


@pytest.mark.parametrize("user", PAIRED_OWNERS)
class TestAllowlistsAgree:
    @staticmethod
    def _report(paths: list[Path], reader) -> str:
        return "\n".join(
            f"  {path.relative_to(REPO_ROOT)}: {sorted(reader(path))}" for path in paths
        )

    def test_every_claude_file_declares_the_same_set(self, user: str) -> None:
        """The platform files split on paths and prose, never on reachable hosts."""
        paths = CLAUDE_BY_OWNER[user]
        sets = {frozenset(claude_domains(path)) for path in paths}
        assert len(sets) == 1, (
            f"{user}'s Claude settings files disagree on allowedDomains:\n"
            f"{self._report(paths, claude_domains)}"
        )

    def test_every_codex_file_declares_the_same_set(self, user: str) -> None:
        paths = CODEX_BY_OWNER[user]
        sets = {frozenset(codex_domains(path)) for path in paths}
        assert len(sets) == 1, (
            f"{user}'s Codex configs disagree on network.domains:\n"
            f"{self._report(paths, codex_domains)}"
        )

    def test_the_two_agents_declare_the_same_set(self, user: str) -> None:
        claude = claude_domains(CLAUDE_BY_OWNER[user][0])
        codex = codex_domains(CODEX_BY_OWNER[user][0])
        assert claude == codex, (
            f"{user}'s agents reach different hosts without asking; "
            f"Claude only: {sorted(claude - codex)}, Codex only: {sorted(codex - claude)}"
        )
