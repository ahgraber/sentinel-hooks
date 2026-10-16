#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Block secret exfiltration and flag credential content (PreToolUse hook).

This hook judges what a call carries and where it sends it. Which file paths
are credentials is `block-sensitive-paths.py`'s judgment, made from the manifest.
"""

import io
import json
import os
import re
import subprocess
import sys
from typing import NoReturn

import bash_commands
from guarded_paths import TOOL_VOCABULARY
from hook_response import UNKNOWN, Decision, invoking_agent, respond, supports_ask
import shell_words

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
    r"|\baws\s+secretsmanager\b",
    re.IGNORECASE,
)

# Options such as `--account work` or `-n prod` may sit between the program and its subcommand.
_LEADING_OPTIONS = r"(?:\s+--?[\w-]+(?:[= ][^\s-]\S*)?)*"

# Stores no agent may read: every agent's sandbox denies their configuration.
# The pattern judges only text the lexer cannot read: an unlexable command or a
# command substitution, where refusing on the text is the safe reading.
USER_ONLY_STORE_RE = re.compile(
    rf"\bop{_LEADING_OPTIONS}\s+(?:read|run|inject|item\s+get|document\s+get)\b"
    rf"|\bkubectl{_LEADING_OPTIONS}\s+get\s+secrets?\b",
    re.IGNORECASE,
)

_OP_VALUE_OPTIONS = frozenset({"--account", "--cache", "--config", "--encoding", "--format", "--session"})
_KUBECTL_VALUE_OPTIONS = frozenset(
    {"-n", "--namespace", "--context", "--kubeconfig", "--cluster", "--user", "-s", "--server", "--token", "--as"}
)
_SUBSTITUTION = re.compile(r"\$\(|[<>]\(")
_QUOTING = re.compile(r"[\"'\\]")
_MAX_NESTING = 4
_UNREAD_FORM = "a 1Password or Kubernetes secret read"


def _operands(words: list[shell_words.Word], value_options: frozenset[str]) -> list[str]:
    """Return the non-option arguments, skipping the value each listed option takes."""
    operands = []
    index = 0
    while index < len(words):
        value = words[index].value
        if value.startswith("-") and value != "-":
            index += value in value_options
        else:
            operands.append(value)
        index += 1
    return operands


def _text_match(text: str) -> str | None:
    """Judge text the lexer cannot read, with quoting removed so `op 'read'` still matches."""
    return _UNREAD_FORM if USER_ONLY_STORE_RE.search(_QUOTING.sub("", text)) else None


def _invokes_user_only_store(words: list[shell_words.Word]) -> str | None:
    """Name the secret read one invocation performs, if it reads a 1Password or Kubernetes secret."""
    if not words:
        return None
    name = os.path.basename(words[0].value)
    if name == "op":
        operands = _operands(words[1:], _OP_VALUE_OPTIONS)
        if operands[:1] and operands[0] in {"read", "run", "inject"}:
            return f"op {operands[0]}"
        if operands[:2] in (["item", "get"], ["document", "get"]):
            return f"op {operands[0]} get"
    if name == "kubectl":
        operands = _operands(words[1:], _KUBECTL_VALUE_OPTIONS)
        resources = [kind.split("/")[0] for operand in operands[1:] for kind in operand.split(",")]
        if operands[:1] == ["get"] and {"secret", "secrets"} & set(resources):
            return "kubectl get secret"
    return None


def _reads_stdin_script(words: list[shell_words.Word]) -> bool:
    """Whether a shell runs a script from its standard input, which the lexer never sees."""
    return (
        bool(words)
        and os.path.basename(words[0].value) in bash_commands.SHELLS
        and not bash_commands.program_text(words)
        and not _operands(words[1:], frozenset())
    )


def user_only_store_read(command: str, depth: int = 0) -> str | None:
    """Name the 1Password or Kubernetes secret read the text runs, or `None` when it runs none."""
    segments = shell_words.lex(command, None)
    # Backticks split across words, so only the whole text shows what they run.
    if segments is None or depth > _MAX_NESTING or "`" in command:
        if match := _text_match(command):
            return match
        if segments is None or depth > _MAX_NESTING:
            return None
    for segment in segments:
        for word in segment:
            if word.kind == "unresolvable" and _SUBSTITUTION.search(word.value) and (match := _text_match(word.value)):
                return match
        words = bash_commands.invoked(segment)
        if match := _invokes_user_only_store(words):
            return match
        for text in bash_commands.program_text(words):
            if match := user_only_store_read(text, depth + 1):
                return match
        if _reads_stdin_script(words) and (match := _text_match(command)):
            return match
    return None


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
        "approve below. Otherwise deny and remove the credential before re-running.",
        "have the user perform the sensitive step manually outside the agent "
        "session. Otherwise remove the credential before re-running.",
    )
    block("Blocked: this agent cannot show a confirmation prompt for this action.\n" + reason)


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
            "block-leaks could not parse the hook payload; this call was not checked.",
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

        user_only_read = user_only_store_read(command)
        reads_store = bool(user_only_read) or bool(CREDENTIAL_STORE_RE.search(command))

        if reads_store and has_network and not is_local:
            block(
                "Blocked: credential store read piped to a remote network destination.\n"
                "This command sends a secret from a keychain, vault, or secrets manager "
                f"to a remote host. {_EXPOSURE_RISK}"
            )

        if user_only_read:
            block(
                f"Blocked: this command runs {user_only_read}, which reads a secret that is for the user alone.\n"
                "Reading it would expose the secret to the agent's context and the model provider. "
                f"{_EXPOSURE_RISK} Ask the user to run this command in their own terminal."
            )

        if CREDENTIAL_STORE_RE.search(command):
            ask(
                "This command reads credentials from a keychain, vault, or secrets "
                "manager. Exposing them to the agent could let prompt injection send "
                f"them to an attacker. {_EXPOSURE_RISK} Approve only if this access "
                "is intentional and the credentials will not leave this session."
            )

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
                "Blocked: block-leaks failed while checking a call that could expose credentials.",
                agent=_AGENT,
            )
        respond(
            Decision.WARN,
            "block-leaks failed; this tool call was not checked.",
            agent=_AGENT,
        )
