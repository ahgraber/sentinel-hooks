"""The manifest itself, and the Python hooks' posture toward it.

`guarded-paths.toml` is the single declaration source `block-hook-tampering.py`
and `block-sensitive-paths.py` both read at invocation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from guarded_paths import ManifestError, load_manifest
from hermetic import load_hook
import pytest
import tomllib

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
MANIFEST = HOOKS_DIR / "guarded-paths.toml"

_ACCEPTED_PREFIXES = ("~/", "<repo>/")


def _all_path_entries(manifest: dict) -> list[str]:
    """Every path in the four policy classes."""
    return [path for name in ("guarded", "block", "exec-through", "write-through") for path in manifest[name]["paths"]]


class TestManifestShape:
    def test_parses_with_tomllib(self) -> None:
        with open(MANIFEST, "rb") as handle:
            manifest = tomllib.load(handle)
        assert manifest

    def test_every_section_is_present(self) -> None:
        with open(MANIFEST, "rb") as handle:
            manifest = tomllib.load(handle)
        assert set(manifest) == {
            "guarded",
            "block",
            "exec-through",
            "write-through",
            "exceptions",
        }

    def test_every_entry_uses_accepted_notation(self) -> None:
        for entry in _all_path_entries(load_manifest(MANIFEST)):
            assert entry.startswith(_ACCEPTED_PREFIXES) or "*" in entry, (
                f"'{entry}' uses neither ~/, <repo>/, nor glob notation"
            )

    def test_a_path_with_no_reason_does_not_load(self, tmp_path: Path) -> None:
        manifest = tmp_path / "guarded-paths.toml"
        manifest.write_text(MANIFEST.read_text().replace('reason = "Codex\'s stored credentials"', ""))
        with pytest.raises(ManifestError, match="`path`, `reason`"):
            load_manifest(manifest)

    def test_exceptions_name_a_surface_and_a_pattern(self) -> None:
        with open(MANIFEST, "rb") as handle:
            manifest = tomllib.load(handle)
        for exception in manifest["exceptions"]:
            assert exception["surface"]
            assert exception["pattern"]
            assert exception["reason"]


class TestManifestGuardsItself:
    def test_the_manifest_is_a_guarded_location(self) -> None:
        hook = load_hook("block-hook-tampering")
        assert hook.is_protected_path(str(MANIFEST)) is True

    def test_a_mutation_of_the_manifest_asks_under_claude(self) -> None:
        result = subprocess.run(
            ["python3", str(HOOKS_DIR / "block-hook-tampering.py")],
            input=(
                '{"tool_name":"Edit","tool_input":{"file_path":' + f'"{MANIFEST}"' + "},"
                '"transcript_path":"/tmp/t.jsonl"}'
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0
        assert '"permissionDecision": "ask"' in result.stdout
        assert "enforcement" in result.stdout


class TestSensitivePathsCredentialCoverage:
    """Every manifest credential path is zero-access through block-sensitive-paths.py."""

    @staticmethod
    @pytest.fixture(scope="class")
    def credential_paths() -> list[str]:
        return load_manifest(MANIFEST)["block"]["paths"]

    def test_every_credential_path_is_zero_access(self, credential_paths: list[str]) -> None:
        hook = load_hook("block-sensitive-paths")
        for path in credential_paths:
            assert hook.should_block(path) is True, f"{path} is not zero-access"


class TestTemporaryManifestCopy:
    """A class addition in a substituted manifest reaches the hook with no code edit."""

    @pytest.fixture
    def substituted_manifest(self, tmp_path: Path) -> Path:
        original = load_manifest(MANIFEST)
        original["block"]["paths"].append("~/.example/new-credential.json")
        copy = tmp_path / "guarded-paths.toml"
        copy.write_text(_dump_minimal_toml(original))
        # A copy that does not parse would make every assertion below pass for
        # the wrong reason: the hook reports the load failure and guards nothing.
        tomllib.loads(copy.read_text())
        return copy

    def test_the_added_path_is_guarded(self, substituted_manifest: Path) -> None:
        hook = load_hook("block-hook-tampering")
        policy = hook.load_policy(substituted_manifest)
        assert policy.error is None
        credentials = policy.classes["block"]
        assert bool(credentials.contains("~/.example/new-credential.json")) is True

    def test_an_unrelated_path_stays_unguarded(self, substituted_manifest: Path) -> None:
        hook = load_hook("block-hook-tampering")
        policy = hook.load_policy(substituted_manifest)
        assert policy.error is None
        credentials = policy.classes["block"]
        assert bool(credentials.contains("~/.example/other-file.json")) is False


class TestReadAndExecAreSeparateClasses:
    """A guarded location is not runnable unless it is also exec-through."""

    @pytest.fixture
    def readable_only(self, tmp_path: Path) -> Path:
        original = load_manifest(MANIFEST)
        original["guarded"]["paths"].append("~/.example/readable/")
        copy = tmp_path / "guarded-paths.toml"
        copy.write_text(_dump_minimal_toml(original))
        tomllib.loads(copy.read_text())
        return copy

    def test_the_added_location_is_readable(self, readable_only: Path) -> None:
        hook = load_hook("block-hook-tampering")
        policy = hook.load_policy(readable_only)
        assert policy.error is None
        assert policy.verdict("~/.example/readable/helper.sh", "read") == "undeclared"

    def test_the_added_location_is_not_exec_through(self, readable_only: Path) -> None:
        hook = load_hook("block-hook-tampering")
        policy = hook.load_policy(readable_only)
        assert policy.error is None
        assert policy.verdict("~/.example/readable/helper.sh", "run") == "guarded"


def _quote(value: str) -> str:
    """A TOML basic string. An exception's `why` is prose and carries quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def _dump_minimal_toml(data: dict) -> str:
    """Serialize a loaded manifest back to its record form. No stdlib TOML writer exists."""
    lines = []
    for section, value in data.items():
        if section == "exceptions":
            for table in value:
                lines.append("[[exceptions]]")
                lines.extend(f"{key} = {_quote(val)}" for key, val in table.items())
            continue
        lines.append(f"[{section}]")
        for path in value["paths"]:
            lines += [f"[[{section}.paths]]", f"path = {_quote(path)}", 'reason = "test"']
    return "\n".join(lines) + "\n"


