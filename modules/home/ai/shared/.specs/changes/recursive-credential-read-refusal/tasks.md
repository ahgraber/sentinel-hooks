# Tasks: recursive-credential-read-refusal

## Before starting

- [ ] Confirm `security-posture-alignment` is synced, so the baseline holds its `BashReadBestEffort`, its `BlockAIGuidance`, and its `cd` tracking in `shell_words`.
- [ ] Confirm `shell_words` reports every directory a segment may run in, including after `cd X ||` and after a subshell; if it reports one directory, add the candidates there first, with lexer tests.

## Recursive-reader table

- [ ] Extend `_operands` in `bash_commands.py` to drop the value of an option that takes one, given separately or attached, and to stop option parsing at `--`; add a test per form to `test_tamper_gate.py`'s operand cases, since the tamper hook reads the same helper.
- [ ] Add `_RECURSIVE_READERS` to `bash_commands.py` with the rows in `design.md` `ARecursiveReaderTableBesideTheOperandTable`, and `recursive_roots(segment, directory)` returning the roots of a recursive form or nothing.
- [ ] Add `tests/test_recursive_roots.py`: one case per row and per recursive flag spelling (short, long, clustered, repeated), with a pattern given positionally and by `-e` or `-f`, with no root, with `--`, with `tar -C` and bundled `tar cf`, with `cp -t` and `--target-directory`, and with `sudo` and `doas` in front.
- [ ] Add cases to `tests/test_recursive_roots.py` showing that a name-listing mode (`rg --files`, `rg --type-list`, `ag -g`, `ag --list-file-types`) returns no roots, and that `rg -l` and `grep -rl` do.
- [ ] Add a case to `tests/test_recursive_roots.py` showing that `find` returns roots only when `-exec`, `-execdir`, `-ok`, or `-okdir` runs a program in `READ_CMDS`.

## Search retry form

- [ ] Add `Instruction.SEARCH` and its text to `hook_response.py`, built from the shared four reporting points, with the wording in `hook-interface` `BlockAIGuidance`.
- [ ] Add tests to `test_hook_response.py`: the search form carries the `---` delimiter, the `AI INSTRUCTIONS:` header, the quoted `"Protected file"` label, the narrower-root instruction, the exclude-flag statement, the prohibition on another route and on retrying another layer's denial, and the four reporting points byte-identical to the stop and retry forms.
- [ ] Add a test to `test_hook_response.py` that an `Ask` sent to Pi with `Instruction.SEARCH` carries the search text in its reason, as `AskAnAdapterMayRefuse` requires of every form.

## Refusal in the read hook

- [ ] In `block-sensitive-paths.py`, after the word checks, judge each segment's `recursive_roots` in every directory it may run in, against every block-class declaration, comparing every spelling of the root with every spelling of the declaration through `guarded_paths.spellings`.
- [ ] Refuse a match with the block decision, a message that names the declaration under `Protected file:` and states that reading or copying it could expose credentials, and `Instruction.SEARCH`.
- [ ] Keep a word that names a block-class location on the stop form; add a test to `test_sensitive_path_cases.py` that `cat ~/.codex/auth.json` still carries the stop form.

## Verdict evidence

- [ ] Add `bash_cases` to `sensitive-path-cases.json` for each scenario of `RecursiveReadAboveADeclaredCredential`, so the Python suite and Pi's runner in `pi/tests/registration.test.mjs` judge the same table: an ancestor, the credential's own directory, a root holding none, a declaration with no file, `rg foo ~`, `rg -g '**' foo ~`, `rg --files ~`, a root after `cd`, a root after `cd /absent ||`, no root, an exclude flag, `cp -r`, and `tar -czf`.
- [ ] Add `bash_cases` for the non-recursive top-level forms: `grep x ~/*` allowed and `grep x ~/.*` refused.
- [ ] Add a `RecursiveReadOfANameRuleSecret` case: `grep -r x .` in a directory holding only a `.env` file is not refused by the hooks.
- [ ] Add a test to `test_sensitive_path_cases.py` for a declaration whose parent directory is a link: a recursive read of the link's target is refused.
- [ ] Add a test for a root spelled in another letter case, skipped where the test volume is case-sensitive.
- [ ] Add a test through `tests/hook_chain.py` that the refusal is a block, not an ask, for Claude, Codex, Copilot, Pi, and an unknown agent.
- [ ] Add a test that `block-sensitive-paths.py` refuses with the search form, not the stop form, and that the refusal names the declaration.

## Read property

- [ ] Add recursive forms to `COMMANDS` in `test_credential_read_properties.py`: `grep -R`, `grep --recursive`, `rg`, `rg -g '**'`, `ag`, `find -exec` with a reader outside `READ_CMDS`, and copy and archive forms that read their own result in the same command (`cp -r {d} out && cat out/*`, `tar -cf - {d} | tar -xOf -`, `rsync -a {d}/ out/ && cat out/*`).
- [ ] Describe the catalog in the module docstring as sampled coverage of the table, not proof that the table is complete.
- [ ] Run the read property and the cross-agent ordering property; record the result here.

## Specs and checks

- [ ] Run `nix build .#checks.<system>.shared-hook-tests` and `.#checks.<system>.pi-hook-tests`.
- [ ] Run `sdd-verify` for this change.
