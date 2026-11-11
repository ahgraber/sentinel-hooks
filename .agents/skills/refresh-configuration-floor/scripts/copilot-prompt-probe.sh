#!/bin/sh
# Find out what Copilot CLI does with the output of a hook that runs when the user sends a prompt.
# A plugin in Sentinel's layout runs three UserPromptSubmit hooks:
#   D gives the model a word in the `additionalContext` field of a JSON reply (marmalade)
#   E gives the model a word as plain standard output (tangerine)
#   F returns a `systemMessage` field (PROBE-F), which a harness may show the user
# The prompt asks the model which words it was given.
# It installs into a separate Copilot home, so your own configuration is not changed.
# Usage: sh copilot-prompt-probe.sh <model-id>
set -eu

model=${1:?usage: sh copilot-prompt-probe.sh <model-id>}
work=$(mktemp -d "${TMPDIR:-/tmp}/copilot-prompt-probe.XXXXXX")
market="${work}/market"
plugin="${market}/plugins/promptprobe"
out="${work}/hook-calls"
mkdir -p "${market}/.github/plugin" "${plugin}/com.github.copilot/hooks" "${out}" "${work}/workspace" "${work}/home"

cat > "${market}/.github/plugin/marketplace.json" << 'EOF'
{"name": "promptprobe-market", "owner": {"name": "promptprobe"}, "plugins": [{"name": "promptprobe", "description": "Prompt-time context.", "version": "0.1.0", "source": "./plugins/promptprobe"}]}
EOF
cat > "${plugin}/plugin.json" << 'EOF'
{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "promptprobe", "version": "0.1.0", "description": "Prompt-time context."}
EOF
cat > "${plugin}/com.github.copilot/hooks/hooks.json" << 'EOF'
{"hooks": {"UserPromptSubmit": [
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/d.sh\"", "timeout": 10},
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/e.sh\"", "timeout": 10},
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/f.sh\"", "timeout": 10}
]}}
EOF
cat > "${plugin}/d.sh" << EOF
#!/bin/sh
cat >"${out}/d-\$\$.json"
printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "A hook gives you this probe word: marmalade."}}'
exit 0
EOF
cat > "${plugin}/e.sh" << EOF
#!/bin/sh
echo ran >"${out}/e-\$\$.txt"
echo 'A hook gives you this probe word: tangerine.'
exit 0
EOF
cat > "${plugin}/f.sh" << EOF
#!/bin/sh
echo ran >"${out}/f-\$\$.txt"
printf '%s\n' '{"systemMessage": "PROBE-F: a systemMessage field at prompt time"}'
exit 0
EOF

COPILOT_HOME="${work}/home"
export COPILOT_HOME
copilot plugin marketplace add "${market}"
copilot plugin install promptprobe@promptprobe-market

cd "${work}/workspace"
echo "=== Watch for a line carrying PROBE-F, and read the model's answer. Then type /exit."
echo "=== marmalade means the additionalContext field reached the model; tangerine means plain output did."
copilot --model "${model}" -i 'This is a test of hook context. Were you given any probe words by a hook? Answer with only the probe words you were given, or the word none. Do not use any tool.'

echo "=== prompt-time hooks that ran:"
ls "${out}"
echo "=== what hook D received:"
for f in "${out}"/d-*.json; do
  if [ -e "${f}" ]; then
    cat "${f}"
    echo
  fi
done
echo "=== files: ${work}"
