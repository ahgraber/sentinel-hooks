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


def _bash_decision(world, monkeypatch, capsys, command):
    """Return the tamper hook's decision on a Bash command, and its reason with the command text replaced."""
    _, repo, hook = world
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(repo),
        "transcript_path": "/tmp/transcript.jsonl",
    }
    monkeypatch.delenv("AI_HOOK_AGENT", raising=False)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    captured = capsys.readouterr()
    if stopped.value.code == 2:
        decision, reason = "block", captured.err
    elif captured.out:
        decision, reason = "ask", json.loads(captured.out)["hookSpecificOutput"]["permissionDecisionReason"]
    else:
        decision, reason = "allow", ""
    return decision, reason.replace(command, "<command>")


def test_a_multi_line_read_is_recognized(world, monkeypatch, capsys):
    multi_line = _bash_decision(world, monkeypatch, capsys, "cat ~/base/file\nhead ~/base/file")
    one_line = _bash_decision(world, monkeypatch, capsys, "cat ~/base/file; head ~/base/file")

    assert multi_line == one_line == ("allow", "")


@pytest.mark.parametrize(
    ("multi_line", "one_line", "expected"),
    [
        ("cat ~/base/file\necho done\n", "cat ~/base/file; echo done", "allow"),
        ("cat ~/base/file\nrm ~/base/file", "cat ~/base/file; rm ~/base/file", "ask"),
        ("cat ~/base/file\ncat ~/base/private", "cat ~/base/file; cat ~/base/private", "block"),
        ("cat ~/base/file |\nxargs rm", "cat ~/base/file | xargs rm", "ask"),
        ("echo x\necho y > ~/base/file", "echo x; echo y > ~/base/file", "ask"),
        ("cd ~/base &&\ncat ./file", "cd ~/base && cat ./file", "ask"),
        ("# rm ~/base/file\ncat ~/base/file", "cat ~/base/file", "allow"),
        ("echo if then\nrm ~/base/file", "echo if then; rm ~/base/file", "ask"),
    ],
)
def test_a_multi_line_command_reaches_its_one_line_verdict(world, monkeypatch, capsys, multi_line, one_line, expected):
    decision = _bash_decision(world, monkeypatch, capsys, multi_line)

    assert decision == _bash_decision(world, monkeypatch, capsys, one_line)
    assert decision[0] == expected


@pytest.mark.xfail(strict=True, reason="known gap HereDocumentReadByARecognizedRead")
@pytest.mark.parametrize("reader", ["head -n 1", "tr a b", "cat -n", "wc -l"])
def test_a_here_document_a_recognized_read_takes_is_data(world, monkeypatch, capsys, reader):
    command = f"{reader} <<'EOF'\nrm ~/base/file\nEOF"

    assert _bash_decision(world, monkeypatch, capsys, command) == ("allow", "")


@pytest.mark.parametrize("character", ["\v", "\f", "\xa0"])
@pytest.mark.parametrize(("command", "expected"), [("rm ~/base/file", "ask"), ("cat ~/base/private", "block")])
def test_a_hash_after_a_character_bash_does_not_split_on_hides_nothing(
    world, monkeypatch, capsys, character, command, expected
):
    assert _bash_decision(world, monkeypatch, capsys, f"echo a{character}#; {command}")[0] == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat ~/base/file \\\n  ~/base/private", "block"),
        ("echo x \\\n> ~/base/file", "ask"),
        ("cd ~/base &\\\n& cat private", "ask"),
        ("if true; then\nbash -c 'rm ~/base/file'\nfi", "ask"),
        ("while false; do\ncat ~/base/private\ndone", "block"),
        ("echo $(#'\n); rm ~/base/file; #')", "ask"),
        ('cat "`echo"`"; rm ~/base/file; " #\n" #"', "ask"),
        ("((cat<<2))\ncat ~/base/private\n2", "block"),
    ],
)
def test_a_multi_line_form_the_lexer_does_not_yet_read_falls_back(world, monkeypatch, capsys, command, expected):
    assert _bash_decision(world, monkeypatch, capsys, command)[0] == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat <<'EOF' > /tmp/out\nrm ~/base/file\nEOF", "allow"),
        ("cat <<'EOF'\ncat ~/base/private\nEOF", "allow"),
        ("git commit -F - <<'EOF'\nfix ~/base/private\nEOF", "allow"),
        ("gh pr create --body-file - <<'EOF'\nfix ~/base/file\nEOF", "allow"),
        ("tee /tmp/out <<'EOF'\nrm ~/base/file\nEOF", "allow"),
        ("git commit -F - <<'EOF'\nPATH=~/base/file fix\nEOF", "allow"),
        ("git commit --file - <<'EOF'\nfix ~/base/private\nEOF", "allow"),
        ("git commit --file=- <<'EOF'\nfix ~/base/private\nEOF", "allow"),
        ("git -C /tmp commit -F - <<'EOF'\nfix ~/base/private\nEOF", "allow"),
        ("git tag -a v1 -F - <<'EOF'\nfix ~/base/private\nEOF", "allow"),
        ("gh issue comment 1 --body-file=- <<'EOF'\nfix ~/base/file\nEOF", "allow"),
        # A body bash expands is unresolvable, so the paths written in it are judged.
        ("cat <<EOF\n$X ~/base/file\nEOF", "ask"),
        ("cat <<EOF\n$X ~/base/private\nEOF", "block"),
        # `|&` pipes the reader's output on, as `|` does.
        ("cat <<'EOF' |& sh\nrm ~/base/file\nEOF", "ask"),
        # The reader's own words and redirections are judged as on one line.
        ("cat <<'EOF' > ~/base/file\nx\nEOF", "ask"),
        ("tee ~/base/file <<'EOF'\nx\nEOF", "ask"),
        ("cat ~/base/private <<'EOF'\nx\nEOF", "block"),
    ],
)
def test_a_here_document_read_as_data_is_not_judged(world, monkeypatch, capsys, command, expected):
    assert _bash_decision(world, monkeypatch, capsys, command)[0] == expected


