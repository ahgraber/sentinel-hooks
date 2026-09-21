"""Guarded declarations do not impose a permission-list or sandbox floor."""

from pathlib import Path
import runpy

import conformance
from guarded_paths import PathPolicy


def test_guarded_declaration_with_no_floor_entry_passes(tmp_path, monkeypatch):
    manifest = {
        "guarded": {"paths": ["~/new-agent/"]},
        "block": {"paths": []},
        "exec-through": {"paths": []},
        "write-through": {"paths": []},
        "exceptions": [],
    }
    policy = PathPolicy(manifest, manifest_path=tmp_path / "guarded-paths.toml")

    assert policy.findings == []
    assert policy.verdict("~/new-agent/settings", "write") == "guarded"

    monkeypatch.setattr(conformance, "load_manifest", lambda: manifest)
    suite = runpy.run_path(str(Path(__file__).with_name("test_secret_floor_declarations.py")))
    for floor_path in suite["SECRET_FLOOR"]:
        for settings_path in suite["CLAUDE_SETTINGS"]:
            suite["test_claude_permission_layer_refuses_the_floor"](settings_path, floor_path)
            suite["test_claude_sandbox_layer_refuses_the_floor"](settings_path, floor_path)
        for config_path in suite["CODEX_CONFIGS"]:
            suite["test_codex_sandbox_refuses_the_floor"](config_path, floor_path)
