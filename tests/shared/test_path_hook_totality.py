"""Both path hooks reach a verdict by their rules for any command text, never by an error.

The lexer properties cover `shell_words` alone. These drive each hook end to
end, so an error the hook raises after the lexer returns is caught too.
"""

from __future__ import annotations

import contextlib
import io
import json

from hermetic import load_hook
from hypothesis import given, settings, strategies as st
import pytest
from shell_strategies import commands

HOOKS = {name: load_hook(name) for name in ("block-hook-tampering", "block-sensitive-paths")}
TEXT = st.one_of(st.text(max_size=200), commands())


def _run(hook, command: str, cwd: str) -> str:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    out, err = io.StringIO(), io.StringIO()
    hook.sys.stdin = io.StringIO(json.dumps(payload))
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), contextlib.suppress(SystemExit):
        hook.main()
    return out.getvalue() + err.getvalue()


@pytest.mark.parametrize("name", sorted(HOOKS))
@settings(max_examples=150, deadline=None)
@given(command=TEXT)
def test_arbitrary_text_reaches_a_verdict_by_the_rules(name, command, tmp_path_factory):
    output = _run(HOOKS[name], command, str(tmp_path_factory.getbasetemp()))
    assert "failed while checking" not in output
