from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
from types import ModuleType

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "flake.nix").is_file())
ADAPTER_PATH = REPO_ROOT / "modules" / "home" / "ai" / "copilot" / "hooks" / "copilot-vscode-hook-adapter.py"


def load_adapter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("copilot_hook_adapter", ADAPTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SECURITY_POLICY = REPO_ROOT / "modules/home/ai/copilot/hooks/security-policy.json"
ADAPTER_INVOCATION_RE = re.compile(r"copilot-vscode-hook-adapter\.py\s+([A-Za-z0-9._-]+)")


def test_configured_dispatch_targets_exist() -> None:
    """Each configured adapter invocation must resolve to a repository script."""
    adapter = load_adapter()
    invoked = set(ADAPTER_INVOCATION_RE.findall(SECURITY_POLICY.read_text()))

    assert invoked, "found no adapter invocations in security-policy.json"

    unknown = invoked - set(adapter.SCRIPT_PATHS)
    assert not unknown, f"security-policy.json invokes scripts the adapter cannot resolve: {sorted(unknown)}"
    missing = {name: str(adapter.SCRIPT_PATHS[name]) for name in invoked if not adapter.SCRIPT_PATHS[name].is_file()}
    assert not missing, f"configured adapter targets do not exist: {missing}"


class TestMultiPathFanOut:
    """A multi-path edit reaches every path, and only the hooks that need it.

    Fanning out `block-hook-tampering.py` would return on the first path's ask,
    so a credential later in the same edit would never be judged.
    """

    def test_the_tamper_hook_is_not_fanned_out(self) -> None:
        adapter = load_adapter()
        assert "block-hook-tampering.py" not in adapter.MULTI_PATH_TARGETS

    def test_a_fanned_out_call_carries_one_path(self, monkeypatch) -> None:
        """The list must not ride along, or each call judges the set again."""
        adapter = load_adapter()
        seen: list[dict] = []

        def record(_script, _args, payload):
            seen.append(payload["tool_input"])
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(adapter, "execute_hook", record)
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                json.dumps(
                    {
                        "tool_name": "editFiles",
                        "tool_input": {"filePaths": ["/tmp/one.txt", "/tmp/two.txt"]},
                    }
                )
            ),
        )
        monkeypatch.setattr("sys.argv", ["adapter", "block-sensitive-paths.py"])

        assert adapter.main() == 0
        assert [call["file_path"] for call in seen] == ["/tmp/one.txt", "/tmp/two.txt"]
        assert not any("file_paths" in call for call in seen)

    def test_a_mixed_class_multi_path_edit_refuses(self) -> None:
        """The credential wins over the enforcement path, whichever comes first."""
        payload = json.dumps(
            {
                "tool_name": "editFiles",
                "tool_input": {"filePaths": ["~/.claude/settings.json", "~/.codex/auth.json"]},
            }
        )
        result = subprocess.run(
            ["uv", "run", "--script", str(ADAPTER_PATH), "block-hook-tampering.py"],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 2, f"expected a refusal, got exit {result.returncode}\nstdout: {result.stdout}"
        assert result.stdout == "", "a refusal must write nothing to stdout"
        assert "credential" in result.stderr.lower()


def test_ask_response_passes_through_intact(monkeypatch, capsys) -> None:
    """An ask survives the adapter: exit code preserved, JSON parseable after rewrite."""
    adapter = load_adapter()
    ask_json = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    "Claude Code may not change this enforcement file without your approval."
                ),
            }
        }
    )
    hook_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=ask_json, stderr="")
    monkeypatch.setattr(adapter, "execute_hook", lambda *args, **kwargs: hook_result)

    exit_code = adapter.run_hook("block-hook-tampering.py", [], {"tool_name": "Write"})

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert payload["permissionDecision"] == "ask"
    assert "Copilot" in payload["permissionDecisionReason"]
    assert "Claude" not in payload["permissionDecisionReason"]
