#!/bin/sh
# Set up a throwaway workspace that shows whether VS Code gives the model the text a session-start hook returns.
# The workspace holds its own hook file (.github/hooks/probe.json); no VS Code setting is changed.
# Two SessionStart hooks each give the model one word a different way: hook D in the `additionalContext`
# field of a JSON reply, hook E as plain standard output.
# Usage: sh vscode-context-probe.sh
set -eu

work=$(mktemp -d "${TMPDIR:-/tmp}/vscode-context-probe.XXXXXX")
hooks="${work}/workspace/.github/hooks"
mkdir -p "${hooks}"

cat > "${hooks}/probe.json" << EOF
{"hooks": {"SessionStart": [
  {"type": "command", "command": "sh '${work}/d.sh'"},
  {"type": "command", "command": "sh '${work}/e.sh'"}
]}}
EOF
cat > "${work}/d.sh" << 'EOF'
#!/bin/sh
printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "A hook gives you this probe word: marmalade."}}'
exit 0
EOF
cat > "${work}/e.sh" << 'EOF'
#!/bin/sh
echo 'A hook gives you this probe word: tangerine.'
exit 0
EOF

cat << EOF
The workspace is ready: ${work}/workspace

1. Open it:    code '${work}/workspace'
    Trust the folder when VS Code asks.
2. Open Chat, choose the agent, start a NEW chat, and send this prompt:

    This is a test of hook context. Were you given any probe words by a hook? Answer with only the probe words you were given, or the word none. Do not use any tool.

3. Tell me the model's answer.
    marmalade means the additionalContext field reached it; tangerine means plain output did.
EOF
