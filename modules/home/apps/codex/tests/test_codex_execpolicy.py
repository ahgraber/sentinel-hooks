"""Behavior checks for the Codex command policy."""

import json
import subprocess
from pathlib import Path

RULES = Path(__file__).resolve().parents[1] / "rules" / "default.rules"


def check_policy(*command: str) -> dict:
    result = subprocess.run(
        ["codex", "execpolicy", "check", "--rules", str(RULES), *command],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_scoped_prek_runs_are_allowed():
    commands = (
        ("prek", "run", "--files", "README.md"),
        ("prek", "run", "-d", "modules/home/apps/codex"),
        ("prek", "run", "--glob", "*.toml"),
    )

    for command in commands:
        assert check_policy(*command)["decision"] == "allow"


def test_bare_prek_run_is_not_automatically_allowed():
    assert "decision" not in check_policy("prek", "run")


def test_network_clients_do_not_prompt_before_the_proxy_checks_the_domain():
    for command in (
        ("curl", "https://api.github.com"),
        ("wget", "https://example.com"),
    ):
        assert "decision" not in check_policy(*command)
