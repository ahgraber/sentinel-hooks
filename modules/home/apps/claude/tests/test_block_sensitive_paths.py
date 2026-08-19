"""Tests for block-sensitive-paths.py hook.

Validates zero-access path blocking for Read, Write, Edit, and Bash tools,
including dot-env files, SSH/AWS/Kube/GPG directories, certificate files,
Terraform state, and name-based patterns with package-dir exemption.
"""

import os

from conftest import assert_allowed, assert_block_contract, assert_blocked, run_hook

HOOK = "block-sensitive-paths.py"
HOME = os.path.expanduser("~")


def read(path: str):
    return run_hook(HOOK, "Read", {"file_path": path})


def write(path: str):
    return run_hook(HOOK, "Write", {"file_path": path})


def edit(path: str):
    return run_hook(
        HOOK, "Edit", {"file_path": path, "old_string": "a", "new_string": "b"}
    )


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


# ── Tool scope ────────────────────────────────────────────────────────────────


class TestToolScope:
    def test_read_tool_blocked_for_zero_access(self):
        """Read tool is now covered — zero-access paths are hard-blocked."""
        assert_blocked(read(f"{HOME}/.ssh/id_rsa"), "zero-access")

    def test_glob_tool_allowed(self):
        result = run_hook(HOOK, "Glob", {"pattern": "*.pem"})
        assert_allowed(result)


# ── Read tool blocking ───────────────────────────────────────────────────────


class TestReadTool:
    def test_read_ssh_key(self):
        assert_blocked(read(f"{HOME}/.ssh/id_ed25519"), "zero-access")

    def test_read_aws_credentials(self):
        assert_blocked(read(f"{HOME}/.aws/credentials"), "zero-access")

    def test_read_dot_env(self):
        assert_blocked(read("/project/.env"), "zero-access")

    def test_read_pem_file(self):
        assert_blocked(read("/project/server.pem"), "zero-access")

    def test_read_credentials_json(self):
        assert_blocked(read("/project/credentials.json"), "zero-access")

    def test_read_credentials_in_venv_allowed(self):
        """Package-dir exemption applies to Read just as it does to Write/Edit."""
        assert_allowed(
            read(
                "/project/.venv/lib/python3.11/site-packages/google/auth/credentials.py"
            )
        )

    def test_read_normal_file_allowed(self):
        assert_allowed(read("/project/src/main.py"))


# ── Dot-env files ────────────────────────────────────────────────────────────


class TestDotEnvFiles:
    def test_write_dot_env(self):
        assert_blocked(write("/project/.env"), "zero-access")

    def test_write_dot_env_production(self):
        assert_blocked(write("/project/.env.production"), "zero-access")

    def test_write_dot_env_local(self):
        assert_blocked(write("/project/.env.local"), "zero-access")

    def test_write_envrc(self):
        assert_blocked(write("/project/.envrc"), "zero-access")

    def test_edit_dot_env(self):
        assert_blocked(edit("/project/.env"), "zero-access")


# ── SSH directory ────────────────────────────────────────────────────────────


class TestSshDirectory:
    def test_write_ssh_id_rsa(self):
        assert_blocked(write(f"{HOME}/.ssh/id_rsa"), "zero-access")

    def test_write_ssh_config(self):
        assert_blocked(write(f"{HOME}/.ssh/config"), "zero-access")

    def test_edit_ssh_authorized_keys(self):
        assert_blocked(edit(f"{HOME}/.ssh/authorized_keys"), "zero-access")

    def test_write_ssh_known_hosts(self):
        assert_blocked(write(f"{HOME}/.ssh/known_hosts"), "zero-access")


# ── AWS directory ────────────────────────────────────────────────────────────


class TestAwsDirectory:
    def test_write_aws_credentials(self):
        assert_blocked(write(f"{HOME}/.aws/credentials"), "zero-access")

    def test_write_aws_config(self):
        assert_blocked(write(f"{HOME}/.aws/config"), "zero-access")


# ── Kube directory ───────────────────────────────────────────────────────────


class TestKubeDirectory:
    def test_write_kube_config(self):
        assert_blocked(write(f"{HOME}/.kube/config"), "zero-access")


# ── GPG directory ────────────────────────────────────────────────────────────


class TestGnupgDirectory:
    def test_write_gnupg_key(self):
        assert_blocked(write(f"{HOME}/.gnupg/secring.gpg"), "zero-access")

    def test_write_gnupg_trustdb(self):
        assert_blocked(write(f"{HOME}/.gnupg/trustdb.gpg"), "zero-access")


# ── Certificate and key files ────────────────────────────────────────────────


