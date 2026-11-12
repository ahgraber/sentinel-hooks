# Changelog

All notable changes to Sentinel's Pi extension are documented in this file.
The extension runs hooks on Pi's events; changes to the hooks themselves are in the plugin's [CHANGELOG.md](../../CHANGELOG.md).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Run Sentinel's hooks, and the user's own Claude Code-format hooks, on Pi's tool, session, and turn events.
- Show the user a confirmation when a hook asks before a tool runs, and refuse the call when Pi has no UI to show it.
- Show the user a hook's `systemMessage` on every event.
- Report a hook file that cannot be read, naming the file, and keep running the hooks from the other files.
