"""Class precedence uses distance at each hop and the strictest hop overall."""

import io
import json

import guarded_paths
from hermetic import build_world, load_hook, policy
import pytest


@pytest.fixture
def policy_world(tmp_path, monkeypatch):
    """A temporary world holding one hook beside the manifest, and no policy."""
    home, repo, manifest = build_world(tmp_path, monkeypatch)
    (manifest.parent / "hook.py").touch()
    return home, repo, manifest


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("read", "undeclared"), ("write", "guarded"), ("run", "guarded")],
)
def test_guarded_base_outcomes(policy_world, operation, expected):
    rules = policy(policy_world, guarded=["~/base/"])

    assert rules.verdict("~/base/file", operation) == expected


@pytest.mark.parametrize("operation", ["read", "write", "run"])
def test_block_overrides_write_through(policy_world, operation):
    rules = policy(policy_world, block=["~/base/file"], write=["~/base/"])

    assert rules.verdict("~/base/file", operation) == "block"


@pytest.mark.parametrize(
    ("guarded", "write", "expected"),
    [
        (["~/base/"], ["~/base/notes/"], "write-through"),
        (["~/base/notes/"], ["~/base/"], "guarded"),
        (["~/base/notes/"], ["~/base/notes/"], "write-through"),
    ],
)
def test_closest_declaration_decides_with_delta_on_tie(policy_world, guarded, write, expected):
    rules = policy(policy_world, guarded=guarded, write=write)

    assert rules.verdict("~/base/notes/file", "write") == expected


def test_exec_through_supplies_a_guarded_default(policy_world):
    rules = policy(policy_world, run=["~/skills/"])

    assert rules.verdict("~/skills/script", "run") == "exec-through"
    assert rules.verdict("~/skills/script", "write") == "guarded"
    assert rules.verdict("~/skills/script", "read") == "undeclared"


def test_write_through_does_not_make_runnable(policy_world):
    rules = policy(policy_world, write=["~/memory/"])

    assert rules.verdict("~/memory/script", "run") == "guarded"


def test_link_into_guarded_space_keeps_stricter_target(policy_world):
    home, _, _ = policy_world
    (home / "memory").mkdir()
    (home / "memory/link").symlink_to(home / "guarded/file")
    rules = policy(policy_world, guarded=["~/guarded/"], write=["~/memory/"])

    assert rules.verdict("~/memory/link", "write") == "guarded"
    assert any("guarded/file" in finding for finding in rules.validate())


def test_link_into_undeclared_space_keeps_exec_through(policy_world):
    home, _, _ = policy_world
    (home / "skills").mkdir()
    (home / "skills/link").symlink_to(home / "other/script")
    rules = policy(policy_world, run=["~/skills/"])

    assert rules.verdict("~/skills/link", "run") == "exec-through"
    assert rules.validate() == []


def test_declaration_order_does_not_change_verdict(policy_world):
    first = policy(policy_world, guarded=["~/base/", "~/base/private/"], write=["~/base/"])
    second = policy(policy_world, guarded=["~/base/private/", "~/base/"], write=["~/base/"])

    assert first.verdict("~/base/private/file", "write") == second.verdict("~/base/private/file", "write") == "guarded"


def test_carve_out_covering_enforcement_is_limited_and_reported(policy_world):
    _, repo, manifest = policy_world
    rules = policy(policy_world, write=[str(repo / "hooks") + "/"])

    assert rules.verdict(str(manifest), "write") == "guarded"
    assert any("does not apply" in finding and "hooks" in finding for finding in rules.findings)


def test_block_overlap_is_reported_with_both_declarations(policy_world):
    rules = policy(policy_world, block=["~/memory/", "~/unrelated"], write=["~/memory/"])

    assert any(
        "block declaration ~/memory/" in finding and "write-through declaration ~/memory/" in finding
        for finding in rules.validate()
    )
    assert not any("~/unrelated" in finding for finding in rules.validate())


def test_overlap_reports_only_the_matching_pair(policy_world):
    rules = policy(policy_world, block=["~/private/", "~/other/"], write=["~/private/"])

    findings = rules.validate()
    assert len(findings) == 1
    assert "~/private/" in findings[0]
    assert "~/other/" not in findings[0]


