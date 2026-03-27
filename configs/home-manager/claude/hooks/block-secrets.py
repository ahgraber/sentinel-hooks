#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Claude Code Hook: Block secret exfiltration and flag sensitive access.

PreToolUse hook — runs for Bash, Read, Write, and Edit tool calls.

Block mode (exit 2):
  - Secret detected in Bash command + network destination (exfiltration)
  - Credential file content piped to network (.env, .npmrc, .ssh, .aws, etc.)
  - Environment variable dump sent to network
  - DNS exfiltration patterns

Ask mode (exit 0 + JSON):
  - Secret detected in tool_input (universal scan — debugging context)
  - Credential store read (keychain, vault, secretsmanager, etc.)
  - Read/Write/Edit targeting a file whose name suggests it holds secrets

Performance: built-in regex patterns run first (~microseconds). gitleaks is only
invoked when built-in patterns find a match (for confirmation + broader coverage)
or when a Bash command has network context (where missing a secret is catastrophic).

Error handling (per hook-interface ErrorHandlingByDamagePotential):
  - Bash/Write/Edit: exit 2 on internal error (fail-closed)
  - All other tools: exit 1 on internal error (fail-open with error logged)
"""

import io
import json
import os
import re
import subprocess
import sys

SENSITIVE_TOOLS = {"Bash", "Write", "Edit"}

# ── Shared risk explanation ───────────────────────────────────────────────────
# Appended to all block/ask messages to give consistent downstream-risk context.
_EXPOSURE_RISK = (
    "Exposed credentials risk unauthorised access, account takeover, and data "
    "exfiltration across every service they protect."
)

# ── Network tool detection ─────────────────────────────────────────────────────
NETWORK_CMD_RE = re.compile(
    r"\b(?:curl|wget|nc|ncat|netcat|ftp|sftp|scp|rsync|socat|ssh(?!-\w)|telnet)\b"
    r"|\bopenssl\s+s_client\b",
    re.IGNORECASE,
)

# Loopback exemption: checks URL hosts and nc host arguments in context.
LOCAL_URL_RE = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)[:/\s\"']",
    re.IGNORECASE,
)
LOCAL_NC_RE = re.compile(
    r"\bnc\b[^|;&\n]*(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)\s+[0-9]",
    re.IGNORECASE,
)
# Loopback exemption for connection-based tools: scp, rsync, ssh
# Matches loopback address in the host/destination position.
LOCAL_HOST_ARG_RE = re.compile(
    r"\b(?:scp|rsync)\b[^|;&\n]*\s(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0):"
    r"|\bssh\b[^|;&\n]*\s(?:localhost|127\.0\.0\.1|::1|0\.0\.0\.0)\b",
    re.IGNORECASE,
)

# ── Environment dump patterns ─────────────────────────────────────────────────
ENV_DUMP_RE = re.compile(r"\b(?:env\b|printenv\b|export\s+-p\b)", re.IGNORECASE)

# ── DNS exfiltration patterns ─────────────────────────────────────────────────
DNS_EXFIL_RE = re.compile(
    r"\$\([^)]+\)\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"  # $(cmd).attacker.com
    r"|\b(?:nslookup|dig|host)\s+.*\$\("  # dig $(...)
)

# ── Credential file pipes (block: file content → network) ────────────────────
# Catches `cat .env | curl`, `cat ~/.npmrc | nc`, etc.
CREDENTIAL_FILE_PIPE_RE = re.compile(
    r"\b(?:cat|less|head|tail|bat)\s+[^\s|;&#]*"
    r"(?:\.env\b|\.envrc\b|\.npmrc\b|\.netrc\b|\.git-credentials\b"
    r"|\.aws/credentials\b|\.ssh/id_\w+\b|\.kube/config\b"
    r"|credentials\b|secret\b)"
    r"[^|;&#]*\|",
    re.IGNORECASE,
)

# ── Credential store reads (ask mode) ─────────────────────────────────────────
CREDENTIAL_STORE_RE = re.compile(
    r"\bsecurity\s+find-(?:generic|internet)-password\b"
    r"|\bvault\s+(?:read|kv\s+get)\b"
    r"|\bop\s+(?:read|item\s+get|run)\b"
    r"|\baws\s+secretsmanager\b"
    r"|\bkubectl\s+get\s+secret\b",
    re.IGNORECASE,
)

# ── Built-in secret patterns ─────────────────────────────────────────────────
# Used as fast pre-scan AND as gitleaks fallback.
# High-precision patterns to minimise false positives.
BUILTIN_SECRET_RES = [
    # Cloud provider keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key ID
    re.compile(r"(?i)aws_secret_access_key\s*=\s*\S{20,}"),  # AWS secret key assignment
    # Platform tokens
    re.compile(r"\b(?:ghp|gho|ghs|ghr)_[a-zA-Z0-9]{36}\b"),  # GitHub tokens
    re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{22,}\b"),  # GitHub fine-grained PAT
    re.compile(r"\bsk-ant-api[0-9]+-[a-zA-Z0-9]{70,}\b"),  # Anthropic
    re.compile(r"\bsk-(?:proj-)?[a-zA-Z0-9T]{48,}\b"),  # OpenAI-style
    re.compile(r"\bxox[bpra]-[0-9]{9,}-[a-zA-Z0-9-]+\b"),  # Slack
    re.compile(r"[MN][A-Za-z\d]{23,}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"),  # Discord
    # Cryptographic material
    re.compile(r"-----BEGIN\s+(?:\w+\s+)?PRIVATE\s+KEY-----"),  # PEM private key
    re.compile(r"-----BEGIN\s+PGP\s+PRIVATE\s+KEY\s+BLOCK-----"),  # GPG private key
    # Auth headers & generic assignments
    re.compile(
        r"(?i)(?:bearer|authorization)\s+[A-Za-z0-9\-_.~+/]{20,}"
    ),  # Bearer/auth tokens
    re.compile(
        r"(?i)(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token)"
        r"\s*[=:]\s*[A-Za-z0-9+/\-_.]{16,}"
    ),  # Generic secret assignment
]

# ── File path heuristics for Read/Write/Edit (ask mode) ───────────────────────
CREDENTIAL_FILE_RE = re.compile(
    r"(?:^|[/\\])(?:"
    r"id_rsa|id_ed25519|id_ecdsa|id_dsa"  # SSH keys
    r"|[^/\\]*\.(?:key|pem|keystore|jks|p12|pfx)"  # key/cert/keystore ext
    r"|[^/\\]*(?:token|password|passwd|api[_-]?key|auth_key|secret|credential)[^/\\]*"  # named patterns
    r"|\.npmrc|\.netrc|\.git-credentials"  # credential config files
    r")$",
    re.IGNORECASE,
)

# ── Directory exemption for name-based patterns ──────────────────────────────
# Name-based patterns don't apply inside these directories, where words like
# 'secret' or 'credentials' are valid file/module names.
EXEMPT_DIR_RE = re.compile(
    r"(?:^|[/\\])(?:\.venv|venv|env|site-packages|node_modules|\.claude|claude[/\\]hooks)(?:[/\\]|$)",
    re.IGNORECASE,
)

# ── Credential directory prefixes (ask mode) ────────────────────────────────
# Files within well-known credential directories trigger ask regardless of name.
CREDENTIAL_DIR_PREFIXES = ["~/.ssh/", "~/.aws/", "~/.kube/", "~/.gnupg/"]


# ── Gitleaks integration ───────────────────────────────────────────────────────


def scan_with_gitleaks(text: str) -> bool | None:
    """Scan text with gitleaks. Returns True/False/None (unavailable)."""
    try:
        result = subprocess.run(
            ["gitleaks", "detect", "--pipe", "--no-banner", "-l", "warn", "--redact"],
            input=text,
            capture_output=True,
            text=True,
            timeout=8,
        )
        return result.returncode == 1
    except FileNotFoundError:
        return None
    except Exception:
        return None


def builtin_has_secret(text: str) -> bool:
    """Fast built-in pattern scan (~microseconds)."""
    return any(p.search(text) for p in BUILTIN_SECRET_RES)


def has_credential(text: str, *, deep: bool = False) -> bool:
    """
    Detect secrets in text.

    Fast path (deep=False): built-in patterns only.
    Deep path (deep=True): built-in first, then gitleaks for broader coverage.
    """
    if builtin_has_secret(text):
        return True
    if deep:
        result = scan_with_gitleaks(text)
        if result is not None:
            return result
    return False


# ── Hook output helpers ────────────────────────────────────────────────────────


def block(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(2)


def ask(reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name: str = data.get("tool_name", "")
    tool_input: dict = data.get("tool_input", {})

    # ── Pre-compute network context for Bash (used by both specific and universal checks)
    command = tool_input.get("command", "") if tool_name == "Bash" else ""
    has_network = bool(NETWORK_CMD_RE.search(command)) if command else False
    is_local = (
        bool(
            LOCAL_URL_RE.search(command)
            or LOCAL_NC_RE.search(command)
            or LOCAL_HOST_ARG_RE.search(command)
        )
        if command
        else False
    )
    is_bash_with_network = has_network and not is_local

    # ── Bash-specific pattern checks ─────────────────────────────────────
    # These run before the universal scan — they detect exfiltration patterns
    # that don't require gitleaks (structural patterns, not secret content).
    if command:
        # DNS exfiltration (block unconditionally — no localhost exemption)
        if DNS_EXFIL_RE.search(command):
            block(
                "Blocked: DNS exfiltration pattern detected.\n"
                "This command encodes credentials or sensitive information into DNS "
                "hostnames, bypassing standard network egress controls while evading "
                f"detection. {_EXPOSURE_RISK}"
            )

        # Credential file content piped to network (block unless localhost)
        if CREDENTIAL_FILE_PIPE_RE.search(command) and has_network and not is_local:
            block(
                "Blocked: credential file piped to a network command.\n"
                "This command reads a file likely to contain credentials or secrets "
                "(.env, .npmrc, SSH keys, AWS credentials) and pipes its contents "
                f"to a remote host, directly exposing those credentials. {_EXPOSURE_RISK}"
            )

        # Environment dump to network (block unless localhost)
        if ENV_DUMP_RE.search(command) and has_network and not is_local:
            block(
                "Blocked: environment variable dump to network detected.\n"
                "This command exports all environment variables — including any "
                "credentials, API keys, or tokens stored there — and sends them "
                f"to a remote host, exposing all of them at once. {_EXPOSURE_RISK}"
            )

        # Credential store read + network → block
        if CREDENTIAL_STORE_RE.search(command) and has_network and not is_local:
            block(
                "Blocked: credential store read piped to a remote network destination.\n"
                "This command reads a secret from a credential store (keychain, vault, "
                "or secrets manager) and sends the result to a remote host, directly "
                f"exposing those credentials. {_EXPOSURE_RISK}"
            )

        # Credential store read (local) → ask
        if CREDENTIAL_STORE_RE.search(command):
            ask(
                "This command reads credentials from a system credential store "
                "(keychain, vault, or secrets manager). Exposing credentials to "
                "Claude's context creates risk: a prompt injection attack could "
                "trick Claude into forwarding the retrieved secret to an attacker. "
                f"{_EXPOSURE_RISK} Approve only if this access is intentional and "
                "the credentials will not leave this session."
            )

    # ── File path heuristics for Read/Write/Edit ─────────────────────────
    if tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path") or tool_input.get("path", "")
        if path:
            # Check 2: credential directory prefixes (unconditional)
            norm_path = os.path.normpath(os.path.expanduser(path))
            for dir_prefix in CREDENTIAL_DIR_PREFIXES:
                expanded = os.path.normpath(os.path.expanduser(dir_prefix))
                if norm_path.startswith(expanded + os.sep) or norm_path == expanded:
                    ask(
                        f"This operation targets '{path}', which is inside a "
                        f"credential directory ({dir_prefix}). Files here typically "
                        "contain private keys, access tokens, or authentication "
                        "credentials. Exposing these to Claude's context risks prompt "
                        f"injection attacks that could forward secrets to an attacker. "
                        f"{_EXPOSURE_RISK} Approve only if you intentionally want "
                        "Claude to access this material."
                    )
            # Check 1: credential file name patterns (with package-dir exemption)
            if CREDENTIAL_FILE_RE.search(path) and not EXEMPT_DIR_RE.search(path):
                ask(
                    f"This operation targets '{path}', whose name suggests it may "
                    "contain credentials, tokens, or key material. Exposing this to "
                    "Claude's context risks prompt injection attacks that could forward "
                    f"secrets to an attacker. {_EXPOSURE_RISK} Approve only if you "
                    "intentionally want Claude to access this material."
                )

    # ── Universal secret scan ────────────────────────────────────────────
    # Serialize tool_input and scan for secret patterns.
    # Fast path: built-in patterns only (~microseconds).
    # Deep path (gitleaks): only for Bash commands with network context,
    # where missing a secret would enable exfiltration.
    serialized = json.dumps(tool_input)

    if has_credential(serialized, deep=is_bash_with_network):
        if is_bash_with_network:
            block(
                "Blocked: credential detected in command with a network destination.\n"
                "This command contains an API key or authentication credential and "
                "sends data to a remote host, directly exposing those credentials. "
                f"{_EXPOSURE_RISK}"
            )
        ask(
            "A credential or API key pattern was detected in this tool call's "
            "arguments. A prompt injection attack could trick Claude into forwarding "
            f"these credentials to an attacker. {_EXPOSURE_RISK} If this is "
            "intentional (e.g., testing authentication locally), approve below. "
            "Otherwise deny and remove the credential before re-running."
        )

    sys.exit(0)


_current_tool_name = ""

if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        try:
            _current_tool_name = json.loads(raw).get("tool_name", "")
        except Exception:
            pass
        sys.stdin = io.StringIO(raw)
        main()
    except SystemExit:
        raise
    except Exception:
        if _current_tool_name in SENSITIVE_TOOLS:
            sys.exit(2)
        sys.exit(1)
