"""The gate's outcome across agents and protected classes.

The per-agent suites pin each agent's encoding in isolation; this file pins the
matrix — the same payload, judged per (agent, tool) pairing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from guarded_paths import folds_case

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
HOOK = HOOKS_DIR / "block-hook-tampering.py"
REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "flake.nix").is_file()
)

CLAUDE = "claude"
CODEX = "codex"
COPILOT = "copilot"
UNKNOWN = "unknown"

REPO_SOURCE = "modules/home/ai/codex/rules/default.rules"
CREDENTIAL_PATHS = (
    "~/.claude/.credentials.json",
    "~/.codex/auth.json",
    "~/.pi/agent/auth.json",
)


@dataclass
class GateResult:
    exit_code: int
    stdout: str
    stderr: str


def run_gate(
    tool_name: str, tool_input: dict, agent: str, home: str | None = None
) -> GateResult:
    """Run the hook as `agent` would invoke it: Claude Code by the transcript
    path its payloads carry, the others by the declaration their adapters set.

    `home` substitutes the home directory the hook expands `~` against, so a
    case that needs files on disk can build them.
    """
    payload: dict = {"tool_name": tool_name, "tool_input": tool_input}
    env = {**os.environ}
    env.pop("AI_HOOK_AGENT", None)
    if home is not None:
        env["HOME"] = home
    if agent == CLAUDE:
        payload["transcript_path"] = "/tmp/transcript.jsonl"
    elif agent != UNKNOWN:
        env["AI_HOOK_AGENT"] = agent

    result = subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env=env,
    )
    return GateResult(result.returncode, result.stdout, result.stderr)


def write(path: str, agent: str, home: str | None = None) -> GateResult:
    return run_gate("Write", {"file_path": path}, agent, home)


def edit(path: str, agent: str) -> GateResult:
    return run_gate(
        "Edit", {"file_path": path, "old_string": "a", "new_string": "b"}, agent
    )


def bash(command: str, agent: str, home: str | None = None) -> GateResult:
    return run_gate("Bash", {"command": command}, agent, home)


def patch(body: str, agent: str) -> GateResult:
    return run_gate("apply_patch", {"command": body}, agent)


def add_file(path: str, *lines: str) -> str:
    """An apply_patch body adding `path`, carrying `lines` as its content."""
    added = "".join(f"+{line}\n" for line in lines)
    return f"*** Begin Patch\n*** Add File: {path}\n{added}*** End Patch"


def ask_reason(result: GateResult) -> str:
    assert result.exit_code == 0, (
        f"Expected ask (exit 0), got {result.exit_code}.\nstderr: {result.stderr}"
    )
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    return output["permissionDecisionReason"]


def assert_refused(result: GateResult, substring: str = "") -> None:
    assert result.exit_code == 2, (
        f"Expected refusal (exit 2), got {result.exit_code}.\nstdout: {result.stdout}"
    )
    assert result.stdout == "", (
        f"A refusal must write nothing to stdout, got: {result.stdout}"
    )
    if substring:
        assert substring.lower() in result.stderr.lower(), (
            f"Expected '{substring}' in stderr, got: {result.stderr}"
        )


class TestGatedClassesByAgent:
    def test_edit_of_deployed_enforcement_asks_under_claude(self) -> None:
        reason = ask_reason(edit("~/.claude/settings.json", CLAUDE))
        assert "settings.json" in reason

    def test_edit_of_deployed_enforcement_refuses_under_codex(self) -> None:
        assert_refused(edit("~/.claude/settings.json", CODEX), "settings.json")

    def test_bash_naming_a_repository_source_asks_under_claude(self) -> None:
        reason = ask_reason(bash(f"echo x >> {REPO_SOURCE}", CLAUDE))
        assert "default.rules" in reason

    def test_operand_attached_spelling_reaches_the_same_outcome(self) -> None:
        spaced = bash(f"echo x >> {REPO_SOURCE}", CLAUDE)
        attached = bash(f"echo x >>{REPO_SOURCE}", CLAUDE)
        assert (spaced.exit_code, attached.exit_code) == (0, 0)
        assert ask_reason(attached)

    def test_edit_of_another_users_configuration_asks_under_claude(self) -> None:
        target = "users/testuser/home-manager/claude/settings.json"
        reason = ask_reason(edit(target, CLAUDE))
        assert "settings.json" in reason

    def test_gated_write_refuses_under_copilot_shell(self) -> None:
        """Copilot's shell tool proceeds past the prompt JSON, so Bash refuses."""
        assert_refused(bash(f"echo x >> {REPO_SOURCE}", COPILOT))

    def test_gated_write_asks_under_copilot_file_tools(self) -> None:
        assert ask_reason(write("~/.claude/settings.json", COPILOT))