@pytest.mark.parametrize(
    ("reader", "body", "expected"),
    [
        ("bash", "rm ~/base/file", "ask"),
        ("python3 -", "open('~/base/file', 'w')", "ask"),
        ("xargs rm", "~/base/file", "ask"),
        ("sudo sh", "rm ~/base/file", "ask"),
        ("source /dev/stdin", "rm ~/base/file", "ask"),
        ("sed -f - /tmp/x", "w ~/base/file", "ask"),
        ("git apply", "+++ ~/base/file", "ask"),
        ("git agent-commit -F -", "~/base/file", "ask"),
        ("unknown-program", "~/base/file", "ask"),
        ("bash", "cat ~/base/private", "block"),
        ("xargs cat", "~/base/private", "block"),
        # A record reader that may still run its input.
        ("env -S'sh -s' tee", "rm ~/base/file", "ask"),
        ("git -c core.editor=sh commit -e -F -", "cat ~/base/private", "block"),
        ("GIT_EDITOR=sh git commit -e -F -", "cat ~/base/private", "block"),
        ("PATH=/tmp/evil tee /tmp/o", "cat ~/base/private", "block"),
        ("gh myalias --body-file -", "rm ~/base/file", "ask"),
    ],
)
def test_a_here_document_read_by_any_other_program_is_program_text(world, monkeypatch, capsys, reader, body, expected):
    decision = _bash_decision(world, monkeypatch, capsys, f"{reader} <<'EOF'\n{body}\nEOF")
    inline = _bash_decision(world, monkeypatch, capsys, f"bash -c '{body}'")

    assert decision[0] == inline[0] == expected


@pytest.mark.parametrize(
    ("multi_line", "one_line"),
    [
        ("echo a\ncat .env.local", "echo a; cat .env.local"),
        ("cat .env.example\necho done", "cat .env.example; echo done"),
        ("echo a |\ncat > .env.example", "echo a | cat > .env.example"),
        ("cd /tmp &&\ncat secret", "cd /tmp && cat secret"),
        ("echo done\ncat id_rsa", "echo done; cat id_rsa"),
    ],
)
def test_a_multi_line_command_reaches_its_one_line_sensitive_verdict(tmp_path, multi_line, one_line):
    hook = load_hook("block-sensitive-paths")

    assert hook.bash_blocked_target(multi_line, str(tmp_path)) == hook.bash_blocked_target(one_line, str(tmp_path))


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat <<'EOF' | sh\nrm ~/base/file\nEOF", "ask"),
        ("cat <<'EOF' | bash\ncat ~/base/private\nEOF", "block"),
        ("cat <<'EOF' | xargs rm\n~/base/file\nEOF", "ask"),
        ("cat <<'EOF' | tr a a | sh\nrm ~/base/file\nEOF", "ask"),
        ("tee /dev/stdout <<'EOF' | sh\nrm ~/base/file\nEOF", "ask"),
    ],
)
def test_a_here_document_piped_on_is_program_text(world, monkeypatch, capsys, command, expected):
    assert _bash_decision(world, monkeypatch, capsys, command)[0] == expected


@pytest.mark.parametrize(
    "command", ["cat <<'EOF'\nrm ~/base/file", "cat <<'EOF'\nrm ~/base/file\nEOF ", "cat ~/base/file\r\nhead x"]
)
def test_a_command_the_lexer_cannot_read_still_reaches_the_fallback(world, monkeypatch, capsys, command):
    assert _bash_decision(world, monkeypatch, capsys, command)[0] == "ask"


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
        ("cat <<'EOF'\n~/base/file", "multi-line form"),
        ("cat ~/base/file \\\n  /tmp/x", "line continuation"),
        ("cat ~/base/file\r\necho done", "carriage return"),
        ("bash <<'EOF'\nrm ~/base/file\nEOF", "here-document"),
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
