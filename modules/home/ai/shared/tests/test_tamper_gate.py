"""The gate's outcome across agents and protected classes.

The per-agent suites pin each agent's encoding in isolation; this file pins the
matrix — the same payload, judged per (agent, tool) pairing.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess

import bash_commands
from guarded_paths import folds_case
import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
HOOK = HOOKS_DIR / "block-hook-tampering.py"
REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "flake.nix").is_file())

CLAUDE = "claude"
CODEX = "codex"
COPILOT = "copilot"
UNKNOWN = "unknown"

REPO_SOURCE = "modules/home/ai/codex/rules/default.rules"
CREDENTIAL_PATHS = (
    "~/.claude.json",
    "~/.config/mcp-secrets.env",
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
    tool_name: str, tool_input: dict, agent: str, home: str | None = None, cwd: str | None = str(REPO_ROOT)
) -> GateResult:
    """Run the hook as `agent` would invoke it: Claude Code by the transcript
    path its payloads carry, the others by the declaration their adapters set.

    `home` substitutes the home directory the hook expands `~` against, so a
    case that needs files on disk can build them. `cwd` is the working
    directory the payload supplies; `None` omits it.
    """
    payload: dict = {"tool_name": tool_name, "tool_input": tool_input}
    if cwd is not None:
        payload["cwd"] = cwd
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
    return run_gate("Edit", {"file_path": path, "old_string": "a", "new_string": "b"}, agent)


def bash(command: str, agent: str, home: str | None = None, cwd: str | None = str(REPO_ROOT)) -> GateResult:
    return run_gate("Bash", {"command": command}, agent, home, cwd)


def patch(body: str, agent: str) -> GateResult:
    return run_gate("apply_patch", {"command": body}, agent)


def add_file(path: str, *lines: str) -> str:
    """An apply_patch body adding `path`, carrying `lines` as its content."""
    added = "".join(f"+{line}\n" for line in lines)
    return f"*** Begin Patch\n*** Add File: {path}\n{added}*** End Patch"


def ask_reason(result: GateResult) -> str:
    assert result.exit_code == 0, f"Expected ask (exit 0), got {result.exit_code}.\nstderr: {result.stderr}"
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "ask"
    return output["permissionDecisionReason"]


def assert_refused(result: GateResult, substring: str = "") -> None:
    assert result.exit_code == 2, f"Expected refusal (exit 2), got {result.exit_code}.\nstdout: {result.stdout}"
    assert result.stdout == "", f"A refusal must write nothing to stdout, got: {result.stdout}"
    if substring:
        assert substring.lower() in result.stderr.lower(), f"Expected '{substring}' in stderr, got: {result.stderr}"


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
    def test_credential_write_refuses_under_every_agent(self, agent: str, credential: str) -> None:
        assert_refused(write(credential, agent), Path(credential).name)

    @pytest.mark.parametrize("credential", CREDENTIAL_PATHS)
    def test_mixed_class_command_refuses(self, credential: str) -> None:
        """The most restrictive class wins, even where the agent could prompt."""
        assert_refused(bash(f"cat {REPO_SOURCE} {credential}", CLAUDE), Path(credential).name)


class TestSpellingReachesTheGate:
    def test_case_variant_spelling_reaches_the_gate(self) -> None:
        if not folds_case(os.path.expanduser("~")):
            pytest.skip("filesystem under test is case-sensitive")
        assert ask_reason(write("~/.CLAUDE/settings.json", CLAUDE))

    def test_unresolvable_protected_path_reaches_the_gate(self) -> None:
        """A path resolution cannot follow is judged from the path as written."""
        target = f"{REPO_ROOT}/modules/home/ai/shared/hooks/x\x00.py"
        assert ask_reason(write(target, CLAUDE))


class TestInstructionMarkdownIsGuarded:
    def test_direct_instruction_markdown_asks(self) -> None:
        result = write("modules/home/ai/claude/hooks/instructions/00-response-style.md", CLAUDE)
        assert ask_reason(result)

    def test_nested_path_under_instructions_is_gated(self) -> None:
        assert ask_reason(write("modules/home/ai/claude/hooks/instructions/nested/note.md", CLAUDE))

    def test_non_markdown_in_instructions_is_gated(self) -> None:
        assert ask_reason(write("modules/home/ai/claude/hooks/instructions/helper.py", CLAUDE))

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
SKILL_DIR = str(Path(SKILL_FILE).parent)
SKILL_REAL = "~/.agents/skills/sdd-sync/references/sdd-spec-formats.md"

READS = [
    f"cat {SKILL_FILE}",
    "cat ~/.codex/skills/.system/openai-docs/SKILL.md",
    f"grep -n Baseline {SKILL_FILE} | head",
    f"grep -n 'Baseline spec\\|## 2' {SKILL_FILE}",
    f"grep -n 'formats$' {SKILL_FILE}",
    f"head -64 {SKILL_FILE} | cut -c1-200",
    f"cat {SKILL_FILE} | tr -s ' ' | sort | wc -l",
    "ls ~/.claude/skills/sdd-sync",
    "find ~/.claude/skills -name SKILL.md",
    f"rg --no-config -n pattern {SKILL_FILE}",
    f"rg --no-config --files {SKILL_DIR}",
    f"rg --no-config -l pattern {SKILL_FILE}",
    f"rg --no-config --pre-glob '*.md' pattern {SKILL_FILE}",
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
    f"cat {SKILL_FILE} && cat evals/x.py | awk '{{print}}'",
    "bash -c 'rm ~/.claude/settings.json'",
    "echo ~/.claude/settings.json | xargs rm",
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
    # Ripgrep is a read only when --no-config is first and no option can run
    # another program.
    f"rg -n pattern {SKILL_FILE}",
    f"rg --no-config --pre /tmp/helper pattern {SKILL_FILE}",
    f"rg --no-config -z pattern {SKILL_FILE}",
    f"rg --no-config --search-zip pattern {SKILL_FILE}",
    f"rg --no-config --hostname-bin /tmp/helper pattern {SKILL_FILE}",
    f"rg --no-config --pre=/tmp/helper pattern {SKILL_FILE}",
    f"rg --no-config -nz pattern {SKILL_FILE}",
    f"rg -e --no-config pattern {SKILL_FILE}",
    f"rg --files --no-config {SKILL_DIR}",
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


class TestGuardedLocationReads:
    """Under a guarded location a recognized read proceeds; the rest gates."""

    @pytest.mark.parametrize("command", READS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_recognized_read_proceeds_under_every_agent(self, command: str, agent: str) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", NOT_READS, ids=lambda c: c[:40])
    def test_anything_else_asks_under_claude(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    @pytest.mark.parametrize("command", NOT_READS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_anything_else_refuses_where_no_prompt_is_honored(self, command: str, agent: str) -> None:
        assert_refused(bash(command, agent), "not recognized as an authorized action")

    def test_reading_skills_and_guarded_settings_proceeds(
        self,
    ) -> None:
        assert_allowed(bash(f"cat {SKILL_FILE} ~/.claude/settings.json", CLAUDE))

    @pytest.mark.parametrize("path", [SKILL_FILE, SKILL_REAL])
    def test_a_write_to_skill_content_still_gates_on_the_file_tools(self, path: str) -> None:
        assert ask_reason(write(path, CLAUDE))
        assert ask_reason(edit(path, CLAUDE))


# Quoting is resolved before the read classifier judges a word. A `$` that
# survives resolution is the literal character, so the word is a search pattern
# and not an option the shell would rewrite into one the classifier never saw.
RESOLVED_DOLLAR_READS = [
    f"grep --regexp='$HOME' {SKILL_FILE}",
    f"grep -e'$HOME' {SKILL_FILE}",
    f"grep --regexp=$'\\x24HOME' {SKILL_FILE}",
]

# The shell rewrites each of these, so the lexer reports the word unresolvable.
EXPANDED_DOLLAR_NOT_READS = [
    f"grep --regexp=$HOME {SKILL_FILE}",
    f'grep --regexp="$HOME" {SKILL_FILE}',
]


class TestAQuotedDollarInAnOptionIsTheLiteralCharacter:
    """An option carrying `$` stays a read where quoting resolved it, and gates where it did not."""

    @pytest.mark.parametrize("command", RESOLVED_DOLLAR_READS, ids=lambda c: c[:36])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_resolved_dollar_leaves_the_read_recognized(self, command: str, agent: str) -> None:
        assert_allowed(bash(command, agent))

    @pytest.mark.parametrize("command", EXPANDED_DOLLAR_NOT_READS, ids=lambda c: c[:36])
    def test_an_unresolved_dollar_gates_the_command(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    def test_resolving_the_quoting_does_not_admit_a_write_option(self) -> None:
        assert ask_reason(bash(f"sort --output='$HOME' {SKILL_FILE}", CLAUDE))


UNJUDGED_BESIDE_A_READ = [
    f"cat {SKILL_FILE} && rg -n 'baseline|treatment' evals/README.md",
    f"cat {SKILL_FILE} && sed -n '1,5p' evals/run.py",
    f"cat {SKILL_FILE} && make test",
]

JUDGED_BESIDE_A_READ = [
    f"cat {SKILL_FILE} && rm -rf ~/.claude/skills/sdd-sync",
    f"cat {SKILL_FILE} && cd ~ && rm -rf .claude/hooks",
    f"cat {SKILL_FILE}\nrm -rf ~/.claude/skills",
    f"cat evals/x.py | tee {SKILL_FILE}",
    "cat evals/x.py ~/.codex/auth.json",
]


class TestOnlySegmentsNamingAGuardedPathAreJudged:
    """A segment naming nothing guarded is not this hook's to classify."""

    @pytest.mark.parametrize("command", UNJUDGED_BESIDE_A_READ, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_an_unrelated_segment_does_not_gate_the_command(self, command: str, agent: str) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", JUDGED_BESIDE_A_READ, ids=lambda c: c[:44])
    def test_a_segment_reaching_a_guarded_path_still_gates(self, command: str) -> None:
        result = bash(command, CLAUDE)
        assert result.exit_code != 0 or json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] in (
            "ask",
            "deny",
        )


