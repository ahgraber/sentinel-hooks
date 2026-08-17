#!/usr/bin/env bash
# Claude Code Hook: relay lifecycle events to the claudebar menu bar app.
#
# Registered on every lifecycle event the app displays (SessionStart,
# UserPromptSubmit, SessionEnd, Stop, SubagentStart, SubagentStop,
# TaskCompleted). claudebar is a macOS-only Homebrew cask, so on any other
# platform this returns without opening a connection; the inline version this
# replaces posted to a dead port on every event instead.
#
# Read more about hooks here: https://docs.anthropic.com/en/docs/claude-code/hooks

set -uo pipefail

# ── Platform gate ─────────────────────────────────────────────────────────────
# Drain stdin before exiting: Claude Code writes the event payload to this
# process, and a hook that exits without reading leaves that write to fail.

os="$(uname -s)"
if [[ "${os}" != "Darwin" ]]; then
  cat > /dev/null
  exit 0
fi

# ── Relay ─────────────────────────────────────────────────────────────────────
# claudebar writes its listening port to the file below. 19847 is the app's
# default, used when the file is absent because the app has not run yet.
# Backgrounded so a stalled or absent listener never delays the event.

port="$(cat "${HOME}/.claude/claudebar-hook-port" 2> /dev/null || echo 19847)"

cat | curl -s -X POST "http://localhost:${port}/hook" \
  -H 'Content-Type: application/json' -d @- > /dev/null 2>&1 &

exit 0
