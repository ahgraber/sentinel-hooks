#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Hard-block reads and writes that reach a zero-access path.

PreToolUse hook for `Read`, `Write`, `Edit`, `Bash`, and Codex's `apply_patch`;
every agent sends the same snake_case `{tool_name, tool_input}` payload, and a
tool a given agent never emits is simply a dead branch there.

Bash handling is fail safe, not precise: the goal is to prevent operations over
secrets, not to model shell grammar. Where a command segment invokes a
recognized read or transfer command, every token of that segment is checked,
with no option/operand modelling, so a secret filename blocks wherever it
appears — operand, attached option value, copy source, or behind a wrapper. That
over-denies (a search pattern such as `grep -r secret .` blocks), which is the
intended bias: missing a real secret read is worse than blocking a benign one.

Out of scope, because they need real shell evaluation that command-text parsing
cannot do; the boundary for them is the sandbox's literal-prefix denies, the
network egress allowlist, and `block-secrets.py`:
  - Interpreters that open the file in code: `python -c`, `perl`, `node -e`.
  - A command word behind a variable: `c=cat; $c .env`.
  - Wrappers whose child is a nested command string: `bash -c`, `eval`,
    backticks, and `xargs`/`find -exec` across pipeline segments.
  - Symlink indirection: `ln -s ~/.aws/credentials link`, then read `link`.
  - On Codex the native `read_file`/`grep` tools emit no PreToolUse, so only
    shell reads are covered there.
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

# The boundary class includes `*` so shell globs (`*.env`, `.env*`) match too.
# Case-insensitive because macOS — the platform whose sandbox globs this mirrors
# — has a case-insensitive filesystem by default.
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


# No generic pattern reaches the agent credential stores: the files are named
# auth.json, and `.claude/` is exempt from the name heuristic so the hook
# sources named for what they guard against stay readable. Built from the
# manifest's `[credentials]` class, whose mutation block-hook-tampering.py
# refuses; this hook is what refuses the read.
def _credential_alternation(paths) -> str:
    """The regex alternation matching any credential path's relative form."""
    parts = []
    for path in paths:
        relative = path.removeprefix("~/")
        parts.append(re.escape(relative).replace("/", r"[/\\]"))
    return "|".join(parts)


try:
    _CREDENTIAL_PATHS = load_manifest()["credentials"]["paths"]
    MANIFEST_ERROR = None
except (ManifestError, KeyError, TypeError) as _exc:
    _CREDENTIAL_PATHS = ()
    MANIFEST_ERROR = str(_exc)

AGENT_CREDENTIAL_RE = re.compile(
    # `(?!)` never matches: the safe fallback when the manifest could not be
    # loaded, since main() then reports the failure and skips every other check
    # too rather than silently narrowing just this one.
    rf"(?:^|[/\\])(?:{_credential_alternation(_CREDENTIAL_PATHS)})[^/\\]*$"
    if _CREDENTIAL_PATHS
    else r"(?!)",
    re.IGNORECASE,
)

