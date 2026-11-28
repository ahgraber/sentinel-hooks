#!/bin/sh
# Find out whether Copilot CLI shows the user a hook's `ask`, or lets its assisted reviewer decide it.
# A hook in Sentinel's layout answers `ask`, in Sentinel's output shape, to any call that names notes.txt,
# and allows every other call.
# Usage: sh copilot-ask-probe.sh manual|assisted|assisted-prompt|autopilot|allow-all|allow-all-interactive <model-id>
#   manual           an interactive session that prompts for each call
#   assisted         an interactive session with defaultPermissionMode "assisted" in the settings file
#   assisted-prompt  a non-interactive run with --assisted-approval, where no prompt can appear
#   autopilot        an interactive session started with --autopilot; choose manual approval if it asks
#   allow-all        a non-interactive run with --allow-all
#   allow-all-interactive  an interactive session started with --allow-all
set -eu

usage='usage: sh copilot-ask-probe.sh manual|assisted|assisted-prompt|autopilot|allow-all|allow-all-interactive <model-id>'
mode=${1:?${usage}}
model=${2:?${usage}}
case "${mode}" in
  manual | assisted | assisted-prompt | autopilot | allow-all | allow-all-interactive) ;;
  *)
    echo "${usage}" >&2
    exit 64
    ;;
esac

work=$(mktemp -d "${TMPDIR:-/tmp}/copilot-ask-probe.XXXXXX")
market="${work}/market"
plugin="${market}/plugins/askprobe"
out="${work}/hook-calls"
mkdir -p "${market}/.github/plugin" "${plugin}/com.github.copilot/hooks" "${out}" "${work}/workspace" "${work}/home"

cat > "${market}/.github/plugin/marketplace.json" << 'EOF'
{"name": "askprobe-market", "owner": {"name": "askprobe"}, "plugins": [{"name": "askprobe", "description": "Asks about notes.txt.", "version": "0.1.0", "source": "./plugins/askprobe"}]}
EOF
cat > "${plugin}/plugin.json" << 'EOF'
{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "askprobe", "version": "0.1.0", "description": "Asks about notes.txt."}
EOF
cat > "${plugin}/com.github.copilot/hooks/hooks.json" << 'EOF'
{"hooks": {"PreToolUse": [{"type": "command", "command": "sh \"${PLUGIN_ROOT}/ask.sh\"", "timeout": 10}]}}
EOF
cat > "${plugin}/ask.sh" << EOF
#!/bin/sh
input=\$(cat)
printf '%s\n' "\${input}" >"${out}/call-\$\$.json"
case "\${input}" in
  *'notes.txt"'* | *'File: notes.txt'*)
    printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "Probe: the hook asks about notes.txt."}}'
    echo ask >"${out}/answer-\$\$.txt"
    ;;
esac
exit 0
EOF

# A separate Copilot home keeps this plugin out of your own configuration.
COPILOT_HOME="${work}/home"
export COPILOT_HOME
# The plugin install adds its entry to this file, so the mode is written first.
case "${mode}" in
  assisted) printf '%s\n' '{"defaultPermissionMode": "assisted"}' > "${COPILOT_HOME}/settings.json" ;;
  allow-all-interactive) printf '%s\n' '{"defaultPermissionMode": "allow-all"}' > "${COPILOT_HOME}/settings.json" ;;
  *) ;;
esac
copilot plugin marketplace add "${market}"
copilot plugin install askprobe@askprobe-market

prompt='This is an authorized test of a hook. Create the file notes.txt containing the word hello, with your file-creation tool. Make one attempt only, and do not use the shell.'
cd "${work}/workspace"
case "${mode}" in
  manual)
    echo "=== manual mode. If Copilot shows a prompt for notes.txt, answer No. Then type /exit."
    copilot --model "${model}" -i "${prompt}"
    ;;
  assisted)
    echo "=== settings.json after the plugin install:"
    cat "${COPILOT_HOME}/settings.json"
    echo "=== assisted mode. Check that the status line shows assisted permissions."
    echo "=== If Copilot shows a prompt for notes.txt, answer No. Then type /exit."
    copilot --model "${model}" -i "${prompt}"
    ;;
  assisted-prompt)
    echo "=== assisted-prompt mode. No prompt can appear; the run ends by itself."
    copilot --model "${model}" --assisted-approval -p "${prompt}" || true
    ;;
  autopilot)
    echo "=== autopilot mode. If Copilot asks which permissions to use, choose manual approval, not all permissions."
    echo "=== If Copilot shows a prompt for notes.txt, answer No. Then type /exit."
    copilot --model "${model}" --autopilot -i "${prompt}"
    ;;
  allow-all)
    echo "=== allow-all mode. No prompt can appear; the run ends by itself."
    copilot --model "${model}" --allow-all -p "${prompt}" || true
    ;;
  allow-all-interactive)
    echo "=== settings.json after the plugin install:"
    cat "${COPILOT_HOME}/settings.json"
    echo "=== allow-all mode, interactive. Check that the status line shows allow-all permissions."
    echo "=== If Copilot shows a prompt for notes.txt, answer No. Then type /exit."
    copilot --model "${model}" -i "${prompt}"
    ;;
  *) exit 64 ;;
esac

echo "=== mode: ${mode}"
if [ -e notes.txt ]; then echo "notes.txt: created"; else echo "notes.txt: not created"; fi
echo "=== hook calls; the ones that answered ask:"
ls "${out}"
for f in "${out}"/call-*.json; do
  if [ -e "${f}" ]; then cat "${f}"; fi
done
echo "=== permission and hook events in the session log"
grep -h -o -i -E '"type":"[^"]*(permission|hook|approv)[^"]*"' "${COPILOT_HOME}"/session-state/*/events.jsonl | sort | uniq -c
echo "=== files: ${work}"
