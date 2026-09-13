#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Block reads and writes that reach zero-access paths.

This PreToolUse hook covers Read, Write, Edit, Bash, and Codex `apply_patch`.
Bash parsing is conservative and can block benign commands. It does not evaluate
shell code, dynamic commands, nested command strings, or symlink indirection.
Codex native read tools emit no PreToolUse and are not covered.
"""

import glob
import json
import os
import re
import shlex
import sys
from typing import NoReturn

from guarded_paths import (
    NAME_HEURISTIC_EXEMPT_RE,
    ManifestError,
    fragment,
    load_manifest,
    spellings,
)
from hook_response import Decision, invoking_agent, respond

_EXPOSURE_RISK = (
    "Exposed credentials risk unauthorized access, account takeover, and data "
    "exfiltration across every service they protect."
)

EXTENSION_RE = re.compile(
    r"\.(pem|key|p12|pfx|crt|cer|tfstate|tfstate\.backup)$",
    re.IGNORECASE,
)

# Include `*` so shell globs match. Use case-insensitive matching to mirror
# the default macOS filesystem.
DOTENV_RE = re.compile(r"(?:^|[/\\*])\.env(?:\.[^/\\]+|\*)?$", re.IGNORECASE)
ENVRC_RE = re.compile(r"(?:^|[/\\*])\.envrc$", re.IGNORECASE)

SSH_KEY_RE = re.compile(
    r"(?:^|[/\\])id_(?:rsa|dsa|ecdsa|ed25519)[^/\\]*$", re.IGNORECASE
)

CRED_FILE_RE = re.compile(
    r"(?:^|[/\\])(?:\.netrc|\.npmrc|\.pypirc|\.git-credentials"
    r"|service-account[^/\\]*\.json|credentials\.json)$",
    re.IGNORECASE,
)
DOCKER_CONFIG_RE = re.compile(r"(?:^|[/\\])\.docker[/\\]config\.json$", re.IGNORECASE)


# Credential paths come from the manifest. This hook blocks reads;
# block-hook-tampering blocks writes.
def _credential_alternation(paths) -> str:
    """The regex alternation matching any credential path's relative form."""
    parts = []
    for path in paths:
        relative = path.removeprefix("~/")
        parts.append(re.escape(relative).replace("/", r"[/\\]"))
    return "|".join(parts)


try:
    _MANIFEST = load_manifest()
    _CREDENTIAL_PATHS = _MANIFEST["credentials"]["paths"]
    MANIFEST_ERROR = None
except (ManifestError, KeyError, TypeError) as _exc:
    _MANIFEST = {}
    _CREDENTIAL_PATHS = ()
    MANIFEST_ERROR = str(_exc)

AGENT_CREDENTIAL_RE = re.compile(
    # `(?!)` matches nothing; `main()` reports the manifest failure.
    rf"(?:^|[/\\])(?:{_credential_alternation(_CREDENTIAL_PATHS)})[^/\\]*$"
    if _CREDENTIAL_PATHS
    else r"(?!)",
    re.IGNORECASE,
)

CRED_DIR_RE = re.compile(
    r"(?:^|[/\\])\.(?:ssh|aws|kube|gnupg|azure)(?:[/\\]|$)", re.IGNORECASE
)


# Apply exceptions only to the spelling that triggered the name heuristic; a
# link must not borrow its target's exception.
def _exception_alternation(manifest) -> str:
    """The regex alternation matching any declared exception's trailing form."""
    parts = [
        re.escape(fragment(exception["pattern"])).replace("/", r"[/\\]")
        for exception in manifest.get("exceptions", ())
        if exception.get("surface") == "sensitive-path-name-heuristic"
    ]
    return "|".join(parts)


_NAME_EXCEPTIONS = _exception_alternation(_MANIFEST)

NAME_HEURISTIC_EXCEPTION_RE = re.compile(
    # `(?!)` never matches, so a manifest that declared none excuses none.
    rf"(?:^|[/\\])(?:{_NAME_EXCEPTIONS})$" if _NAME_EXCEPTIONS else r"(?!)",
    re.IGNORECASE,
)

ZERO_ACCESS_FILES_RE = re.compile(
    r"(?:^|[/\\])\.(?:bash_history|zsh_history|sh_history|node_repl_history|python_history)$",
    re.IGNORECASE,
)

# The only class subject to the package-directory exemption.
NAME_PATTERN_RE = re.compile(r"credentials|secret", re.IGNORECASE)

PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (?P<path>.+)$", re.MULTILINE
)


