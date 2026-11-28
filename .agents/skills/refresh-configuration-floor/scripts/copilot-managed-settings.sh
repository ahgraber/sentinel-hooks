#!/bin/sh
# Show where this computer holds managed GitHub Copilot settings, and what they say about hooks,
# plugins, and permission modes. It reads only; it changes nothing and sends nothing anywhere.
# For each location it prints the setting names, and the values of the settings named in ${wanted}.
# Usage: sh copilot-managed-settings.sh    (macOS or Linux)
set -u

wanted='disableAllHooks|enabledPlugins|defaultPermissionMode|permissions|hooks|strictKnownMarketplaces'

show_json() {
  # Print the top-level setting names of a JSON file, then the wanted values.
  if command -v python3 > /dev/null 2>&1; then
    python3 - "$1" "${wanted}" << 'EOF'
import json, re, sys
path, wanted = sys.argv[1], re.compile(sys.argv[2])
try:
    data = json.load(open(path))
except (OSError, ValueError) as exc:
    print(f"  could not read as JSON: {exc}")
    raise SystemExit(0)
print("  setting names:", ", ".join(sorted(data)) or "(none)")
for key in sorted(data):
    if wanted.match(key):
        print(f"  {key} = {json.dumps(data[key])}")
EOF
  else
    echo "  python3 is not installed; setting names only:"
    grep -o -E '^\s*"[A-Za-z.]+"\s*:' "$1" | tr -d ' ":' | sort -u | sed 's/^/    /'
  fi
}

show_plist() {
  # Print the setting names of a managed-preferences file, then the wanted values.
  if command -v plutil > /dev/null 2>&1; then
    echo "  setting names:"
    plutil -p "$1" | sed -n -E 's/^ +"([^"]+)" => .*/    \1/p'
    echo "  values:"
    plutil -p "$1" | grep -E "^ +\"(${wanted})[^\"]*\" => " || echo "    (none of the wanted settings)"
  else
    echo "  plutil is not installed"
  fi
}

printf "=== computer: "
uname -sr
if command -v copilot > /dev/null 2>&1; then
  printf "=== "
  copilot --version 2>&1 || true
else
  echo "=== copilot is not on PATH"
fi

for file in "/Library/Application Support/GitHubCopilot/managed-settings.json" /etc/github-copilot/managed-settings.json; do
  echo "=== file: ${file}"
  if [ -r "${file}" ]; then
    show_json "${file}"
  elif [ -e "${file}" ]; then
    echo "  present, but this user cannot read it"
  else
    echo "  not present"
  fi
done

for file in "/Library/Managed Preferences/com.github.copilot.plist" "/Library/Managed Preferences/${USER:-}/com.github.copilot.plist"; do
  echo "=== managed preferences: ${file}"
  if [ -r "${file}" ]; then
    show_plist "${file}"
  elif [ -e "${file}" ]; then
    echo "  present, but this user cannot read it"
  else
    echo "  not present"
  fi
done

home="${COPILOT_HOME:-${HOME}/.copilot}"
echo "=== files in ${home} whose names suggest managed or server-delivered settings"
if [ -d "${home}" ]; then
  find "${home}" -maxdepth 2 \( -iname '*managed*' -o -iname '*policy*' -o -iname '*remote-settings*' \) | sed 's/^/  /'
else
  echo "  ${home} is not present"
fi
echo "=== done"