# `trap` quotes its body into one word, so the word-level checks do not see the
# paths inside it, and the body runs beside every later command.
INSTALLS_DEFERRED_CODE = [
    f"trap '/bin/echo banner' DEBUG; cat {SKILL_FILE}",
    f"trap '/bin/echo banner' ERR; cat {SKILL_FILE}",
    f"trap '/bin/echo banner' EXIT; cat {SKILL_FILE}",
    f"trap 'cp /tmp/replacement.md {SKILL_FILE}' DEBUG; cat {SKILL_FILE}",
    f"trap 'rm -rf {SKILL_DIR}' DEBUG; cat {SKILL_FILE}",
    f"trap '/bin/echo banner' DEBUG; rg --no-config -n pattern {SKILL_FILE}",
    f"cat {SKILL_FILE}; trap '/bin/echo banner' DEBUG",
    # `builtin` only chooses how the shell dispatches `trap`.
    f"builtin trap '/bin/echo banner' DEBUG; cat {SKILL_FILE}",
    f"builtin trap 'cp /tmp/replacement.md {SKILL_FILE}' DEBUG; cat {SKILL_FILE}",
    # The body alone, without a read beside it.
    f"trap 'cp /tmp/replacement.md {SKILL_FILE}' DEBUG",
    f"trap 'rm -rf {SKILL_DIR}' DEBUG; cat /etc/hosts",
    # A definition rebinds the name, so it reaches the body, not the admitted program.
    f'cat() {{ cp /tmp/replacement.md "$1"; }}; cat {SKILL_FILE}',
    f'function cat {{ cp /tmp/replacement.md "$1"; }}; cat {SKILL_FILE}',
    f'grep() {{ cp /tmp/replacement.md "$2"; }}; grep pattern {SKILL_FILE}',
    f'rg() {{ command rg "${{@:2}}"; }}; rg --no-config needle {SKILL_FILE}',
]

