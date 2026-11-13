"""Tests for zero-access path blocking in the block-sensitive-paths.py hook."""

import json
import os

from conftest import assert_allowed, assert_ask, assert_block_contract, assert_blocked, run_hook
import pytest

HOOK = "block-sensitive-paths.py"
HOME = os.path.expanduser("~")


def read(path: str):
    return run_hook(HOOK, "Read", {"file_path": path})


def write(path: str):
    return run_hook(HOOK, "Write", {"file_path": path})


def edit(path: str):
    return run_hook(HOOK, "Edit", {"file_path": path, "old_string": "a", "new_string": "b"})


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


class TestToolScope:
    def test_read_tool_blocked_for_zero_access(self):
        """Zero-access paths are hard-blocked for Read, not merely gated."""
        assert_blocked(read(f"{HOME}/.ssh/id_rsa"), "zero-access")

    def test_glob_tool_allowed(self):
        result = run_hook(HOOK, "Glob", {"pattern": "*.pem"})
        assert_allowed(result)


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
        assert_allowed(read("/project/.venv/lib/python3.11/site-packages/google/auth/credentials.py"))

    def test_read_normal_file_allowed(self):
        assert_allowed(read("/project/src/main.py"))


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


class TestSshDirectory:
    def test_write_ssh_id_rsa(self):
        assert_blocked(write(f"{HOME}/.ssh/id_rsa"), "zero-access")

    def test_write_ssh_config(self):
        assert_blocked(write(f"{HOME}/.ssh/config"), "zero-access")

    def test_edit_ssh_authorized_keys(self):
        assert_blocked(edit(f"{HOME}/.ssh/authorized_keys"), "zero-access")

    def test_write_ssh_known_hosts(self):
        assert_blocked(write(f"{HOME}/.ssh/known_hosts"), "zero-access")

    def test_case_variant_directory_blocks_on_any_volume(self):
        """This set is matched by what a path looks like, not by which file it
        is, so a heuristic that stopped applying because a letter was
        capitalized would be defeated by capitalizing a letter."""
        assert_blocked(write(f"{HOME}/.SSH/id_rsa"), "zero-access")
        assert_blocked(write(f"{HOME}/Certs/Server.PEM"), "zero-access")


class TestAwsDirectory:
    def test_write_aws_credentials(self):
        assert_blocked(write(f"{HOME}/.aws/credentials"), "zero-access")

    def test_write_aws_config(self):
        assert_blocked(write(f"{HOME}/.aws/config"), "zero-access")


class TestKubeDirectory:
    def test_write_kube_config(self):
        assert_blocked(write(f"{HOME}/.kube/config"), "zero-access")


class TestGnupgDirectory:
    def test_write_gnupg_key(self):
        assert_blocked(write(f"{HOME}/.gnupg/secring.gpg"), "zero-access")

    def test_write_gnupg_trustdb(self):
        assert_blocked(write(f"{HOME}/.gnupg/trustdb.gpg"), "zero-access")


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


class TestTerraformState:
    def test_write_tfstate(self):
        assert_blocked(write("/project/terraform.tfstate"), "zero-access")

    def test_write_tfstate_backup(self):
        assert_blocked(write("/project/terraform.tfstate.backup"), "zero-access")


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


class TestShellHistory:
    def test_write_bash_history(self):
        assert_blocked(write(f"{HOME}/.bash_history"), "zero-access")

    def test_write_zsh_history(self):
        assert_blocked(write(f"{HOME}/.zsh_history"), "zero-access")

    def test_write_node_repl_history(self):
        assert_blocked(write(f"{HOME}/.node_repl_history"), "zero-access")

    def test_write_python_history(self):
        assert_blocked(write(f"{HOME}/.python_history"), "zero-access")


class TestPackageDirExemption:
    def test_credentials_in_venv_allowed(self):
        assert_allowed(write("/project/.venv/lib/python3.11/site-packages/google/auth/credentials.py"))

    def test_secret_in_venv_allowed(self):
        assert_allowed(write("/project/.venv/lib/python3.11/site-packages/my_lib/secret.py"))

    def test_credentials_in_node_modules_allowed(self):
        assert_allowed(write("/project/node_modules/@aws-sdk/credentials/index.js"))

    def test_secret_in_site_packages_allowed(self):
        assert_allowed(write("/usr/lib/python3/site-packages/secret_module/core.py"))

    def test_credentials_in_claude_hooks_allowed(self):
        """claude/hooks directory is exempt for name patterns."""
        assert_allowed(write("/Users/me/.claude/hooks/block-secrets.py"))

    @pytest.mark.parametrize("tool", [read, write, edit])
    def test_a_planted_hook_source_does_not_exempt(self, tool, tmp_path):
        """Validates: APlantedHookSourceDoesNotExempt."""
        (tmp_path / "hooks").mkdir()
        (tmp_path / "hooks" / "guarded_paths.py").write_text("")
        assert_blocked(tool(str(tmp_path / "app" / "credentials.yaml")), "zero-access")

    @pytest.mark.parametrize("target", ["codex/hooks/block-secrets.py", "project/tests/test_secrets.py"])
    def test_a_hook_or_test_directory_does_not_earn_the_exemption(self, target, tmp_path):
        """A harness-named or test directory is not a package directory."""
        assert_blocked(write(str(tmp_path / target)), "zero-access")

    def test_pem_in_venv_still_blocked(self):
        """Extension-based patterns are NOT exempt — .pem is always blocked."""
        assert_blocked(write("/project/.venv/cert.pem"), "zero-access")


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


