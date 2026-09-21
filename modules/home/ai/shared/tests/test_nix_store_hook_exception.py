"""Only verified Home Manager links to declared hook sources bypass name guessing."""

from guarded_paths import GuardedLocations
from hermetic import load_hook
import pytest


@pytest.fixture
def sensitive():
    return load_hook("block-sensitive-paths")


@pytest.mark.parametrize(
    ("name", "target", "link", "expected"),
    [
        ("hm_blocksecrets.py", "block-secrets.py", True, True),
        ("hm_block_secrets.py", "block_secrets.py", True, True),
        ("hm_blocksecrets.py", "different.py", True, False),
        ("hm_othersecret.py", "block-secrets.py", True, False),
        ("hm_blocksecrets.py", "block-secrets.py", False, False),
    ],
)
def test_store_wrapper_requires_matching_name_and_known_source(
    sensitive, tmp_path, monkeypatch, name, target, link, expected
):
    store = tmp_path / "store"
    store.mkdir()
    source = tmp_path / "repository" / target
    source.parent.mkdir()
    source.touch()
    wrapper = store / ("0" * 32 + "-" + name)
    if link:
        wrapper.symlink_to(source)
    else:
        wrapper.touch()
    monkeypatch.setattr(sensitive, "NIX_STORE", store)
    monkeypatch.setattr(sensitive, "NIX_HOOK_SOURCES", GuardedLocations([str(source)]))

    assert sensitive.is_nix_hook_wrapper(str(wrapper)) is expected


def test_hm_prefix_outside_store_is_not_exempt(sensitive, tmp_path, monkeypatch):
    source = tmp_path / "block-secrets.py"
    source.touch()
    wrapper = tmp_path / ("0" * 32 + "-hm_blocksecrets.py")
    wrapper.symlink_to(source)
    monkeypatch.setattr(sensitive, "NIX_STORE", tmp_path / "store")
    monkeypatch.setattr(sensitive, "NIX_HOOK_SOURCES", GuardedLocations([str(source)]))

    assert not sensitive.is_nix_hook_wrapper(str(wrapper))


def test_unknown_source_is_not_exempt(sensitive, tmp_path, monkeypatch):
    source = tmp_path / "block-secrets.py"
    source.touch()
    store = tmp_path / "store"
    store.mkdir()
    wrapper = store / ("0" * 32 + "-hm_blocksecrets.py")
    wrapper.symlink_to(source)
    monkeypatch.setattr(sensitive, "NIX_STORE", store)
    monkeypatch.setattr(sensitive, "NIX_HOOK_SOURCES", GuardedLocations([]))

    assert not sensitive.is_nix_hook_wrapper(str(wrapper))