# `trap -p` lists the installed handlers and `trap -` resets them.
INSTALLS_NOTHING = [
    f"trap -p DEBUG; cat {SKILL_FILE}",
    f"trap - DEBUG; cat {SKILL_FILE}",
    f"builtin trap -p DEBUG; cat {SKILL_FILE}",
]


def _admitted_utilities() -> list[str]:
    """Read the admitted set from the classifier, so the test follows the source."""
    return sorted(bash_commands.READ_ONLY_UTILITIES)


class TestAnAdmittedUtilityWritesNoOperand:
    """Every admitted utility must leave a second file operand untouched."""

    @pytest.mark.parametrize("utility", _admitted_utilities())
    def test_a_second_file_operand_is_not_written(self, utility: str, tmp_path: Path) -> None:
        if shutil.which(utility) is None:
            pytest.skip(f"{utility} is not installed here")
        source = tmp_path / "source.txt"
        source.write_text("REPLACEMENT\n")
        target = tmp_path / "target.txt"
        target.write_text("SENTINEL\n")
        try:
            subprocess.run(
                [utility, str(source), str(target)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(f"{utility} did not exit; it does not simply read its operands")
        assert target.read_text() == "SENTINEL\n", (
            f"{utility} wrote its second operand, so it is not a read. Remove it from bash_commands.READ_ONLY_UTILITIES."
        )


_STOP = "do not attempt to find alternative commands"
_RETRY = "the classifier stopped this call"
_REPORT = "how the user can help — describe exactly what command or steps"


class TestTheInstructionFormFollowsWhatTheRefusalOffers:
    """A refusal naming accepted commands says to use one; every other says stop."""

    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_a_refusal_naming_accepted_commands_says_to_use_one(self, agent: str) -> None:
        stderr = bash(f"sed -n '1,5p' {SKILL_FILE}", agent).stderr.lower()
        assert "recognized reads use:" in stderr
        assert _RETRY in stderr
        assert _STOP not in stderr

    @pytest.mark.parametrize("agent", [CODEX, UNKNOWN])
    def test_a_refusal_naming_none_says_to_stop(self, agent: str) -> None:
        stderr = write(SKILL_FILE, agent).stderr.lower()
        assert "recognized reads use:" not in stderr
        assert _STOP in stderr
        assert _RETRY not in stderr

    # The classifier stops on the shape of each of these, so a different utility
    # runs into the same stop and the refusal omits the accepted set.
    @pytest.mark.parametrize(
        "command",
        [
            f"echo pwned > {SKILL_FILE}",
            f"cat /tmp/x >> {SKILL_FILE}",
            f"PATH=/tmp cat {SKILL_FILE}",
            f"cat $(echo {SKILL_FILE})",
            f"trap 'cp /tmp/x {SKILL_FILE}' DEBUG; cat {SKILL_FILE}",
        ],
        ids=lambda c: c[:34],
    )
    @pytest.mark.parametrize("agent", [CODEX, UNKNOWN])
    def test_an_objection_no_other_command_resolves_says_to_stop(self, command: str, agent: str) -> None:
        stderr = bash(command, agent).stderr.lower()
        assert "recognized reads use:" not in stderr
        assert _STOP in stderr
        assert _RETRY not in stderr

    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_an_ancestor_refusal_names_none_and_says_to_stop(self, agent: str) -> None:
        # An ancestor matches no declaration, so this reaches the ancestor gate.
        stderr = bash(f"rm -rf {REPO_ROOT}/modules/home/ai/pi", agent).stderr.lower()
        assert "recognized reads use:" not in stderr
        assert _STOP in stderr
        assert _RETRY not in stderr

    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_credential_refusal_says_to_stop(self, agent: str) -> None:
        stderr = bash("cat ~/.codex/auth.json", agent).stderr.lower()
        assert _STOP in stderr
        assert _RETRY not in stderr

    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_credential_refusal_says_to_stop_when_unrecognized(self, agent: str) -> None:
        stderr = bash("sed -n '1,5p' ~/.codex/auth.json", agent).stderr.lower()
        assert _STOP in stderr
        assert _RETRY not in stderr

    def test_a_decision_reaching_the_user_carries_neither(self) -> None:
        reason = ask_reason(bash(f"sed -n '1,5p' {SKILL_FILE}", CLAUDE)).lower()
        assert _STOP not in reason
        assert _RETRY not in reason

    @pytest.mark.parametrize("agent", [CODEX, UNKNOWN])
    def test_both_forms_ask_for_the_same_report(self, agent: str) -> None:
        retry = bash(f"sed -n '1,5p' {SKILL_FILE}", agent).stderr.lower()
        stop = write(SKILL_FILE, agent).stderr.lower()
        assert _REPORT in retry
        assert _REPORT in stop


class TestInstallingDeferredCodeTakesNoReadCarveOut:
    """A command that installs code for the shell to run later is judged whole."""

    @pytest.mark.parametrize("command", INSTALLS_DEFERRED_CODE, ids=lambda c: c[:44])
    def test_it_asks_under_claude(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    @pytest.mark.parametrize("command", INSTALLS_DEFERRED_CODE, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_it_refuses_where_no_prompt_is_honored(self, command: str, agent: str) -> None:
        assert_refused(bash(command, agent), "not recognized as an authorized action")

    def test_a_trap_body_naming_a_credential_refuses_everywhere(self) -> None:
        assert_refused(
            bash(f"trap 'cat ~/.codex/auth.json' DEBUG; cat {SKILL_FILE}", CLAUDE),
            "credential",
        )

    @pytest.mark.parametrize("command", INSTALLS_NOTHING, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_listing_or_resetting_handlers_keeps_the_carve_out(self, command: str, agent: str) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""


# Absolute, unlike the named-path cases above. An ancestor carries no
# declaration fragment, so it is found by resolving it inside its repository,
# and a relative spelling resolves against the directory the payload supplies.
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
    def test_taking_the_ancestor_away_refuses_where_no_prompt_is_honored(self, command: str, agent: str) -> None:
        assert_refused(bash(command, agent), "holds agent enforcement")

    @pytest.mark.parametrize("command", LEAVES_THE_ANCESTOR_ALONE, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_reading_or_adding_beneath_an_ancestor_proceeds(self, command: str, agent: str) -> None:
        """Only taking the directory away is asked about, not working inside it."""
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""


# With no working directory in the payload, a relative operand may name any
# directory, an ancestor of a declaration included.
DESTROYS_A_RELATIVE_OPERAND = [
    "rm -r modules/home/ai/pi",
    "rm -rf build",
    "mv modules /tmp/elsewhere",
    "mv /tmp/replacement modules",
    "rm -rf ..",
    "ls && rm -rf .",
]

NAMES_EVERY_DESTROYED_OPERAND_ABSOLUTELY = [
    "rm -rf /tmp/scratch",
    "rm -rf ~/scratch",
    "cat modules/home/ai/pi/default.nix",
    "cp modules/home/ai/pi/default.nix /tmp/copy.nix",
]


class TestRelativeOperandWithoutAWorkingDirectory:
    """A relative operand the payload gives no directory for cannot be judged, so it is refused."""

    @pytest.mark.parametrize("command", DESTROYS_A_RELATIVE_OPERAND, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_destroying_a_relative_operand_refuses_and_stops(self, command: str, agent: str) -> None:
        """No prompt is offered: the user cannot judge a path the hook cannot place either."""
        result = bash(command, agent, cwd=None)
        assert_refused(result, "supplies no working directory")
        assert "absolute path" in result.stderr
        assert "Do NOT attempt to find alternative commands" in result.stderr

    @pytest.mark.parametrize("command", NAMES_EVERY_DESTROYED_OPERAND_ABSOLUTELY, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX])
    def test_absolute_or_unharmed_operands_proceed(self, command: str, agent: str) -> None:
        result = bash(command, agent, cwd=None)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    def test_an_absolute_ancestor_is_still_judged(self) -> None:
        reason = ask_reason(bash(f"rm -rf {AI_MODULE}/pi", CLAUDE, cwd=None))
        assert "remove, rename, or replace" in reason

    @pytest.mark.parametrize("agent", [CLAUDE, CODEX])
    def test_a_supplied_directory_decides_where_it_leads(self, agent: str) -> None:
        """Resolved against a directory outside the repository, the same spelling is not an ancestor."""
        result = bash("rm -r modules/home/ai/pi", agent, cwd="/tmp")
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
    # Read-through is not exec-through.
    "uv run ~/.claude/hooks/block-secrets.py",
]


class TestAgentHomeReadsProceed:
    """Session data an agent home mostly holds is readable; enforcement stays write-gated."""

    @pytest.mark.parametrize("command", AGENT_HOME_READS, ids=lambda c: c[:44])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_recognized_read_proceeds_under_every_agent(self, command: str, agent: str) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", AGENT_HOME_WRITES, ids=lambda c: c[:44])
    def test_a_write_route_still_asks_under_claude(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    @pytest.mark.parametrize("credential", CREDENTIAL_PATHS)
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_credential_read_is_still_refused_under_every_agent(self, credential: str, agent: str) -> None:
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
    def test_reading_a_deployed_repository_source_proceeds(self, command: str) -> None:
        """Reads of guarded files proceed through every spelling."""
        assert_allowed(bash(command, CLAUDE))


PI_SOURCE = "modules/home/ai/pi/hooks/extension.ts"
HOOK_SOURCE = "modules/home/ai/shared/hooks/block-secrets.py"

MODULE_TREE_READS = [
    f"cat {PI_SOURCE}",
    f"head -40 {HOOK_SOURCE}",
    f"grep -rn registerHooks {PI_SOURCE}",
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


class TestAgentModuleTreeReadsProceed:
    """The agent module sources are reviewable by every agent; writes still gate."""

    @pytest.mark.parametrize("command", MODULE_TREE_READS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CLAUDE, CODEX, COPILOT, UNKNOWN])
    def test_a_recognized_read_proceeds_under_every_agent(self, command: str, agent: str) -> None:
        result = bash(command, agent)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", MODULE_TREE_WRITES, ids=lambda c: c[:40])
    def test_a_write_route_still_asks_under_claude(self, command: str) -> None:
        assert ask_reason(bash(command, CLAUDE))

    @pytest.mark.parametrize("command", MODULE_TREE_WRITES, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_a_write_route_still_refuses_where_no_prompt_is_honored(self, command: str, agent: str) -> None:
        assert_refused(bash(command, agent))

    def test_reading_module_source_and_guarded_settings_proceeds(self) -> None:
        assert_allowed(bash(f"cat {PI_SOURCE} ~/.claude/settings.json", CLAUDE))

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
    def test_a_deployed_file_resolving_into_the_tree_reads_through(self, command: str) -> None:
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
    def test_reading_deployed_user_settings_proceeds(self, command: str) -> None:
        # User settings sources are guarded and readable.
        assert_allowed(bash(command, CLAUDE))


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
    def test_a_guarded_target_refuses_where_no_prompt_is_honored(self, agent: str) -> None:
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

    def test_instruction_markdown_refuses_without_a_prompt(self) -> None:
        result = patch(add_file(INSTRUCTION_MARKDOWN, "## Heading"), CODEX)
        assert_refused(result)

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
    def test_a_recognized_run_proceeds_under_every_agent(self, command: str, agent: str, skills_home: str) -> None:
        result = bash(command, agent, skills_home)
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.parametrize("command", NOT_RUNS, ids=lambda c: c[:40])
    def test_anything_else_asks_under_claude(self, command: str, skills_home: str) -> None:
        assert ask_reason(bash(command, CLAUDE, skills_home))

    @pytest.mark.parametrize("command", NOT_RUNS, ids=lambda c: c[:40])
    @pytest.mark.parametrize("agent", [CODEX, COPILOT, UNKNOWN])
    def test_anything_else_refuses_where_no_prompt_is_honored(
        self, command: str, agent: str, skills_home: str
    ) -> None:
        assert_refused(bash(command, agent, skills_home), "not recognized as an authorized action")

    def test_an_argument_outside_the_carve_out_gates_the_whole_run(self, skills_home: str) -> None:
        # `~/.pi/agent/` carries a declaration that no carve-out covers; the
        # agent homes below `~/.claude` and `~/.codex` are guarded, and a read
        # of a guarded location proceeds.
        command = f"bash {SCRIPTS}/run.sh --settings ~/.pi/agent/settings.json"
        reason = ask_reason(bash(command, CLAUDE, skills_home))
        assert "not recognized" in reason

    def test_a_write_to_the_script_still_gates_on_the_file_tools(self, skills_home: str) -> None:
        assert ask_reason(write(f"{SCRIPTS}/run.sh", CLAUDE, skills_home))


# This manifest separates a guarded-only location from an exec-through one, so a
# run can be told from a read. The hook binds its classes at import, so the case
# has to reach a hook running from its own copy.
SPLIT_CLASSES = """\
exceptions = []
[guarded]
paths = ["~/.example/readable/", "~/.example/runnable/"]
[block]
paths = []
[exec-through]
paths = ["~/.example/runnable/"]
[write-through]
paths = []
"""


class TestExecThroughIsItsOwnClass:
    """A run is judged against the exec-through class; a read proceeds under any class but block."""

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

    def test_a_run_under_a_guarded_only_location_gates(self, split) -> None:
        """Judging the run against the exec-through class is what makes this
        gate; the guarded default alone does not permit a run."""
        assert ask_reason(self._judge(split, "bash ~/.example/readable/run.sh"))

    def test_a_read_under_a_guarded_only_location_still_proceeds(self, split) -> None:
        result = self._judge(split, "cat ~/.example/readable/run.sh")
        assert result.exit_code == 0
        assert result.stdout == ""


class TestReaderHint:
    """A command stopped by the classifier says so, and names what would pass."""

    def test_the_prompt_names_the_accepted_readers(self) -> None:
        reason = ask_reason(bash(f"sed -n '1,5p' {SKILL_FILE}", CLAUDE))
        assert "not recognized as an authorized action" in reason
        for utility in ("cat", "grep", "head", "cut"):
            assert utility in reason

    def test_the_prompt_leaves_them_out_where_they_would_not_help(self) -> None:
        reason = ask_reason(bash(f"echo pwned > {SKILL_FILE}", CLAUDE))
        assert "recognized reads use" not in reason.lower()
        assert "a redirection" in reason

    def test_the_prompt_states_required_first_options(self) -> None:
        reason = ask_reason(bash(f"rg -n pattern {SKILL_FILE}", CLAUDE))
        assert "rg requires --no-config as its first option" in reason

    def test_the_prompt_names_the_accepted_interpreters(self) -> None:
        reason = ask_reason(bash(f"sed -n '1,5p' {SKILL_FILE}", CLAUDE))
        for interpreter in ("python3", "node", "uvx", "Rscript"):
            assert interpreter in reason

    def test_the_prompt_does_not_call_a_read_a_modification(self) -> None:
        reason = ask_reason(bash(f"sed -n '1,5p' {SKILL_FILE}", CLAUDE))
        assert "would modify" not in reason

    def test_a_guarded_settings_read_proceeds(self) -> None:
        assert_allowed(bash("cat ~/.claude/settings.json", CLAUDE))

    def test_the_guidance_reaches_an_agent_that_cannot_prompt(self) -> None:
        assert_refused(bash(f"sed -n '1,5p' {SKILL_FILE}", CODEX), "not recognized as an authorized action")


class TestAskReasonContract:
    def test_reason_names_the_file_and_states_the_enforcement_consequence(
        self,
    ) -> None:
        reason = ask_reason(edit("~/.claude/settings.json", CLAUDE))
        assert "settings.json" in reason
        assert "enforcement" in reason.lower()
        assert "guardrail" in reason.lower()


def assert_allowed(result: GateResult) -> None:
    assert (result.exit_code, result.stdout, result.stderr) == (0, "", "")
