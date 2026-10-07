#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Block secret exfiltration and flag sensitive access (PreToolUse hook)."""

import io
import json
import re
import subprocess
import sys
from typing import NoReturn

import apply_patch
from guarded_paths import NAME_HEURISTIC_EXEMPT_RE, TOOL_VOCABULARY, GuardedLocations
from hook_response import UNKNOWN, Decision, invoking_agent, respond, supports_ask

MUTATING_TOOLS = TOOL_VOCABULARY.group("mutating")

_AGENT = UNKNOWN

_EXPOSURE_RISK = "Exposed credentials can enable unauthorized access, account takeover, or data exfiltration."

NETWORK_CMD_RE = re.compile(
    r"\b(?:curl|curlie|wget|aria2c|xh|httpie|nc|ncat|netcat|ftp|sftp|scp|rsync|socat|ssh(?!-\w)|telnet)\b"
    r"|\bhttps?\b(?!://)"  # httpie `http`/`https` command (not a URL scheme)
    r"|\bopenssl\s+s_client\b",
    re.IGNORECASE,
)

LOCAL_URL_RE = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)[:/\s\"']",
    re.IGNORECASE,
)
# Any remote URL cancels the loopback exemption.
REMOTE_URL_RE = re.compile(
    r"https?://(?!localhost|127\.0\.0\.1|::1|0\.0\.0\.0)[^\s\"']",
    re.IGNORECASE,
)

# Exclude bare `ssh` because `.ssh` paths would match as egress.
EGRESS_CMD_RE = re.compile(
    r"\b(?:curl|curlie|wget|aria2c|xh|httpie|scp|sftp|rsync|nc|ncat|netcat|socat|ftp|telnet)\b"
    r"|\bhttps?\b(?!://)",
    re.IGNORECASE,
)
LOCAL_NC_RE = re.compile(
    r"\bnc\b[^|;&\n]*(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)\s+[0-9]",
    re.IGNORECASE,
)
LOCAL_HOST_ARG_RE = re.compile(
    r"\b(?:scp|rsync)\b[^|;&\n]*\s(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0):"
    r"|\bssh\b[^|;&\n]*\s(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)\b",
    re.IGNORECASE,
)

ENV_DUMP_RE = re.compile(r"\b(?:env\b|printenv\b|export\s+-p\b)", re.IGNORECASE)

DNS_EXFIL_RE = re.compile(
    r"\$\([^)]+\)\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"  # $(cmd).attacker.com
    r"|\b(?:nslookup|dig|host)\s+.*\$\("
)

CREDENTIAL_FILE_PIPE_RE = re.compile(
    r"\b(?:cat|less|head|tail|bat)\s+[^\s|;&#]*"
    r"(?:\.env\b|\.envrc\b|\.npmrc\b|\.netrc\b|\.git-credentials\b"
    r"|\.aws/credentials\b|\.ssh/id_\w+\b|\.kube/config\b"
    r"|credentials\b|secret\b)"
    r"[^|;&#]*\|",
    re.IGNORECASE,
)

CRED_PATH_IN_CMD_RE = re.compile(
    r"(?:^|[\s=@\"'/])(?:"
    r"\.env(?:\.[^\s\"']*)?|\.envrc|\.npmrc|\.netrc|\.pypirc|\.git-credentials"
    r"|id_(?:rsa|dsa|ecdsa|ed25519)[^\s\"']*"
    r"|[^\s/\"']*\.(?:pem|key|p12|pfx|keystore|jks)"
    r"|service-account[^\s\"']*\.json|credentials\.json"
    r")(?:$|[\s\"';|&)])"
    r"|[/~]\.(?:ssh|aws|kube|gnupg|azure)(?:[/\\]|\b)",
    re.IGNORECASE,
)

CREDENTIAL_STORE_RE = re.compile(
    r"\bsecurity\s+find-(?:generic|internet)-password\b"
    r"|\bvault\s+(?:read|kv\s+get)\b"
    r"|\bop\s+(?:read|item\s+get|run)\b"
    r"|\baws\s+secretsmanager\b"
    r"|\bkubectl\s+get\s+secret\b",
    re.IGNORECASE,
)

BUILTIN_SECRET_RES = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)aws_secret_access_key\s*=\s*\S{20,}"),
    re.compile(r"\b(?:ghp|gho|ghs|ghr)_[a-zA-Z0-9]{36}\b"),
    re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{22,}\b"),
    re.compile(r"\bsk-ant-api[0-9]+-[a-zA-Z0-9]{70,}\b"),
    re.compile(r"\bsk-(?:proj-)?[a-zA-Z0-9T]{48,}\b"),
    re.compile(r"\bxox[bpra]-[0-9]{9,}-[a-zA-Z0-9-]+\b"),
    re.compile(r"[MN][A-Za-z\d]{23,}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"),
    re.compile(r"-----BEGIN\s+(?:\w+\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"-----BEGIN\s+PGP\s+PRIVATE\s+KEY\s+BLOCK-----"),
    re.compile(r"(?i)(?:bearer|authorization)\s+[A-Za-z0-9\-_.~+/]{20,}"),
    re.compile(
        r"(?i)(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token)"
        r"\s*[=:]\s*[A-Za-z0-9+/\-_.]{16,}"
    ),
]

