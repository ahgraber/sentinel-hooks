"""Hook decisions follow the supplied class policy and the shared lexer."""

import io
import json

from hermetic import load_hook
import pytest


def test_sensitive_relative_path_does_not_use_process_cwd(tmp_path, monkeypatch):
    hook = load_hook("block-sensitive-paths")
    (tmp_path / "ordinary").symlink_to(tmp_path / "secret-material")
    monkeypatch.chdir(tmp_path)
    assert not hook.should_block("ordinary")
    assert hook.should_block("ordinary", cwd=str(tmp_path))


@pytest.mark.parametrize(
    ("tool", "target", "expected"),
    [
        ("Read", "~/base/file", "allow"),
        ("Read", "~/base/private", "block"),
        ("Write", "~/base/notes/note.md", "allow"),
        ("Write", "~/base/notes/nested/note.md", "ask"),
        ("Write", "~/base/notes/note.py", "ask"),
        ("Write", "~/memory/note", "allow"),
        ("Write", "~/memory/link", "ask"),
        ("Bash", "~/memory/note", "ask"),
        ("Bash", "bash ~/memory/note", "ask"),
        ("Bash", "python3 ~/memory/note --flag", "ask"),
        ("Write", "~/other-agent/settings", "ask"),
        ("Bash", "cat ~/base/file", "allow"),
        ("Bash", "time cat ~/base/file", "allow"),
        ("Bash", "timeout -s TERM 5 cat ~/base/file", "allow"),
        ("Bash", "stdbuf -o L cat ~/base/file", "allow"),
        ("Bash", "setsid -w cat ~/base/file", "allow"),
        ("Bash", "time -o~/base/file cat /tmp/input", "ask"),
        ("Bash", "cat ~/base/file ; time xargs", "ask"),
        ("Bash", "cat ~/base/file | time xargs rm", "ask"),
        ("Bash", "cat ~/base/file | timeout 5 unknown-wrapper", "ask"),
        ("Bash", "cat ~/base/file | python", "ask"),
        ("Bash", "cat ~/base/file | unknown-wrapper", "ask"),
        ("Bash", "time env PATH=/tmp cat ~/base/file", "ask"),
        ("Bash", "cat ~/base/file 2>&1", "allow"),
        ("Bash", "cat ~/base/file 2>&-", "allow"),
        ("Bash", "echo value >&~/base/file", "ask"),
        ("Bash", "cat ~/base/private", "block"),
        ("Bash", "cat $(cat ~/base/private)", "block"),
        ("Bash", "tee ~/memory/note ~/base/file", "ask"),
        ("Bash", "echo x > ~/memory/note", "allow"),
        ("Bash", "echo x > ~/base/file", "ask"),
        ("Bash", "dd if=/tmp/source of=~/base/file", "ask"),
        # An admitted utility's write option is refused; the utility still reads.
        ("Bash", "sort -o ~/base/file /tmp/source", "ask"),
        ("Bash", "od ~/base/file", "allow"),
        # A utility that writes an operand is not admitted; an option refusal
        # cannot reach an operand.
        ("Bash", "xxd /tmp/source ~/base/file", "ask"),
        ("Bash", "uniq /tmp/source ~/base/file", "ask"),
        ("Bash", "rm ~/base/file=name", "ask"),
        ("Bash", "cp /tmp/source -t~/base/", "ask"),
        ("Bash", "tar -C~/base/", "ask"),
        ("Bash", "curl -o~/base/file https://example.invalid", "ask"),
        ("Bash", 'T=~/base/file; rm "$T"', "ask"),
        ("Bash", "rm '~/base/file'", "allow"),
        # Bash expands these from the directory stack, which the hook does not know.
        ("Bash", "cd ~; echo hi > ~+/base/file", "ask"),
        ("Bash", "cd ~; rm -rf ~+/base", "ask"),
        ("Bash", "echo hi > ~-/base/file", "ask"),
        ("Bash", "echo hi > ~1/base/file", "ask"),
        ("Bash", "rm ~/base/file", "ask"),
        ("Bash", "mv /tmp/source ~/base/absent*", "ask"),
        ("Bash", "cat /tmp/backup/base/private", "allow"),
        ("Bash", "python ~/skills/task.py", "allow"),
        ("Bash", "python ~/base/task.py", "ask"),
        ("Read", "~/skills/task.py", "allow"),
        ("Bash", "python ~/skills/task.py ~/base/file", "ask"),
        ("Bash", "python ~/skills/task.py -o~/base/file", "ask"),
        ("Bash", "python -c 'print(1)' ~/base/file", "ask"),
        ("Bash", "cd ~/base; cat ./file", "ask"),
        ("Bash", "cat ~/base/file > ~/memory/note", "allow"),
        ("Bash", "cat ~/memory/note > ~/base/file", "ask"),
        ("Bash", "cat < ~/base/file", "allow"),
        ("Bash", "cat <> ~/base/file", "ask"),
        ("Bash", "python ~/skills/task.py > /tmp/output", "allow"),
        ("Bash", "python ~/skills/task.py > ~/base/file", "ask"),
        ("Bash", "cat < ~/base/private", "block"),
        ("Bash", "bash -c 'rm ~/base/file'", "ask"),
        ("Bash", 'python3 -c\'open("~/base/file", "w")\'', "ask"),
        ("Bash", "perl -e'unlink \"~/base/file\"'", "ask"),
        ("Bash", "ruby -e'File.delete(\"~/base/file\")'", "ask"),
        ("Bash", "env sh -c 'rm ~/base/file'", "ask"),
        ("Bash", "nice -n 5 sh -c 'rm ~/base/file'", "ask"),
        ("Bash", "git -c core.pager='cat ~/base/private' log", "block"),
        ("Bash", "echo 'cat ~/base/private' | sh", "block"),
        ("Bash", "printf '%s' 'rm ~/base/file' | cat | sh", "ask"),
        ("Bash", "echo 'cat ~/base/private'; sh", "allow"),
        ("Bash", "echo 'cat ~/base/private | sh'", "allow"),
        ("Bash", "/bin/bash -c 'rm ~/base/file'", "ask"),
        ("Bash", 'python -c \'open("~/base/file", "w")\'', "ask"),
        ("Bash", "bash -c 'cat ~/base/private'", "block"),
        ("Bash", "echo ~/base/file | xargs rm", "ask"),
        ("Bash", "echo ~/base/file | sh", "ask"),
        ("Bash", "cat ~/base/file; eval 'true'", "ask"),
        ("Bash", "python ~/skills/task.py | xargs rm", "ask"),
        # A reserved word leaves the word after it in command position.
        ("Bash", "{ bash -c 'rm ~/base/file'; }", "ask"),
        ("Bash", "if true; then bash -c 'rm ~/base/file'; fi", "ask"),
        ("Bash", "! bash -c 'rm ~/base/file'", "ask"),
        ("Bash", "while false; do eval 'rm ~/base/file'; done", "ask"),
        ("Bash", "if true; then trap 'rm ~/base/file' DEBUG; fi; cat ~/base/file", "ask"),
        ("Bash", "{ cat ~/base/file; }", "allow"),
        ("Bash", "if true; then cat ~/base/private; fi", "block"),
        # `file -z` may run an outside decompressor, and `-C` writes a compiled magic file.
        ("Bash", "file ~/base/file", "allow"),
        ("Bash", "file -z ~/base/file", "ask"),
        ("Bash", "file -bZ ~/base/file", "ask"),
        ("Bash", "file --uncompress ~/base/file", "ask"),
        ("Bash", "file -C -m ~/base/file", "ask"),
        # `&>` redirects both streams; it does not end the command.
        ("Bash", "cd ~/base &>/dev/null && echo x > file", "ask"),
        ("Bash", "cat ~/base/file &> /tmp/out", "allow"),
        ("Bash", "echo x &>> ~/base/file", "ask"),
    ],
)
def test_class_outcomes(world, monkeypatch, capsys, tool, target, expected):
    _, repo, hook = world
    payload = {
        "tool_name": tool,
        "tool_input": {"command" if tool == "Bash" else "file_path": target},
        "cwd": str(repo),
        "transcript_path": "/tmp/transcript.jsonl",
    }
    monkeypatch.delenv("AI_HOOK_AGENT", raising=False)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))

    with pytest.raises(SystemExit) as stopped:
        hook.main()
    captured = capsys.readouterr()

    if expected == "block":
        assert stopped.value.code == 2
    else:
        assert stopped.value.code == 0
        if expected == "allow":
            assert captured.out == ""
        else:
            assert json.loads(captured.out)["hookSpecificOutput"]["permissionDecision"] == "ask"


