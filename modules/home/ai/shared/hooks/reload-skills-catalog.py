#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Re-inject the skills catalog after SessionStart compaction."""

import json
import os
from pathlib import Path
import sys

try:
    import yaml
except ImportError:
    yaml = None


def extract_frontmatter_raw(text: str) -> str | None:
    """Return the raw YAML frontmatter string between --- fences."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[4:end]


def parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from a SKILL.md file."""
    raw = extract_frontmatter_raw(text)
    if raw is None:
        return {}
    if yaml is not None:
        try:
            data = yaml.safe_load(raw)
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError:
            return {}
    result = {}
    for line in raw.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            val = val.strip().strip("\"'")
            if val and val not in ("|-", ">-", "|", ">"):
                result[key.strip()] = val
    return result


def _user_skill_dirs() -> list[Path]:
    """Return default and existing project-level Claude skill directories."""
    home = Path.home()
    dirs = [home / ".claude" / "skills"]
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if project_dir:
        p = Path(project_dir) / ".claude" / "skills"
        if p.is_dir():
            dirs.append(p)
    return dirs


def _plugin_cache_dir() -> Path:
    """Return the plugin cache directory."""
    return Path.home() / ".claude" / "plugins" / "cache"


# Skip official-plugin symlinks and stale temporary checkouts.
_SKIP_PLUGIN_PREFIXES = ("claude-plugins-official", "temp_git_")


def _read_skill(skill_file: Path) -> tuple[str, str] | None:
    """Read a SKILL.md and return (name, description) or None."""
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None
    meta = parse_frontmatter(text)
    name = meta.get("name", "")
    if not name:
        return None
    desc = meta.get("description", "")
    desc = " ".join(desc.split())
    if len(desc) > 250:
        desc = desc[:249] + "\u2026"
    return (name, desc)


def _collect_user_skills() -> list[tuple[str, str]]:
    """Collect unique user skills from direct child directories in sorted order.

    Direct iteration follows skill-directory symlinks consistently on Python 3.13.
    """
    seen: set[str] = set()
    skills: list[tuple[str, str]] = []
    for d in _user_skill_dirs():
        if not d.is_dir():
            continue
        for child in sorted(d.iterdir()):
            if not child.is_dir() and not (child.is_symlink() and child.resolve().is_dir()):
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue
            result = _read_skill(skill_file)
            if result is None:
                continue
            name, desc = result
            if name in seen:
                continue
            seen.add(name)
            skills.append((name, desc))
    return skills


def _collect_plugin_skills(exclude: set[str]) -> list[tuple[str, str]]:
    """Collect unique `plugin:skill` entries, skipping excluded names and prefixes."""
    cache = _plugin_cache_dir()
    if not cache.is_dir():
        return []

    seen: set[str] = set()
    skills: list[tuple[str, str]] = []

    for plugin_dir in sorted(cache.iterdir()):
        if not plugin_dir.is_dir():
            continue
        if any(plugin_dir.name.startswith(p) for p in _SKIP_PLUGIN_PREFIXES):
            continue
        namespace = plugin_dir.name
        for root, _dirs, files in os.walk(plugin_dir, followlinks=True):
            if "SKILL.md" not in files:
                continue
            result = _read_skill(Path(root) / "SKILL.md")
            if result is None:
                continue
            raw_name, desc = result
            qualified = f"{namespace}:{raw_name}"
            if qualified in seen or raw_name in exclude:
                continue
            seen.add(qualified)
            skills.append((qualified, desc))

    return skills


def collect_skills() -> list[tuple[str, str]]:
    """Return deduplicated (name, description) pairs."""
    user_skills = _collect_user_skills()
    user_names = {name for name, _ in user_skills}
    plugin_skills = _collect_plugin_skills(exclude=user_names)
    return user_skills + plugin_skills


def main() -> None:
    """Emit the skills catalog as SessionStart additional context."""
    skills = collect_skills()
    if not skills:
        sys.exit(0)

    lines = []
    for name, desc in skills:
        if desc:
            lines.append(f"- {name}: {desc}")
        else:
            lines.append(f"- {name}")

    content = "## Available Skills\n\n" + "\n".join(lines) + "\n"

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": content,
        }
    }
    json.dump(output, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
