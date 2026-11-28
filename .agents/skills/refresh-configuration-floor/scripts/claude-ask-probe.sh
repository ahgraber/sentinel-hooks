#!/bin/sh
# Find out, for one Claude Code permission mode, whether a hook's `ask` reaches the user,
# and which kind of session-start hook output Claude Code shows the user.
# The plugin loads for this session only (--plugin-dir); it changes no configuration.
# Its PreToolUse hook answers `ask`, in Sentinel's output shape, to a call whose file path is notes.txt,
# and allows every other call. Its two SessionStart hooks each send one marked line a different way.
# Usage: sh claude-ask-probe.sh manual|auto|bypassPermissions|dontAsk
set -eu

usage='usage: sh claude-ask-probe.sh manual|auto|bypassPermissions|dontAsk'
mode=${1:?${usage}}
case "${mode}" in
  manual | auto | bypassPermissions | dontAsk) ;;
  *)
    echo "${usage}" >&2
    exit 64
    ;;
esac

work=$(mktemp -d "${TMPDIR:-/tmp}/claude-ask-probe.XXXXXX")
plugin="${work}/askprobe"
out="${work}/hook-calls"
mkdir -p "${plugin}/.claude-plugin" "${plugin}/hooks" "${out}" "${work}/workspace"

cat > "${plugin}/.claude-plugin/plugin.json" << 'EOF'
{"name": "askprobe", "version": "0.1.0", "description": "Asks about notes.txt."}
EOF
cat > "${plugin}/hooks/hooks.json" << 'EOF'
{"hooks": {
  "PreToolUse": [{"hooks": [{"type": "command", "command": "sh \"${CLAUDE_PLUGIN_ROOT}/ask.sh\""}]}],
  "SessionStart": [{"hooks": [
    {"type": "command", "command": "sh \"${CLAUDE_PLUGIN_ROOT}/start-stderr.sh\""},
    {"type": "command", "command": "sh \"${CLAUDE_PLUGIN_ROOT}/start-message.sh\""}
  ]}]
}}
EOF
cat > "${plugin}/ask.sh" << EOF
#!/bin/sh
input=\$(cat)
printf '%s\n' "\${input}" >"${out}/call-\$\$.json"
case "\${input}" in
  *'notes.txt"'*)
    printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "Probe: the hook asks about notes.txt."}}'
    echo ask >"${out}/answer-\$\$.txt"
    ;;
esac
exit 0
EOF
cat > "${plugin}/start-stderr.sh" << 'EOF'
#!/bin/sh
echo 'PROBE-A: a line on standard error, exit 0' >&2
exit 0
EOF
cat > "${plugin}/start-message.sh" << 'EOF'
#!/bin/sh
printf '%s\n' '{"systemMessage": "PROBE-B: a systemMessage field"}'
exit 0
EOF

cd "${work}/workspace"
echo "=== ${mode} mode. At session start, note which of PROBE-A and PROBE-B you can see."
echo "=== If Claude Code shows a prompt for notes.txt, answer No. Then type /exit."
claude --plugin-dir "${plugin}" --permission-mode "${mode}" 'This is an authorized test of a hook. Create the file notes.txt containing the word hello, with the Write tool. Make one attempt only, and do not use the shell.'

echo "=== mode: ${mode}"
if [ -e notes.txt ]; then echo "notes.txt: created"; else echo "notes.txt: not created"; fi
echo "=== hook calls; the ones that answered ask:"
ls "${out}"
for f in "${out}"/call-*.json; do
  if [ -e "${f}" ]; then
    cat "${f}"
    echo
  fi
done
echo "=== files: ${work}"