CRED_DIR_RE = re.compile(
    r"(?:^|[/\\])\.(?:ssh|aws|kube|gnupg|azure)(?:[/\\]|$)", re.IGNORECASE
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
    """True if the file name is the only signal, and the directory does not excuse it."""
    return bool(
        NAME_PATTERN_RE.search(os.path.basename(path))
        and not NAME_HEURISTIC_EXEMPT_RE.search(path)
    )


def should_block(path: str) -> bool:
    """True if any spelling of `path` reaches a zero-access location.

    Each spelling is judged whole. Matching under one spelling and taking the
    exemption from another would let a symbolic link outside a package tree
    borrow that tree's exemption.
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
        f"{action} this path would expose credentials, private keys, or "
        "authentication secrets to Claude's context. A prompt injection attack "
        "could trick Claude into forwarding this material to an attacker. "
        f"{_EXPOSURE_RISK}",
    )


# Commands that read or transfer file contents. cp/mv/scp/rsync/sftp are here so
# a secret used as a *source* operand blocks, not just secret destinations.
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
        # archive / compression / crypto readers (dump file contents)
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
        # editors / pagers that can print a file
        "vi",
        "vim",
        "view",
        "ex",
        "nano",
        "pico",
        "emacs",
    }
)

# shlex(punctuation_chars=True) groups runs of ();<>|& into single tokens, so a
# token may be e.g. '(<' or ');'. A punctuation-only token is never a word; one
# that contains a command separator ends a segment.
_PUNCT_ONLY_RE = re.compile(r"^[|&;<>()]+$")
_SEGMENT_SEP_RE = re.compile(r"[|;&()]")
_LEADING_OPT_RE = re.compile(r"^-{1,2}[A-Za-z][A-Za-z-]*")

# Bash decodes the C escapes in `$'...'` (`\056` -> '.'), so the literal
# filename regexes must see the decoded form, not the escape sequence.
_ANSI_C_RE = re.compile(r"\$'((?:[^'\\]|\\.)*)'")


def _decode_ansi_c(command: str) -> str:
    """Decode `$'...'` ANSI-C quoted spans to their literal characters.

    The decoded text is re-wrapped in single quotes so shlex still treats it as
    one token. Fail-safe: on any decode error the span is left untouched.
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
    """Quote- and operator-aware tokenisation (flat list).

    Falls back to a permissive split on unbalanced quotes, so a command shlex
    cannot parse is still scanned.
    """
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
    """Yield the strings in a token that could name a file, so an attached option value (`if=.env`, `-f.env`) is caught."""
    yield token
    if "=" in token:
        yield token.split("=", 1)[1]
    stripped = _LEADING_OPT_RE.sub("", token)
    if stripped and stripped != token:
        yield stripped


def expand_glob_candidates(token: str, cwd: str):
    """Yield the token and, if it globs, every path it expands to, as the shell would.

    Closes the class where a wildcard hides a sensitive literal from the
    regexes (`cat .en*`). Fail-safe: an expansion error yields the token alone.
    """
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
    """Candidate read paths: input-redirection targets, and every token of a segment invoking a read command."""
    targets: list[str] = []
    tokens = _lex_tokens(_decode_ansi_c(command))

    # Input redirection reads a file whatever the command word is, so a bare
    # `mapfile < .env` or `$(< .env)` is caught. The '<' may be grouped with
    # other punctuation ('(<'); here-docs ('<<') are excluded.
    for i, tok in enumerate(tokens):
        if _PUNCT_ONLY_RE.match(tok) and "<" in tok and "<<" not in tok:
            for nxt in tokens[i + 1 :]:
                if not _PUNCT_ONLY_RE.match(nxt):
                    targets.extend(_candidate_paths(nxt))
                    break

    # Checking every token of a read segment includes the command's own search
    # pattern, so `grep -r secret .` over-denies. Accepted: over-deny beats a
    # missed secret. A carve-out must not reintroduce option modelling — narrow
    # NAME_PATTERN out of the search commands instead.
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
    """Extract likely write-destination paths from a Bash command string."""
    targets: list[str] = []

    # Excludes here-docs and here-strings (<<, <<<) and stderr-only `2>`.
    for m in re.finditer(r"(?:(?<![<2&])>>?\|?|&>>?)\s*([^\s|&;><]+)", command):
        targets.append(m.group(1))

    # cp / mv / install — destination is the final non-option token
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
    """Extract target file paths from a Codex apply_patch command body."""
    return [match.group("path").strip() for match in PATCH_PATH_RE.finditer(command)]


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        # Fail open: the tool is unknown on a parse failure, and this hook
        # handles read-only tools as well as sensitive ones.
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "") or ""

    if tool_name not in ("Bash", "Read", "Write", "Edit", "apply_patch"):
        sys.exit(0)

    if MANIFEST_ERROR is not None:
        # A broken manifest leaves the agent-credential class unmatchable, so
        # the call proceeds rather than checking a narrowed, silent subset, and
        # the break is reported. block-hook-tampering.py does the same.
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
        # Fail open: Read is read-only, so the tool mix here implies no damage
        # potential from an internal error.
        sys.exit(0)