class TestManifestLoadFailure:
    """Manifest failures gate mutations and preserve independent sensitive rules.

    Run from a copy of the hooks directory: the live tamper hook is active on
    every tool call this suite runs under and must not be broken.
    """

    @pytest.fixture
    def hooks_copy(self, tmp_path: Path) -> Path:
        copy = tmp_path / "hooks"
        shutil.copytree(HOOKS_DIR, copy)
        return copy

    @pytest.mark.parametrize("defect", ["absent", "unparsable", "missing-table"])
    @pytest.mark.parametrize("agent", ["claude", "codex", "copilot"])
    @pytest.mark.parametrize("tool", ["Read", "Write", "Bash"])
    def test_failure_matches_tool_and_agent(self, hooks_copy, defect, agent, tool):
        manifest = hooks_copy / "guarded-paths.toml"
        if defect == "absent":
            manifest.unlink()
        elif defect == "unparsable":
            manifest.write_text("invalid [ toml")
        else:
            data = load_manifest(manifest)
            del data["block"]
            manifest.write_text(_dump_minimal_toml(data))
        result = subprocess.run(
            [sys.executable, str(hooks_copy / "block-hook-tampering.py")],
            input=json.dumps(
                {
                    "tool_name": tool,
                    "tool_input": {
                        "file_path": "/tmp/ordinary",
                        "command": "echo ordinary",
                    },
                }
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={**os.environ, "AI_HOOK_AGENT": agent},
        )

        assert "guarded-paths.toml" in result.stdout + result.stderr
        if tool == "Read":
            assert result.returncode in (0, 1)
        elif agent == "claude" or (agent == "copilot" and tool == "Write"):
            assert result.returncode == 0
            assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"
        else:
            assert result.returncode == 2

    def _run(self, hooks_copy: Path, hook_name: str, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(hooks_copy / f"{hook_name}.py")],
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_sensitive_block_list_survives_an_unrelated_missing_table(self, hooks_copy):
        manifest = hooks_copy / "guarded-paths.toml"
        data = load_manifest(manifest)
        del data["exceptions"]
        manifest.write_text(_dump_minimal_toml(data))
        result = self._run(
            hooks_copy,
            "block-sensitive-paths",
            json.dumps({"tool_name": "Read", "tool_input": {"file_path": "~/.codex/auth.json"}}),
        )
        assert result.returncode == 2
        assert "guarded-paths.toml" in result.stderr

    @pytest.mark.parametrize("tool", ["Read", "Write", "Bash"])
    def test_sensitive_rules_survive_manifest_failure(self, hooks_copy, tool):
        (hooks_copy / "guarded-paths.toml").unlink()
        result = self._run(
            hooks_copy,
            "block-sensitive-paths",
            json.dumps(
                {
                    "tool_name": tool,
                    "tool_input": {
                        "file_path": "/tmp/id_rsa",
                        "command": "cat /tmp/id_rsa",
                    },
                }
            ),
        )
        assert result.returncode == 2
        assert "guarded-paths.toml" in result.stderr
        assert "zero-access" in result.stderr

    def test_tamper_hook_proceeds_and_reports_when_manifest_is_missing(self, hooks_copy: Path) -> None:
        (hooks_copy / "guarded-paths.toml").unlink()
        payload = (
            '{"tool_name":"Write","tool_input":{"file_path":"~/.claude/settings.json"},'
            '"transcript_path":"/tmp/t.jsonl"}'
        )
        result = self._run(hooks_copy, "block-hook-tampering", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stdout
        assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_sensitive_paths_hook_proceeds_and_reports_when_manifest_is_missing(self, hooks_copy: Path) -> None:
        (hooks_copy / "guarded-paths.toml").unlink()
        payload = '{"tool_name":"Read","tool_input":{"file_path":"/tmp/notes.txt"}}'
        result = self._run(hooks_copy, "block-sensitive-paths", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stderr
        assert "strong rules" in result.stderr

    def test_tamper_hook_stays_quiet_on_a_tool_it_never_judges(self, hooks_copy: Path) -> None:
        """Unregistered tools do not load policy."""
        (hooks_copy / "guarded-paths.toml").unlink()
        payload = '{"tool_name":"Glob","tool_input":{"file_path":"/tmp/notes.txt"},"transcript_path":"/tmp/t.jsonl"}'
        result = self._run(hooks_copy, "block-hook-tampering", payload)
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

    def test_tamper_hook_proceeds_and_reports_when_manifest_is_unparsable(self, hooks_copy: Path) -> None:
        (hooks_copy / "guarded-paths.toml").write_text("not [ valid toml")
        payload = (
            '{"tool_name":"Write","tool_input":{"file_path":"~/.claude/settings.json"},'
            '"transcript_path":"/tmp/t.jsonl"}'
        )
        result = self._run(hooks_copy, "block-hook-tampering", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stdout
        assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_sensitive_paths_hook_proceeds_and_reports_when_manifest_is_unparsable(self, hooks_copy: Path) -> None:
        (hooks_copy / "guarded-paths.toml").write_text("not [ valid toml")
        payload = '{"tool_name":"Read","tool_input":{"file_path":"/tmp/notes.txt"}}'
        result = self._run(hooks_copy, "block-sensitive-paths", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stderr
        assert "strong rules" in result.stderr