def test_parent_component_after_link_uses_the_target_parent(policy_world):
    home, _, _ = policy_world
    (home / "ordinary").mkdir()
    (home / "guarded/nested").mkdir(parents=True)
    (home / "ordinary/link").symlink_to(home / "guarded/nested")
    rules = policy(policy_world, guarded=["~/guarded/"])

    assert rules.verdict("~/ordinary/link/../file", "write") == "guarded"


def test_nested_block_is_valid_policy(policy_world):
    rules = policy(policy_world, block=["~/memory/private"], write=["~/memory/"])

    assert rules.validate() == []
    assert rules.verdict("~/memory/private", "write") == "block"


@pytest.mark.parametrize("operation", ["read", "write", "run"])
@pytest.mark.parametrize("path", ["~/base/settings", "~/base/skills/task.py", "~/base/memory/note"])
def test_equivalent_policies_reach_equal_verdicts(policy_world, operation, path):
    base = policy(
        policy_world,
        guarded=["~/base/"],
        run=["~/base/skills/"],
        write=["~/base/memory/"],
    )
    enumerated = policy(
        policy_world,
        guarded=["~/base/", "~/base/settings"],
        run=["~/base/skills/"],
        write=["~/base/memory/"],
    )
    assert base.verdict(path, operation) == enumerated.verdict(path, operation)


@pytest.mark.parametrize("member", ["manifest", "hook", "source"])
def test_enforcement_members_cannot_be_carved_out(policy_world, member, monkeypatch, capsys):
    _, repo, manifest = policy_world
    source = repo / "source.py"
    source.touch()
    (manifest.parent / "deployed.py").symlink_to(source)
    target = {
        "manifest": manifest,
        "hook": manifest.parent / "hook.py",
        "source": source,
    }[member]
    rules = policy(policy_world, write=[str(target)])
    assert rules.verdict(str(target), "write") == "guarded"
    assert any(str(target) in finding and "does not apply" in finding for finding in rules.findings)
    hook = load_hook("block-hook-tampering")
    monkeypatch.setattr(hook, "POLICY", rules)
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target)},
                    "transcript_path": "/tmp/transcript.jsonl",
                }
            )
        ),
    )
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    assert stopped.value.code == 0
    response = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert response["permissionDecision"] == "ask"
    assert "does not apply" in response["permissionDecisionReason"]


def test_link_with_matching_target_carve_out_is_silent(policy_world):
    home, _, _ = policy_world
    (home / "skills").mkdir()
    (home / "skills/link").symlink_to(home / "guarded/script")
    rules = policy(policy_world, guarded=["~/guarded/"], run=["~/skills/", "~/guarded/script"])
    assert rules.validate() == []
    assert rules.verdict("~/skills/link", "run") == "exec-through"


@pytest.mark.parametrize("agent", ["claude", "codex", "copilot"])
def test_each_declared_hook_tree_is_enforcement(policy_world, agent):
    _, repo, _ = policy_world
    relative = f"modules/home/ai/{agent}/hooks/"
    folder = repo / relative
    folder.mkdir(parents=True)
    target = folder / "hook.py"
    target.touch()
    declaration = "<repo>/" + relative
    rules = policy(policy_world, guarded=[declaration], write=[declaration])
    assert rules.verdict(str(target), "write") == "guarded"
    assert any("does not apply" in finding and declaration in finding for finding in rules.findings)


def test_enforcement_follows_directory_links_without_cycles(policy_world):
    _, repo, manifest = policy_world
    source = repo / "source"
    source.mkdir()
    target = source / "hook.py"
    target.touch()
    (source / "cycle").symlink_to(manifest.parent, target_is_directory=True)
    (manifest.parent / "instructions").symlink_to(source, target_is_directory=True)
    rules = policy(policy_world, write=[str(source) + "/"])
    assert rules.verdict(str(target), "write") == "guarded"
    assert rules.findings


