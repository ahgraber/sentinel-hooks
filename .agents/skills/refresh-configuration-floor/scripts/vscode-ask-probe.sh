#!/bin/sh
# Set up a throwaway workspace that shows, for each VS Code approval setting, whether a hook's `ask`
# reaches the user, and which kind of session-start hook output VS Code shows.
# The workspace holds its own hook file (.github/hooks/probe.json); no VS Code setting is changed.
# The PreToolUse hook answers `ask`, in Sentinel's output shape, to a call that names a notes-*.txt file,
# and allows every other call. Two SessionStart hooks each send one marked line a different way.
# Usage: sh vscode-ask-probe.sh          set up the workspace and print the steps
#        sh vscode-ask-probe.sh <dir>    print the results for the workspace made earlier
set -eu

if [ $# -eq 1 ]; then
  work=$1
  echo "=== files created (a file listed here was created although the hook asked):"
  find "${work}/workspace" -maxdepth 1 -name "notes-*" -exec basename {} ';'
  echo "=== hook calls that answered ask, in order:"
  for f in "${work}"/hook-calls/answer-*.txt; do
    if [ -e "${f}" ]; then cat "${f}"; fi
  done
  echo "=== session-start hooks that ran:"
  find "${work}/hook-calls" -name "start-*" -exec basename {} ';'
  exit 0
fi

work=$(mktemp -d "${TMPDIR:-/tmp}/vscode-ask-probe.XXXXXX")
out="${work}/hook-calls"
hooks="${work}/workspace/.github/hooks"
mkdir -p "${out}" "${hooks}"

cat > "${hooks}/probe.json" << EOF
{"hooks": {
  "PreToolUse": [{"type": "command", "command": "sh '${work}/ask.sh'"}],
  "SessionStart": [
    {"type": "command", "command": "sh '${work}/start-stderr.sh'"},
    {"type": "command", "command": "sh '${work}/start-message.sh'"}
  ]
}}
EOF
cat > "${work}/ask.sh" << EOF
#!/bin/sh
input=\$(cat)
printf '%s\n' "\${input}" >"${out}/call-\$\$.json"
case "\${input}" in
  *notes-*.txt*)
    printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "Probe: the hook asks about a notes file."}}'
    printf '%s\n' "\${input}" | grep -o -E 'notes-[a-z]+\.txt' | head -1 >"${out}/answer-\$\$.txt"
    ;;
esac
exit 0
EOF
cat > "${work}/start-stderr.sh" << EOF
#!/bin/sh
echo ran >"${out}/start-stderr-\$\$.txt"
echo 'PROBE-A: a line on standard error, exit 0' >&2
exit 0
EOF
cat > "${work}/start-message.sh" << EOF
#!/bin/sh
echo ran >"${out}/start-message-\$\$.txt"
printf '%s\n' '{"systemMessage": "PROBE-B: a systemMessage field"}'
exit 0
EOF

cat << EOF
The workspace is ready: ${work}/workspace

1. Open it:    code '${work}/workspace'
    Trust the folder when VS Code asks. Hooks run only in a trusted workspace.
2. Open Chat and choose the agent. When the chat session starts, note whether you can see
    PROBE-A, PROBE-B, both, or neither.
3. Do one run for each approval setting below. Start a NEW chat for each run, choose the setting
    in the chat input's pickers, and send the prompt on that line.
    If VS Code shows a confirmation that carries "Probe: the hook asks about a notes file",
    note that it appeared and choose Skip or Deny.

    manual approvals (the default):
      Create the file notes-manual.txt containing the word hello, with your file-creation tool. One attempt, no terminal.
    assisted approvals:
      Create the file notes-assisted.txt containing the word hello, with your file-creation tool. One attempt, no terminal.
    allow all (bypass approvals):
      Create the file notes-allowall.txt containing the word hello, with your file-creation tool. One attempt, no terminal.
    autopilot mode:
      Create the file notes-autopilot.txt containing the word hello, with your file-creation tool. One attempt, no terminal.

    A setting your VS Code does not offer can be skipped; say which.
4. Print the results:    sh '$0' '${work}'
EOF
