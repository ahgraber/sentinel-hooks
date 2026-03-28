"""Tests for block-destructive-ops.py + block-destructive-ops-patterns.toml.

Validates that the hook loads TOML rules and correctly blocks or asks
for destructive operations across git, filesystem, cloud, infra,
database, publishing, and network categories.

Note: assert_blocked/assert_ask substring checks match against the TOML
description and reason fields, not the command name.
"""

from conftest import (
    assert_allowed,
    assert_ask,
    assert_block_contract,
    assert_blocked,
    run_hook,
)

HOOK = "block-destructive-ops.py"


def bash(command: str):
    return run_hook(HOOK, "Bash", {"command": command})


# ── Tool scope ────────────────────────────────────────────────────────────────


class TestToolScope:
    def test_non_bash_tool_allowed(self):
        result = run_hook(HOOK, "Write", {"file_path": "/tmp/test"})
        assert_allowed(result)

    def test_empty_command_allowed(self):
        assert_allowed(bash(""))

    def test_safe_command_allowed(self):
        assert_allowed(bash("echo hello"))

    def test_malformed_json_fails_closed(self):
        result = run_hook(HOOK, stdin_text="not json")
        assert result.exit_code == 2


# ── Git: block mode ─────────────────────────────────────────────────────────


class TestGitBlock:
    def test_filter_branch(self):
        assert_blocked(
            bash("git filter-branch --tree-filter 'rm -f file' HEAD"), "rewrites"
        )

    def test_filter_repo(self):
        assert_blocked(bash("git filter-repo --path src/"), "rewrites")

    def test_reflog_expire(self):
        assert_blocked(bash("git reflog expire --all --expire=now"), "reflog")

    def test_force_push_without_lease(self):
        assert_blocked(bash("git push --force origin main"), "force")

    def test_force_push_short_flag(self):
        assert_blocked(bash("git push -f origin main"), "force")

    def test_force_push_combined_flags(self):
        assert_blocked(bash("git push -fv origin main"), "force")

    def test_gh_repo_delete(self):
        assert_blocked(bash("gh repo delete myorg/myrepo --yes"), "repository")


# ── Git: ask mode ────────────────────────────────────────────────────────────


class TestGitAsk:
    def test_force_push_with_lease(self):
        assert_ask(bash("git push --force-with-lease origin feature"), "force")

    def test_push_delete(self):
        assert_ask(bash("git push --delete origin old-branch"), "remote branch")

    def test_reset_hard(self):
        assert_ask(bash("git reset --hard HEAD~1"), "uncommitted")

    def test_clean_f(self):
        assert_ask(bash("git clean -f"), "untracked")

    def test_clean_fd(self):
        assert_ask(bash("git clean -fd"), "untracked")

    def test_clean_fdx(self):
        assert_ask(bash("git clean -fdx"), "untracked")

    def test_stash_drop(self):
        assert_ask(bash("git stash drop"), "stash")

    def test_stash_clear(self):
        assert_ask(bash("git stash clear"), "stash")

    def test_branch_delete_force(self):
        assert_ask(bash("git branch -D feature-branch"), "unmerged")

    def test_checkout_dot(self):
        assert_ask(bash("git checkout ."), "unstaged")

    def test_restore_dot(self):
        assert_ask(bash("git restore ."), "unstaged")

    def test_git_add_all(self):
        assert_ask(bash("git add ."), "stages all")

    def test_git_add_A(self):
        assert_ask(bash("git add -A"), "stages all")


# ── Git: allowed ─────────────────────────────────────────────────────────────


class TestGitAllowed:
    def test_git_status(self):
        assert_allowed(bash("git status"))

    def test_git_commit(self):
        assert_allowed(bash('git commit -m "fix: update tests"'))

    def test_git_log(self):
        assert_allowed(bash("git log --oneline -10"))

    def test_git_diff(self):
        assert_allowed(bash("git diff HEAD~1"))

    def test_git_push_normal(self):
        assert_allowed(bash("git push origin main"))

    def test_git_add_specific_file(self):
        assert_allowed(bash("git add src/main.py"))


# ── Filesystem: block mode ──────────────────────────────────────────────────


