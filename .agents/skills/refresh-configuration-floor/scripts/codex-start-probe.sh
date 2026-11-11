#!/bin/sh
# Find out which kind of session-start hook output Codex shows the user.
# A throwaway project carries its own hook file (.codex/hooks.json) with three SessionStart hooks;
# each sends one marked line a different way. Your Codex home is not changed.
# Usage: sh codex-start-probe.sh          set up the project and print the steps
#        sh codex-start-probe.sh <dir>    print which hooks ran in the project made earlier
set -eu

if [ $# -eq 1 ]; then
  echo "=== session-start hooks that ran:"
  ls "$1/workspace/hook-calls"
  exit 0
fi

work=$(mktemp -d "${TMPDIR:-/tmp}/codex-start-probe.XXXXXX")
# The record is inside the project, where a sandboxed hook can still write.
out="${work}/workspace/hook-calls"
mkdir -p "${out}" "${work}/workspace/.codex"

cat > "${work}/workspace/.codex/hooks.json" << EOF
{"hooks": {"SessionStart": [{"matcher": "startup|resume|compact|clear", "hooks": [
  {"type": "command", "command": "sh '${work}/a.sh'", "timeout": 10},
  {"type": "command", "command": "sh '${work}/b.sh'", "timeout": 10},
  {"type": "command", "command": "sh '${work}/c.sh'", "timeout": 10}
]}]}}
EOF
cat > "${work}/a.sh" << EOF
#!/bin/sh
echo ran >"${out}/a-\$\$.txt"
echo 'PROBE-A: a line on standard error, exit 0' >&2
exit 0
EOF
cat > "${work}/b.sh" << EOF
#!/bin/sh
echo ran >"${out}/b-\$\$.txt"
printf '%s\n' '{"systemMessage": "PROBE-B: a systemMessage field"}'
exit 0
EOF
cat > "${work}/c.sh" << EOF
#!/bin/sh
echo ran >"${out}/c-\$\$.txt"
echo 'PROBE-C: a line on standard error, exit 1' >&2
exit 1
EOF

cat << EOF
The project is ready: ${work}/workspace

1. Start Codex there:    cd '${work}/workspace' && codex
    Trust the folder when Codex asks.
2. Codex runs a project's hooks only after you trust them. If it does not ask, type /hooks,
    trust the three hooks from this project, then quit and start Codex in the folder again.
3. When the session opens, note which of PROBE-A, PROBE-B, and PROBE-C you can see, and where.
    Then quit Codex.
4. Print which hooks ran:    sh '$0' '${work}'
EOF