@pytest.mark.parametrize(
    ("command", "blocked"),
    [
        ("rg secret .", False),
        # A reading program may open whatever an unresolvable word becomes.
        ("cat ${VALUE:-secret}", True),
        ("echo ${VALUE:-secret}", False),
        ("cd $DIR && cat secret", True),
        # After a known `cd`, a word that names no entry there is a pattern, as before one.
        ("cd /tmp && rg secret .", False),
        ("cat id_rsa", True),
        ("cat ./secret", True),
        ("cat $(cat .env)", True),
        ("printf x < .env", True),
        ("cat $'\\056env'", True),
        ("cat '.env'", True),
    ],
)
def test_sensitive_words_use_their_kinds(tmp_path, command, blocked):
    hook = load_hook("block-sensitive-paths")

    assert bool(hook.bash_blocked_target(command, str(tmp_path))) is blocked


def test_a_word_written_as_a_path_after_a_cd_is_judged_as_a_file(tmp_path):
    hook = load_hook("block-sensitive-paths")
    (tmp_path / "sub").mkdir()

    assert hook.bash_blocked_target("cd sub && cat ./secret-absent", str(tmp_path))


def test_a_parent_reached_through_a_link_after_a_cd_is_judged_where_the_link_points(tmp_path):
    hook = load_hook("block-sensitive-paths")
    (tmp_path / "store/nested").mkdir(parents=True)
    (tmp_path / "store/secret.txt").touch()
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo/link").symlink_to(tmp_path / "store/nested")

    assert hook.bash_blocked_target("cd link && cat ../secret.txt", str(tmp_path / "repo"))