class TestFilesystemBlock:
    def test_rm_rf_root(self):
        assert_blocked(bash("rm -rf /"), "recursively")

    def test_rm_rf_home(self):
        assert_blocked(bash("rm -rf ~/"), "recursively")

    def test_rm_rf_with_flag_reorder(self):
        """rm -rf with flags in -rf order (the TOML pattern expects r before f)."""
        assert_blocked(bash("rm -rf /tmp/important"), "recursively")

    def test_mkfs(self):
        assert_blocked(bash("mkfs.ext4 /dev/sda1"), "formats")

    def test_dd_to_disk(self):
        assert_blocked(bash("dd if=/dev/zero of=/dev/sda bs=1M"), "raw data")

    def test_chmod_777_system(self):
        assert_blocked(bash("chmod 777 /etc/passwd"), "777")


class TestFilesystemBlockFlagOrder:
    """rm with f-before-r flag order is now caught by the TOML pattern."""

    def test_rm_fr_root(self):
        assert_blocked(bash("rm -fr /"), "recursively")

    def test_rm_fR_home(self):
        assert_blocked(bash("rm -fR ~/"), "recursively")


# ── Filesystem: ask mode ────────────────────────────────────────────────────


class TestFilesystemAsk:
    def test_rm_r(self):
        assert_ask(bash("rm -r some_directory"), "recursive")

    def test_chmod_recursive(self):
        assert_ask(bash("chmod -R 755 /app"), "permission")

    def test_chown_recursive(self):
        assert_ask(bash("chown -R www-data:www-data /var/www"), "ownership")

    def test_history_clear(self):
        assert_ask(bash("history -c"), "history")


# ── Process management: ask mode ────────────────────────────────────────────


class TestProcessManagement:
    def test_killall(self):
        assert_ask(bash("killall node"), "killall")

    def test_pkill(self):
        assert_ask(bash("pkill -f python"), "pkill")

    def test_kill_9(self):
        assert_ask(bash("kill -9 12345"), "SIGKILL")


# ── Database: block mode ────────────────────────────────────────────────────


class TestDatabaseBlock:
    def test_drop_table(self):
        assert_blocked(bash("psql -c 'DROP TABLE users;'"), "DROP")

    def test_drop_database(self):
        assert_blocked(bash("psql -c 'DROP DATABASE mydb;'"), "DROP")

    def test_delete_without_where(self):
        assert_blocked(bash("psql -c 'DELETE FROM users;'"), "DELETE")

    def test_dropdb(self):
        assert_blocked(bash("dropdb production"), "dropdb")

    def test_mysqladmin_drop(self):
        assert_blocked(bash("mysqladmin drop mydb"), "mysqladmin")

    def test_redis_flushall(self):
        assert_blocked(bash("redis-cli FLUSHALL"), "FLUSH")

    def test_redis_flushdb(self):
        assert_blocked(bash("redis-cli FLUSHDB"), "FLUSH")

    def test_mongo_drop_database(self):
        assert_blocked(bash("mongosh --eval 'db.dropDatabase()'"), "drop")


# ── Database: ask mode ──────────────────────────────────────────────────────


class TestDatabaseAsk:
    def test_truncate_table(self):
        assert_ask(bash("psql -c 'TRUNCATE TABLE logs;'"), "TRUNCATE")


# ── Cloud: ask mode ─────────────────────────────────────────────────────────


class TestCloudAsk:
    def test_aws_s3_rm_recursive(self):
        assert_ask(bash("aws s3 rm s3://mybucket/path --recursive"), "S3")

    def test_aws_s3_sync_delete(self):
        assert_ask(bash("aws s3 sync ./local s3://bucket --delete"), "S3")

    def test_gcloud_delete(self):
        assert_ask(bash("gcloud compute instances delete my-vm"), "Google Cloud")

    def test_firebase_delete(self):
        assert_ask(bash("firebase projects:delete myproject"), "Firebase")

    def test_vercel_remove(self):
        assert_ask(bash("vercel projects rm myproject"), "Vercel")

    def test_heroku_destroy(self):
        assert_ask(bash("heroku apps:destroy myapp"), "Heroku")

    def test_fly_destroy(self):
        assert_ask(bash("fly apps destroy myapp"), "Fly")

    def test_supabase_delete(self):
        assert_ask(bash("supabase projects delete myproject"), "Supabase")