class TestCertificateFiles:
    def test_write_pem(self):
        assert_blocked(write("/project/server.pem"), "zero-access")

    def test_write_key(self):
        assert_blocked(write("/project/private.key"), "zero-access")

    def test_write_p12(self):
        assert_blocked(write("/project/cert.p12"), "zero-access")

    def test_write_pfx(self):
        assert_blocked(write("/project/cert.pfx"), "zero-access")

    def test_write_crt(self):
        assert_blocked(write("/project/server.crt"), "zero-access")

    def test_write_cer(self):
        assert_blocked(write("/project/server.cer"), "zero-access")


# ── Terraform state ─────────────────────────────────────────────────────────


class TestTerraformState:
    def test_write_tfstate(self):
        assert_blocked(write("/project/terraform.tfstate"), "zero-access")

    def test_write_tfstate_backup(self):
        assert_blocked(write("/project/terraform.tfstate.backup"), "zero-access")


# ── Name-based patterns ─────────────────────────────────────────────────────


class TestNameBasedPatterns:
    def test_write_credentials_json(self):
        assert_blocked(write("/project/credentials.json"), "zero-access")

    def test_write_my_credentials(self):
        assert_blocked(write("/project/my_credentials.yaml"), "zero-access")

    def test_write_secret_yaml(self):
        assert_blocked(write("/project/secret.yaml"), "zero-access")

    def test_write_app_secret(self):
        assert_blocked(write("/project/app_secret.json"), "zero-access")

    def test_edit_credentials_file(self):
        assert_blocked(edit("/project/credentials.ini"), "zero-access")


# ── Shell history files ─────────────────────────────────────────────────────


class TestShellHistory:
    def test_write_bash_history(self):
        assert_blocked(write(f"{HOME}/.bash_history"), "zero-access")

    def test_write_zsh_history(self):
        assert_blocked(write(f"{HOME}/.zsh_history"), "zero-access")

    def test_write_node_repl_history(self):
        assert_blocked(write(f"{HOME}/.node_repl_history"), "zero-access")

    def test_write_python_history(self):
        assert_blocked(write(f"{HOME}/.python_history"), "zero-access")


# ── Package-dir exemption ───────────────────────────────────────────────────


class TestPackageDirExemption:
    def test_credentials_in_venv_allowed(self):
        assert_allowed(
            write(
                "/project/.venv/lib/python3.11/site-packages/google/auth/credentials.py"
            )
        )

    def test_secret_in_venv_allowed(self):
        assert_allowed(
            write("/project/.venv/lib/python3.11/site-packages/my_lib/secret.py")
        )

    def test_credentials_in_node_modules_allowed(self):
        assert_allowed(write("/project/node_modules/@aws-sdk/credentials/index.js"))

    def test_secret_in_site_packages_allowed(self):
        assert_allowed(write("/usr/lib/python3/site-packages/secret_module/core.py"))

    def test_credentials_in_claude_hooks_allowed(self):
        """claude/hooks directory is exempt for name patterns."""
        assert_allowed(write("/Users/me/.claude/hooks/block-secrets.py"))

    def test_credentials_in_claude_tests_allowed(self):
        """claude/tests directory is exempt — symmetric with claude/hooks for hook test files."""
        assert_allowed(
            write("/repo/modules/home/apps/claude/tests/test_block_secrets.py")
        )

    def test_credentials_in_codex_hooks_allowed(self):
        """codex/hooks directory is exempt for name patterns."""
        assert_allowed(write("/repo/modules/home/apps/codex/hooks/block-secrets.py"))

    def test_credentials_in_codex_tests_allowed(self):
        """codex/tests directory is exempt — symmetric with codex/hooks for hook test files."""
        assert_allowed(
            write("/repo/modules/home/apps/codex/tests/test_codex_block_secrets.py")
        )

    def test_pem_in_venv_still_blocked(self):
        """Extension-based patterns are NOT exempt — .pem is always blocked."""
        assert_blocked(write("/project/.venv/cert.pem"), "zero-access")


# ── Bash write-to-path detection ────────────────────────────────────────────


