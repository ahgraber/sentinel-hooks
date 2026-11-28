"""Sentinel finds the Pi extensions a package loads the way Pi reads `package.json`."""

import json
from pathlib import Path

import json_records
import pytest


def _package(root: Path, pi: dict | None) -> Path:
    (root / "extensions" / "pi").mkdir(parents=True)
    (root / "extensions" / "pi" / "index.ts").write_text("")
    (root / "other").mkdir()
    (root / "other" / "runner.ts").write_text("")
    manifest = {"name": "example"} if pi is None else {"name": "example", "pi": pi}
    (root / "package.json").write_text(json.dumps(manifest))
    return root


@pytest.mark.parametrize(
    ("pi", "expected"),
    [
        pytest.param({"extensions": ["./extensions/pi/index.ts"]}, ["extensions/pi"], id="dot-slash-file"),
        pytest.param({"extensions": ["extensions/pi/index.ts"]}, ["extensions/pi"], id="relative-file"),
        pytest.param({"extensions": ["other"]}, ["other"], id="directory"),
        pytest.param({"extensions": ["*/pi/*.ts"]}, ["extensions/pi"], id="glob"),
        pytest.param({"extensions": ["**/*.ts", "!other/runner.ts"]}, ["extensions/pi", "other"], id="exclusion-kept"),
        pytest.param(None, ["extensions"], id="no-pi-manifest"),
        pytest.param({"skills": ["./skills"]}, ["extensions"], id="no-extensions-entry"),
        pytest.param({"extensions": []}, [], id="none-loaded"),
    ],
)
def test_each_extension_pi_loads_is_found(tmp_path: Path, pi: dict | None, expected: list[str]) -> None:
    """Validates: ThePluginIsSelfContained, for the Pi extensions its repository names."""
    package = _package(tmp_path, pi)

    found = json_records.pi_extensions(package)

    assert sorted(found) == sorted(package / name for name in expected)
