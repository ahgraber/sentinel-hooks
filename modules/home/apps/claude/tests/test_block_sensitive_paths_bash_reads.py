"""Tests for Bash read-target blocking in block-sensitive-paths.py.

The Bash read path is deliberately fail-safe: it tokenises with `shlex` and, if a
segment invokes a recognised read command, checks every token against the
sensitivity rules. There is no option/operand modelling — a secret filename that
appears anywhere blocks, and a secret-looking search pattern over-denies. That
over-deny is accepted on purpose (missing a real secret read is worse than
blocking a benign command); see the `TODO(over-deny carve-out)` in the hook.

These tests cover: recognised readers and redirection, obfuscation handling,
expanded credential paths, the accepted over-denies, the genuinely-safe commands
that still pass, and the classes deliberately left out of scope.

Place this file in `tests/` alongside `test_block_sensitive_paths.py`.
"""

from conftest import assert_allowed, assert_blocked, run_hook

HOOK = "block-sensitive-paths.py"


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


# ── Reads that must block ─────────────────────────────────────────────────────


class TestBashReadBlocked:
    def test_cat_project_dotenv(self):
        assert_blocked(bash("cat ./project/.env"), "zero-access")

    def test_dotenv_variant(self):
        assert_blocked(bash("cat .env.production"), "zero-access")

    def test_service_account_json(self):
        assert_blocked(
            bash("head -n 5 ./deploy/service-account-prod.json"), "zero-access"
        )

    def test_credentials_json(self):
        assert_blocked(bash("grep -i token ./config/credentials.json"), "zero-access")

    def test_standalone_ssh_key(self):
        assert_blocked(bash("cat /tmp/checkout/id_rsa"), "zero-access")

    def test_pem_file(self):
        assert_blocked(bash("cat ./certs/server.pem"), "zero-access")

    def test_non_home_aws_dir(self):
        assert_blocked(bash("less /opt/app/.aws/credentials"), "zero-access")

    def test_non_home_npmrc(self):
        assert_blocked(bash("cat ./sub/.npmrc"), "zero-access")

    def test_docker_config(self):
        assert_blocked(bash("cat ~/.docker/config.json"), "zero-access")

    def test_shell_history(self):
        assert_blocked(bash("sort ~/.bash_history"), "zero-access")

    def test_read_after_operator(self):
        assert_blocked(bash("cd repo && cat .env"), "zero-access")


# ── Recognised readers and redirection (fail-safe coverage) ───────────────────


class TestReaderCoverage:
    def test_input_redirect_spaced(self):
        assert_blocked(bash("cat < ./project/.env"), "zero-access")

    def test_input_redirect_unspaced(self):
        assert_blocked(bash("cat <.env"), "zero-access")

    def test_input_redirect_fd_prefixed(self):
        assert_blocked(bash("cat 0<.env"), "zero-access")

    def test_mapfile_redirect_no_command(self):
        # No external command word — caught via the unconditional redirect scan.
        assert_blocked(bash("mapfile -t arr < .env"), "zero-access")

    def test_read_builtin_redirect(self):
        assert_blocked(bash("read -r line < .env"), "zero-access")

    def test_while_read_redirect(self):
        assert_blocked(
            bash('while read -r l; do echo "$l"; done < .env'), "zero-access"
        )

    def test_null_command_substitution_redirect(self):
        assert_blocked(bash("x=$(< .env); echo $x"), "zero-access")

    def test_openssl_reads_key(self):
        assert_blocked(bash("openssl rsa -in server.pem"), "zero-access")

    def test_gpg_decrypt(self):
        assert_blocked(bash("gpg -d mysecret.txt"), "zero-access")

    def test_tar_extract_to_stdout(self):
        assert_blocked(bash("tar xOf archive.tar .env"), "zero-access")

    def test_unzip_to_stdout(self):
        assert_blocked(bash("unzip -p archive.zip .env"), "zero-access")

    def test_editor_prints_file(self):
        assert_blocked(bash("ex -s -c '%p' -c 'q' .env"), "zero-access")

    def test_editor_opens_secret(self):
        assert_blocked(bash("vim .env"), "zero-access")

    def test_install_reads_source(self):
        assert_blocked(bash("install /home/u/.ssh/id_rsa /tmp/x"), "zero-access")

    def test_truncate_write(self):
        assert_blocked(bash("truncate -s0 .env"), "zero-access")


# ── Obfuscation handled by shlex tokenisation ─────────────────────────────────


class TestObfuscationClosed:
    def test_backslash_command(self):
        assert_blocked(bash("\\cat .env"), "zero-access")

    def test_quoted_command(self):
        assert_blocked(bash("'cat' .env"), "zero-access")

    def test_internal_quote_command(self):
        assert_blocked(bash('c""at .env'), "zero-access")

    def test_glob_leading(self):
        assert_blocked(bash("cat *.env"), "zero-access")

    def test_case_insensitive_dotenv(self):
        assert_blocked(bash("cat .ENV"), "zero-access")

    def test_dd_if(self):
        assert_blocked(bash("dd if=.env"), "zero-access")

    def test_attached_option_value(self):
        assert_blocked(bash("grep -f.env README.md"), "zero-access")

    def test_command_substitution_inner_reader(self):
        # punctuation_chars exposes the inner `cat` segment.
        assert_blocked(bash("echo $(cat .env)"), "zero-access")


# ── Bare credential filenames and wrappers (fail-safe: scan all tokens) ───────