def test_a_relative_path_after_a_cd_is_judged_where_it_points(tmp_path):
    hook = load_hook("block-sensitive-paths")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/secret").touch()
    (tmp_path / "sub").mkdir()

    assert hook.bash_blocked_target("cd .. && cat node_modules/secret", str(tmp_path / "sub")) is None


def test_a_word_naming_an_entry_after_a_known_cd_is_judged_as_a_file(tmp_path):
    hook = load_hook("block-sensitive-paths")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys/secret").touch()

    assert hook.bash_blocked_target("cd keys && cat secret", str(tmp_path))


def test_bare_heuristic_word_depends_on_existence(tmp_path):
    hook = load_hook("block-sensitive-paths")
    assert hook.bash_blocked_target("rg secret .", str(tmp_path)) is None
    (tmp_path / "secret").touch()

    assert hook.bash_blocked_target("rg secret .", str(tmp_path)) is not None


@pytest.mark.parametrize(
    "command",
    [
        "cat notes",
        "MODE=1 cat ./file",
        "cat <notes",
        "cat *.absent",
        "cat $VALUE",
        "cat '{a,b}'",
        "cat $'a\\tb'",
        "cat a | head b",
        "cat $(cat /guarded/file)",
        "cat a\nhead b",
    ],
)
def test_two_hooks_one_reading(world, monkeypatch, command):
    _, repo, tamper = world
    sensitive = load_hook("block-sensitive-paths")
    lexer = tamper.shell_words.lex
    expected = lexer(command, str(repo))
    readings = []

    def record(text, cwd):
        result = lexer(text, cwd)
        readings.append(result)
        return result

    monkeypatch.setattr(tamper.shell_words, "lex", record)
    tamper.command_protected_class(command, str(repo))
    assert readings == [expected]
    readings.clear()
    sensitive.bash_blocked_target(command, str(repo))
    assert readings == [expected]


@pytest.mark.parametrize(
    ("command", "syntax"),
    [
        ("bash -c 'rm ~/base/file'", "program text"),
        ("echo ~/base/file | xargs rm", "command builder"),
        ("cat ~/base/file\necho done", "newline"),
        ("cat ${FILE:-~/base/file}", "substitution"),
        ("cat ~/base/{file,other}", "brace"),
        ("cd ~/base; cat ./$NAME", "substitution"),
    ],
)
def test_unrecognized_reason_names_syntax(world, command, syntax):
    _, repo, hook = world
    reason = hook.bash_commands.read(command, str(repo)).stopping_syntax()
    assert syntax in reason
    # The classifier stops on the shape of each of these, so the refusal omits
    # the accepted set: a different program meets the same stop.
    assert not hook.offers_accepted_forms(reason)
    assert not hook.bash_commands.asks_for_absolute_paths(reason)
    for explain in (hook._unrecognized_reason, hook._unrecognized_refusal):
        message = explain(command, "Bash", reason)
        assert syntax in message
        assert "Recognized reads use" not in message


@pytest.mark.parametrize("command", ["cd ~/base; cat ./file", "cd ~/base && cat file other"])
def test_a_relative_path_stop_asks_for_absolute_paths(world, command):
    """Restating a relative path absolutely is the rewrite that resolves this stop."""
    _, repo, hook = world
    reason = hook.bash_commands.read(command, str(repo)).stopping_syntax()
    assert "relative path" in reason
    assert hook.bash_commands.asks_for_absolute_paths(reason)
    assert not hook.offers_accepted_forms(reason)
    for explain in (hook._unrecognized_reason, hook._unrecognized_refusal):
        message = explain(command, "Bash", reason)
        assert "Name every path absolutely" in message
        assert "Recognized reads use" not in message


def test_an_unreadable_program_names_the_accepted_set(world):
    _, repo, hook = world
    reason = hook.bash_commands.read("sed -n '1,5p' ~/base/file", str(repo)).stopping_syntax()
    assert hook.offers_accepted_forms(reason)
    for explain in (hook._unrecognized_reason, hook._unrecognized_refusal):
        message = explain("~/base/file", "Bash", reason)
        assert "Name paths absolutely" in message
        assert "cat" in message
        assert "python" in message


@pytest.mark.parametrize("agent", ["claude", "codex", "copilot"])
def test_a_write_to_another_agents_guarded_location_asks(world, monkeypatch, capsys, agent):
    _, repo, hook = world
    monkeypatch.setenv("AI_HOOK_AGENT", agent)
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "~/other-agent/settings"},
                    "cwd": str(repo),
                }
            )
        ),
    )
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    result = capsys.readouterr()
    if agent == "codex":
        assert stopped.value.code == 2
    else:
        assert stopped.value.code == 0
        assert json.loads(result.out)["hookSpecificOutput"]["permissionDecision"] == "ask"
