#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Extract the shell inputs from mvdan/sh's parser tests into a corpus bash checks.

Usage: extract_mvdan_sh.py <path to mvdan/sh syntax/filetests_test.go> <version>

Fetch the source with `go mod download -json mvdan.cc/sh/v3@<version>` and pass
`<Dir>/syntax/filetests_test.go`. Each `fileTest(` names inputs mvdan/sh parses
to one program. Only inputs bash accepts are kept, and a group is marked as one
program only where bash starts the same programs with the same words for each
input; mvdan/sh's grouping is a hint, and bash decides.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from shellprobe import ShellProbe  # noqa: E402

# Inputs that could act outside the probe's directory or on other processes.
UNSAFE = re.compile(r"\b(kill|exec|suspend|ulimit|enable|trap|disown|coproc|reboot|shutdown)\b|/dev/(tcp|udp)")


def go_string_lists(source: str) -> list[list[str]]:
    """Return the string literals of the `[]string{...}` that opens each `fileTest(` call."""
    groups = []
    for match in re.finditer(r"fileTest\(\s*\[\]string\{", source):
        index, parts, current = match.end(), [], None
        while index < len(source):
            char = source[index]
            if char in " \t\n,":
                index += 1
            elif source.startswith("//", index):
                index = source.index("\n", index)
            elif char == "+":
                index += 1
                current = parts.pop() if parts else ""
            elif char in '"`':
                end = index + 1
                while source[end] != char:
                    end += 2 if char == '"' and source[end] == "\\" else 1
                literal = source[index : end + 1]
                value = literal[1:-1] if char == "`" else ast.literal_eval(literal)
                parts.append((current or "") + value)
                current = None
                index = end + 1
            elif char == "}":
                groups.append(parts)
                break
            else:
                break
    return groups


def bash_accepts(bash: str, text: str) -> bool:
    """Whether bash parses `text` without an error."""
    result = subprocess.run([bash, "-n"], input=text, capture_output=True, text=True, check=False, timeout=5)
    errors = [line for line in result.stderr.splitlines() if line.strip() and "warning:" not in line]
    return result.returncode == 0 and not errors


def main() -> None:
    source, version = Path(sys.argv[1]).read_text(), sys.argv[2]
    probe = ShellProbe(Path(tempfile.mkdtemp()), set(), record_missing=True)
    groups = []
    for inputs in go_string_lists(source):
        kept = sorted(
            {
                text
                for text in inputs
                if not {"\r", "\x00"} & set(text) and not UNSAFE.search(text) and bash_accepts(probe.bash, text)
            }
        )
        if not kept:
            continue
        runs = {json.dumps(sorted(invocation.words for invocation in probe.run(text, timeout=2))) for text in kept}
        groups.append({"inputs": kept, "one_program": len(runs) == 1})
    corpus = {
        "source": f"mvdan.cc/sh/v3@{version} syntax/filetests_test.go",
        "license": "mvdan-sh-LICENSE",
        "groups": groups,
    }
    (HERE / "mvdan-sh-inputs.json").write_text(json.dumps(corpus, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(groups)} groups, {sum(len(g['inputs']) for g in groups)} inputs")


if __name__ == "__main__":
    main()