class TestBashWriteDetection:
    def test_redirect_to_env_file(self):
        assert_blocked(bash("echo SECRET=val > .env"), "zero-access")

    def test_append_to_env_file(self):
        assert_blocked(bash("echo NEW_VAR=1 >> .env"), "zero-access")

    def test_cp_to_ssh_dir(self):
        assert_blocked(bash(f"cp key.pub {HOME}/.ssh/authorized_keys"), "zero-access")

    def test_mv_to_aws_dir(self):
        assert_blocked(bash(f"mv creds.txt {HOME}/.aws/credentials"), "zero-access")

    def test_tee_to_ssh_config(self):
        assert_blocked(bash(f"echo 'Host *' | tee {HOME}/.ssh/config"), "zero-access")

    def test_chmod_on_pem(self):
        assert_blocked(bash("chmod 600 /app/server.pem"), "zero-access")

    def test_safe_redirect_allowed(self):
        assert_blocked(bash("echo test > output.key"), "zero-access")

    def test_safe_command_allowed(self):
        assert_allowed(bash("echo hello world"))

    def test_ls_command_allowed(self):
        assert_allowed(bash("ls -la ~/.ssh/"))


# ── Normal files allowed ────────────────────────────────────────────────────


class TestNormalFilesAllowed:
    def test_write_py_file(self):
        assert_allowed(write("/project/src/main.py"))

    def test_write_readme(self):
        assert_allowed(write("/project/README.md"))

    def test_write_config_yaml(self):
        assert_allowed(write("/project/config.yaml"))

    def test_write_package_json(self):
        assert_allowed(write("/project/package.json"))

    def test_edit_typescript(self):
        assert_allowed(edit("/project/src/app.ts"))


# ── Error handling ──────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_malformed_json_fails_open(self):
        """Mixed sensitive+read-only hook fails-open on malformed JSON (cannot determine tool type)."""
        result = run_hook(HOOK, stdin_text="not json")
        assert result.exit_code == 0


# ── Directory prefix false positive ─────────────────────────────────────────


class TestDirectoryPrefixBoundary:
    def test_ssh2_dir_not_matched(self):
        """~/.ssh2/ should NOT match the ~/.ssh/ prefix."""
        assert_allowed(write(f"{HOME}/.ssh2/some_file"))

    def test_aws_cli_dir_not_matched(self):
        """~/.aws-cli/ should NOT match the ~/.aws/ prefix."""
        assert_allowed(write(f"{HOME}/.aws-cli/config"))

    def test_claude_dash_tests_not_matched(self):
        """claude-tests (with hyphen) must NOT satisfy the claude/tests exemption."""
        assert_blocked(write("/project/claude-tests/credentials.json"), "zero-access")

    def test_codex_tests_extra_not_matched(self):
        """codex/tests-extra must NOT satisfy the codex/tests exemption (segment boundary)."""
        assert_blocked(write("/project/codex/tests-extra/secret.json"), "zero-access")


# ── Block contract ───────────────────────────────────────────────────────────


class TestBlockContract:
    """Verify every block-mode response includes the two-section AI guidance contract."""

    def test_read_ssh_key_includes_ai_instructions(self):
        assert_block_contract(read(f"{HOME}/.ssh/id_ed25519"), "zero-access")

    def test_read_aws_credentials_includes_ai_instructions(self):
        assert_block_contract(read(f"{HOME}/.aws/credentials"), "zero-access")

    def test_write_dot_env_includes_ai_instructions(self):
        assert_block_contract(write("/project/.env"), "zero-access")

    def test_write_pem_includes_ai_instructions(self):
        assert_block_contract(write("/project/server.pem"), "zero-access")

    def test_bash_redirect_to_env_includes_ai_instructions(self):
        assert_block_contract(bash("echo SECRET=val > .env"), "zero-access")


# ── apply_patch (Codex edit tool; shared hook) ───────────────────────────────


def apply_patch(command: str):
    return run_hook(HOOK, "apply_patch", {"command": command})


class TestApplyPatch:
    """Codex applies edits via `apply_patch`; the shared hook checks its targets."""

    def test_add_file_to_env_blocks(self):
        patch = "*** Begin Patch\n*** Add File: config/.env\n+X=1\n*** End Patch"
        assert_blocked(apply_patch(patch), "zero-access")

    def test_update_credentials_json_blocks(self):
        patch = (
            "*** Begin Patch\n*** Update File: app/credentials.json\n+{}\n*** End Patch"
        )
        assert_blocked(apply_patch(patch), "zero-access")

    def test_move_to_ssh_key_blocks(self):
        patch = f"*** Begin Patch\n*** Move to: {HOME}/.ssh/id_rsa\n*** End Patch"
        assert_blocked(apply_patch(patch), "zero-access")

    def test_update_normal_file_allowed(self):
        patch = (
            "*** Begin Patch\n*** Update File: src/main.py\n+print(1)\n*** End Patch"
        )
        assert_allowed(apply_patch(patch))

    def test_empty_command_allowed(self):
        assert_allowed(apply_patch(""))
