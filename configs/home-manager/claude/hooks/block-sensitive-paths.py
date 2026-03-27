#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Claude Code Hook: Block reads and writes to sensitive/zero-access paths.

PreToolUse hook for Read, Write, Edit, and Bash tools.
Hard-blocks (exit 2) any attempt to read from or write to zero-access paths.

Zero-access paths include: dot-env files, ~/.ssh, ~/.aws, ~/.kube, ~/.gnupg,
certificate/key files, Terraform state, and files with 'credentials' or
'secret' in their name (with package-directory exemption).
"""

import json
import os
import re
import sys

# ── Shared risk explanation ───────────────────────────────────────────────────
_EXPOSURE_RISK = (
    "Exposed credentials risk unauthorised access, account takeover, and data "
    "exfiltration across every service they protect."
)

# ── Directory exemption for name-based patterns ──────────────────────────────
# Name-based patterns ('credentials', 'secret') don't apply inside these
# directories, where those words are valid file/module names rather than
# indicators of actual secrets.
#   - Package/dependency dirs: .venv, site-packages, node_modules
#   - Tool config dirs: ~/.claude, claude/hooks (hooks like 'block-secrets.py')
EXEMPT_DIR_RE = re.compile(
    r"(?:^|[/\\])(?:\.venv|venv|env|site-packages|node_modules|\.claude|claude[/\\]hooks)(?:[/\\]|$)",
    re.IGNORECASE,
)

# ── Extension-based patterns (unconditional, no package-dir exemption) ────────
EXTENSION_RE = re.compile(
    r"\.(pem|key|p12|pfx|crt|cer|tfstate|tfstate\.backup)$",
    re.IGNORECASE,
)

# ── Dot-env file patterns (unconditional) ─────────────────────────────────────
DOTENV_RE = re.compile(r"(?:^|[/\\])\.env(?:\.[^/\\]+)?$")
ENVRC_RE = re.compile(r"(?:^|[/\\])\.envrc$")

# ── Directory prefixes that are always zero-access ────────────────────────────
ZERO_ACCESS_DIRS = ["~/.ssh/", "~/.aws/", "~/.kube/", "~/.gnupg/"]

# ── Specific files that are always zero-access ───────────────────────────────
ZERO_ACCESS_FILES_RE = re.compile(
    r"(?:^|[/\\])\.(?:bash_history|zsh_history|sh_history|node_repl_history|python_history)$",
    re.IGNORECASE,
)

# ── Name-based patterns (require package-dir exemption check) ─────────────────
NAME_PATTERN_RE = re.compile(r"credentials|secret", re.IGNORECASE)

# ── Bash write-to-path detection ──────────────────────────────────────────────
# Patterns that indicate a bash command is writing to a path:
#   - output redirection: > path or >> path
#   - cp/mv/install with destination as last argument
#   - tee writing to a file
#   - chmod or chown targeting a path


def expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def is_in_exempt_dir(path: str) -> bool:
    return bool(EXEMPT_DIR_RE.search(path))


def is_zero_access(path: str) -> tuple[bool, bool]:
    """Return (is_zero_access, needs_exemption_check)."""
    norm = expand(path)

    if EXTENSION_RE.search(norm):
        return True, False

    if DOTENV_RE.search(path) or ENVRC_RE.search(path):
        return True, False

    if ZERO_ACCESS_FILES_RE.search(path):
        return True, False

    for dir_pat in ZERO_ACCESS_DIRS:
        prefix = expand(dir_pat)
        if norm.startswith(prefix + os.sep) or norm == prefix:
            return True, False

    basename = os.path.basename(norm)
    if NAME_PATTERN_RE.search(basename):
        return True, True  # matched but needs package-dir exemption check

    return False, False


def should_block(path: str) -> bool:
    matched, needs_exemption = is_zero_access(path)
    if not matched:
        return False
    if needs_exemption and is_in_exempt_dir(path):
        return False
    return True


def block(path: str, tool: str) -> None:
    action = "Reading" if tool == "Read" else "Accessing"
    sys.stderr.write(
        f"Blocked: {tool} targeting zero-access path '{path}'.\n"
        f"{action} this path would expose credentials, private keys, or "
        "authentication secrets to Claude's context. A prompt injection attack "
        "could trick Claude into forwarding this material to an attacker. "
        f"{_EXPOSURE_RISK}\n"
    )
    sys.exit(2)


def extract_bash_write_targets(command: str) -> list[str]:
    """Extract likely write-destination paths from a Bash command string."""
    targets: list[str] = []

    # Output redirections: > path or >> path (exclude <<, <<<, 2>, etc.)
    for m in re.finditer(r"(?<![<2&])>>?\s*([^\s|&;><]+)", command):
        targets.append(m.group(1))

    # cp / mv / install — destination is the final non-option token
    for cmd in ("cp", "mv", "install"):
        for m in re.finditer(
            rf"\b{cmd}\b\s+((?:(?:-[^\s]+|--[^\s]+|\S+)\s+)+?)(\S+)\s*(?:$|[|&;])",
            command,
        ):
            targets.append(m.group(2))

    # tee: tee [-ai] <file>
    for m in re.finditer(r"\btee\b(?:\s+-[ai]+)*\s+([^\s|&;]+)", command):
        targets.append(m.group(1))

    # chmod / chown: <cmd> <mode-or-owner> <path>
    for cmd in ("chmod", "chown"):
        for m in re.finditer(rf"\b{cmd}\b\s+\S+\s+([^\s|&;]+)", command):
            targets.append(m.group(1))

    return targets


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(
            0
        )  # fail-open: this hook handles mixed sensitive+read-only tools (Bash/Read/Write/Edit);
        # on parse failure the tool type is unknown, so fail-open per hook-interface spec

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ("Bash", "Read", "Write", "Edit"):
        sys.exit(0)

    if tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path") or tool_input.get("path", "")
        if path and should_block(path):
            block(path, tool_name)

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            sys.exit(0)
        for target in extract_bash_write_targets(command):
            if should_block(target):
                block(target, "Bash write")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # ErrorHandlingByDamagePotential: this hook handles Read (read-only) in addition
        # to Bash/Write/Edit (sensitive), so fail-open on internal error per hook-interface spec.
        sys.exit(0)
