#!/usr/bin/env bash
set -euo pipefail

# Benchmark note: keep the Python adapter as the default. In local measurements
# it was faster than this bash adapter because this path adds shell orchestration
# overhead on top of repeated jq/perl-heavy downstream hook invocations.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd -P)"
CLAUDE_HOOKS_DIR="${REPO_ROOT}/configs/home-manager/claude/hooks"
COPILOT_HOOKS_DIR="${REPO_ROOT}/configs/home-manager/copilot/hooks"
TEMP_DIR=''

MULTI_PATH_TARGETS='^(block-sensitive-paths\.py|block-secrets\.py|copilot-block-hook-tampering\.py)$'

usage() {
  printf '%s\n' 'Usage: copilot-vscode-hook-adapter.sh <script> [args...]' >&2
}

rewrite_agent_names() {
  sed \
    -e "s/Claude Code/GitHub Copilot/g" \
    -e "s/Claude's context/Copilot's context/g" \
    -e "s/Claude/Copilot/g"
}

emit_result() {
  local stdout_file="${1}"
  local stderr_file="${2}"

  if [[ -s "${stdout_file}" ]]; then
    rewrite_agent_names < "${stdout_file}"
  fi

  if [[ -s "${stderr_file}" ]]; then
    rewrite_agent_names < "${stderr_file}" >&2
  fi
}

resolve_hook_path() {
  case "${1}" in
    session-tool-checks.sh|session-instructions.sh|git-baseline.sh|block-dangerous-bash.sh|block-sensitive-paths.py|block-destructive-ops.py|block-secrets.py|bash-command-validator.sh|posttooluse-precommit.sh)
      printf '%s\n' "${CLAUDE_HOOKS_DIR}/${1}"
      ;;
    copilot-block-hook-tampering.py)
      printf '%s\n' "${COPILOT_HOOKS_DIR}/${1}"
      ;;
    *)
      return 1
      ;;
  esac
}

map_tool_name() {
  case "${1}" in
    Bash|runInTerminal|run_in_terminal|terminal)
      printf '%s\n' 'Bash'
      ;;
    Read|readFile|read_file)
      printf '%s\n' 'Read'
      ;;
    Write|create_file|createFile)
      printf '%s\n' 'Write'
      ;;
    Edit|editFiles|replace_string_in_file|insert_edit_into_file|delete_file|rename_file)
      printf '%s\n' 'Edit'
      ;;
    apply_patch)
      printf '%s\n' 'apply_patch'
      ;;
    *)
      printf '%s\n' "${1}"
      ;;
  esac
}

normalize_payload() {
  local raw_json="${1}"
  local mapped_name="${2}"

  jq -c --arg mapped_name "${mapped_name}" '
    . as $root
    | (($root.tool_input // {}) | if type == "object" then . else {} end) as $input
    | if $mapped_name == "Bash" then
        $root + {
          tool_name: $mapped_name,
          tool_input: {
            command: (($input.command // $input.text // "") | if type == "string" then . else "" end)
          }
        }
      elif ($mapped_name == "Read" or $mapped_name == "Write" or $mapped_name == "Edit") then
        ([
          $input.file_path?,
          $input.filePath?,
          $input.path?,
          ($input.file_paths[]?),
          ($input.filePaths[]?),
          ($input.files[]?)
        ] | map(select(type == "string" and length > 0)) | unique) as $paths
        | $root + {
            tool_name: $mapped_name,
            tool_input: ($input + if ($paths | length) > 0 then {
              file_path: $paths[0],
              file_paths: $paths,
              path: $paths[0]
            } else {} end)
          }
      elif $mapped_name == "apply_patch" then
        $root + {
          tool_name: $mapped_name,
          tool_input: {
            command: (($input.command // $input.input // "") | if type == "string" then . else "" end)
          }
        }
      else
        $root + {
          tool_name: $mapped_name,
          tool_input: $input
        }
      end
  ' <<< "${raw_json}"
}

execute_hook() {
  local script_name="${1}"
  local payload_json="${2}"
  shift 2
  local script_args=("$@")
  local script_path

  if ! script_path="$(resolve_hook_path "${script_name}")"; then
    printf 'Unknown hook script: %s\n' "${script_name}" > "${HOOK_STDERR_FILE}"
    : > "${HOOK_STDOUT_FILE}"
    HOOK_EXIT_CODE=1
    return 0
  fi

  local -a command
  case "${script_path}" in
    *.py)
      command=(uv run --script "${script_path}" "${script_args[@]}")
      ;;
    *.sh)
      command=(bash "${script_path}" "${script_args[@]}")
      ;;
    *)
      command=("${script_path}" "${script_args[@]}")
      ;;
  esac

  if printf '%s' "${payload_json}" | "${command[@]}" > "${HOOK_STDOUT_FILE}" 2> "${HOOK_STDERR_FILE}"; then
    HOOK_EXIT_CODE=0
  else
    HOOK_EXIT_CODE=$?
  fi
}

main() {
  if (($# < 1)); then
    usage
    return 1
  fi

  local script_name="${1}"
  shift
  local script_args=("$@")

  local raw_json
  raw_json="$(cat)"
  if ! jq -e . >/dev/null 2>&1 <<< "${raw_json}"; then
    raw_json='{}'
  fi

  local original_tool_name
  original_tool_name="$(jq -r '.tool_name // ""' <<< "${raw_json}")"
  local mapped_name
  mapped_name="$(map_tool_name "${original_tool_name}")"
  local normalized_json
  normalized_json="$(normalize_payload "${raw_json}" "${mapped_name}")"

  local temp_dir
  TEMP_DIR="$(mktemp -d)"
  trap '[[ -n "${TEMP_DIR}" ]] && rm -rf "${TEMP_DIR}"' EXIT
  HOOK_STDOUT_FILE="${TEMP_DIR}/stdout"
  HOOK_STDERR_FILE="${TEMP_DIR}/stderr"

  local multi_path_count
  multi_path_count="$(jq -r '(.tool_input.file_paths // []) | length' <<< "${normalized_json}")"

  if [[ "${script_name}" =~ ${MULTI_PATH_TARGETS} ]] && [[ "${mapped_name}" =~ ^(Read|Write|Edit)$ ]] && (( multi_path_count > 1 )); then
    mapfile -t file_paths < <(jq -r '.tool_input.file_paths[]? | select(type == "string" and length > 0)' <<< "${normalized_json}")

    local path
    for path in "${file_paths[@]}"; do
      local per_path_json
      per_path_json="$(jq -c --arg path "${path}" '.tool_input.file_path = $path | .tool_input.path = $path' <<< "${normalized_json}")"
      execute_hook "${script_name}" "${per_path_json}" "${script_args[@]}"
      if (( HOOK_EXIT_CODE != 0 )) || [[ -s "${HOOK_STDOUT_FILE}" ]]; then
        emit_result "${HOOK_STDOUT_FILE}" "${HOOK_STDERR_FILE}"
        return "${HOOK_EXIT_CODE}"
      fi
    done

    return 0
  fi

  execute_hook "${script_name}" "${normalized_json}" "${script_args[@]}"
  emit_result "${HOOK_STDOUT_FILE}" "${HOOK_STDERR_FILE}"
  return "${HOOK_EXIT_CODE}"
}

main "$@"
