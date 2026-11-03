#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Block reads and writes that reach zero-access paths.

This PreToolUse hook covers Read, Write, Edit, Bash, and Codex `apply_patch`.
Bash parsing is conservative and can block benign commands. It does not evaluate
shell code, dynamic commands, or nested command strings. Path checks follow
symlink chains.
Codex native read tools emit no PreToolUse and are not covered.
"""

import json
import os
import re
import sys
from typing import NoReturn

import apply_patch
import bash_commands
from guarded_paths import (
    NAME_HEURISTIC_EXEMPT_RE,
    TOOL_VOCABULARY,
    GuardedLocations,
    ManifestError,
    PathPolicy,
    load_manifest,
    spellings,
)
from hook_response import Decision, invoking_agent, respond, supports_ask
import shell_words

SENSITIVE_PATH_TOOLS = TOOL_VOCABULARY.group("sensitive-path")
MUTATING_TOOLS = TOOL_VOCABULARY.group("mutating")
FILE_TOOLS = TOOL_VOCABULARY.group("file")

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

SSH_KEY_RE = re.compile(r"(?:^|[/\\])id_(?:rsa|dsa|ecdsa|ed25519)[^/\\]*$", re.IGNORECASE)

CRED_FILE_RE = re.compile(
    r"(?:^|[/\\])(?:\.netrc|\.npmrc|\.pypirc|\.git-credentials"
    r"|service-account[^/\\]*\.json|credentials\.json)$",
    re.IGNORECASE,
)
DOCKER_CONFIG_RE = re.compile(r"(?:^|[/\\])\.docker[/\\]config\.json$", re.IGNORECASE)


# Credential paths come from the manifest. This hook blocks reads;
# block-hook-tampering blocks writes.
def _credential_alternation(paths) -> str:
    """Build the regex alternation matching any credential path's relative form."""
    parts = []
    for path in paths:
        relative = path.removeprefix("~/")
        parts.append(re.escape(relative).replace(r"\*", r"[^/\\]*").replace("/", r"[/\\]"))
    return "|".join(parts)


def _require_str_list(block_paths: object) -> list:
    """Return `block_paths` unchanged, or raise if it is not a list of strings."""
    if not isinstance(block_paths, list) or any(not isinstance(path, str) for path in block_paths):
        raise ManifestError("block paths must be a list of strings")
    return block_paths


_CREDENTIAL_PATHS = ()
try:
    _MANIFEST = load_manifest()
    block_paths = _require_str_list(_MANIFEST["block"]["paths"])
    _CREDENTIAL_PATHS = tuple(block_paths)
    POLICY = PathPolicy(_MANIFEST)
    MANIFEST_ERROR = None
except Exception as _exc:  # noqa: BLE001 -- preserve independent checks and report construction failures
    POLICY = None
    _MANIFEST = {}
    MANIFEST_ERROR = str(_exc)

AGENT_CREDENTIAL_RE = re.compile(
    # `(?!)` matches nothing; `main()` reports the manifest failure.
    rf"(?:^|[/\\])(?:{_credential_alternation(_CREDENTIAL_PATHS)})[^/\\]*$" if _CREDENTIAL_PATHS else r"(?!)",
    re.IGNORECASE,
)

CRED_DIR_RE = re.compile(r"(?:^|[/\\])\.(?:ssh|aws|kube|gnupg|azure)(?:[/\\]|$)", re.IGNORECASE)


# Apply exceptions only to the spelling that triggered the name heuristic; a
# link must not borrow its target's exception.
NAME_HEURISTIC_EXCEPTIONS = GuardedLocations(
    exception["pattern"]
    for exception in _MANIFEST.get("exceptions", ())
    if exception.get("surface") == "sensitive-path-name-heuristic"
)

DOTENV_PLACEHOLDERS = frozenset(
    exception["pattern"].lower()
    for exception in _MANIFEST.get("exceptions", ())
    if exception.get("surface") == "sensitive-path-dotenv-placeholder"
)

ZERO_ACCESS_FILES_RE = re.compile(
    r"(?:^|[/\\])\.(?:bash_history|zsh_history|sh_history|node_repl_history|python_history)$",
    re.IGNORECASE,
)

# The only class subject to the package-directory exemption.
NAME_PATTERN_RE = re.compile(r"credentials|secret", re.IGNORECASE)