def is_zero_access(path: str) -> bool:
    """True if one spelling of a path matches a strong zero-access signal."""
    return bool(
        EXTENSION_RE.search(path)
        or DOTENV_RE.search(path)
        or ENVRC_RE.search(path)
        or ZERO_ACCESS_FILES_RE.search(path)
        or SSH_KEY_RE.search(path)
        or CRED_FILE_RE.search(path)
        or DOCKER_CONFIG_RE.search(path)
        or CRED_DIR_RE.search(path)
        or AGENT_CREDENTIAL_RE.search(path)
    )


def is_named_for_secrets(path: str) -> bool:
    """Return whether only the unexempted file name signals a secret."""
    return bool(
        NAME_PATTERN_RE.search(os.path.basename(path))
        and not NAME_HEURISTIC_EXEMPT_RE.search(path)
        and not NAME_HEURISTIC_EXCEPTION_RE.search(path)
    )


def should_block(path: str) -> bool:
    """Return whether any spelling of `path` reaches a zero-access location.

    Apply heuristics and exemptions to the same spelling.
    """
    return any(
        is_zero_access(candidate) or is_named_for_secrets(candidate)
        for candidate in spellings(path)
    )


def block(path: str, tool: str) -> NoReturn:
    action = "Reading" if tool in ("Read", "Bash read") else "Accessing"
    respond(
        Decision.BLOCK,
        f"Blocked: {tool} targeting zero-access path '{path}'.\n"
        f"{action} it could expose credentials or private keys to the agent, where "
        "a later tool call could disclose or use them.",
    )


# Include transfer commands so secret source operands also block.
READ_CMDS = frozenset(
    {
        "cat",
        "tac",
        "nl",
        "less",
        "more",
        "bat",
        "head",
        "tail",
        "od",
        "xxd",
        "hexdump",
        "strings",
        "base64",
        "base32",
        "cut",
        "column",
        "fold",
        "fmt",
        "rev",
        "sort",
        "uniq",
        "wc",
        "cmp",
        "diff",
        "comm",
        "paste",
        "expand",
        "unexpand",
        "tr",
        "shasum",
        "md5sum",
        "sha1sum",
        "sha256sum",
        "sha512sum",
        "b2sum",
        "cksum",
        "sum",
        "pr",
        "join",
        "look",
        "csplit",
        "split",
        "source",
        ".",
        "dd",
        "readlink",
        "realpath",
        "install",
        "cp",
        "mv",
        "scp",
        "rsync",
        "sftp",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "ag",
        "ack",
        "sed",
        "awk",
        "gawk",
        "jq",
        "yq",
        "xq",
        "tomlq",
        "envsubst",
        "tar",
        "unzip",
        "zcat",
        "zless",
        "zgrep",
        "gzcat",
        "bzcat",
        "xzcat",
        "gunzip",
        "bunzip2",
        "unxz",
        "openssl",
        "gpg",
        "gpg2",
        "age",
        "vi",
        "vim",
        "view",
        "ex",
        "nano",
        "pico",
        "emacs",
    }
)

# `shlex` groups punctuation runs. A punctuation-only token is never a word;
# a run containing a separator ends the segment.
_PUNCT_ONLY_RE = re.compile(r"^[|&;<>()]+$")
_SEGMENT_SEP_RE = re.compile(r"[|;&()]")
_LEADING_OPT_RE = re.compile(r"^-{1,2}[A-Za-z][A-Za-z-]*")

# Bash decodes the C escapes in `$'...'` (`\056` -> '.'), so the literal
# filename regexes must see the decoded form, not the escape sequence.
_ANSI_C_RE = re.compile(r"\$'((?:[^'\\]|\\.)*)'")


def _decode_ansi_c(command: str) -> str:
    """Decode ANSI-C quoted spans and preserve token boundaries.

    Leave a span unchanged if decoding fails.
    """

    def repl(m: "re.Match[str]") -> str:
        body = m.group(1)
        try:
            decoded = body.encode("latin-1", "backslashreplace").decode(
                "unicode_escape"
            )
        except Exception:  # noqa: BLE001
            return m.group(0)
        return "'" + decoded.replace("'", "'\\''") + "'"

    return _ANSI_C_RE.sub(repl, command)


def _norm_cmdword(token: str) -> str:
    """Basename of a command word (already unquoted by shlex)."""
    return os.path.basename(token.lstrip("\\"))


