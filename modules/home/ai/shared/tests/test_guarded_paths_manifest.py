"""The manifest itself, and the Python hooks' posture toward it.

`guarded-paths.toml` is the single declaration source `block-hook-tampering.py`
and `block-sensitive-paths.py` both read at invocation.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
MANIFEST = HOOKS_DIR / "guarded-paths.toml"

_ACCEPTED_PREFIXES = ("~/", "<repo>/")


def load_hook(name: str):
    """Import a hook by location; its filename is not a valid identifier."""
    spec = importlib.util.spec_from_file_location(name, HOOKS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec.loader.exec_module(module)
    return module


def _all_path_entries(manifest: dict) -> list[str]:
    """Every declared path string in the manifest, flattened.

    An instruction-layer pair's second element is a fragment appended to the
    first, not a path in its own right, so only the location half is collected.
    """
    entries: list[str] = []
    gated = manifest["gated"]
    entries += gated["deployed"] + gated["sources"]
    entries += manifest["credentials"]["paths"]
    entries += [
        location for location, _layer in manifest["instruction-layers"]["layers"]
    ]
    entries += manifest["location-only"]["paths"]
    entries += manifest["secret-floor"]["paths"]
    return entries


class TestManifestShape:
    def test_parses_with_tomllib(self) -> None:
        with open(MANIFEST, "rb") as handle:
            manifest = tomllib.load(handle)
        assert manifest

    def test_every_section_is_present(self) -> None:
        with open(MANIFEST, "rb") as handle:
            manifest = tomllib.load(handle)
        for section in (
            "gated",
            "credentials",
            "instruction-layers",
            "location-only",
            "secret-floor",
            "exceptions",
        ):
            assert section in manifest, f"manifest is missing [{section}]"

    def test_every_entry_uses_accepted_notation(self) -> None:
        with open(MANIFEST, "rb") as handle:
            manifest = tomllib.load(handle)
        for entry in _all_path_entries(manifest):
            assert entry.startswith(_ACCEPTED_PREFIXES) or "*" in entry, (
                f"'{entry}' uses neither ~/, <repo>/, nor glob notation"
            )

    def test_exceptions_name_a_surface_and_a_pattern(self) -> None:
        with open(MANIFEST, "rb") as handle:
            manifest = tomllib.load(handle)
        for exception in manifest["exceptions"]:
            assert exception["surface"]
            assert exception["pattern"]
            assert exception["why"]


class TestManifestGuardsItself:
    def test_the_manifest_is_a_guarded_location(self) -> None:
        hook = load_hook("block-hook-tampering")
        assert hook.is_protected_path(str(MANIFEST)) is True

    def test_a_mutation_of_the_manifest_asks_under_claude(self) -> None:
        result = subprocess.run(
            ["python3", str(HOOKS_DIR / "block-hook-tampering.py")],
            input=(
                '{"tool_name":"Edit","tool_input":{"file_path":'
                + f'"{MANIFEST}"'
                + "},"
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
        with open(MANIFEST, "rb") as handle:
            return tomllib.load(handle)["credentials"]["paths"]

    def test_every_credential_path_is_zero_access(
        self, credential_paths: list[str]
    ) -> None:
        hook = load_hook("block-sensitive-paths")
        for path in credential_paths:
            assert hook.should_block(path) is True, f"{path} is not zero-access"


class TestTemporaryManifestCopy:
    """A class addition in a substituted manifest reaches the hook with no code edit."""

    @pytest.fixture
    def substituted_manifest(self, tmp_path: Path) -> Path:
        original = tomllib.loads(MANIFEST.read_text())
        original["credentials"]["paths"].append("~/.example/new-credential.json")
        copy = tmp_path / "guarded-paths.toml"
        copy.write_text(_dump_minimal_toml(original))
        # A copy that does not parse would make every assertion below pass for
        # the wrong reason: the hook reports the load failure and guards nothing.
        tomllib.loads(copy.read_text())
        return copy

    def test_the_added_path_is_guarded(self, substituted_manifest: Path) -> None:
        hook = load_hook("block-hook-tampering")
        _guarded, credentials, *_rest = hook.build_guarded(substituted_manifest)
        assert credentials.contains("~/.example/new-credential.json") is True

    def test_an_unrelated_path_stays_unguarded(
        self, substituted_manifest: Path
    ) -> None:
        hook = load_hook("block-hook-tampering")
        _guarded, credentials, *_rest = hook.build_guarded(substituted_manifest)
        assert credentials.contains("~/.example/other-file.json") is False


def _quote(value: str) -> str:
    """A TOML basic string. An exception's `why` is prose and carries quotes."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _dump_minimal_toml(data: dict) -> str:
    """Serialise the subset of TOML this manifest uses. No stdlib TOML writer exists."""
    lines = []
    for section, value in data.items():
        if section == "exceptions":
            for table in value:
                lines.append("[[exceptions]]")
                for key, val in table.items():
                    lines.append(f"{key} = {_quote(val)}")
            continue
        lines.append(f"[{section}]")
        for key, val in value.items():
            if key == "layers":
                pairs = ", ".join(
                    "[" + ", ".join(_quote(item) for item in pair) + "]" for pair in val
                )
                lines.append(f"{key} = [{pairs}]")
            else:
                items = ", ".join(_quote(item) for item in val)
                lines.append(f"{key} = [{items}]")
    return "\n".join(lines) + "\n"


