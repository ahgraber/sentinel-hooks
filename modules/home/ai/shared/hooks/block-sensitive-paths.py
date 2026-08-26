#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Claude Code / Codex Hook: Block reads and writes to sensitive/zero-access paths.

PreToolUse hook for Read, Write, Edit, Bash, and apply_patch tools.
Hard-blocks (exit 2) any attempt to read from or write to zero-access paths.

This hook is shared (symlinked) between Claude Code and Codex. Both send the same
snake_case `{tool_name, tool_input}` PreToolUse payload. `Read`/`Write`/`Edit` are
Claude tools; `apply_patch` is the Codex edit tool; `Bash` is common (Codex's
shell tool also reports `tool_name == "Bash"`). A tool a given agent never emits
is simply a dead branch there.

Zero-access paths include: dot-env files, SSH keys (anywhere), the credential
directories ~/.ssh, .aws, .kube, .gnupg, .azure (anywhere), credential config
files (.netrc, .npmrc, .pypirc, .git-credentials, .docker/config.json,
service-account*.json, credentials.json), certificate/key files, Terraform
state, shell history, and files with 'credentials' or 'secret' in their name
(with package-directory exemption).

Bash handling — fail safe, not precise:
  The goal is to prevent operations over secrets, not to model shell grammar.
  A command is tokenised with `shlex` (quote- and operator-aware). If the
  command invokes a recognised read command (`cat`, `grep`, `sed`, `jq`, `cp`,
  `mv`, `scp`, `rsync`, ...), EVERY token in that segment is checked against the
  sensitivity rules and any match blocks. There is deliberately no option/operand
  modelling: a secret filename that appears anywhere — as an operand, an attached
  option value (`-f.env`, `if=.env`), a copy/transfer source (`cp ~/.ssh/id_rsa
  x`), or behind a wrapper (`sudo -u root cat .env`) — is blocked. This trades
  false positives (a secret-looking search pattern such as `grep -r secret .`
  blocks) for the absence of false negatives, which is the intended bias: missing
  a real secret read is worse than blocking a benign one.

  Two extra fail-safe decodings run before matching so shell-level rewrites of a
  secret filename cannot hide it from the literal regexes:
    - ANSI-C quoting (`$'\\056env'`) is decoded to its literal (`.env`).
    - Glob tokens (`cat .en*`, `cat cred*.json`, `cp ~/.ssh/id_rs? x`) are
      expanded against the filesystem (relative to the command's cwd), exactly as
      the shell would, and each real match is checked.

  Still out of scope — these need real shell evaluation, which command-text
  parsing cannot do; the boundary for them is the sandbox's literal-prefix
  denies, the network egress allowlist, and `block-secrets.py`:
    - Interpreters that open the file in code: `python -c`, `perl`, `ruby`,
      `node -e`.
    - Command words hidden behind a variable: `c=cat; $c .env` (shlex does not
      expand `$c`).
    - Wrappers whose child is a nested command string: `bash -c '...'`, `eval`,
      backticks, and `xargs`/`find -exec` where the secret and the reader end up
      in different pipeline segments.
    - Symlink indirection: `ln -s ~/.aws/credentials link` then reading `link`.
    - On Codex, the native `read_file`/`grep` tools do not emit PreToolUse yet,
      so only shell (`Bash`) reads are covered there.
"""

import glob
import json
import os
import re
import shlex
import sys

# ── Shared risk explanation ───────────────────────────────────────────────────
_EXPOSURE_RISK = (
    "Exposed credentials risk unauthorised access, account takeover, and data "
    "exfiltration across every service they protect."
)

# ── Directory exemption for name-based patterns ──────────────────────────────
# Name-based patterns ('credentials', 'secret') don't apply inside these
# directories, where those words are valid file/module names rather than
# indicators of actual secrets. NOTE: a bare `env` component is deliberately NOT
# exempt — a directory literally named `env/` can hold real secrets; only the
# explicit virtualenv names `.venv`/`venv` are treated as package dirs.
EXEMPT_DIR_RE = re.compile(
    r"(?:^|[/\\])(?:\.venv|venv|site-packages|node_modules|\.claude|(?:claude|codex)[/\\](?:hooks|tests))(?:[/\\]|$)",
    re.IGNORECASE,
)

# ── Extension-based patterns (unconditional, no package-dir exemption) ────────
EXTENSION_RE = re.compile(
    r"\.(pem|key|p12|pfx|crt|cer|tfstate|tfstate\.backup)$",
    re.IGNORECASE,
)

# ── Dot-env file patterns (unconditional) ─────────────────────────────────────
# Boundary class includes `*` so shell globs (`*.env`, `.env*`) are matched too.
# Case-insensitive because macOS — the platform whose sandbox globs this mirrors
# — has a case-insensitive filesystem by default.
DOTENV_RE = re.compile(r"(?:^|[/\\*])\.env(?:\.[^/\\]+|\*)?$", re.IGNORECASE)
ENVRC_RE = re.compile(r"(?:^|[/\\*])\.envrc$", re.IGNORECASE)

# ── SSH key filenames, anywhere (unconditional) ───────────────────────────────
SSH_KEY_RE = re.compile(
    r"(?:^|[/\\])id_(?:rsa|dsa|ecdsa|ed25519)[^/\\]*$", re.IGNORECASE
)

# ── Credential config / high-value credential files, anywhere (unconditional) ─
CRED_FILE_RE = re.compile(
    r"(?:^|[/\\])(?:\.netrc|\.npmrc|\.pypirc|\.git-credentials"
    r"|service-account[^/\\]*\.json|credentials\.json)$",
    re.IGNORECASE,
)
DOCKER_CONFIG_RE = re.compile(r"(?:^|[/\\])\.docker[/\\]config\.json$", re.IGNORECASE)

# ── Credential directories, anywhere (unconditional) ──────────────────────────
CRED_DIR_RE = re.compile(
    r"(?:^|[/\\])\.(?:ssh|aws|kube|gnupg|azure)(?:[/\\]|$)", re.IGNORECASE
)

# ── Specific files that are always zero-access ───────────────────────────────
ZERO_ACCESS_FILES_RE = re.compile(
    r"(?:^|[/\\])\.(?:bash_history|zsh_history|sh_history|node_repl_history|python_history)$",
    re.IGNORECASE,
)

# ── Name-based patterns (require package-dir exemption check) ─────────────────
NAME_PATTERN_RE = re.compile(r"credentials|secret", re.IGNORECASE)

# ── apply_patch path extraction (Codex edit tool) ─────────────────────────────
# Codex applies edits via an `apply_patch` tool whose command body names the
# target files (`*** Add File: path`, `*** Update File: path`, etc.). Claude Code
# has no such tool, so this is inert there.
PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (?P<path>.+)$", re.MULTILINE
)


def expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def is_in_exempt_dir(path: str) -> bool:
    return bool(EXEMPT_DIR_RE.search(path))


def is_zero_access(path: str) -> tuple[bool, bool]:
    """Return (is_zero_access, needs_exemption_check).

    needs_exemption is True only for the weak name-based signal
    (`credentials`/`secret` in the basename); all other matches are strong.
    """
    norm = expand(path)

    if EXTENSION_RE.search(norm):
        return True, False

    if DOTENV_RE.search(path) or ENVRC_RE.search(path):
        return True, False

    if ZERO_ACCESS_FILES_RE.search(path):
        return True, False

    if (
        SSH_KEY_RE.search(norm)
        or CRED_FILE_RE.search(norm)
        or DOCKER_CONFIG_RE.search(norm)
        or CRED_DIR_RE.search(norm)
    ):
        return True, False

    basename = os.path.basename(norm)
    if NAME_PATTERN_RE.search(basename):
        return True, True  # matched but needs package-dir exemption check

    return False, False


def should_block(path: str) -> bool:
    matched, needs_exemption = is_zero_access(path)
    if not matched:
        return False
    return not (needs_exemption and is_in_exempt_dir(path))


_AI_INSTRUCTIONS = """
---
AI INSTRUCTIONS:
You have been blocked from performing this operation. Do NOT attempt to find alternative commands, equivalent steps, or workarounds that achieve the same result through a different path.

Stop and report the following to the user immediately:
1. Your current task — what you were working on
2. Your intended step — what you were trying to do and why
3. What was blocked — the specific action blocked and the reason given above
4. How the user can help — describe exactly what command or steps the user could run manually to complete this on your behalf, and explain why they might or might not want to proceed"""


def block(path: str, tool: str) -> None:
    action = "Reading" if tool in ("Read", "Bash read") else "Accessing"
    sys.stderr.write(
        f"Blocked: {tool} targeting zero-access path '{path}'.\n"
        f"{action} this path would expose credentials, private keys, or "
        "authentication secrets to Claude's context. A prompt injection attack "
        "could trick Claude into forwarding this material to an attacker. "
        f"{_EXPOSURE_RISK}\n"
        f"{_AI_INSTRUCTIONS}\n"
    )
    sys.exit(2)


# ── Bash tokenisation ─────────────────────────────────────────────────────────
# Commands that read/transfer file contents. If one appears in a command
# segment, every token in that segment is checked (fail-safe: no operand/option
# modelling). cp/mv/scp/rsync/sftp are included so a secret used as a *source*
# operand (`cp ~/.ssh/id_rsa /tmp`, `scp ~/.aws/credentials host:`) blocks — not
# just secret destinations.
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

# ANSI-C quoting: `$'...'` — bash decodes the C escapes (`\056` -> '.'), so the
# literal filename regexes must see the decoded form, not the escape sequence.
_ANSI_C_RE = re.compile(r"\$'((?:[^'\\]|\\.)*)'")


def _decode_ansi_c(command: str) -> str:
    """Decode `$'...'` ANSI-C quoted spans to their literal characters.

    The decoded text is re-wrapped in single quotes (with embedded quotes
    escaped) so shlex still treats it as one token. Fail-safe: on any decode
    error the original span is left untouched.
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

    shlex with punctuation_chars keeps quoted operators inside their token
    (`grep 'a|b'` is one arg) and turns real operators into their own tokens,
    grouping consecutive punctuation (e.g. '(<'). Falls back to a permissive
    split on unbalanced quotes (fail-safe: still scan).
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
    """Yield strings from a token that could name a file, so attached option
    values are caught: the token itself, the part after `=` (`if=.env`), and the
    token with a leading option cluster stripped (`-f.env` -> `.env`)."""
    yield token
    if "=" in token:
        yield token.split("=", 1)[1]
    stripped = _LEADING_OPT_RE.sub("", token)
    if stripped and stripped != token:
        yield stripped


def expand_glob_candidates(token: str, cwd: str):
    """Yield the token and — if it contains glob metacharacters — every real
    filesystem path it expands to, exactly as the shell would before the command
    runs. This closes the `cat .en*` / `cat cred*.json` / `cp ~/.ssh/id_rs? x`
    class where a wildcard hides a sensitive literal from the regexes. Fail-safe:
    any expansion error yields just the literal token."""
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
    """Candidate read paths: input-redirection targets (any command) and every
    token of a segment that invokes a recognised read command."""
    targets: list[str] = []
    tokens = _lex_tokens(_decode_ansi_c(command))

    # Input redirection reads a file regardless of the command word, so a bare
    # `mapfile < .env`, `read < .env`, or `$(< .env)` is caught. The '<' may be
    # grouped with other punctuation (e.g. '(<'); exclude here-docs ('<<').
    for i, tok in enumerate(tokens):
        if _PUNCT_ONLY_RE.match(tok) and "<" in tok and "<<" not in tok:
            for nxt in tokens[i + 1 :]:
                if not _PUNCT_ONLY_RE.match(nxt):
                    targets.extend(_candidate_paths(nxt))
                    break

    # Command-gated scan: split into segments on separator punctuation; if a
    # segment invokes a read command, check every token in it.
    #
    # TODO(over-deny carve-out): checking EVERY token of a read segment includes
    # the command's search pattern, so `grep -r secret .` and `git grep
    # credentials` over-deny — the fuzzy `secret`/`credentials` NAME_PATTERN
    # matches the pattern argument, not a file. Current stance is to accept this
    # (fail-safe: over-deny beats a missed secret). If the over-deny becomes a
    # real blocker, add a targeted carve-out — WITHOUT reintroducing a getopt
    # model: split READ_CMDS into "dump" commands (cat/head/less/...) and
    # "search/filter" commands (grep/egrep/rg/ag/ack/sed/awk/gawk/jq/yq, plus
    # `git grep`), and for the search set check tokens with a strong-signals-only
    # predicate (skip the NAME_PATTERN weak match). Structured signals (.env,
    # SSH keys, .aws/, *.pem, credentials.json, ...) would still block in every
    # command, so real secret reads stay covered; only a bare secret *word* used
    # as a search pattern would be allowed.
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

    # Output redirections: > path, >> path, >| path (force-clobber), and the
    # combined stdout+stderr forms &> / &>> path. Excludes here-docs/strings
    # (<<, <<<) and stderr-only `2>`.
    for m in re.finditer(r"(?:(?<![<2&])>>?\|?|&>>?)\s*([^\s|&;><]+)", command):
        targets.append(m.group(1))

    # cp / mv / install — destination is the final non-option token
    for cmd in ("cp", "mv", "install"):
        for m in re.finditer(
            rf"\b{cmd}\b\s+((?:(?:-[^\s]+|--[^\s]+|\S+)\s+)+?)(\S+)\s*(?:$|[|&;])",
            command,
        ):
            targets.append(m.group(2))

    # tee: tee [options] <file> — skip any leading short/long option tokens
    for m in re.finditer(
        r"\btee\b(?:\s+-{1,2}[A-Za-z][\w=-]*)*\s+([^\s|&;]+)", command
    ):
        targets.append(m.group(1))

    # chmod / chown: <cmd> <mode-or-owner> <path>
    for cmd in ("chmod", "chown"):
        for m in re.finditer(rf"\b{cmd}\b\s+\S+\s+([^\s|&;]+)", command):
            targets.append(m.group(1))

    # dd of=path
    for m in re.finditer(r"(?<![\w/])of=([^\s|&;<>]+)", command):
        targets.append(_strip_quotes(m.group(1)))

    # truncate [-s N] <path> — destroys a file's contents
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
        sys.exit(
            0
        )  # fail-open: this hook handles mixed sensitive+read-only tools (Bash/Read/Write/Edit);
        # on parse failure the tool type is unknown, so fail-open per hook-interface spec

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "") or ""

    if tool_name not in ("Bash", "Read", "Write", "Edit", "apply_patch"):
        sys.exit(0)

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
        # ErrorHandlingByDamagePotential: this hook handles Read (read-only) in addition
        # to Bash/Write/Edit (sensitive), so fail-open on internal error per hook-interface spec.
        sys.exit(0)