class TestErrorHandling:
    def test_malformed_json_fails_open(self):
        """Mixed sensitive+read-only hook fails-open on malformed JSON (cannot determine tool type)."""
        result = run_hook(HOOK, stdin_text="not json")
        assert result.exit_code == 0


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


def apply_patch(command: str):
    return run_hook(HOOK, "apply_patch", {"command": command})


class TestApplyPatch:
    """Codex applies edits via `apply_patch`; the shared hook checks its targets."""

    def test_add_file_to_env_blocks(self):
        patch = "*** Begin Patch\n*** Add File: config/.env\n+X=1\n*** End Patch"
        assert_blocked(apply_patch(patch), "zero-access")

    def test_update_credentials_json_blocks(self):
        patch = "*** Begin Patch\n*** Update File: app/credentials.json\n+{}\n*** End Patch"
        assert_blocked(apply_patch(patch), "zero-access")

    def test_move_to_ssh_key_blocks(self):
        patch = f"*** Begin Patch\n*** Move to: {HOME}/.ssh/id_rsa\n*** End Patch"
        assert_blocked(apply_patch(patch), "zero-access")

    def test_update_normal_file_allowed(self):
        patch = "*** Begin Patch\n*** Update File: src/main.py\n+print(1)\n*** End Patch"
        assert_allowed(apply_patch(patch))

    def test_empty_command_allowed(self):
        assert_allowed(apply_patch(""))

    def test_update_token_named_file_asks(self):
        patch = "*** Begin Patch\n*** Update File: app/auth_token.json\n+{}\n*** End Patch"
        assert_ask(apply_patch(patch), "auth_token.json")


# Spec: hook-interface ExplanationContract. Any member of a set satisfies its concept.
_EXPOSURE = {"expose", "exposing", "exposed"}
_CREDENTIAL = {"credential", "credentials", "token", "tokens", "key", "keys", "password", "passwords"}
_RISK = {"unauthorized access", "account takeover"}


def assert_explained_ask(result, path: str) -> None:
    """Assert an ask whose reason names the file and satisfies the explanation contract."""
    assert_ask(result)
    reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    lowered = reason.lower()
    assert path in reason
    assert any(word in lowered for word in _EXPOSURE), reason
    assert any(word in lowered for word in _CREDENTIAL), reason
    assert any(word in lowered for word in _RISK), reason


class TestNamesThatSuggestACredentialAsk:
    """A name that suggests a credential without proving one asks; it is not refused."""

    @pytest.mark.parametrize(
        "path",
        [
            "/project/auth_token.json",
            "/project/passwords.txt",
            "/project/passwd.bak",
            "/project/api_key.cfg",
            "/project/api-key.cfg",
            "/project/auth_key",
            "/project/credential.txt",
            "/project/release.keystore",
            "/project/release.jks",
        ],
    )
    def test_read_asks(self, path):
        assert_explained_ask(read(path), path)

    def test_write_and_edit_ask(self):
        assert_ask(write("/project/auth_token.json"))
        assert_ask(edit("/project/auth_token.json"))

    def test_a_strong_credential_file_asks_even_in_a_package_directory(self):
        path = "/project/.venv/lib/python3.11/site-packages/pkg/.credentials.json"
        assert_explained_ask(read(path), path)

    def test_a_package_directory_excuses_a_suggestive_name(self):
        assert_allowed(read("/project/.venv/lib/python3.11/site-packages/pkg/token.py"))

    def test_a_bash_read_is_not_asked(self):
        """The ask covers the file tools; a Bash read of the name is judged by the read rules."""
        assert_allowed(bash("cat /project/auth_token.json"))

    def test_an_ordinary_name_is_allowed(self):
        assert_allowed(read("/project/src/main.py"))

    def test_an_agent_that_cannot_prompt_is_refused_without_an_approval_line(self):
        result = run_hook(
            HOOK, "Read", {"file_path": "/project/auth_token.json"}, env={**os.environ, "AI_HOOK_AGENT": "codex"}
        )
        assert_blocked(result)
        assert "approve" not in result.stderr.lower()


class TestDeclaredReadsReachNoAsk:
    """A declared placeholder or exception is readable: no rule in this hook asks on it."""

    def test_a_dotenv_placeholder_is_readable(self):
        assert_allowed(read("/project/apps/web/.env.example"))


class TestLinkedFilesInCredentialDirectories:
    def test_a_declaratively_managed_file_is_still_in_the_directory(self, tmp_path):
        """A symlinked file is judged by where it sits, not by where it resolves.

        `programs.ssh` and sops-nix deploy these files as links out to the Nix store
        or a secrets mount, so a rule that follows only the link finds nothing.
        """
        home = tmp_path / "home"
        store = tmp_path / "store"
        store.mkdir()
        (store / "config-abc123").write_text("Host example\n")
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "config").symlink_to(store / "config-abc123")

        result = run_hook(
            HOOK, "Read", {"file_path": str(home / ".ssh" / "config")}, env={**os.environ, "HOME": str(home)}
        )

        assert_blocked(result, "zero-access")