CREDENTIAL_FILE_RE = re.compile(
    r"(?:^|[/\\])(?:"
    r"id_rsa|id_ed25519|id_ecdsa|id_dsa"
    r"|[^/\\]*\.(?:key|pem|keystore|jks|p12|pfx)"
    r"|[^/\\]*(?:token|password|passwd|api[_-]?key|auth_key|secret|credential)[^/\\]*"
    r"|\.env(?:\.[^/\\]*)?|\.envrc"
    r"|\.npmrc|\.netrc|\.pypirc|\.git-credentials"
    r")$",
    re.IGNORECASE,
)

# Always match, even inside an exempt package directory.
STRONG_CRED_FILE_RE = re.compile(
    r"(?:^|[/\\])(?:\.?credentials\.json|service-account[^/\\]*\.json)$",
    re.IGNORECASE,
)

CREDENTIAL_DIRS = {prefix: GuardedLocations([prefix]) for prefix in ("~/.ssh/", "~/.aws/", "~/.kube/", "~/.gnupg/")}


def scan_with_gitleaks(text: str) -> bool | None:
    """Return True for a leak, False for clean input, or None when unavailable."""
    try:
        result = subprocess.run(
            ["gitleaks", "detect", "--pipe", "--no-banner", "-l", "warn", "--redact"],
            input=text,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        return None
    else:
        return result.returncode == 1


def builtin_has_secret(text: str) -> bool:
    """Return whether text matches a built-in secret pattern."""
    return any(p.search(text) for p in BUILTIN_SECRET_RES)


def has_credential(text: str, *, deep: bool = False) -> bool:
    """Return whether text contains a credential; use gitleaks for deep scans."""
    if builtin_has_secret(text):
        return True
    if deep:
        result = scan_with_gitleaks(text)
        if result is not None:
            return result
    return False


def block(message: str) -> NoReturn:
    """Respond with a block decision."""
    respond(Decision.BLOCK, message, agent=_AGENT)


def ask(reason: str) -> NoReturn:
    """Respond with an ask decision, or block when the agent cannot prompt."""
    if supports_ask(_AGENT):
        respond(Decision.ASK, reason, agent=_AGENT)

    reason = reason.replace(
        "Approve only if this access is intentional and the credentials will not leave this session.",
        "If this access is intentional, have the user perform it manually outside the agent session.",
    )
    reason = reason.replace(
        "Approve only if you intentionally want the agent to access this material.",
        "If this access is intentional, have the user perform it manually outside the agent session.",
    )
    reason = reason.replace(
        "approve below. Otherwise deny and remove the credential before re-running.",
        "have the user perform the sensitive step manually outside the agent "
        "session. Otherwise remove the credential before re-running.",
    )
    block("Blocked: this agent cannot show a confirmation prompt for this action.\n" + reason)


def extract_apply_patch_paths(tool_input: dict) -> list[str]:
    """Extract target file paths from a Codex apply_patch command body."""
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return []
    return apply_patch.targets(command)


def ask_if_sensitive_path(path: str) -> None:
    """Ask when supported; otherwise block access to a sensitive path."""
    if not path:
        return

    if STRONG_CRED_FILE_RE.search(path):
        ask(
            f"This operation targets '{path}', a credential store file with "
            "OAuth tokens or a cloud service-account key. Exposing it to the agent "
            "could let prompt injection send credentials to an attacker. "
            f"{_EXPOSURE_RISK} Approve only if you intentionally want the agent to "
            "access this material."
        )

    for dir_prefix, credential_dir in CREDENTIAL_DIRS.items():
        if credential_dir.contains(path):
            ask(
                f"This operation targets '{path}' inside credential directory "
                f"({dir_prefix}), where files may contain private keys, tokens, or "
                "credentials. Exposing them to the agent could let prompt injection "
                f"send them to an attacker. {_EXPOSURE_RISK} Approve only if you "
                "intentionally want the agent to access this material."
            )

    if CREDENTIAL_FILE_RE.search(path) and not NAME_HEURISTIC_EXEMPT_RE.search(path):
        ask(
            f"This operation targets '{path}', whose name suggests credentials, "
            "tokens, or key material. Exposing it to the agent could let prompt "
            f"injection send it to an attacker. {_EXPOSURE_RISK} Approve only if "
            "you intentionally want the agent to access this material."
        )


def main() -> None:
    """Read the hook payload from stdin and respond to the tool call."""
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        raw = sys.stdin.getvalue() if hasattr(sys.stdin, "getvalue") else ""
        # A payload that does not parse names no tool, so the read-only direction applies.
        if not raw.strip():
            respond(Decision.ALLOW, agent=_AGENT)
        respond(
            Decision.WARN,
            "block-secrets could not parse the hook payload; this call was not checked.",
            agent=_AGENT,
        )

    tool_name: str = data.get("tool_name", "")
    tool_input: dict = data.get("tool_input", {})

    command = tool_input.get("command", "") if tool_name == "Bash" else ""
    has_network = bool(NETWORK_CMD_RE.search(command)) if command else False
    has_loopback = (
        bool(LOCAL_URL_RE.search(command) or LOCAL_NC_RE.search(command) or LOCAL_HOST_ARG_RE.search(command))
        if command
        else False
    )
    has_remote_url = bool(REMOTE_URL_RE.search(command)) if command else False
    is_local = has_loopback and not has_remote_url
    is_bash_with_network = has_network and not is_local

    if command:
        # DNS queries always leave the machine.
        if DNS_EXFIL_RE.search(command):
            block(
                "Blocked: DNS exfiltration pattern detected.\n"
                "This command may put credentials in a DNS hostname to bypass network "
                f"egress controls. {_EXPOSURE_RISK}"
            )

        if CREDENTIAL_FILE_PIPE_RE.search(command) and has_network and not is_local:
            block(
                "Blocked: credential file piped to a network command.\n"
                "This command sends a likely credential file (.env, .npmrc, SSH keys, "
                f"or cloud credentials) to a remote host. {_EXPOSURE_RISK}"
            )

        # Catch egress commands the pipe regex misses without matching `.ssh`
        # as a network tool.
        is_egress_exfil = bool(EGRESS_CMD_RE.search(command)) and not is_local
        if is_egress_exfil and CRED_PATH_IN_CMD_RE.search(command):
            block(
                "Blocked: credential file referenced in a command with network egress.\n"
                "This command names likely credentials or keys (.env, SSH keys, .aws, "
                ".gnupg, *.pem, or credentials.json) and contacts a remote host. "
                f"{_EXPOSURE_RISK}"
            )

        if ENV_DUMP_RE.search(command) and has_network and not is_local:
            block(
                "Blocked: environment variable dump to network detected.\n"
                "This command sends all environment variables, including credentials, "
                f"API keys, and tokens, to a remote host. {_EXPOSURE_RISK}"
            )

        if CREDENTIAL_STORE_RE.search(command) and has_network and not is_local:
            block(
                "Blocked: credential store read piped to a remote network destination.\n"
                "This command sends a secret from a keychain, vault, or secrets manager "
                f"to a remote host. {_EXPOSURE_RISK}"
            )

        if CREDENTIAL_STORE_RE.search(command):
            ask(
                "This command reads credentials from a keychain, vault, or secrets "
                "manager. Exposing them to the agent could let prompt injection send "
                f"them to an attacker. {_EXPOSURE_RISK} Approve only if this access "
                "is intentional and the credentials will not leave this session."
            )

    if tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path") or tool_input.get("path", "")
        if path:
            ask_if_sensitive_path(path)

    elif tool_name == "apply_patch":
        for path in extract_apply_patch_paths(tool_input):
            ask_if_sensitive_path(path)

    # Run gitleaks only before egress; other checks use built-in patterns.
    serialized = json.dumps(tool_input)

    if has_credential(serialized, deep=is_bash_with_network):
        if is_bash_with_network:
            block(
                "Blocked: credential detected in command with a network destination.\n"
                "This command sends an API key or authentication credential to a "
                f"remote host. {_EXPOSURE_RISK}"
            )
        ask(
            "A credential or API key pattern was detected in this tool call. "
            "Exposing it to the agent could let prompt injection send it to an attacker. "
            f"{_EXPOSURE_RISK} If this is intentional (e.g., testing authentication "
            "locally), approve below. Otherwise deny and remove the credential before "
            "re-running."
        )

    sys.exit(0)


_current_tool_name = ""

if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        try:
            _parsed = json.loads(raw)
            _current_tool_name = _parsed.get("tool_name", "")
            _AGENT = invoking_agent(payload=_parsed)
        except Exception:  # noqa: BLE001, S110
            pass
        sys.stdin = io.StringIO(raw)
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        if _current_tool_name in MUTATING_TOOLS:
            respond(
                Decision.BLOCK,
                "Blocked: block-secrets failed while checking a call that could expose credentials.",
                agent=_AGENT,
            )
        respond(
            Decision.WARN,
            "block-secrets failed; this tool call was not checked.",
            agent=_AGENT,
        )