def _dotenv_refuses(path: str, reading: bool) -> bool:
    """Apply the dotenv rule; a declared placeholder name escapes it only on a read."""
    if not DOTENV_RE.search(path):
        return False
    return not (reading and os.path.basename(path).lower() in DOTENV_PLACEHOLDERS)


def is_zero_access(path: str, *, reading: bool = False) -> bool:
    """Return True if one spelling of a path matches a strong zero-access signal."""
    return bool(
        EXTENSION_RE.search(path)
        or _dotenv_refuses(path, reading)
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
        and not NAME_HEURISTIC_EXCEPTIONS.matches_hop(path)
    )


# Names that suggest a credential without proving one: the file tools ask rather than refuse.
SUGGESTIVE_NAME_RE = re.compile(r"token|password|passwd|api[_-]?key|auth_key|credential", re.IGNORECASE)
SUGGESTIVE_EXTENSION_RE = re.compile(r"\.(?:keystore|jks)$", re.IGNORECASE)
# An OAuth credential store asked about even inside a package directory, where the
# name heuristic's exemption lets it through; `credentials.json` itself is refused.
STRONG_CRED_FILE_RE = re.compile(r"(?:^|[/\\])\.credentials\.json$", re.IGNORECASE)


def _candidates(path: str, cwd: str | None) -> list[str]:
    """Return the spellings `should_block` judges for `path`."""
    if not os.path.isabs(path) and not path.startswith("~"):
        if cwd is None:
            return [path]
        path = os.path.join(cwd, path)
    return list(spellings(path))


def ask_reason(path: str, cwd: str | None = None) -> str | None:
    """Return why a file tool should ask before touching `path`, or `None`.

    The name heuristic's exemptions and declared exceptions excuse a suggestive
    name here as they excuse a refused one, so a declaration holds for every rule.
    """
    for candidate in _candidates(path, cwd):
        if STRONG_CRED_FILE_RE.search(candidate):
            return f"This operation targets '{path}', a credential store file with OAuth tokens."
        suggestive = SUGGESTIVE_NAME_RE.search(os.path.basename(candidate)) or SUGGESTIVE_EXTENSION_RE.search(
            candidate
        )
        if (
            suggestive
            and not NAME_HEURISTIC_EXEMPT_RE.search(candidate)
            and not NAME_HEURISTIC_EXCEPTIONS.matches_hop(candidate)
        ):
            return f"This operation targets '{path}', whose name suggests credentials, tokens, or key material."
    return None


def ask(path: str, tool: str, reason: str) -> NoReturn:
    """Ask before a file tool touches a suggestively named file; refuse where no prompt exists."""
    agent = _CALL["agent"]
    exposure = f" Exposing it to the agent could let prompt injection send it to an attacker. {_EXPOSURE_RISK}"
    if supports_ask(agent, tool):
        respond(
            Decision.ASK,
            reason + exposure + " Approve only if you intentionally want the agent to access this material.",
            agent=agent,
            tool_name=tool,
        )
    respond(
        Decision.BLOCK,
        "Blocked: this agent cannot show a confirmation prompt for this action.\n"
        + reason
        + exposure
        + " If this access is intentional, the user can perform it outside the agent session.",
        agent=agent,
    )


def should_block(path: str, cwd: str | None = None, *, reading: bool = False) -> bool:
    """Return whether any spelling of `path` reaches a zero-access location.

    Apply heuristics and exemptions to the same spelling. A caller that does
    not state `reading` gets the write verdict.
    """
    if POLICY and POLICY.verdict(path, "read", cwd=cwd) == "block":
        return True
    if not os.path.isabs(path) and not path.startswith("~"):
        if cwd is None:
            return is_zero_access(path, reading=reading) or is_named_for_secrets(path)
        path = os.path.join(cwd, path)
    return any(
        is_zero_access(candidate, reading=reading) or is_named_for_secrets(candidate) for candidate in spellings(path)
    )


def _manifest_warning() -> str:
    return (
        "block-sensitive-paths could not load guarded-paths.toml "
        f"({MANIFEST_ERROR}); the full declared policy could not be checked; "
        "available block declarations and strong rules still apply."
    )


