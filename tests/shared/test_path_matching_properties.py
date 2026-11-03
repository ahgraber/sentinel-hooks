"""Generated paths preserve declaration coverage and class precedence."""

from pathlib import Path
from tempfile import TemporaryDirectory

from guarded_paths import GuardedLocations, PathPolicy, spellings
from hypothesis import example, given, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

COMPONENT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=40)


@given(name=COMPONENT, child=COMPONENT, operation=st.sampled_from(["read", "write", "run"]))
@settings(max_examples=100, deadline=None)
def test_redundant_guarded_bases_preserve_equivalent_policies(name, child, operation):
    with TemporaryDirectory() as directory:
        manifest_path = Path(directory) / "manifest.toml"
        base = {
            "guarded": {"paths": ["/base/"]},
            "enforcement-floor": {"paths": []},
            "block": {"paths": ["/base/private"]},
            "exec-through": {"paths": [f"/base/{name}/scripts/"]},
            "write-through": {"paths": [f"/base/{name}/notes/"]},
            "exceptions": [],
        }
        redundant = {
            **base,
            "guarded": {"paths": ["/base/", f"/base/{name}/scripts/", f"/base/{name}/notes/"]},
        }
        left = PathPolicy(base, manifest_path=manifest_path)
        right = PathPolicy(redundant, manifest_path=manifest_path)
        for path in (
            f"/base/{name}/scripts/{child}",
            f"/base/{name}/notes/{child}",
            f"/base/{child}",
            f"/ordinary/{child}",
            "/base/private",
        ):
            assert left.verdict(path, operation) == right.verdict(path, operation)


@given(components=st.lists(COMPONENT, min_size=1, max_size=6))
def test_single_component_glob_never_spans_a_separator(components):
    locations = GuardedLocations(["/example/*.md"])
    path = "/example/" + "/".join(components) + ".md"

    assert bool(locations.contains(path)) is (len(components) == 1)


@given(path=st.text())
@example(path="~\x00")
@settings(max_examples=500)
def test_arbitrary_path_has_a_total_reading(path):
    locations = GuardedLocations(["/guarded/", "/patterns/*.md"])

    assert isinstance(spellings(path), tuple)
    assert isinstance(locations.contains(path), list)


@given(depth=st.integers(min_value=1, max_value=12), name=COMPONENT)
def test_every_symlink_hop_reaches_a_declared_target(depth, name):
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        target = root / "target"
        target.mkdir()
        previous = target
        for number in range(depth):
            link = root / f"link-{number}"
            link.symlink_to(previous)
            previous = link
        locations = GuardedLocations([str(previous) + "/"])

        for hop in spellings(str(previous / name)):
            assert locations.contains(hop), hop


@settings(deadline=None)
@given(order=st.permutations(["/base/", "/base/private/", "/other/"]), name=COMPONENT)
def test_manifest_order_cannot_widen_a_guarded_subdirectory(order, name):
    manifest = {
        "guarded": {"paths": list(order)},
        "enforcement-floor": {"paths": []},
        "block": {"paths": []},
        "exec-through": {"paths": []},
        "write-through": {"paths": ["/base/"]},
        "exceptions": [],
    }
    with TemporaryDirectory() as directory:
        manifest_path = Path(directory) / "guarded-paths.toml"
        manifest_path.touch()
        policy = PathPolicy(manifest, manifest_path=manifest_path)

        assert policy.verdict(f"/base/private/{name}", "write") == "guarded"
        assert policy.verdict(f"/base/public/{name}", "write") == "write-through"


class LinkRetargeting(RuleBasedStateMachine):
    """A permitted link name cannot preserve permission after its target changes."""

    @initialize()
    def initialize_world(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        for name in ("memory", "guarded", "ordinary", "hooks"):
            (self.root / name).mkdir()
        self.link = self.root / "memory" / "link"
        self.destination = "ordinary"
        self.link.symlink_to(self.root / self.destination / "file")
        manifest_path = self.root / "hooks" / "manifest.toml"
        manifest_path.touch()
        self.policy = PathPolicy(
            {
                "guarded": {"paths": [str(self.root / "guarded") + "/"]},
                "enforcement-floor": {"paths": []},
                "block": {"paths": [str(self.root / "blocked")]},
                "exec-through": {"paths": []},
                "write-through": {"paths": [str(self.root / "memory") + "/"]},
                "exceptions": [],
            },
            manifest_path=manifest_path,
        )

    @rule(destination=st.sampled_from(["ordinary", "guarded", "blocked"]))
    def retarget_link(self, destination):
        self.link.unlink()
        target = self.root / destination
        if destination != "blocked":
            target /= "file"
        self.link.symlink_to(target)
        self.destination = destination

    @invariant()
    def current_target_decides(self):
        expected = {
            "ordinary": "write-through",
            "guarded": "guarded",
            "blocked": "block",
        }[self.destination]

        assert self.policy.verdict(str(self.link), "write") == expected

    def teardown(self):
        self.directory.cleanup()


TestLinkRetargeting = LinkRetargeting.TestCase
TestLinkRetargeting.settings = settings(max_examples=40, stateful_step_count=30, deadline=None)