class TestCredentialClass:
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    @pytest.mark.parametrize("credential", CREDENTIAL_PATHS)
    def test_credential_write_refuses_under_every_agent(
        self, agent: str, credential: str
    ) -> None:
        assert_refused(write(credential, agent), Path(credential).name)

    @pytest.mark.parametrize("credential", CREDENTIAL_PATHS)
    def test_mixed_class_command_refuses(self, credential: str) -> None:
        """The most restrictive class wins, even where the agent could prompt."""
        assert_refused(
            bash(f"cat {REPO_SOURCE} {credential}", CLAUDE), Path(credential).name
        )


class TestSpellingReachesTheGate:
    def test_case_variant_spelling_reaches_the_gate(self) -> None:
        if not folds_case(os.path.expanduser("~")):
            pytest.skip("filesystem under test is case-sensitive")
        assert ask_reason(write("~/.CLAUDE/settings.json", CLAUDE))

    def test_unresolvable_protected_path_reaches_the_gate(self) -> None:
        """A path resolution cannot follow is judged from the path as written."""
        target = f"{REPO_ROOT}/modules/home/ai/shared/hooks/x\x00.py"
        assert ask_reason(write(target, CLAUDE))


class TestInstructionMarkdownCarveOut:
    def test_direct_instruction_markdown_stays_writable(self) -> None:
        result = write(
            "modules/home/ai/claude/hooks/instructions/00-response-style.md", CLAUDE
        )
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_nested_path_under_instructions_is_gated(self) -> None:
        assert ask_reason(
            write("modules/home/ai/claude/hooks/instructions/nested/note.md", CLAUDE)
        )

    def test_non_markdown_in_instructions_is_gated(self) -> None:
        assert ask_reason(
            write("modules/home/ai/claude/hooks/instructions/helper.py", CLAUDE)
        )

    def test_markdown_name_leading_to_enforcement_is_gated(self, tmp_path: Path):
        """A write to a link is a write to what the link leads to."""
        (tmp_path / ".git").mkdir()
        hooks = tmp_path / "modules" / "home" / "ai" / "shared" / "hooks"
        (hooks / "instructions").mkdir(parents=True)
        (hooks / "block-destructive-ops.py").write_text("original\n")
        alias = hooks / "instructions" / "notes.md"
        alias.symlink_to("../block-destructive-ops.py")

        assert ask_reason(write(str(alias), CLAUDE))


SKILL_FILE = "~/.claude/skills/sdd-sync/references/sdd-spec-formats.md"
SKILL_REAL = "~/.agents/skills/sdd-sync/references/sdd-spec-formats.md"

READS = [
    f"cat {SKILL_FILE}",
    "cat ~/.codex/skills/.system/openai-docs/SKILL.md",
    f"grep -n Baseline {SKILL_FILE} | head",
    f"grep -n 'Baseline spec\\|## 2' {SKILL_FILE}",
    f"grep -n 'formats$' {SKILL_FILE}",
    f"head -64 {SKILL_FILE} | cut -c1-200",
    f"cat {SKILL_FILE} | tr -s ' ' | sort | uniq -c | wc -l",
    "ls ~/.claude/skills/sdd-sync",
    "find ~/.claude/skills -name SKILL.md",
    f"cat {SKILL_REAL}",
    f"grep -c . {SKILL_REAL}",
    # A banner separating two reads reaches standard output only, so it leaves
    # the surrounding reads recognized rather than gating the whole command.
    f"cat {SKILL_FILE} && printf '\\n--- next ---\\n' && cat {SKILL_REAL}",
    f"cat {SKILL_FILE} && echo '---' && cat {SKILL_REAL}",
]