def block(path: str, tool: str) -> NoReturn:
    """Respond with a block decision for a zero-access path."""
    action = "Reading" if tool in ("Read", "Bash read") else "Accessing"
    respond(
        Decision.BLOCK,
        f"Blocked: {tool} targeting zero-access path '{path}'.\n"
        f"{action} it could expose credentials or private keys to the agent, where "
        "a later tool call could disclose or use them."
        + (f"\n{_manifest_warning()}" if MANIFEST_ERROR is not None else "")
        + ("\n" + "\n".join(POLICY.findings) if POLICY and POLICY.findings else ""),
    )


def block_placeholder_form(path: str, command: str, cwd: str | None) -> NoReturn:
    """Refuse a placeholder read for its command's form, naming the reads that would proceed."""
    syntax = bash_commands.read(command, cwd).stopping_syntax()
    offers = bash_commands.offers_accepted_forms(syntax)
    respond(
        Decision.BLOCK,
        f"Blocked: Bash read of '{path}', a placeholder dotenv file. "
        "A placeholder is readable by a command that only reads its arguments; writing to it is refused. "
        f"Recognition stopped at {syntax}."
        + (bash_commands.read_forms() if offers else "")
        + (bash_commands.ABSOLUTE_PATH_HINT if bash_commands.asks_for_absolute_paths(syntax) else ""),
        instruction=bash_commands.refusal_instruction(syntax),
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


def _word_candidates(word):
    yield word.value
    yield from word.paths
    if "=" in word.value:
        yield word.value.split("=", 1)[1]
    if word.kind == "option" and not word.value.startswith("--"):
        # Which letters of `-fvalue` are flags depends on the program, so every
        # suffix may be the attached value.
        for start in range(2, len(word.value)):
            yield word.value[start:]


def _input_redirect(word) -> bool:
    return bool(word.redirection and "<" in word.redirection and "<<" not in word.redirection)


def _reads(segment) -> bool:
    """Return whether a segment runs a reading program or reads a redirected file."""
    return any(os.path.basename(word.value) in READ_CMDS or _input_redirect(word) for word in segment)


def _may_name_a_file(word, segment, reads: bool) -> bool:
    """Return whether the name heuristic applies to `word`.

    It applies to a word that denotes a file. An unresolvable word in a reading
    segment may denote one when it is written as a path, when the shell builds
    it from an expansion, when the segment's directory is unknown, or when it
    names an entry in a directory the segment may run in; a search pattern
    after a `cd` names none.
    """
    if word.kind in {"path candidate", "redirection target"}:
        return True
    if word.kind != "unresolvable" or not reads:
        return False
    if "/" in word.value or word.value.startswith("~"):
        return True
    if segment.directories is None or any(char in word.value for char in "$`{*?["):
        return True
    return any(os.path.isabs(path) and os.path.lexists(path) for path in word.paths)


def _read_words(segment):
    # A loop header's values reach its body through the loop variable, where any program may read them.
    reads = segment.loop_header or any(os.path.basename(word.value) in READ_CMDS for word in segment)
    for word in segment:
        # A here-document body a data reader takes is input, not a name.
        if word.kind != "here-document" and (reads or _input_redirect(word) or word.kind == "unresolvable"):
            yield word


def _write_words(segment):
    for word in segment:
        if bash_commands.redirect_writes(word) or word.value.startswith("of="):
            yield word
    words = [word for word in segment if word.kind not in {"option", "redirection target", "here-document"}]
    if not words:
        return
    name = os.path.basename(words[0].value)
    if name in {"cp", "mv", "install"} and len(words) > 2:
        yield words[-1]
    elif name in {"tee", "truncate"}:
        yield from words[1:]
    elif name in {"chmod", "chown"}:
        yield from words[2:]


def bash_blocked_target(command: str, cwd: str | None = None) -> str | None:
    """Return the path a Bash command is refused for, or None."""
    refusal = _bash_refusal(command, cwd)
    return None if refusal is None else refusal[0]


def _bash_refusal(command: str, cwd: str | None) -> tuple[str, bool] | None:
    """Return the refused path, and whether a recognized read of it would have proceeded.

    A refusal another rule makes wins over one the command's form alone causes,
    whatever order the words come in, so its stop instruction is the one given.
    """
    segments = shell_words.lex(command, cwd)
    if segments is None or bash_commands.unread_here_document(segments):
        # No shell reading exists for this command, which holds syntax the
        # lexer refuses or a here-document a program may act on. Judge every
        # path spelling in the text, the body included, by the strong rules
        # and the declared block paths. Whether a spelling is read, written,
        # or only mentioned is unknown, so a placeholder gets the write
        # verdict. The tamper hook gates unresolved guarded text.
        for spelling in shell_words.unlexable_text_paths(command, cwd):
            if is_zero_access(spelling) or (POLICY and POLICY.verdict(spelling, "read", cwd=cwd) == "block"):
                return spelling, False
        return None
    form_only = None
    for segment in segments:
        reads = _reads(segment)
        # A placeholder is excused only where the utility cannot write what it names.
        only_reads = bash_commands.read_only(segment)
        for word in _write_words(segment):
            for path in _word_candidates(word):
                if should_block(path, cwd):
                    return path, False
        for word in _read_words(segment):
            for path in _word_candidates(word):
                resolved = path
                if cwd and not os.path.isabs(path) and not path.startswith("~"):
                    resolved = os.path.join(cwd, path)
                if POLICY and POLICY.verdict(path, "read", cwd=cwd) == "block":
                    return path, False
                forms = spellings(resolved)
                named = _may_name_a_file(word, segment, reads) and any(is_named_for_secrets(form) for form in forms)
                if any(is_zero_access(form, reading=only_reads) for form in forms):
                    if named or any(is_zero_access(form, reading=True) for form in forms):
                        return path, False
                    form_only = form_only or (path, True)
                elif named:
                    return path, False
    return form_only


_CALL = {"tool_name": "", "agent": None}


def internal_error(exc: BaseException) -> NoReturn:
    """Warn for a read or an unnamed tool; ask, or block where no prompt exists, for a mutation."""
    # Reuse parsed state because recomputing the agent can repeat the failure.
    agent, tool_name = _CALL["agent"], _CALL["tool_name"]
    fault = f"{type(exc).__name__}: {exc}"
    if tool_name not in MUTATING_TOOLS:
        respond(
            Decision.WARN,
            f"block-sensitive-paths failed ({fault}). This call will proceed unchecked.",
            agent=agent,
        )
    if supports_ask(agent, tool_name):
        respond(
            Decision.ASK,
            f"block-sensitive-paths failed while checking this {tool_name} call ({fault}). "
            "It cannot determine whether the call reaches a credential. Approve only after "
            "verifying that it does not, and report the hook failure.",
            agent=agent,
            tool_name=tool_name,
        )
    respond(
        Decision.BLOCK,
        f"Blocked: block-sensitive-paths failed while checking this {tool_name} call ({fault}) "
        "and cannot determine whether it reaches a credential. This agent cannot ask for "
        "the required approval.",
        agent=agent,
    )


def main() -> None:
    """Read the hook payload from stdin and respond to the tool call."""
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        # A payload that does not parse names no tool, so the read-only direction applies.
        respond(Decision.WARN, "block-sensitive-paths could not parse the hook payload; this call was not checked.")

    tool_name = data.get("tool_name", "")
    _CALL["tool_name"] = tool_name
    _CALL["agent"] = invoking_agent(payload=data)
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "") or ""

    if tool_name not in SENSITIVE_PATH_TOOLS:
        sys.exit(0)

    if tool_name in FILE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("path", "")
        if path and should_block(path, cwd or None, reading=tool_name == "Read"):
            block(path, tool_name)
        if path and (reason := ask_reason(path, cwd or None)):
            ask(path, tool_name, reason)

    elif tool_name == "apply_patch":
        command = tool_input.get("command", "")
        targets = apply_patch.targets(command)
        for target in targets:
            if should_block(target, cwd or None):
                block(target, "apply_patch")
        for target in targets:
            if reason := ask_reason(target, cwd or None):
                ask(target, "apply_patch", reason)

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        refusal = _bash_refusal(command, cwd or None)
        if refusal is not None:
            target, form_only = refusal
            if form_only:
                block_placeholder_form(target, command, cwd or None)
            block(target, "Bash read")

    if MANIFEST_ERROR is not None:
        respond(Decision.WARN, _manifest_warning(), agent=invoking_agent(payload=data))
    if POLICY and POLICY.findings:
        respond(
            Decision.WARN,
            "\n".join(POLICY.findings),
            agent=invoking_agent(payload=data),
        )
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        internal_error(exc)
