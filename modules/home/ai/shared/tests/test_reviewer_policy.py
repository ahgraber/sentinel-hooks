"""Every Codex reviewer policy must route a guardrail edit to the user, not refuse it.

Codex cannot honor a PreToolUse `ask`, so the tamper hook degrades to a refusal
and the only user-approval route left is the escalation prompt the reviewer
decides to raise. The policies are prose, so the assertions match on the phrases
that carry that decision — coarse, but the alternative is no check at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)
CODEX_CONFIGS = sorted(REPO_ROOT.glob("users/*/home-manager/codex/config*.toml"))


def reviewer_policy(config_path: Path) -> str:
    return tomllib.loads(config_path.read_text())["auto_review"]["policy"]


def test_configuration_files_are_discovered() -> None:
    """Guards the glob itself: an empty set would make every test below vacuous."""
    assert CODEX_CONFIGS, "found no Codex configuration files to check"


@pytest.mark.parametrize(
    "config_path", CODEX_CONFIGS, ids=lambda p: f"{p.parents[2].name}/{p.name}"
)
class TestGuardrailEditsReachTheUser:
    def test_the_reviewer_is_the_policy(self, config_path: Path) -> None:
        config = tomllib.loads(config_path.read_text())
        assert config.get("approvals_reviewer") == "auto_review", (
            f"{config_path.relative_to(REPO_ROOT)} does not route approvals "
            "through the policy these tests check"
        )

    def test_guardrail_modification_routes_to_user_authorization(
        self, config_path: Path
    ) -> None:
        policy = reviewer_policy(config_path)
        assert "USER_APPROVAL_REQUIRED" in policy, (
            f"{config_path.relative_to(REPO_ROOT)} has no USER_APPROVAL_REQUIRED "
            "routing at all"
        )
        clause = next(
            (
                line
                for line in policy.splitlines()
                if "security hooks" in line and "permission profiles" in line
            ),
            None,
        )
        assert clause is not None, (
            f"{config_path.relative_to(REPO_ROOT)} names no clause covering "
            "security-hook modification"
        )
        assert "USER_APPROVAL_REQUIRED" in clause, (
            f"{config_path.relative_to(REPO_ROOT)} denies guardrail modification "
            f"outright instead of routing it to the user:\n  {clause}"
        )

    def test_wholesale_bypass_is_still_refused(self, config_path: Path) -> None:
        """Routing the edit to the user must not soften disabling enforcement."""
        policy = reviewer_policy(config_path)
        for bypass in (
            "--no-verify",
            "features.hooks = false",
            'sandbox_mode = "danger-full-access"',
            ":danger-full-access",
        ):
            assert bypass in policy, (
                f"{config_path.relative_to(REPO_ROOT)} no longer names {bypass} "
                "as a wholesale bypass to refuse"
            )

    def test_the_escalation_path_is_carved_out_of_finality(
        self, config_path: Path
    ) -> None:
        """Without this, the finality clause auto-denies the escalation the
        routing above depends on, and the routing never fires."""
        clause = next(
            (
                line
                for line in reviewer_policy(config_path).splitlines()
                if "independent enforcement layers" in line
            ),
            None,
        )
        assert clause is not None, (
            f"{config_path.relative_to(REPO_ROOT)} names no enforcement-layer "
            "finality clause"
        )
        assert "escalation" in clause, (
            f"{config_path.relative_to(REPO_ROOT)} makes every layer's denial "
            f"final with no escalation carve-out, so a user-approved guardrail "
            f"edit is auto-denied:\n  {clause}"
        )
