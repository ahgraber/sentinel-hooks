/** Command rules ported from bash-command-validator.sh. */

export const BASH_VALIDATOR_RULES: Array<[RegExp, string]> = [
  [
    /(?<!<)<<[^<]/,
    "Heredoc bodies are blocked because zsh BANG_HIST can silently mangle '!' (e.g. '!=', '!word', shebangs) before Bash receives the command. Rewrite the body without '!', or write it to $TMPDIR/script.sh or $TMPDIR/script.py and run that file.",
  ],
  [
    /"[^"]*![^" \t][^"]*"/,
    "'!' inside a double-quoted string is expanded by zsh BANG_HIST (e.g. \"val!=x\" mangles silently). Use single quotes if no variable expansion is needed. If $vars are required, write the content to $TMPDIR and run from a file.",
  ],
  [
    /(^|[\s;|&(])![^=\s"]/,
    "An unquoted '!word' is expanded by zsh BANG_HIST as a history reference. Single-quote the argument containing '!' to prevent expansion, or restructure to avoid '!'.",
  ],
  [
    /(^|\s)\.#[a-zA-Z0-9_-]/,
    "'.#target' — '#' is a zsh EXTENDED_GLOB repetition operator, causing 'no matches found'. Quote nix flake refs: nix build '.#target' --impure",
  ],
  [
    /\b[0-9a-f]{6,40}\^/,
    "'^' after a git commit hash is a zsh EXTENDED_GLOB negation operator. Quote it: 'abc123^' or 'abc123^..HEAD', or use '~1' instead of '^'",
  ],
  [
    /--[a-zA-Z_-]+=\*/,
    "The '*' in '--flag=*.ext' is expanded by zsh glob before reaching the command. Quote the value: --include='*.py'",
  ],
  [
    /\/nix\/store\/\*/,
    "Globbing /nix/store/* is unreliable — store paths are non-deterministic hashes. Use 'rg --files /nix/store | rg pattern' or an explicit known path.",
  ],
  [
    /\brg\b[^|]*\s-[a-zA-Z]*r[a-zA-Z]*(?:=\S*)?(?:\s|$)/,
    "rg is recursive by default — '-r' means '--replace' (substitution), not '--recursive'. 'rg -rn' replaces matches with literal 'n' and silently corrupts output. Drop the '-r': use 'rg -n' for line numbers, 'rg -l' for filenames.",
  ],
  [
    /(?:^|[;|&()]{1,2})\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S+)\s+)*(?:[./][\w./]*\/)?(?:python|python3)(?:[0-9.]+)?\s/,
    "Use 'uv run' instead of invoking python/python3 directly. For scripts with dependencies, use uv inline script metadata (# /// script) and run with 'uv run script.py'",
  ],
  [
    /(?<!\w)(?<!uv )pip\s+(install|uninstall|download)\b/,
    "Use 'uv add' or 'uv run --with <pkg>' instead of pip. For one-off scripts, declare dependencies inline with uv script metadata (# /// script)",
  ],
  [
    /(?<!\w)pip3\s+(install|uninstall|download)\b/,
    "Use 'uv add' or 'uv run --with <pkg>' instead of pip3. For one-off scripts, declare dependencies inline with uv script metadata (# /// script)",
  ],
  [/^(?!.*\buv\s+run\b).*\bpy(?:test|\.test)\b/, "Use 'uv run pytest' instead of invoking pytest/py.test directly"],
  [
    /\bpre-commit\s+run\b/,
    "Use 'prek run' instead of 'pre-commit run' — prek is the sandbox-compatible wrapper available in PATH",
  ],
  [
    /(?:^|[;\n|&()]{1,2})\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S+)\s+)*(?:command\s+)?git(?:\s+(?:(?:-[cC])\s+\S+|-[pP]|--\S+))*\s+commit\b/,
    "Use 'git agent-commit' alias instead of 'git commit' — the alias signs with the dedicated agent key",
  ],
  [
    // The separator class omits '|' on purpose; see bash-command-validator.sh.
    /(?:^|[;\n&()]{1,2})\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S+)\s+)*(?:command\s+)?git(?:\s+(?:-[pP]|--\S+))*\s+-C\b/,
    "Use 'cd <path>' in its own Bash call, then the plain subcommand ('git status --short', 'git --no-pager diff'), instead of 'git -C <path>' — the plain form runs without an approval prompt",
  ],
]
