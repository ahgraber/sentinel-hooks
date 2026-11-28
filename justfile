# sentinel-hooks tasks. Run `just` (or `just --list`) to see recipes.
#
# This repository ships two independently versioned components (see AGENTS.md, "Versioning and Releases"):
#   - the Sentinel plugin: CHANGELOG.md, tags plugin-v<X.Y.Z>
#   - the Pi extension: extensions/pi/CHANGELOG.md, tags pi-v<X.Y.Z>

# List available recipes
default:
    @just --list

# Cut a plugin release from CHANGELOG.md, e.g. `just release-plugin 0.2.0`
release-plugin version:
    scripts/release.sh plugin {{ version }}

# Cut a Pi extension release from extensions/pi/CHANGELOG.md, e.g. `just release-pi 0.2.0`
release-pi version:
    scripts/release.sh pi {{ version }}