# One per way a command can escape the classifier: a second command it never
# reaches, a binary that is not the utility it is named after, and a utility
# whose behavior is set by an argument rather than by the command line.
NOT_READS = [
    f"cat {SKILL_FILE}\nrm -rf ~/.claude/skills",
    f"cat {SKILL_FILE} |& rm -rf ~/.claude/skills",
    f"cat {SKILL_FILE} ;& rm -rf ~/.claude/skills",
    f"cat {SKILL_FILE}; rm -rf ~/.claude/skills",
    f"/tmp/cat {SKILL_FILE}",
    f"PATH=/tmp:$PATH cat {SKILL_FILE}",
    f"cat $(echo {SKILL_FILE})",
    f"cat `echo {SKILL_FILE}`",
    f"grep -$flag pattern {SKILL_FILE}",
    f"sed -n '50,64p' {SKILL_FILE}",
    f"sed -i 's/a/b/' {SKILL_FILE}",
    f"sed -n 'w ~/.claude/skills/sdd-sync/SKILL.md' {SKILL_FILE}",
    f"gsed -n '1,5p' {SKILL_FILE}",
    f"awk '/^## 2/,/^## 3/' {SKILL_FILE}",
    "awk 'BEGIN{system(\"rm -rf ~/.claude/skills\")}' " + SKILL_FILE,
    f"awk -f /tmp/program.awk {SKILL_FILE}",
    f"yq -i '.a = 1' {SKILL_FILE}",
    # No form of ripgrep is a recognized read. It takes options from
    # RIPGREP_CONFIG_PATH, and `-z` runs a decompressor named outside the
    # command line, so the command text does not say what it does.
    f"rg --pre /tmp/helper pattern {SKILL_FILE}",
    f"rg -n pattern {SKILL_FILE}",
    f"rg -z pattern {SKILL_FILE}",
    f"rg --search-zip pattern {SKILL_FILE}",
    f"less {SKILL_FILE}",
    f"bat {SKILL_FILE}",
    f"sort --compress-program=/tmp/helper {SKILL_FILE}",
    f"sort -o ~/.claude/skills/sdd-sync/SKILL.md {SKILL_FILE}",
    "find ~/.claude/skills -name SKILL.md -delete",
    "find ~/.claude/skills -name SKILL.md -exec rm {} ;",
    f"cp /tmp/replacement.md {SKILL_FILE}",
    f"cat /tmp/replacement.md > {SKILL_FILE}",
    f"cat {SKILL_FILE} >> ~/.claude/skills/sdd-sync/SKILL.md",
    f"uv run {SKILL_FILE}",
    f"echo pwned > {SKILL_FILE}",
    f"echo pwned >{SKILL_FILE}",
    f"echo pwned >> {SKILL_FILE}",
    f"printf pwned > {SKILL_FILE}",
    f"echo pwned | tee {SKILL_FILE}",
    "echo $(rm -rf ~/.claude/skills/sdd-sync)",
]


