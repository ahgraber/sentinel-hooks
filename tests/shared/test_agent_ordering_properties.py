"""An agent that cannot show a prompt is never allowed more than one that can.

Claude can show a prompt for every tool, Copilot for some, and Codex and an
unknown agent for none. Each verdict runs through `respond` and `supports_ask`,
so an ask turns into a refusal where no prompt exists. This property holds that
for every generated call; `.specs/WHEN-CODEX-CAN-ASK.md` names it as the check
to keep when an agent gains a prompt.
"""

from __future__ import annotations

from hook_chain import RANK, verdicts
from hypothesis import HealthCheck, given, settings, strategies as st
from shell_strategies import commands, paths

PROMPTLESS = ["codex", "copilot", "unknown"]
CREDENTIAL = "~/.codex/auth.json"


def calls() -> st.SearchStrategy[dict]:
    """A Bash call or a file-tool call, over guarded, credential, and ordinary paths."""
    targets = st.one_of(paths(), st.just(CREDENTIAL))
    bash = st.builds(lambda command: {"tool_name": "Bash", "tool_input": {"command": command}}, commands())
    files = st.builds(
        lambda tool, path: {"tool_name": tool, "tool_input": {"file_path": path, "content": "x"}},
        st.sampled_from(["Read", "Write", "Edit"]),
        targets,
    )
    return st.one_of(bash, files)


@given(call=calls())
@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_a_promptless_agent_is_never_allowed_more_than_claude(tmp_path_factory, call: dict) -> None:
    root = tmp_path_factory.mktemp("agents")
    (root / "home").mkdir()
    (root / "repo/.git").mkdir(parents=True)

    reached = verdicts(call, ["claude", *PROMPTLESS], root / "home", root / "repo")

    for agent in PROMPTLESS:
        assert RANK[reached[agent]] >= RANK[reached["claude"]], f"{agent} {reached}: {call}"