class TestBareCredentialsAndWrappers:
    def test_bare_ssh_key(self):
        assert_blocked(bash("cat id_rsa"), "zero-access")

    def test_bare_credentials(self):
        assert_blocked(bash("cat credentials"), "zero-access")

    def test_bare_secret(self):
        assert_blocked(bash("cat secret"), "zero-access")

    def test_sudo_with_options(self):
        assert_blocked(bash("sudo -u root cat .env"), "zero-access")

    def test_env_wrapper(self):
        assert_blocked(bash("env -i cat .env"), "zero-access")

    def test_credentials_in_venv_allowed(self):
        # Package-dir exemption still applies to the weak name signal.
        assert_allowed(bash("cat .venv/lib/python3.11/site-packages/pkg/credentials"))


# ── Accepted over-denies (fail-safe bias — intentional false positives) ───────
# A secret-looking search pattern is blocked even though it names no file. This
# is deliberate; see the TODO(over-deny carve-out) in the hook.


class TestAcceptedOverDeny:
    def test_grep_secret_pattern(self):
        assert_blocked(bash("grep -r secret ."), "zero-access")

    def test_jq_credentials_filter(self):
        assert_blocked(bash("jq '.credentials' config.json"), "zero-access")

    def test_grep_context_dotenv_pattern(self):
        assert_blocked(bash("grep -A 3 .env README.md"), "zero-access")

    def test_sed_script_touching_aws(self):
        assert_blocked(bash("sed 's/.aws/X/g' file"), "zero-access")


# ── Genuinely-safe commands that must still pass ──────────────────────────────


class TestSafeCommandsAllowed:
    def test_ls_sensitive_dir(self):
        assert_allowed(bash("ls -la ~/.ssh/"))

    def test_echo(self):
        assert_allowed(bash("echo hello world"))

    def test_cat_readme(self):
        assert_allowed(bash("cat README.md"))

    def test_head_pyproject(self):
        assert_allowed(bash("head -n 20 pyproject.toml"))

    def test_git_status(self):
        assert_allowed(bash("git status"))

    def test_grep_neutral_pattern(self):
        assert_allowed(bash("grep -rn TODO src/"))

    def test_vim_normal_file(self):
        assert_allowed(bash("vim src/main.py"))

    def test_tar_create_normal(self):
        assert_allowed(bash("tar czf out.tgz src/"))

    def test_settings_json_not_secret(self):
        assert_allowed(bash("cat ./users/nrl/home-manager/claude/settings.json"))


# ── Out-of-scope gaps: need real shell evaluation (boundary is the sandbox) ────
# Assert CURRENT behavior (allowed) so a future change that closes one is noticed.


class TestKnownGaps:
    def test_interpreter_not_covered(self):
        assert_allowed(bash("python -c \"print(open('.env').read())\""))

    def test_variable_hidden_command_not_covered(self):
        assert_allowed(bash("c=cat; $c .env"))

    def test_quoted_wrapper_not_covered(self):
        assert_allowed(bash("bash -c 'cat .env'"))

    def test_xargs_segment_orphan_not_covered(self):
        assert_allowed(bash("echo .env | xargs cat"))


# ── Glob expansion: a wildcard must not hide a sensitive filename ─────────────
# The token is expanded against the filesystem exactly as the shell would, so a
# `*`/`?`/`[..]` that resolves to a real secret file blocks. These chdir into a
# tmp dir holding decoy files; the hook inherits that cwd for the expansion.


class TestGlobExpansion:
    @staticmethod
    def _seed(monkeypatch, tmp_path, names):
        for n in names:
            (tmp_path / n).write_text("x")
        monkeypatch.chdir(tmp_path)

    def test_star_hides_dotenv(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path, [".env"])
        assert_blocked(bash("cat .en*"), "zero-access")

    def test_question_mark_hides_dotenv(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path, [".env"])
        assert_blocked(bash("cat .en?"), "zero-access")

    def test_star_hides_credentials_json(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path, ["credentials.json"])
        assert_blocked(bash("cat cred*.json"), "zero-access")

    def test_question_mark_hides_ssh_key(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path, ["id_rsa"])
        assert_blocked(bash("cat id_rs?"), "zero-access")

    def test_glob_without_sensitive_match_allowed(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path, ["README.md", "notes.md"])
        assert_allowed(bash("cat *.md"))


# ── ANSI-C quoting: `$'\\056env'` decodes to `.env` before matching ──────────


class TestAnsiCQuoting:
    def test_octal_escaped_dotenv(self):
        assert_blocked(bash(r"cat $'\056env'"), "zero-access")

    def test_hex_escaped_dotenv(self):
        assert_blocked(bash(r"cat $'\x2eenv'"), "zero-access")


# ── Transfer/copy source: a secret used as a source operand blocks ───────────
# cp/mv/scp/rsync are scanned like readers, so a secret *source* (not just a
# secret destination) is caught.


class TestTransferSource:
    def test_cp_secret_source(self):
        assert_blocked(bash("cp /tmp/checkout/id_rsa /tmp/x"), "zero-access")

    def test_mv_secret_source(self):
        assert_blocked(bash("mv ./config/credentials.json /tmp/x"), "zero-access")

    def test_scp_secret_source(self):
        assert_blocked(bash("scp ./deploy/.env host:/tmp"), "zero-access")

    def test_rsync_secret_dir_source(self):
        assert_blocked(bash("rsync ./app/.aws/credentials host:/tmp"), "zero-access")

    def test_cp_benign_allowed(self):
        assert_allowed(bash("cp README.md docs/README.md"))


# ── Write-clobber operators: >| and &> / &>> truncate their target ───────────


class TestWriteClobber:
    def test_force_clobber_dotenv(self):
        assert_blocked(bash("id >| .env"), "zero-access")

    def test_stdout_stderr_redirect_dotenv(self):
        assert_blocked(bash("id &> .env"), "zero-access")

    def test_tee_long_option_dotenv(self):
        assert_blocked(bash("echo x | tee --append .env"), "zero-access")