class TestReadThroughCarveOut:
    """Under a read-through location a recognized read proceeds; the rest gates."""

    @pytest.mark.parametrize("command", READS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_recognized_read_proceeds_under_every_agent(
        self, command: str, agent: str
    ) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", NOT_READS, ids=lambda c: c[:40])
    def test_anything_else_asks_under_claude(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    @pytest.mark.parametrize("command", NOT_READS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_anything_else_refuses_where_no_prompt_is_honored(
        self, command: str, agent: str
    ) -> None:
        assert_refused(bash(command, agent), "not a recognized read")

    def test_one_guarded_path_outside_the_carve_out_gates_the_whole_command(
        self,
    ) -> None:
        assert ask_reason(bash(f"cat {SKILL_FILE} ~/.claude/settings.json", CLAUDE))

    @pytest.mark.parametrize("path", [SKILL_FILE, SKILL_REAL])
    def test_a_write_to_skill_content_still_gates_on_the_file_tools(
        self, path: str
    ) -> None:
        assert ask_reason(write(path, CLAUDE))
        assert ask_reason(edit(path, CLAUDE))


UNJUDGED_BESIDE_A_READ = [
    f"cat {SKILL_FILE} && rg -n 'baseline|treatment' evals/README.md",
    f"cat {SKILL_FILE} && sed -n '1,5p' evals/run.py",
    f"cat {SKILL_FILE} && make test",
    f"cat {SKILL_FILE} && cat evals/x.py | awk '{{print}}'",
]

JUDGED_BESIDE_A_READ = [
    f"cat {SKILL_FILE} && rm -rf ~/.claude/skills/sdd-sync",
    f"cat {SKILL_FILE} && cd ~ && rm -rf .claude/hooks",
    f"cat {SKILL_FILE} && cat ~/.pi/agent/settings.json",
    f"cat {SKILL_FILE}\nrm -rf ~/.claude/skills",
    f"cat {SKILL_FILE} && rm -rf $(cat /tmp/target)",
    f"cat evals/x.py | tee {SKILL_FILE}",
    "cat evals/x.py ~/.codex/auth.json",
]


class TestOnlySegmentsNamingAGuardedPathAreJudged:
    """A segment naming nothing guarded is not this hook's to classify."""

    @pytest.mark.parametrize("command", UNJUDGED_BESIDE_A_READ, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_an_unrelated_segment_does_not_gate_the_command(
        self, command: str, agent: str
    ) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", JUDGED_BESIDE_A_READ, ids=lambda c: c[:44])
    def test_a_segment_reaching_a_guarded_path_still_gates(self, command: str) -> None:
        result = bash(command, CLAUDE)
        assert result.exit_code != 0 or json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecision"
        ] in ("ask", "deny")


# Absolute, unlike the named-path cases above. An ancestor carries no
# declaration fragment, so it is found by resolving it inside its repository,
# and a relative spelling resolves against whatever directory the hook runs in.
AI_MODULE = f"{REPO_ROOT}/modules/home/ai"

DESTROYS_AN_ANCESTOR = [
    f"rm -rf {AI_MODULE}/pi",
    f"rm -rf {AI_MODULE}",
    f"rm -rf {REPO_ROOT}/modules",
    f"mv {AI_MODULE}/pi /tmp/elsewhere",
    f"mv /tmp/replacement {AI_MODULE}/pi",
    f"cp -r /tmp/replacement {AI_MODULE}/pi",
    f"ln -sfn /tmp/replacement {AI_MODULE}/pi",
    f"truncate -s 0 {AI_MODULE}/pi",
    f"ls && rm -rf {AI_MODULE}/pi",
    # `~/.claude/` is a declaration in its own right, so removing it is judged
    # by the naming rule and carries that rule's wording. The home above it is
    # an ancestor and nothing else.
    "rm -rf ~",
]

LEAVES_THE_ANCESTOR_ALONE = [
    f"cat {AI_MODULE}/pi/default.nix",
    f"ls {AI_MODULE}/pi",
    f"grep -rn foo {AI_MODULE}",
    f"cp /tmp/new.nix {AI_MODULE}/pi/new.nix",
    f"rm -rf {AI_MODULE}-backup",
    f"rm -rf {REPO_ROOT}/modules-old",
    "rm -rf /tmp/scratch",
    f"grep -rn 'rm -rf' {AI_MODULE}",
]


class TestDestructiveOperationsOnAnAncestor:
    """A declaration protects what it holds; the path to it has to be judged too."""

    @pytest.mark.parametrize("command", DESTROYS_AN_ANCESTOR, ids=lambda c: c[:44])
    def test_taking_the_ancestor_away_asks_under_claude(self, command: str) -> None:
        reason = ask_reason(bash(command, CLAUDE))
        assert "remove, rename, or replace" in reason

    @pytest.mark.parametrize("command", DESTROYS_AN_ANCESTOR, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_taking_the_ancestor_away_refuses_where_no_prompt_is_honored(
        self, command: str, agent: str
    ) -> None:
        assert_refused(bash(command, agent), "holds agent enforcement")

    @pytest.mark.parametrize("command", LEAVES_THE_ANCESTOR_ALONE, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_reading_or_adding_beneath_an_ancestor_proceeds(
        self, command: str, agent: str
    ) -> None:
        """Only taking the directory away is asked about, not working inside it."""
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""


AGENT_HOME_READS = [
    "cat ~/.codex/attachments/ec44cdf6/pasted-text.txt",
    "cat ~/.claude/projects/x/session.jsonl",
    "cat ~/.codex/sessions/2026/rollout.jsonl",
    "head -100 ~/.codex/history.jsonl",
    "grep -rn pattern ~/.claude/projects/",
    "ls ~/.codex/",
]

AGENT_HOME_WRITES = [
    "echo x > ~/.claude/settings.json",
    "cp /tmp/evil.py ~/.claude/hooks/block-secrets.py",
    "rm -rf ~/.codex/rules/",
    "sed -i s/a/b/ ~/.codex/config.toml",
    "echo x > ~/.claude/projects/x/session.jsonl",
    # Read-through is not exec-through.
    "uv run ~/.claude/hooks/block-secrets.py",
]


class TestAgentHomeIsReadThrough:
    """Session data an agent home mostly holds is readable; enforcement stays write-gated."""

    @pytest.mark.parametrize("command", AGENT_HOME_READS, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_recognized_read_proceeds_under_every_agent(
        self, command: str, agent: str
    ) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", AGENT_HOME_WRITES, ids=lambda c: c[:44])
    def test_a_write_route_still_asks_under_claude(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    @pytest.mark.parametrize("credential", CREDENTIAL_PATHS)
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_credential_read_is_still_refused_under_every_agent(
        self, credential: str, agent: str
    ) -> None:
        """The credential class is judged before any carve-out, so it outranks this one."""
        assert_refused(bash(f"cat {credential}", agent), Path(credential).name)

    def test_a_credential_beside_a_transcript_is_refused(self) -> None:
        assert_refused(
            bash("cat ~/.claude/projects/x.jsonl ~/.codex/auth.json", CLAUDE),
            "auth.json",
        )

    @pytest.mark.parametrize(
        "command",
        ["cat ~/.claude/settings.json", "cat ~/.codex/config.toml"],
        ids=lambda c: c[:40],
    )
    def test_a_deployed_file_resolving_into_a_repository_source_still_gates(
        self, command: str
    ) -> None:
        """The home carve-out covers the written form; the link's target carries its own."""
        assert ask_reason(bash(command, CLAUDE))


PI_SOURCE = "modules/home/ai/pi/security/shell-words.ts"
HOOK_SOURCE = "modules/home/ai/shared/hooks/block-secrets.py"

MODULE_TREE_READS = [
    f"cat {PI_SOURCE}",
    f"head -40 {HOOK_SOURCE}",
    f"grep -rn bashWriteTargets {PI_SOURCE}",
    "ls modules/home/ai/codex/rules/",
    "find modules/home/ai/copilot/hooks -name '*.md'",
    f"cat {PI_SOURCE} && echo --- && cat {HOOK_SOURCE}",
]

MODULE_TREE_WRITES = [
    f"echo pwned > {PI_SOURCE}",
    f"cp /tmp/replacement.ts {PI_SOURCE}",
    f"sed -i 's/a/b/' {HOOK_SOURCE}",
    # Spelled with the trailing separator: a bare directory name carries no
    # declaration fragment, so it is judged by repository resolution alone.
    "rm -rf modules/home/ai/shared/hooks/",
    f"cat {PI_SOURCE} && rm modules/home/ai/codex/rules/default.rules",
    # Read-through is not exec-through: a script held here stays unrunnable.
    f"uv run {HOOK_SOURCE}",
]


class TestAgentModuleTreeIsReadThrough:
    """The agent module sources are reviewable by every agent; writes still gate."""

    @pytest.mark.parametrize("command", MODULE_TREE_READS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_recognized_read_proceeds_under_every_agent(
        self, command: str, agent: str
    ) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", MODULE_TREE_WRITES, ids=lambda c: c[:40])
    def test_a_write_route_still_asks_under_claude(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    @pytest.mark.parametrize("command", MODULE_TREE_WRITES, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_a_write_route_still_refuses_where_no_prompt_is_honored(
        self, command: str, agent: str
    ) -> None:
        assert_refused(bash(command, agent))

    def test_a_guarded_path_outside_the_tree_gates_the_whole_command(self) -> None:
        assert ask_reason(bash(f"cat {PI_SOURCE} ~/.claude/settings.json", CLAUDE))

    def test_editing_module_source_still_gates_on_the_file_tools(self) -> None:
        assert ask_reason(write(PI_SOURCE, CLAUDE))
        assert ask_reason(edit(HOOK_SOURCE, CLAUDE))

    @pytest.mark.parametrize(
        "command",
        [
            "cat ~/.claude/hooks/block-secrets.py",
            "cat ~/.codex/rules/default.rules",
            "cat ~/.copilot/hooks/security-policy.json",
        ],
        ids=lambda c: c[:40],
    )
    def test_a_deployed_file_resolving_into_the_tree_reads_through(
        self, command: str
    ) -> None:
        # A deployed guardrail is a link into this tree, and a path is judged in
        # every spelling it has, so the declaration reaches the deployed name
        # too. Intended: the copy an agent meets first is the one it reviews.
        result = bash(command, CODEX)
        assert result.exit_code == 0
        assert result.stderr == ""

    @pytest.mark.parametrize(
        "command",
        ["cat ~/.claude/settings.json", "cat ~/.codex/config.toml"],
        ids=lambda c: c[:40],
    )
    def test_a_deployed_file_resolving_elsewhere_still_gates(
        self, command: str
    ) -> None:
        # These resolve into users/*/home-manager/, which no carve-out covers.
        assert ask_reason(bash(command, CLAUDE))


INSTRUCTION_MARKDOWN = "modules/home/ai/shared/hooks/instructions/00-response-style.md"

# Prose an agent has ordinary reason to write: it names guarded paths and
# changes none of them.
PROSE_NAMING_GUARDED_PATHS = (
    f"The hook refused a write to {HOOK_SOURCE}.",
    f"See also {PI_SOURCE} and ~/.claude/settings.json.",
)


class TestPatchIsJudgedByItsTargets:
    """A patch changes the files its headers name; the text it inserts is content.

    Judging the body would refuse an agent the ordinary work of writing about a
    guarded path — a note recording a refusal, or a spec citing the hook it
    specifies — and refuse it hardest on the agent that cannot ask.
    """

    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_content_naming_a_guarded_path_proceeds(self, agent: str) -> None:
        body = add_file("docs/incident.md", *PROSE_NAMING_GUARDED_PATHS)
        result = patch(body, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize(
        "header",
        ["*** Add File", "*** Update File", "*** Delete File", "*** Move to"],
    )
    def test_every_header_form_is_read_as_a_target(self, header: str) -> None:
        body = f"*** Begin Patch\n{header}: {HOOK_SOURCE}\n+x\n*** End Patch"
        assert ask_reason(patch(body, CLAUDE))

    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_a_guarded_target_refuses_where_no_prompt_is_honored(
        self, agent: str
    ) -> None:
        assert_refused(patch(add_file(HOOK_SOURCE, "# x"), agent))

    def test_one_guarded_target_among_several_gates_the_patch(self) -> None:
        body = (
            "*** Begin Patch\n"
            "*** Add File: docs/notes.md\n+ordinary\n"
            f"*** Update File: {PI_SOURCE}\n+// x\n"
            "*** End Patch"
        )
        assert ask_reason(patch(body, CLAUDE))

    def test_a_credential_target_refuses_on_every_agent(self) -> None:
        for credential in CREDENTIAL_PATHS:
            assert_refused(patch(add_file(credential, "{}"), CLAUDE), "credential")

    def test_instruction_markdown_stays_writable(self) -> None:
        result = patch(add_file(INSTRUCTION_MARKDOWN, "## Heading"), CODEX)
        assert result.exit_code == 0

    def test_a_body_no_header_parses_is_judged_by_its_text(self) -> None:
        # Nothing states a target, so the text is all that is left to judge.
        body = f"*** Begin Patch\n+touching {HOOK_SOURCE}\n*** End Patch"
        assert ask_reason(patch(body, CLAUDE))


SCRIPTS = "~/.agents/skills/demo/scripts"

RUNS = [
    f"{SCRIPTS}/run.sh",
    f"{SCRIPTS}/run.sh --port 8080",
    f"{SCRIPTS}/run-tool",
    f"uv run {SCRIPTS}/audit.py --json",
    f"python3 {SCRIPTS}/audit.py",
    f"node {SCRIPTS}/helper.cjs",
    f"bash {SCRIPTS}/run.sh | head -5",
]

# One per way a run can reach past the script it names: inline program text, a
# file that is not a program, a second command, a substituted binary, a write
# dressed as an argument, and a path the run would create.
NOT_RUNS = [
    f"bash -c 'rm -rf {SCRIPTS}'",
    f"python3 -c 'import shutil; shutil.rmtree(\"{SCRIPTS}\")'",
    "uv run ~/.agents/skills/demo/SKILL.md",
    f"bash {SCRIPTS}/run.sh; rm -rf {SCRIPTS}",
    f"PATH=/tmp:$PATH bash {SCRIPTS}/run.sh",
    f"cp /tmp/replacement.sh {SCRIPTS}/run.sh",
    f"uv run {SCRIPTS}/absent.py",
    f"bash {SCRIPTS}/run.sh {SCRIPTS}/audit.py",
]


@pytest.fixture
def skills_home(tmp_path: Path) -> str:
    """A home whose exec-through location holds one script of each recognized form."""
    scripts = tmp_path / ".agents" / "skills" / "demo" / "scripts"
    scripts.mkdir(parents=True)
    runnable = scripts / "run.sh"
    runnable.write_text("#!/usr/bin/env bash\necho ran\n")
    runnable.chmod(0o755)
    # No suffix: the execute bit is what makes it a script.
    extensionless = scripts / "run-tool"
    extensionless.write_text("#!/usr/bin/env bash\necho ran\n")
    extensionless.chmod(0o755)
    # No execute bit: its suffix is what makes it a script.
    (scripts / "helper.cjs").write_text("console.log('ran')\n")
    (scripts / "audit.py").write_text("print('ran')\n")
    (tmp_path / ".agents" / "skills" / "demo" / "SKILL.md").write_text("# Demo\n")
    return str(tmp_path)


class TestExecThroughCarveOut:
    """Under an exec-through location a run of a script held there proceeds."""

    @pytest.mark.parametrize("command", RUNS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_recognized_run_proceeds_under_every_agent(
        self, command: str, agent: str, skills_home: str
    ) -> None:
        result = bash(command, agent, skills_home)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", NOT_RUNS, ids=lambda c: c[:40])
    def test_anything_else_asks_under_claude(
        self, command: str, skills_home: str
    ) -> None:
        assert ask_reason(bash(command, CLAUDE, skills_home))

    @pytest.mark.parametrize("command", NOT_RUNS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_anything_else_refuses_where_no_prompt_is_honored(
        self, command: str, agent: str, skills_home: str
    ) -> None:
        assert_refused(bash(command, agent, skills_home), "not a recognized read")

    def test_an_argument_outside_the_carve_out_gates_the_whole_run(
        self, skills_home: str
    ) -> None:
        # `~/.pi/agent/` carries a declaration that no carve-out covers; the
        # agent homes below `~/.claude` and `~/.codex` are read-through.
        command = f"bash {SCRIPTS}/run.sh --settings ~/.pi/agent/settings.json"
        reason = ask_reason(bash(command, CLAUDE, skills_home))
        assert "enforcement" in reason

    def test_a_write_to_the_script_still_gates_on_the_file_tools(
        self, skills_home: str
    ) -> None:
        assert ask_reason(write(f"{SCRIPTS}/run.sh", CLAUDE, skills_home))


# The declared read-through and exec-through lists are identical, so no command
# against the real manifest tells the two apart. A substituted manifest can, but
# the hook binds both classes at import, so it has to reach a hook running from
# its own copy.
SPLIT_CLASSES = """\
[gated]
deployed = ["~/.example/readable/", "~/.example/runnable/"]
sources = []
[credentials]
paths = []
[instruction-layers]
layers = []
[location-only]
paths = []
[read-through]
paths = ["~/.example/readable/", "~/.example/runnable/"]
[exec-through]
paths = ["~/.example/runnable/"]
[secret-floor]
paths = []
"""


class TestExecThroughIsItsOwnClass:
    """A run is judged against the exec-through class, a read against read-through."""

    @staticmethod
    @pytest.fixture
    def split(tmp_path: Path) -> tuple[Path, str]:
        hooks = tmp_path / "hooks"
        shutil.copytree(HOOKS_DIR, hooks)
        (hooks / "guarded-paths.toml").write_text(SPLIT_CLASSES)

        home = tmp_path / "home"
        for location in ("readable", "runnable"):
            directory = home / ".example" / location
            directory.mkdir(parents=True)
            script = directory / "run.sh"
            script.write_text("#!/usr/bin/env bash\necho ran\n")
            script.chmod(0o755)
        return hooks / "block-hook-tampering.py", str(home)

    @staticmethod
    def _judge(split: tuple[Path, str], command: str) -> GateResult:
        hook, home = split
        env = {**os.environ, "HOME": home}
        env.pop("AI_HOOK_AGENT", None)
        result = subprocess.run(
            ["python3", str(hook)],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "transcript_path": "/tmp/transcript.jsonl",
                }
            ),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=env,
        )
        return GateResult(result.returncode, result.stdout, result.stderr)

    def test_a_run_under_an_exec_through_location_proceeds(self, split) -> None:
        result = self._judge(split, "bash ~/.example/runnable/run.sh")
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_a_run_under_a_read_through_location_gates(self, split) -> None:
        """Reading the exec-through class is what makes this gate; reading the
        read-through class in its place would let it through."""
        assert ask_reason(self._judge(split, "bash ~/.example/readable/run.sh"))

    def test_a_read_under_a_read_through_location_still_proceeds(self, split) -> None:
        result = self._judge(split, "cat ~/.example/readable/run.sh")
        assert result.exit_code == 0
        assert result.stdout == ""


class TestReaderHint:
    """A command stopped by the classifier says so, and names what would pass."""

    def test_the_prompt_names_the_accepted_readers(self) -> None:
        reason = ask_reason(bash(f"sed -n '1,5p' {SKILL_FILE}", CLAUDE))
        assert "not recognized as a read" in reason
        for utility in ("cat", "grep", "head", "cut"):
            assert utility in reason

    def test_the_prompt_names_the_accepted_interpreters(self) -> None:
        reason = ask_reason(bash(f"sed -n '1,5p' {SKILL_FILE}", CLAUDE))
        for interpreter in ("python3", "node", "uvx", "Rscript"):
            assert interpreter in reason

    def test_the_prompt_does_not_call_a_read_a_modification(self) -> None:
        reason = ask_reason(bash(f"sed -n '1,5p' {SKILL_FILE}", CLAUDE))
        assert "would modify" not in reason

    def test_a_path_outside_the_carve_out_keeps_the_enforcement_wording(self) -> None:
        reason = ask_reason(bash("cat ~/.claude/settings.json", CLAUDE))
        assert "recognized as a read" not in reason
        assert "enforcement" in reason

    def test_the_guidance_reaches_an_agent_that_cannot_prompt(self) -> None:
        assert_refused(
            bash(f"sed -n '1,5p' {SKILL_FILE}", CODEX), "not a recognized read"
        )


class TestAskReasonContract:
    def test_reason_names_the_file_and_states_the_enforcement_consequence(
        self,
    ) -> None:
        reason = ask_reason(edit("~/.claude/settings.json", CLAUDE))
        assert "settings.json" in reason
        assert "enforcement" in reason.lower()
        assert "guardrail" in reason.lower()
