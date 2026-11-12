#!/usr/bin/env bash

set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat << 'USAGE'
Usage: release.sh <plugin|pi> <version>

Cut a release of one component: set its version, promote the [Unreleased]
section of its changelog to <version>, commit, and create an annotated tag.
Push the commit and the tag yourself.

Components:
  plugin  The Sentinel plugin: every plugin manifest, the root package.json,
          and each catalog's Sentinel entry. Changelog: CHANGELOG.md.
          Tag: plugin-v<version>.
  pi      The Pi extension: extensions/pi/package.json.
          Changelog: extensions/pi/CHANGELOG.md. Tag: pi-v<version>.
USAGE
}

readonly REPO_URL="https://github.com/ahgraber/sentinel-hooks"
readonly PLUGIN_MANIFESTS=(plugins/sentinel/.claude-plugin/plugin.json plugins/sentinel/plugin.json package.json)
readonly PLUGIN_CATALOGS=(.claude-plugin/marketplace.json .agents/plugins/marketplace.json .github/plugin/marketplace.json)

# Writes the jq filter's output over the file, through a temporary file in the same directory.
jq_in_place() {
  local filter="${1}" version="${2}" file="${3}" tmp
  tmp="$(mktemp "${file}.XXXXXX")"
  jq --arg version "${version}" "${filter}" "${file}" > "${tmp}"
  mv "${tmp}" "${file}"
}

# Prints the version of the latest tag with the prefix, or nothing when there is none.
previous_version() {
  local prefix="${1}"
  git tag --list "${prefix}*" --sort=-version:refname | head -n 1 | sed "s/^${prefix}//"
}

# Renames [Unreleased] to the version, opens a new empty [Unreleased] above it,
# and rewrites the footer links for both.
promote_changelog() {
  local changelog="${1}" prefix="${2}" version="${3}" previous="${4}" today tmp version_link
  today="$(date +%Y-%m-%d)"
  if [[ -n "${previous}" ]]; then
    version_link="${REPO_URL}/compare/${prefix}${previous}...${prefix}${version}"
  else
    version_link="${REPO_URL}/releases/tag/${prefix}${version}"
  fi
  tmp="$(mktemp "${changelog}.XXXXXX")"
  awk -v version="${version}" -v today="${today}" \
    -v unreleased_link="[Unreleased]: ${REPO_URL}/compare/${prefix}${version}...HEAD" \
    -v version_link="[${version}]: ${version_link}" '
    /^## \[Unreleased\]$/ { lines[++n] = $0; lines[++n] = ""; lines[++n] = "## [" version "] - " today; next }
    # mdformat lowercases link labels, so the old link may read [unreleased].
    tolower($0) ~ /^\[unreleased\]: / { next }
    { lines[++n] = $0 }
    END {
      while (n > 0 && lines[n] == "") n--
      footer = 0
      for (i = 1; i <= n; i++) if (lines[i] ~ /^\[[^]]+\]: /) { footer = 1; break }
      for (i = 1; i <= n; i++) print lines[i]
      if (!footer) print ""
      print unreleased_link
      print version_link
    }
  ' "${changelog}" > "${tmp}"
  mv "${tmp}" "${changelog}"
}

main() {
  handle_help "${1:-}"
  if (($# != 2)); then
    usage >&2
    die "expected a component and a version"
  fi
  local component="${1}" version="${2}" prefix changelog
  local -a files

  [[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version must be X.Y.Z, got '${version}'"
  require_cmd git jq awk prek uv
  cd "${REPO_ROOT}"

  case "${component}" in
    plugin)
      prefix="plugin-v"
      changelog="CHANGELOG.md"
      files=("${PLUGIN_MANIFESTS[@]}" "${PLUGIN_CATALOGS[@]}")
      ;;
    pi)
      prefix="pi-v"
      changelog="extensions/pi/CHANGELOG.md"
      files=(extensions/pi/package.json)
      ;;
    *)
      usage >&2
      die "unknown component: ${component}"
      ;;
  esac

  local status
  status="$(git status --porcelain)"
  [[ -z "${status}" ]] || die "the working tree has changes; commit or stash them first"
  ! git rev-parse -q --verify "refs/tags/${prefix}${version}" > /dev/null || die "tag ${prefix}${version} already exists"
  awk '/^## \[Unreleased\]$/ { inside = 1; next } /^## / { inside = 0 } inside && /^- / { found = 1 } END { exit !found }' \
    "${changelog}" || die "${changelog} has no entries under [Unreleased]"

  local previous
  previous="$(previous_version "${prefix}")"

  local file
  # shellcheck disable=SC2016 # $version is a jq variable, bound by --arg.
  for file in "${files[@]}"; do
    case "${file}" in
      */marketplace.json) jq_in_place '(.plugins[] | select(.name == "sentinel") | .version) = $version' "${version}" "${file}" ;;
      *) jq_in_place '.version = $version' "${version}" "${file}" ;;
    esac
  done
  promote_changelog "${changelog}" "${prefix}" "${version}" "${previous}"

  # The formatters restore each file's layout after jq rewrites it; a first run that
  # reformats exits nonzero, so the second run is the check.
  prek run --files "${files[@]}" "${changelog}" > /dev/null || prek run --files "${files[@]}" "${changelog}"
  uv run --locked pytest -q tests/shared/test_plugin_manifests.py

  git add -- "${files[@]}" "${changelog}"
  git commit -m "chore(release): ${component} v${version}"
  git tag -a "${prefix}${version}" -m "${prefix}${version}"
  echo "Created ${prefix}${version}. Push with: git push origin HEAD ${prefix}${version}"
}

main "$@"