# ── Infrastructure: ask mode ────────────────────────────────────────────────


class TestInfraAsk:
    def test_terraform_destroy(self):
        assert_ask(bash("terraform destroy -auto-approve"), "infrastructure")

    def test_tofu_destroy(self):
        assert_ask(bash("tofu destroy"), "infrastructure")

    def test_pulumi_destroy(self):
        assert_ask(bash("pulumi destroy"), "Pulumi")

    def test_kubectl_delete_namespace(self):
        assert_ask(bash("kubectl delete namespace staging"), "namespace")

    def test_docker_system_prune(self):
        assert_ask(bash("docker system prune -a"), "Docker")

    def test_docker_rm_force(self):
        assert_ask(bash("docker rm -f container1"), "Docker")

    def test_docker_volume_prune(self):
        assert_ask(bash("docker volume prune"), "Docker")

    def test_helm_uninstall(self):
        assert_ask(bash("helm uninstall my-release"), "Helm")

    def test_helm_install(self):
        assert_ask(bash("helm install my-release my-chart"), "Helm")

    def test_serverless_remove(self):
        assert_ask(bash("serverless remove"), "Serverless")

    def test_sls_remove(self):
        assert_ask(bash("sls remove --stage prod"), "Serverless")

    def test_sam_delete(self):
        assert_ask(bash("sam delete --stack-name mystack"), "SAM")


# ── Infrastructure: block mode ──────────────────────────────────────────────


class TestInfraBlock:
    def test_kubectl_delete_all(self):
        assert_blocked(bash("kubectl delete pods --all"), "Kubernetes")

    def test_kubectl_delete_all_namespaces(self):
        assert_blocked(bash("kubectl delete pods --all-namespaces"), "Kubernetes")


# ── Publishing: ask mode ────────────────────────────────────────────────────


class TestPublishingAsk:
    def test_npm_publish(self):
        assert_ask(bash("npm publish"), "publish")

    def test_yarn_publish(self):
        assert_ask(bash("yarn publish"), "publish")

    def test_npm_unpublish(self):
        assert_ask(bash("npm unpublish my-package"), "unpublish")

    def test_docker_push(self):
        assert_ask(bash("docker push myimage:latest"), "container image")

    def test_uv_publish(self):
        assert_ask(bash("uv publish"), "PyPI")


# ── Network: ask mode ───────────────────────────────────────────────────────


class TestNetworkAsk:
    def test_ssh(self):
        assert_ask(bash("ssh user@remote-host"), "SSH")

    def test_scp(self):
        assert_ask(bash("scp file.txt user@remote:/path"), "remote")

    def test_rsync(self):
        assert_ask(bash("rsync -av ./src/ user@remote:/dest/"), "rsync")

    def test_ssh_keygen_allowed(self):
        """ssh-keygen should NOT be caught by the ssh pattern."""
        assert_allowed(bash("ssh-keygen -t ed25519"))

    def test_ssh_agent_allowed(self):
        assert_allowed(bash("ssh-agent bash"))

    def test_ssh_add_allowed(self):
        assert_allowed(bash("ssh-add ~/.ssh/id_ed25519"))


# ── Package management: ask mode ────────────────────────────────────────────


class TestPackageManagement:
    def test_uv_remove(self):
        assert_ask(bash("uv remove requests"), "package")


# ── Block contract ───────────────────────────────────────────────────────────


class TestBlockContract:
    """Verify every block-mode response includes the two-section AI guidance contract."""

    def test_force_push_includes_ai_instructions(self):
        assert_block_contract(bash("git push --force origin main"), "force")

    def test_drop_table_includes_ai_instructions(self):
        assert_block_contract(bash("psql -c 'DROP TABLE users;'"), "DROP")

    def test_rm_rf_includes_ai_instructions(self):
        assert_block_contract(bash("rm -rf /"), "recursively")

    def test_kubectl_delete_all_includes_ai_instructions(self):
        assert_block_contract(bash("kubectl delete pods --all"), "Kubernetes")

    def test_redis_flushall_includes_ai_instructions(self):
        assert_block_contract(bash("redis-cli FLUSHALL"), "FLUSH")
