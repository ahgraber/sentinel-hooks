#!/bin/sh
# Find out which kind of session-start hook output Copilot CLI shows the user.
# A plugin in Sentinel's layout runs three SessionStart hooks; each sends one marked line a different way.
# It installs into a separate Copilot home, so your own configuration is not changed.
# Usage: sh copilot-start-probe.sh <model-id>
set -eu

model=${1:?usage: sh copilot-start-probe.sh <model-id>}
work=$(mktemp -d "${TMPDIR:-/tmp}/copilot-start-probe.XXXXXX")
market="${work}/market"
plugin="${market}/plugins/startprobe"
out="${work}/hook-calls"
mkdir -p "${market}/.github/plugin" "${plugin}/com.github.copilot/hooks" "${out}" "${work}/workspace" "${work}/home"

cat > "${market}/.github/plugin/marketplace.json" << 'EOF'
{"name": "startprobe-market", "owner": {"name": "startprobe"}, "plugins": [{"name": "startprobe", "description": "Session-start lines.", "version": "0.1.0", "source": "./plugins/startprobe"}]}
EOF
cat > "${plugin}/plugin.json" << 'EOF'
{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "startprobe", "version": "0.1.0", "description": "Session-start lines."}
EOF
cat > "${plugin}/com.github.copilot/hooks/hooks.json" << 'EOF'
{"hooks": {"SessionStart": [
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/a.sh\"", "timeout": 10},
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/b.sh\"", "timeout": 10},
  {"type": "command", "command": "sh \"${PLUGIN_ROOT}/c.sh\"", "timeout": 10}
]}}
EOF
cat > "${plugin}/a.sh" << EOF
#!/bin/sh
echo ran >"${out}/a-\$\$.txt"
echo 'PROBE-A: a line on standard error, exit 0' >&2
exit 0
EOF
cat > "${plugin}/b.sh" << EOF
#!/bin/sh
echo ran >"${out}/b-\$\$.txt"
printf '%s\n' '{"systemMessage": "PROBE-B: a systemMessage field"}'
exit 0
EOF
cat > "${plugin}/c.sh" << EOF
#!/bin/sh
echo ran >"${out}/c-\$\$.txt"
echo 'PROBE-C: a line on standard error, exit 1' >&2
exit 1
EOF

COPILOT_HOME="${work}/home"
export COPILOT_HOME
copilot plugin marketplace add "${market}"
copilot plugin install startprobe@startprobe-market

cd "${work}/workspace"
echo "=== When the session opens, note which of PROBE-A, PROBE-B, and PROBE-C you can see, and where."
echo "=== Then type /exit."
copilot --model "${model}" -i 'Say the word hello and stop.'

echo "=== session-start hooks that ran:"
ls "${out}"
echo "=== probe lines in the session log:"
grep -h -o -E '.{0,80}PROBE-[ABC][^"\\]{0,45}' "${COPILOT_HOME}"/session-state/*/events.jsonl | sort -u || echo "  none"
echo "=== files: ${work}"
