# Tasks: extend-read-tool-blocking

## block-sensitive-paths.py

- [x] Add `Read` branch to `main()`: extract `tool_input.get("file_path")` and call
  `should_block()`; exit 2 if matched
- [x] Add `"Read"` to the `tool_name not in (...)` early-exit guard
- [x] Change parse-failure exit code from `sys.exit(2)` to `sys.exit(0)` in the outer
  `except Exception` block (mixed-tool hook — fail-open per `hook-interface` spec)
- [x] Update module docstring to reflect Read tool coverage

## settings.json

- [x] Update the `block-sensitive-paths.py` PreToolUse matcher from `"Bash|Write|Edit"`
  to `"Bash|Read|Write|Edit"` in `~/.nixconfig/users/mithras/home-manager/claude-settings.json`
  (and the source file it is generated from, if different)

## block-secrets.py — ask message quality

- [x] Update credential-dir-prefix ask message to name the specific file and state the
  downstream risk (secret in context → usable in subsequent operations without
  further confirmation)
- [x] Update credential-file-name ask message with the same structure: specific file +
  specific danger

## Tests — block-sensitive-paths.py

- [x] Add pytest cases for `Read` + `~/.ssh/id_ed25519` → exit 2
- [x] Add pytest cases for `Read` + `~/.aws/credentials` → exit 2
- [x] Add pytest cases for `Read` + `.env` in project dir → exit 2
- [x] Add pytest cases for `Read` + `*.pem` file → exit 2
- [x] Add pytest cases for `Read` + `credentials.json` outside package dir → exit 2
- [x] Add pytest cases for `Read` + `credentials.py` inside `.venv/` → exit 0
- [x] Add pytest case for malformed JSON input → exit 0 (parse-failure behaviour change)

## Tests — block-secrets.py

- [x] Add or update pytest cases asserting that ask messages for credential-dir and
  credential-name paths include both the filename and the downstream risk description
