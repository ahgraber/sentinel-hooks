#!/bin/sh
# Find out whether Copilot CLI gives the model the text a session-start hook returns.
# A plugin in Sentinel's layout runs two SessionStart hooks. Each gives the model one word a different way:
# hook D in the `additionalContext` field of a JSON reply, hook E as plain standard output.
# The prompt then asks the model which words it was given.
# It installs into a separate Copilot home, so your own configuration is not changed.
# Usage: sh copilot-context-probe.sh <model-id>
set -eu

model=${1:?usage: sh copilot-context-probe.sh <model-id>}
work=$(mktemp -d "${TMPDIR:-/tmp}/copilot-context-probe.XXXXXX")
market="${work}/market"
plugin="${market}/plugins/contextprobe"
out="${work}/hook-calls"
mkdir -p "${market}/.github/plugin" "${plugin}/com.github.copilot/hooks" "${out}" "${work}/workspace" "${work}/home"

cat > "${market}/.github/plugin/marketplace.json" << 'EOF'
{"name": "contextprobe-market", "owner": {"name": "contextprobe"}, "plugins": [{"name": "contextprobe", "description": "Session-start context.", "version": "0.1.0", "source": "./plugins/contextprobe"}]}
EOF
cat > "${plugin}/plugin.json" << 'EOF'
{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "contextprobe", "version": "0.1.0", "description": "Session-start context."}
EOF
cat > "${plugin}/com.github.copilot/hooks/hooks.json" << 'EOF'
{"hooks": {"SessionStart": [
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/d.sh\"", "timeout": 10},
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/e.sh\"", "timeout": 10}
]}}
EOF
cat > "${plugin}/d.sh" << EOF
#!/bin/sh
echo ran >"${out}/d-\$\$.txt"
printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "A hook gives you this probe word: marmalade."}}'
exit 0
EOF
cat > "${plugin}/e.sh" << EOF
#!/bin/sh
echo ran >"${out}/e-\$\$.txt"
echo 'A hook gives you this probe word: tangerine.'
exit 0
EOF

COPILOT_HOME="${work}/home"
export COPILOT_HOME
copilot plugin marketplace add "${market}"
copilot plugin install contextprobe@contextprobe-market

cd "${work}/workspace"
echo "=== The model's answer follows. marmalade means the additionalContext field reached it; tangerine means plain output did."
copilot --model "${model}" -p 'This is a test of hook context. Were you given any probe words by a hook? Answer with only the probe words you were given, or the word none. Do not use any tool.' || true

echo "=== session-start hooks that ran:"
ls "${out}"
echo "=== files: ${work}"
