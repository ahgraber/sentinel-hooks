#!/bin/sh
# Find out what Pi writes to its settings when a package's extension is turned off with `pi config`.
# It installs the isolated clone of this repository into a Pi home under tmp/homes/, opens `pi config`,
# and prints the settings file before and after. The real Pi home is not read or changed.
# Usage: sh pi-switch-off-probe.sh    (from anywhere inside the repository)
set -eu

repo=$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)
source_clone="${repo}/tmp/homes/src"
settings="${repo}/tmp/homes/.pi/agent/settings.json"
if [ ! -d "${source_clone}" ]; then
  echo "The isolated clone ${source_clone} is missing." >&2
  exit 1
fi

cd "${repo}"
bash scripts/isolated-harness.sh pi install "${source_clone}"
echo "=== settings.json after the install:"
cat "${settings}"
echo
echo "=== Next, Pi opens its resource screen. Turn OFF the extension of the package from tmp/homes/src,"
echo "=== leave every other item as it is, and exit the screen."
bash scripts/isolated-harness.sh pi config
echo "=== settings.json after pi config:"
cat "${settings}"
echo
echo "=== pi list:"
bash scripts/isolated-harness.sh pi list || true
