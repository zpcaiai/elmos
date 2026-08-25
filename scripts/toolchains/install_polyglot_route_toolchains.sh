#!/usr/bin/env bash
set -euo pipefail

umask 022

readonly KOTLIN_VERSION="2.2.20"
readonly KOTLIN_ARCHIVE_SHA256="81f0264c9073b5cbbdb3ff8418cf2c5dac076879fc156fa1a6462f5a5acc4420"
readonly KOTLIN_ARCHIVE_BYTES="78709601"
readonly KOTLIN_BUILD_NUMBER="2.2.20-release-333"
readonly KOTLINC_SHA256="90750c977cc043dd2b05c69dd4e052c10377554925dd5a155e74ef732be28c7d"
readonly KOTLIN_COMPILER_JAR_SHA256="8546feb440ec2d59e00d475936523fcd3f528e21c7e8eb8a95e6de5044a6d496"
readonly KOTLIN_STDLIB_JAR_SHA256="8836ccffd3585fadda9901244b20d42901d2f3cd581058d8434e2ffabcf3a3e7"
readonly KOTLIN_TREE_SHA256="0f6e2cea7d2dd94f63e84a3f4be5c8252cb3a53f2abbd19fa4165fc2665082b8"
readonly KOTLIN_TREE_RECORD_COUNT="123"
readonly KOTLIN_TREE_FILE_COUNT="118"
readonly KOTLIN_TREE_DIRECTORY_COUNT="5"
readonly KOTLIN_TREE_BYTES="85861305"
readonly KOTLIN_VERSION_BANNER="kotlinc-jvm 2.2.20 (JRE 21.0.11)"
readonly KOTLIN_ARCHIVE_URL="https://github.com/JetBrains/kotlin/releases/download/v${KOTLIN_VERSION}/kotlin-compiler-${KOTLIN_VERSION}.zip"
readonly PIN_SCRIPT_SHA256="60540ef44a6a8a5a2a65343868951f2dcfc0063b1cd91f1e4db46dff1b86a1ac"
readonly PIN_SCRIPT_BYTES="21518"

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly REPOSITORY_ROOT
readonly PIN_SCRIPT="${REPOSITORY_ROOT}/engines/polyglot-route-engine/tools/pin_kotlin_toolchain.py"
readonly PROJECT_TOOLCHAIN_ROOT="${ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT:-${HOME}/.local/share/elmos/toolchains}"
readonly TOOLCHAIN_ROOT="${ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT:-${PROJECT_TOOLCHAIN_ROOT}}"
readonly KOTLIN_PARENT="${TOOLCHAIN_ROOT}/kotlin"
readonly KOTLIN_TARGET="${KOTLIN_PARENT}/${KOTLIN_VERSION}"

if [[ -n "${ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT:-}" \
  && -n "${ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT:-}" \
  && "${ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT}" != "${ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT}" ]]; then
  printf 'Polyglot and synthesis toolchain roots must be identical\n' >&2
  exit 2
fi

