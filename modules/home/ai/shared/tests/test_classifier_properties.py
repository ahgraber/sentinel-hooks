"""Properties of the read classifier over generated command text.

The example suites encode the commands somebody thought of. This file states
what must hold for every command, and lets Hypothesis look for the ones nobody
thought of.

The load-bearing property is `differential lexing`: the classifier decides from
`shlex` tokens, the shell runs words it produces afterwards, and every defect
found in this classifier so far has been a divergence between the two.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, example, given, settings, target
from hypothesis import strategies as st
from shellprobe import ShellProbe

HOOKS_DIR = Path(__file__).parent.parent / "hooks"


def _load_gate():
    """Import the tamper hook; its filename is not a Python identifier."""
    spec = importlib.util.spec_from_file_location(
        "tamper_gate_under_test", HOOKS_DIR / "block-hook-tampering.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

# A path under a read-through location, so a command naming it can reach the
# classifier rather than being gated before the lexer matters.
GUARDED = "~/.claude/skills/sdd-sync/references/sdd-spec-formats.md"
GUARDED_DIR = "~/.claude/skills/sdd-sync"
ORDINARY = "notes.md"

# A brace group holding an unquoted space is lexed into several words, so no one
# word states the whole group. The classifier must still refuse it.
GUARDED_SPACED = "~/.claude/skills/sdd-sync/a b.md"

RECORDED_PROGRAMS = set(gate.READ_ONLY_UTILITIES) | set(gate.INTERPRETERS) | {
    "rm", "tee", "cp", "mv", "install", "dd", "truncate",
}  # fmt: skip


@pytest.fixture(scope="module")
def probe(tmp_path_factory) -> ShellProbe:
    return ShellProbe(tmp_path_factory.mktemp("shellprobe"), RECORDED_PROGRAMS)


def allows(command: str) -> bool:
    """True if the command would run with no prompt."""
    cls = gate.command_protected_class(command)
    if cls is None:
        return True
    if cls == gate.GATED and gate.only_carved_out(command):
        return gate.is_read_only_command(command) or gate.runs_exec_through_script(
            command
        )
    return False


def classifier_words(command: str) -> list[tuple[str, ...]] | None:
    """The words the classifier believes each program will receive."""
    segments = gate._segments(command)
    if segments is None:
        return None
    return [tuple(segment) for segment in segments]


# Ways a shell word can be spelled. Each takes the text a generator wants in the
# command and returns the text to write, which the shell turns back into that
# word — or into two.
# Forms the classifier resolves to the same word the shell does. Every quoting
# form belongs here, ANSI-C quoting included, because the classifier decodes it.
STABLE_FORMS = [
    lambda w: w,
    lambda w: f"'{w}'",
    lambda w: f'"{w}"',
    lambda w: "{" + w + "}",
    lambda w: "$'" + w + "'",
]

# Forms that produce words from text the classifier cannot read: a brace
# expansion states the words directly, and a parameter expansion names a value
# the hook's own environment does not hold. Neither may be judged, so neither
# may be allowed.
UNRESOLVED_FORMS = [
    lambda w: "{" + w + ",second-word}",
    lambda w: "${HYPOTHESIS_UNSET:-" + w + "}",
    lambda w: "{" + w + ",--output=/tmp/out}",
    lambda w: "$HYPOTHESIS_UNSET" + w,
]

OPTIONS = ["-n", "-r", "--output=/tmp/out", "-o", "-delete", "--exec", "-i", "-l"]
PROGRAMS = sorted(gate.READ_ONLY_UTILITIES | {"rm", "tee", "cp"})
SEPARATORS = [" && ", " ; ", " | ", " || "]

ORDINARY_DIR = "notes"

# A filename the shell passes as an operand and the program reads as an option.
# `--` and `-` mean something to the program besides a file, and both are legal
# names, so a classifier reading operand position alone gets them wrong.
OPTION_NAMED_FILES = ["-n", "--output=/tmp/out", "-o", "--", "-"]

# Last components that reach a boundary the three fixed paths cannot.
# The two non-ASCII names are written as escapes because a spellchecker rewrites
# the characters themselves back to ASCII, which is the whole of what they test.
BOUNDARY_COMPONENTS = [
    "\ufb01le.md",  # the "fi" ligature, which normalizes onto ASCII under NFKC
    "\uff53kill.md",  # a fullwidth letter where an ASCII one is expected
    "x" * 300,  # longer than a filesystem allows one component to be
    "SKILL.md",  # differs from a real name only in case
    "a b.md",  # a space, which the shell splits on unless it is quoted
    "a\nb.md",  # a newline, which separates commands unless it is quoted
    "..",
    ".",
]


def paths() -> st.SearchStrategy[str]:
    """A path a command can name.

    The three anchors are drawn most often: a command naming nothing guarded
    reaches no gate, so it exercises little of what these properties are about.
    The rest reach the spellings a fixed set cannot — a name that is itself an
    option, a name differing from a declared one only in case, and a component
    whose bytes the filesystem will not accept as written.
    """
    anchors = st.sampled_from([GUARDED, GUARDED_DIR, ORDINARY])
    cased = st.sampled_from(
        [
            GUARDED_DIR.replace(".claude", ".Claude"),
            GUARDED.replace("sdd-sync", "SDD-SYNC"),
        ]
    )
    beneath = st.builds(
        lambda base, component: f"{base}/{component}",
        st.sampled_from([GUARDED_DIR, ORDINARY_DIR]),
        st.sampled_from(BOUNDARY_COMPONENTS),
    )
    return st.one_of(
        anchors, anchors, st.sampled_from(OPTION_NAMED_FILES), cased, beneath
    )


@st.composite
def words(draw: st.DrawFn, forms: list) -> str:
    """One shell word: a path or an option, spelled in one of `forms`."""
    payload = draw(st.one_of(paths(), st.sampled_from(OPTIONS)))
    return draw(st.sampled_from(forms))(payload)


@st.composite
def segments(draw: st.DrawFn, forms: list) -> str:
    program = draw(st.sampled_from(PROGRAMS))
    arguments = draw(st.lists(words(forms), min_size=1))
    return " ".join([program, *arguments])


@st.composite
def commands(draw: st.DrawFn, forms: list = STABLE_FORMS) -> str:
    parts = draw(st.lists(segments(forms), min_size=1, max_size=3))
    joins = [draw(st.sampled_from(SEPARATORS)) for _ in parts[1:]]
    command = parts[0]
    for join, part in zip(joins, parts[1:], strict=True):
        command += join + part
    return command


class TestDifferentialLexing:
    """What the classifier lexed is what the shell runs."""

    @staticmethod
    def comparable(words: tuple[str, ...]) -> tuple[str, ...]:
        """Apply the one expansion the classifier performs for itself.

        `spellings` expands `~` before judging a token, so the written and
        expanded forms denote one path and a difference between them is not a
        divergence. Every other expansion is the shell's alone, and a token that
        changes under one is what this property exists to catch. Python's
        expansion is used deliberately: where the shell disagrees with it, the
        classifier is judging a path the shell will not open, and that still fails.
        """
        return tuple(os.path.expanduser(word) for word in words)

    def check(self, probe: ShellProbe, command: str) -> None:
        assume(allows(command))
        lexed = classifier_words(command)
        assume(lexed is not None)
        expected = [self.comparable(words) for words in lexed]

        observed = [
            self.comparable(invocation.words) for invocation in probe.run(command)
        ]
        assume(observed)

        # A larger difference in word count is a more interesting example.
        flat_observed = sum(len(words) for words in observed)
        flat_expected = sum(len(words) for words in expected)
        target(float(abs(flat_observed - flat_expected)), label="word count")

        # Containment rather than equality: `&&` and `||` short-circuit, so the
        # shell may run fewer programs than the classifier judged. Judging one
        # that never runs is conservative. Running one that was never judged is
        # the unsound direction, and the only one this property forbids.
        unjudged = [words for words in observed if words not in expected]

        assert not unjudged, (
            "the classifier allowed this command after lexing it one way, and the "
            "shell ran a program it never judged:\n"
            f"  command:    {command}\n"
            f"  classifier: {expected}\n"
            f"  shell:      {observed}\n"
            f"  unjudged:   {unjudged}"
        )

    @given(command=commands(STABLE_FORMS))
    @settings(
        max_examples=250,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_the_shell_runs_the_words_the_classifier_judged(
        self, probe: ShellProbe, command: str
    ) -> None:
        """Quoting forms that keep one word as one word must agree with the shell."""
        self.check(probe, command)

    @given(command=commands(UNRESOLVED_FORMS))
    @settings(max_examples=250, deadline=None)
    @example(command=f"sort {{--output=/tmp/out,{GUARDED}}}")
    @example(command=f"sort ${{HYPOTHESIS_UNSET:---output=/tmp/out}} {GUARDED}")
    @example(command=f"cat {{{GUARDED},notes.md}}")
    @example(command=f"basename {{{GUARDED_SPACED},second-word}}")
    @example(command=f"sort {{--output=/tmp/out,{GUARDED_SPACED}}}")
    @example(command=f"cat {{{GUARDED_SPACED}..zzz}}")
    def test_a_word_the_classifier_cannot_resolve_is_never_read_as_a_read(
        self, command: str
    ) -> None:
        """A word produced from text the classifier cannot read is not judged.

        These forms have no oracle: what the shell does with `${VAR}` depends on
        an environment the hook does not hold. The classifier must therefore
        decline to call the command a read, whatever the words turn out to be.
        """
        assert gate.is_read_only_command(command) is False
        assert gate.runs_exec_through_script(command) is False

    @given(command=commands(UNRESOLVED_FORMS))
    @settings(max_examples=250, deadline=None)
    def test_a_guarded_path_inside_an_unresolved_word_is_still_seen(
        self, command: str
    ) -> None:
        """Syntax wrapped around a path does not hide it from the containment tests.

        `{--output=/tmp/out,GUARDED}` is one `shlex` token and matches no
        declaration as written, so without this the command would name nothing
        guarded and proceed unjudged.
        """
        assume(GUARDED in command or GUARDED_DIR in command)
        assert gate.command_protected_class(command) == gate.GATED


class TestPathnameExpansion:
    """A pattern is judged by what it matches, not by how it is written.

    Pathname expansion is the one expansion the classifier performs for itself,
    because refusing it would cost every `cat hooks/*.py` under a read-through
    location a prompt the agent may not be able to answer.
    """

    def test_a_pattern_that_expands_to_an_option_is_not_a_read(
        self, tmp_path, monkeypatch
    ) -> None:
        """The pattern names a file; the word the shell builds from it is an option."""
        injected = tmp_path / "--output=" / "tmp"
        injected.mkdir(parents=True)
        (injected / "out").touch()
        monkeypatch.chdir(tmp_path)

        command = f"sort ?-output=/tmp/out {GUARDED}"
        assert gate._expanded(command) == ["sort", "--output=/tmp/out", GUARDED]
        assert not allows(command)

    def test_a_pattern_is_judged_by_the_files_it_matches(
        self, tmp_path, monkeypatch
    ) -> None:
        (tmp_path / "a.md").touch()
        (tmp_path / "b.md").touch()
        monkeypatch.chdir(tmp_path)

        assert gate._expanded("cat *.md") == ["cat", "a.md", "b.md"]
        assert allows(f"cat *.md {GUARDED}")

    def test_a_pattern_matching_nothing_stays_as_written(
        self, tmp_path, monkeypatch
    ) -> None:
        """What a shell does with `nullglob` unset, which is the default."""
        monkeypatch.chdir(tmp_path)
        assert gate._expanded("cat *.md") == ["cat", "*.md"]

    def test_a_quoted_pattern_is_a_filename(self, tmp_path, monkeypatch) -> None:
        (tmp_path / "a.md").touch()
        monkeypatch.chdir(tmp_path)
        assert gate._expanded("cat '*.md'") == ["cat", "*.md"]


class TestMetamorphicRelations:
    """Relations between verdicts on related commands."""

    @given(command=commands())
    @settings(max_examples=200, deadline=None)
    def test_naming_a_guarded_path_never_becomes_more_permissive(
        self, command: str
    ) -> None:
        """Adding a guarded operand cannot turn a gate into an allow.

        Stated as an implication rather than a filtered case: most generated
        commands are allowed, so assuming the gate would discard nearly all of
        them and leave the relation barely exercised.
        """
        if allows(f"{command} {GUARDED}"):
            assert allows(command)

    @given(command=commands(), suffix=st.sampled_from(["", "/", "/."]))
    @settings(max_examples=200, deadline=None)
    def test_a_trailing_separator_does_not_change_the_verdict(
        self, command: str, suffix: str
    ) -> None:
        """A directory is the same location however its name ends."""
        spelled = command.replace(GUARDED_DIR, GUARDED_DIR + suffix)
        assume(spelled != command)
        assert allows(spelled) == allows(command)


class TestTotality:
    """The classifier reaches a verdict on anything, without raising.

    Generation alone cannot establish that the hook's failure path is
    unreachable, which is what this property would have to show to justify
    failing open. `~\\x00` is the standing reminder: `os.path.expanduser` raises
    on it, and this property passed for months before it drew that byte.
    What the failure path does when it is reached is pinned by injection below,
    not by generation.
    """

    @given(command=st.text())
    @settings(max_examples=500, deadline=None)
    @example(command="~\x00")
    def test_arbitrary_text_reaches_a_verdict(self, command: str) -> None:
        assert allows(command) in (True, False)

    @given(
        command=st.text(
            alphabet=st.characters(codec="utf-8"),
            min_size=1,
        )
    )
    @settings(max_examples=500, deadline=None)
    def test_arbitrary_unicode_reaches_a_verdict(self, command: str) -> None:
        assert allows(command) in (True, False)


def boom(*args, **kwargs):
    """Stand in for any step of the hook that can fail."""
    raise RuntimeError("injected fault")


def _fail_at_executable_lookup(patch: pytest.MonkeyPatch) -> None:
    """Reach the executable test, which only a file already on disk reaches."""
    patch.setattr(gate.os.path, "isfile", lambda path: True)
    patch.setattr(gate.os, "access", boom)


# Each pairs a step of the hook with a payload that reaches it.
FAULT_SITES = [
    pytest.param(
        lambda patch: patch.setattr(gate, "spellings", boom),
        "Write",
        {"file_path": GUARDED},
        id="path-resolution",
    ),
    pytest.param(
        lambda patch: patch.setattr(gate.GUARDED, "contains", boom),
        "Bash",
        {"command": f"cat {GUARDED}"},
        id="containment",
    ),
    pytest.param(
        lambda patch: patch.setattr(gate.globbing, "glob", boom),
        "Bash",
        {"command": f"cat {GUARDED_DIR}/*"},
        id="pathname-expansion",
    ),
    pytest.param(
        lambda patch: patch.setattr(gate.os.path, "isfile", boom),
        "Bash",
        {"command": f"{GUARDED_DIR}/helper.sh"},
        id="filesystem-metadata",
    ),
    pytest.param(
        _fail_at_executable_lookup,
        "Bash",
        {"command": f"{GUARDED_DIR}/helper"},
        id="executable-lookup",
    ),
    pytest.param(
        lambda patch: patch.setattr(gate, "invoking_agent", boom),
        "Bash",
        {"command": f"cat {GUARDED}"},
        id="naming-the-agent",
    ),
]


def decide(patch: pytest.MonkeyPatch, tool_name: str, tool_input: dict, agent: str):
    """Run the hook over one payload in this process, returning its exit and output."""
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    patch.setenv("AI_HOOK_AGENT", agent)
    patch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out, err = io.StringIO(), io.StringIO()
    patch.setattr(sys, "stdout", out)
    patch.setattr(sys, "stderr", err)
    with pytest.raises(SystemExit) as exit_info:
        gate.run()
    return exit_info.value.code or 0, out.getvalue(), err.getvalue()


class TestFailClosedOnInternalError:
    """A step of the hook failing does not let the call through.

    `hook-interface` `ErrorHandlingByDamagePotential` sets the direction: a tool
    that can modify state must not proceed because the hook judging it crashed.
    The hook is registered for `Read` as well, which is why the direction is
    chosen per tool rather than per hook.
    """

    @pytest.mark.parametrize(("inject", "tool_name", "tool_input"), FAULT_SITES)
    def test_a_failure_reaches_the_user_under_claude(
        self, monkeypatch: pytest.MonkeyPatch, inject, tool_name: str, tool_input: dict
    ) -> None:
        inject(monkeypatch)
        code, out, _ = decide(monkeypatch, tool_name, tool_input, "claude")
        assert code == 0
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"
        assert "injected fault" in decision["permissionDecisionReason"]

    @pytest.mark.parametrize(("inject", "tool_name", "tool_input"), FAULT_SITES)
    def test_a_failure_refuses_where_no_prompt_can_be_shown(
        self, monkeypatch: pytest.MonkeyPatch, inject, tool_name: str, tool_input: dict
    ) -> None:
        inject(monkeypatch)
        code, out, err = decide(monkeypatch, tool_name, tool_input, "codex")
        assert code == 2
        assert out == ""
        assert "injected fault" in err

    def test_a_failure_judging_a_read_still_lets_it_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Blocking a read on a hook defect is disruption without a gain.

        It proceeds and the failure is reported, rather than proceeding in
        silence: a hook that checks nothing and says nothing is how a defect
        lasts.
        """
        monkeypatch.setattr(gate, "invoking_agent", boom)
        code, out, err = decide(monkeypatch, "Read", {"file_path": GUARDED}, "claude")
        assert (code, out) == (0, "")
        assert "injected fault" in err

    def test_an_unparsable_payload_warns_rather_than_refusing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tool is unnamed, and this hook is registered for reads too."""
        monkeypatch.setenv("AI_HOOK_AGENT", "claude")
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        out, err = io.StringIO(), io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", err)
        with pytest.raises(SystemExit) as exit_info:
            gate.run()
        assert exit_info.value.code in (0, 1)
        assert "not checked" in err.getvalue()