def _lex_tokens(command: str) -> list[str]:
    """Tokenize quotes and operators; use a permissive split for unclosed quotes."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        tokens: list[str] = []
        for part in re.split(r"([|&;\n<>()]+)", command):
            tokens.extend(part.split())
        return tokens


def _candidate_paths(token: str):
    """Yield the token and any attached option value that can name a file."""
    yield token
    if "=" in token:
        yield token.split("=", 1)[1]
    stripped = _LEADING_OPT_RE.sub("", token)
    if stripped and stripped != token:
        yield stripped


def expand_glob_candidates(token: str, cwd: str):
    """Yield the token and its glob matches; yield only the token on error."""
    yield token
    try:
        if not glob.has_magic(token):
            return
        pattern = os.path.expanduser(token)
        if os.path.isabs(pattern):
            matches = glob.glob(pattern)
        else:
            matches = glob.glob(pattern, root_dir=cwd or None)
        yield from matches
    except (OSError, ValueError):
        return


def extract_bash_read_targets(command: str) -> list[str]:
    """Return input-redirection targets and tokens from read-command segments."""
    targets: list[str] = []
    tokens = _lex_tokens(_decode_ansi_c(command))

    # Input redirection reads a file regardless of the command. Exclude
    # here-docs and include `<` inside punctuation runs.
    for i, tok in enumerate(tokens):
        if _PUNCT_ONLY_RE.match(tok) and "<" in tok and "<<" not in tok:
            for nxt in tokens[i + 1 :]:
                if not _PUNCT_ONLY_RE.match(nxt):
                    targets.extend(_candidate_paths(nxt))
                    break

    # Checking every token can block benign search patterns. Keep that bias and
    # narrow `NAME_PATTERN` instead of modeling options.
    segment: list[str] = []
    for tok in [*tokens, ";"]:  # trailing sentinel flushes the last segment
        if _PUNCT_ONLY_RE.match(tok) and _SEGMENT_SEP_RE.search(tok):
            words = [t for t in segment if not _PUNCT_ONLY_RE.match(t)]
            if any(_norm_cmdword(w) in READ_CMDS for w in words):
                for word in words:
                    targets.extend(_candidate_paths(word))
            segment = []
        else:
            segment.append(tok)
    return targets


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] in "\"'" and token[-1] == token[0]:
        token = token[1:-1]
    return token.strip("\"'")


def extract_bash_write_targets(command: str) -> list[str]:
    """Return likely write destinations in a Bash command."""
    targets: list[str] = []

    # Excludes here-docs and here-strings (<<, <<<) and stderr-only `2>`.
    for m in re.finditer(r"(?:(?<![<2&])>>?\|?|&>>?)\s*([^\s|&;><]+)", command):
        targets.append(m.group(1))

    # `cp`, `mv`, and `install` use the final non-option token as destination.
    for cmd in ("cp", "mv", "install"):
        for m in re.finditer(
            rf"\b{cmd}\b\s+((?:(?:-[^\s]+|--[^\s]+|\S+)\s+)+?)(\S+)\s*(?:$|[|&;])",
            command,
        ):
            targets.append(m.group(2))

    for m in re.finditer(
        r"\btee\b(?:\s+-{1,2}[A-Za-z][\w=-]*)*\s+([^\s|&;]+)", command
    ):
        targets.append(m.group(1))

    for cmd in ("chmod", "chown"):
        for m in re.finditer(rf"\b{cmd}\b\s+\S+\s+([^\s|&;]+)", command):
            targets.append(m.group(1))

    for m in re.finditer(r"(?<![\w/])of=([^\s|&;<>]+)", command):
        targets.append(_strip_quotes(m.group(1)))

    for m in re.finditer(r"\btruncate\b\s+(?:-[^\s]+\s+)*([^\s|&;<>]+)", command):
        targets.append(_strip_quotes(m.group(1)))

    return targets


def extract_apply_patch_targets(command: str) -> list[str]:
    """Return paths named by Codex `apply_patch` headers."""
    return [match.group("path").strip() for match in PATCH_PATH_RE.finditer(command)]


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        # Fail open because a malformed payload does not identify the tool.
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "") or ""

    if tool_name not in ("Bash", "Read", "Write", "Edit", "apply_patch"):
        sys.exit(0)

    if MANIFEST_ERROR is not None:
        # Report a broken manifest and fail open instead of checking a partial set.
        respond(
            Decision.WARN,
            "block-sensitive-paths could not load guarded-paths.toml "
            f"({MANIFEST_ERROR}); this tool call was not checked.",
            agent=invoking_agent(payload=data),
        )

    if tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path") or tool_input.get("path", "")
        if path and should_block(path):
            block(path, tool_name)

    elif tool_name == "apply_patch":
        command = tool_input.get("command", "")
        if not command:
            sys.exit(0)
        for target in extract_apply_patch_targets(command):
            if should_block(target):
                block(target, "apply_patch")

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            sys.exit(0)
        for target in extract_bash_write_targets(command):
            for cand in expand_glob_candidates(target, cwd):
                if should_block(cand):
                    block(cand, "Bash write")
        for target in extract_bash_read_targets(command):
            for cand in expand_glob_candidates(target, cwd):
                if should_block(cand):
                    block(cand, "Bash read")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        sys.exit(0)