case "${TOOLCHAIN_ROOT}" in
  /*) ;;
  *) printf 'ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT must be absolute\n' >&2; exit 2 ;;
esac
case "/${TOOLCHAIN_ROOT#/}/" in
  *"/../"*|*"/./"*)
    printf 'ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT must be normalized: %s\n' "${TOOLCHAIN_ROOT}" >&2
    exit 2
    ;;
esac
if [[ "${TOOLCHAIN_ROOT}" == "/" || "${TOOLCHAIN_ROOT}" == "${HOME}" ]]; then
  printf 'Refusing broad polyglot route toolchain root: %s\n' "${TOOLCHAIN_ROOT}" >&2
  exit 2
fi
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  printf 'This exact polyglot route installer currently supports only Darwin arm64\n' >&2
  exit 2
fi
for command_name in curl shasum unzip python3.12 grep awk stat; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required host command is unavailable: %s\n' "${command_name}" >&2
    exit 2
  fi
done
if [[ -L "${TOOLCHAIN_ROOT}" ]]; then
  printf 'Refusing symlinked polyglot route toolchain root: %s\n' "${TOOLCHAIN_ROOT}" >&2
  exit 2
fi

file_sha256() {
  shasum -a 256 "$1" | awk '{print $1}'
}

file_bytes() {
  stat -f '%z' "$1"
}

directory_identity() {
  local directory="$1"
  [[ -d "${directory}" && ! -L "${directory}" ]] || return 1
  stat -f '%d:%i' "${directory}"
}

verify_pin_script_identity() {
  local before after observed_bytes observed_sha256
  [[ -f "${PIN_SCRIPT}" && ! -L "${PIN_SCRIPT}" ]] || return 1
  before="$(stat -f '%d:%i:%z:%m' "${PIN_SCRIPT}")" || return 1
  observed_bytes="$(file_bytes "${PIN_SCRIPT}")" || return 1
  observed_sha256="$(file_sha256 "${PIN_SCRIPT}")" || return 1
  after="$(stat -f '%d:%i:%z:%m' "${PIN_SCRIPT}")" || return 1
  [[ "${before}" == "${after}" ]] || return 1
  [[ "${observed_bytes}" == "${PIN_SCRIPT_BYTES}" ]] || return 1
  [[ "${observed_sha256}" == "${PIN_SCRIPT_SHA256}" ]]
}

if ! verify_pin_script_identity; then
  printf 'Kotlin route pin verifier identity mismatch: %s\n' "${PIN_SCRIPT}" >&2
  exit 2
fi

pin_has_exact_line() {
  local pin_output="$1"
  local expected="$2"
  grep -Fqx -- "${expected}" <<<"${pin_output}"
}

verify_exact_install() {
  local target="$1"
  local pin_output
  [[ -d "${target}" && ! -L "${target}" ]] || return 1
  [[ -f "${target}/bin/kotlinc" && ! -L "${target}/bin/kotlinc" ]] || return 1
  [[ -f "${target}/bin/kotlin" && ! -L "${target}/bin/kotlin" ]] || return 1
  [[ -f "${target}/lib/kotlin-compiler.jar" && ! -L "${target}/lib/kotlin-compiler.jar" ]] || return 1
  [[ -f "${target}/lib/kotlin-stdlib.jar" && ! -L "${target}/lib/kotlin-stdlib.jar" ]] || return 1
  [[ -f "${target}/build.txt" && ! -L "${target}/build.txt" ]] || return 1
  [[ "$(<"${target}/build.txt")" == "${KOTLIN_BUILD_NUMBER}" ]] || return 1
  [[ "$(file_sha256 "${target}/bin/kotlinc")" == "${KOTLINC_SHA256}" ]] || return 1
  [[ "$(file_sha256 "${target}/lib/kotlin-compiler.jar")" == "${KOTLIN_COMPILER_JAR_SHA256}" ]] || return 1
  [[ "$(file_sha256 "${target}/lib/kotlin-stdlib.jar")" == "${KOTLIN_STDLIB_JAR_SHA256}" ]] || return 1

  # The engine's pin generator reuses the exact tree-identity implementation
  # enforced by toolchains._kotlin. Matching its emitted facts proves the whole
  # extracted tree, not only the three named files above.
  verify_pin_script_identity || return 1
  if ! pin_output="$(python3.12 "${PIN_SCRIPT}" "${target}" 2>/dev/null)"; then
    return 1
  fi
  verify_pin_script_identity || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_VERSION = '${KOTLIN_VERSION_BANNER}'" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLINC_EXECUTABLE_SHA256 = '${KOTLINC_SHA256}'" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_COMPILER_JAR_SHA256 = '${KOTLIN_COMPILER_JAR_SHA256}'" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_STDLIB_JAR_SHA256 = '${KOTLIN_STDLIB_JAR_SHA256}'" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_TREE_SHA256 = '${KOTLIN_TREE_SHA256}'" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_TREE_RECORD_COUNT = ${KOTLIN_TREE_RECORD_COUNT}" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_TREE_FILE_COUNT = ${KOTLIN_TREE_FILE_COUNT}" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_TREE_DIRECTORY_COUNT = ${KOTLIN_TREE_DIRECTORY_COUNT}" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_TREE_BYTES = ${KOTLIN_TREE_BYTES}" || return 1
  pin_has_exact_line "${pin_output}" "_EXPECTED_KOTLIN_BUILD_NUMBER = '${KOTLIN_BUILD_NUMBER}'" || return 1
}

download_verified() {
  local destination="$1"
  local actual bytes
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
    --output "${destination}" "${KOTLIN_ARCHIVE_URL}"
  actual="$(file_sha256 "${destination}")"
  bytes="$(wc -c <"${destination}" | tr -d '[:space:]')"
  if [[ "${actual}" != "${KOTLIN_ARCHIVE_SHA256}" || "${bytes}" != "${KOTLIN_ARCHIVE_BYTES}" ]]; then
    printf 'Kotlin archive identity mismatch: expected %s/%s, observed %s/%s\n' \
      "${KOTLIN_ARCHIVE_SHA256}" "${KOTLIN_ARCHIVE_BYTES}" "${actual}" "${bytes}" >&2
    exit 3
  fi
}

verify_archive_paths() {
  local archive="$1"
  local entries="$2"
  local entry
  unzip -Z1 "${archive}" >"${entries}"
  while IFS= read -r entry; do
    case "${entry}" in
      kotlinc|kotlinc/*) ;;
      *) printf 'Kotlin archive contains an out-of-root entry: %s\n' "${entry}" >&2; return 1 ;;
    esac
    case "/${entry}/" in
      *"/../"*|*"/./"*)
        printf 'Kotlin archive contains an unsafe path: %s\n' "${entry}" >&2
        return 1
        ;;
    esac
  done <"${entries}"
}

if [[ -L "${KOTLIN_PARENT}" \
  || -e "${KOTLIN_PARENT}" && ! -d "${KOTLIN_PARENT}" ]]; then
  printf 'Refusing unsafe Kotlin toolchain parent: %s\n' "${KOTLIN_PARENT}" >&2
  exit 2
fi
if [[ -e "${KOTLIN_TARGET}" || -L "${KOTLIN_TARGET}" ]]; then
  if verify_exact_install "${KOTLIN_TARGET}"; then
    printf 'Kotlin route compiler %s already installed and exact at %s\n' \
      "${KOTLIN_VERSION}" "${KOTLIN_TARGET}"
    exit 0
  fi
  printf 'Refusing to overwrite a non-matching Kotlin route target: %s\n' \
    "${KOTLIN_TARGET}" >&2
  exit 3
fi

mkdir -p "${KOTLIN_PARENT}"
if [[ ! -d "${KOTLIN_PARENT}" || -L "${KOTLIN_PARENT}" ]]; then
  printf 'Refusing unsafe Kotlin toolchain parent: %s\n' "${KOTLIN_PARENT}" >&2
  exit 2
fi
readonly INSTALL_LOCK="${KOTLIN_TARGET}.install-lock"
if ! mkdir "${INSTALL_LOCK}" 2>/dev/null; then
  printf 'Kotlin route installation is already active or left an unresolved lock: %s\n' \
    "${INSTALL_LOCK}" >&2
  exit 3
fi

temporary_root=""
preserve_temporary_root=0
cleanup() {
  if [[ -n "${temporary_root}" && "${preserve_temporary_root}" == "0" ]]; then
    rm -rf -- "${temporary_root}"
  elif [[ -n "${temporary_root}" ]]; then
    printf 'Preserved Kotlin installer staging for manual recovery: %s\n' \
      "${temporary_root}" >&2
  fi
  rmdir "${INSTALL_LOCK}" 2>/dev/null || true
}
trap cleanup EXIT
temporary_root="$(mktemp -d "${KOTLIN_PARENT}/.elmos-polyglot-route-toolchains.XXXXXX")"

rollback_promoted_target() {
  local expected_identity="$1"
  local current_identity rollback_identity
  local rollback_target="${temporary_root}/rolled-back-kotlinc"

  if ! current_identity="$(directory_identity "${KOTLIN_TARGET}")" \
    || [[ "${current_identity}" != "${expected_identity}" ]]; then
    printf 'Refusing to roll back a Kotlin target that is not the promoted directory: %s\n' \
      "${KOTLIN_TARGET}" >&2
    return 1
  fi
  if [[ -e "${rollback_target}" || -L "${rollback_target}" ]]; then
    printf 'Refusing occupied Kotlin rollback path: %s\n' "${rollback_target}" >&2
    return 1
  fi
  if ! mv "${KOTLIN_TARGET}" "${rollback_target}"; then
    printf 'Failed to move the promoted Kotlin target back to staging: %s\n' \
      "${KOTLIN_TARGET}" >&2
    return 1
  fi
  if ! rollback_identity="$(directory_identity "${rollback_target}")" \
    || [[ "${rollback_identity}" != "${expected_identity}" ]]; then
    # Never let cleanup delete a directory whose identity is no longer the
    # one promoted by this process. Preserve it for explicit recovery.
    preserve_temporary_root=1
    printf 'Kotlin rollback identity changed; refusing automatic deletion: %s\n' \
      "${rollback_target}" >&2
    return 1
  fi
  printf 'Rolled back the newly promoted Kotlin route target: %s\n' \
    "${KOTLIN_TARGET}" >&2
}

# Recheck after taking the lock so a concurrent installer cannot turn `mv`
# into a merge with an existing directory.
if [[ -e "${KOTLIN_TARGET}" || -L "${KOTLIN_TARGET}" ]]; then
  printf 'Refusing target created during Kotlin route installation: %s\n' \
    "${KOTLIN_TARGET}" >&2
  exit 3
fi

archive="${temporary_root}/kotlin-compiler-${KOTLIN_VERSION}.zip"
entries="${temporary_root}/archive-entries.txt"
unpack="${temporary_root}/unpack"
mkdir -p "${unpack}"
download_verified "${archive}"
verify_archive_paths "${archive}" "${entries}"
unzip -q "${archive}" -d "${unpack}"
if ! verify_exact_install "${unpack}/kotlinc"; then
  printf 'Refusing Kotlin archive whose extracted tree does not match the route pin\n' >&2
  exit 3
fi

staged_identity="$(directory_identity "${unpack}/kotlinc")"
# Keep the promotion on one filesystem and make one last no-preexisting-target
# check immediately before moving the verified directory into its final name.
if [[ -e "${KOTLIN_TARGET}" || -L "${KOTLIN_TARGET}" ]]; then
  printf 'Refusing target created before Kotlin route promotion: %s\n' \
    "${KOTLIN_TARGET}" >&2
  exit 3
fi
mv "${unpack}/kotlinc" "${KOTLIN_TARGET}"
if [[ "$(directory_identity "${KOTLIN_TARGET}" 2>/dev/null || true)" != "${staged_identity}" ]]; then
  printf 'Kotlin route promotion did not produce the verified directory identity; refusing cleanup of the target: %s\n' \
    "${KOTLIN_TARGET}" >&2
  exit 3
fi
if ! verify_exact_install "${KOTLIN_TARGET}"; then
  printf 'Installed Kotlin route tree failed its post-promotion verification: %s\n' \
    "${KOTLIN_TARGET}" >&2
  rollback_promoted_target "${staged_identity}" || true
  exit 3
fi

printf 'Installed exact Kotlin route compiler %s at %s\n' \
  "${KOTLIN_VERSION}" "${KOTLIN_TARGET}"