class TestManifestLoadFailure:
    """A hook that cannot load its declarations proceeds, and says so.

    Run from a copy of the hooks directory: the live tamper hook is active on
    every tool call this suite runs under and must not be broken.
    """

    @pytest.fixture
    def hooks_copy(self, tmp_path: Path) -> Path:
        copy = tmp_path / "hooks"
        shutil.copytree(HOOKS_DIR, copy)
        return copy

    def _run(
        self, hooks_copy: Path, hook_name: str, payload: str
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(hooks_copy / f"{hook_name}.py")],
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_tamper_hook_proceeds_and_reports_when_manifest_is_missing(
        self, hooks_copy: Path
    ) -> None:
        (hooks_copy / "guarded-paths.toml").unlink()
        payload = (
            '{"tool_name":"Write","tool_input":{"file_path":"~/.claude/settings.json"},'
            '"transcript_path":"/tmp/t.jsonl"}'
        )
        result = self._run(hooks_copy, "block-hook-tampering", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stderr
        assert "not checked" in result.stderr

    def test_sensitive_paths_hook_proceeds_and_reports_when_manifest_is_missing(
        self, hooks_copy: Path
    ) -> None:
        (hooks_copy / "guarded-paths.toml").unlink()
        payload = '{"tool_name":"Read","tool_input":{"file_path":"/tmp/notes.txt"}}'
        result = self._run(hooks_copy, "block-sensitive-paths", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stderr
        assert "not checked" in result.stderr

    def test_tamper_hook_stays_quiet_on_a_tool_it_never_judges(
        self, hooks_copy: Path
    ) -> None:
        """The registration covers Read, so reporting a broken manifest there
        would put a failure notice on every read of the session."""
        (hooks_copy / "guarded-paths.toml").unlink()
        payload = (
            '{"tool_name":"Read","tool_input":{"file_path":"/tmp/notes.txt"},'
            '"transcript_path":"/tmp/t.jsonl"}'
        )
        result = self._run(hooks_copy, "block-hook-tampering", payload)
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

    def test_tamper_hook_proceeds_and_reports_when_manifest_is_unparsable(
        self, hooks_copy: Path
    ) -> None:
        (hooks_copy / "guarded-paths.toml").write_text("not [ valid toml")
        payload = (
            '{"tool_name":"Write","tool_input":{"file_path":"~/.claude/settings.json"},'
            '"transcript_path":"/tmp/t.jsonl"}'
        )
        result = self._run(hooks_copy, "block-hook-tampering", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stderr
        assert "not checked" in result.stderr

    def test_sensitive_paths_hook_proceeds_and_reports_when_manifest_is_unparsable(
        self, hooks_copy: Path
    ) -> None:
        (hooks_copy / "guarded-paths.toml").write_text("not [ valid toml")
        payload = '{"tool_name":"Read","tool_input":{"file_path":"/tmp/notes.txt"}}'
        result = self._run(hooks_copy, "block-sensitive-paths", payload)
        assert result.returncode in (0, 1)
        assert "guarded-paths.toml" in result.stderr
        assert "not checked" in result.stderr