def test_generated_bytecode_is_not_an_enforcement_declaration(policy_world):
    _, _, manifest = policy_world
    cache = manifest.parent / "__pycache__"
    cache.mkdir()
    bytecode = cache / "hook.cpython.pyc"
    bytecode.touch()
    rules = policy(policy_world)
    assert str(bytecode) not in rules.floor.declarations
    assert str(manifest.parent / "hook.py") in rules.floor.declarations


def test_construction_does_not_walk_carve_out_contents(policy_world, monkeypatch):
    home, _, _ = policy_world
    (home / "skills").mkdir()

    def no_directory_walk(_path):
        raise AssertionError("carve-out directory walk outside session validation")

    monkeypatch.setattr(type(home), "iterdir", no_directory_walk)
    rules = policy(policy_world, run=["~/skills/"])
    assert rules.verdict("~/skills/task.py", "run") == "exec-through"


def test_unknown_exception_surface_is_a_manifest_failure(policy_world):
    home, repo, manifest = policy_world
    data = {name: {"paths": []} for name in ("guarded", "block", "exec-through", "write-through")}
    data["exceptions"] = [{"surface": "misspelled-surface", "pattern": "~/file", "reason": "test"}]
    with pytest.raises(guarded_paths.ManifestError, match="surface"):
        guarded_paths.PathPolicy(data, home=str(home), repo_root=str(repo), manifest_path=manifest)


def test_a_capability_coverage_exception_loads_and_changes_no_verdict(policy_world):
    """The assessment reads it; no path verdict does."""
    home, repo, manifest = policy_world
    data = {name: {"paths": []} for name in ("guarded", "block", "exec-through", "write-through")}
    data["block"]["paths"] = ["~/file"]
    data["exceptions"] = [{"surface": "capability-coverage", "pattern": "~/file", "reason": "test"}]
    policy = guarded_paths.PathPolicy(data, home=str(home), repo_root=str(repo), manifest_path=manifest)
    assert policy.verdict("~/file", "read") == "block"


def test_real_manifest_validation_returns_diagnostics():
    assert guarded_paths.validate() == []


@pytest.mark.parametrize("missing", ["guarded", "block", "exec-through", "write-through", "exceptions"])
def test_missing_table_diagnostic_identifies_only_missing_table(missing):
    data = {name: {"paths": []} for name in ("guarded", "block", "exec-through", "write-through")}
    data["exceptions"] = []
    del data[missing]
    with pytest.raises(guarded_paths.ManifestError, match=f"missing tables: {missing}$"):
        guarded_paths.PathPolicy(data)


def test_exec_through_beneath_guarded(policy_world):
    rules = policy(policy_world, guarded=["~/base/"], run=["~/base/skills/"])
    assert rules.verdict("~/base/skills/script", "run") == "exec-through"
    assert rules.verdict("~/base/skills/script", "write") == "guarded"


@pytest.mark.parametrize(
    ("declaration", "candidate"),
    [
        ("~/base/?.md", "~/base/a.md"),
        ("~/base/[ab].md", "~/base/a.md"),
        ("~/base/**/file", "~/base/a/b/file"),
    ],
)
def test_other_glob_forms_do_not_expand(policy_world, declaration, candidate):
    rules = policy(policy_world, guarded=[declaration])
    assert rules.verdict(candidate, "write") == "undeclared"


@pytest.mark.parametrize(
    ("declaration", "ancestor"),
    [
        ("~/base/*/file", "~/base/anything"),
        ("~/base/?/file", "~/base/a"),
        ("~/base/[ab]/file", "~/base/a"),
    ],
)
def test_the_ancestor_check_reads_the_same_glob_form_as_the_distance_check(policy_world, declaration, ancestor):
    """`*` spans one component; `?` and `[` stay literal, as they do for a verdict."""
    rules = policy(policy_world, guarded=[declaration])
    assert rules.classes["guarded"].encloses(ancestor) is ("*" in declaration)


def test_stated_limits_are_documented():
    documentation = guarded_paths.__doc__.lower()
    for limit in (
        "directory change",
        "hard links",
        "links held inside",
        "no path",
        "paths absolutely",
    ):
        assert limit in documentation
