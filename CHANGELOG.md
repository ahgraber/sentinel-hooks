# Changelog

All notable changes to the Sentinel plugin are documented in this file.
Changes to the Pi extension are in [extensions/pi/CHANGELOG.md](extensions/pi/CHANGELOG.md).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Install Sentinel as a plugin in Claude Code, Codex, GitHub Copilot CLI, GitHub Copilot in VS Code, and Pi, each from this repository's marketplace or git URL; every agent runs the same hooks and policy.
- Refuse reading credentials or sending them off the machine, gaining privileges, persistence, or remote control, destroying work that cannot be recovered, and calling a tool Sentinel does not know.
- Ask the user before changing Sentinel's installed copy or its settings, before destructive operations that have a legitimate use, and before reading what may be a credential; where an agent cannot ask, refuse instead.
- Report at session start each missing program Sentinel needs and each agent setting that turns its hooks off or lets something other than the user answer its questions.
- Install Sentinel's hooks into Codex with `harnesses/codex/install-hooks.py`, because Codex does not run hooks from plugins in the standard plugin format.
