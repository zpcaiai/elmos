#!/usr/bin/env bash
set -euo pipefail

umask 022

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  printf 'The exact CI route toolchain requires Darwin arm64.\n' >&2
  exit 2
fi
: "${RUNNER_TEMP:?RUNNER_TEMP must be provided by GitHub Actions}"
: "${GITHUB_ENV:?GITHUB_ENV must be provided by GitHub Actions}"
: "${GITHUB_PATH:?GITHUB_PATH must be provided by GitHub Actions}"
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_ENVIRONMENT:-}" != "github-hosted" ]]; then
  printf 'Refusing to provision the CI closure outside a GitHub-hosted runner.\n' >&2
  exit 2
fi
for command_name in brew chmod codesign curl find git install mv python3 realpath shasum stat sudo sw_vers tar; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required host command is unavailable: %s\n' "${command_name}" >&2
    exit 2
  fi
done
readonly REALPATH_PATH="$(command -v realpath)"
case "${REALPATH_PATH}" in
  /bin/realpath|/usr/bin/realpath) ;;
  *) printf 'Required realpath must be a system executable, observed %s\n' "${REALPATH_PATH}" >&2; exit 2 ;;
esac
if [[ ! -x "${REALPATH_PATH}" || -L "${REALPATH_PATH}" ]]; then
  printf 'Required realpath system executable identity is invalid.\n' >&2
  exit 2
fi

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly REPOSITORY_ROOT
readonly PINNED_HOME="${ELMOS_ROUTE_CI_HOME:-${HOME}}"
readonly PINNED_LOCAL="${PINNED_HOME}/.local"
readonly TOOLCHAIN_ROOT="${PINNED_LOCAL}/share/elmos/toolchains"
readonly PINNED_BIN="${PINNED_LOCAL}/bin"
readonly HOMEBREW_PREFIX="$(brew --prefix)"
readonly HOMEBREW_CELLAR="$(brew --cellar)"
readonly UV_PATH="${HOMEBREW_CELLAR}/uv/0.11.16/bin/uv"
readonly TAP_NAME="elmos/pinned-route-ci"
readonly CI_PROFILE="${ELMOS_POLYGLOT_ROUTE_CI_PROFILE:-full}"
temporary_root="$(mktemp -d "${RUNNER_TEMP}/elmos-route-ci-toolchains.XXXXXX")"

case "${CI_PROFILE}" in
  full|frontend-formal|java-python|typed-sql) ;;
  *) printf 'Unknown ELMOS_POLYGLOT_ROUTE_CI_PROFILE: %s\n' "${CI_PROFILE}" >&2; exit 2 ;;
esac
if [[ "${CI_PROFILE}" == "full" || "${CI_PROFILE}" == "frontend-formal" ]]; then
  case "$(sw_vers -productVersion)" in
    26.*) ;;
    *)
      printf 'The pinned Node/ada-url bottle receipt is Tahoe-only.\n' >&2
      exit 2
      ;;
  esac
fi

cleanup() {
  rm -rf -- "${temporary_root}"
}
trap cleanup EXIT

file_sha256() {
  shasum -a 256 "$1" | awk '{print $1}'
}

download_verified() {
  local url="$1"
  local expected="$2"
  local destination="$3"
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
    --output "${destination}" "${url}"
  local observed
  observed="$(file_sha256 "${destination}")"
  if [[ "${observed}" != "${expected}" ]]; then
    printf 'Pinned source checksum mismatch for %s: expected %s, observed %s\n' \
      "${url}" "${expected}" "${observed}" >&2
    exit 3
  fi
}

install -d -m 0755 "${PINNED_HOME}"
install -d -m 0755 "${PINNED_LOCAL}" "${TOOLCHAIN_ROOT}" "${PINNED_BIN}"

# GitHub's macOS images can carry an unrelated, untrusted AWS tap. Homebrew
# refuses to resolve even the explicitly pinned closure while that tap is
# present. The runner is disposable; remove only that known unrelated tap so
# dependency resolution remains fail-closed instead of disabling tap trust.
if brew tap | grep -Fqx "aws/tap"; then
  HOMEBREW_NO_AUTO_UPDATE=1 brew untap aws/tap
fi

if ! brew tap | grep -Fqx "${TAP_NAME}"; then
  brew tap-new --no-git "${TAP_NAME}"
fi
TAP_ROOT="$(brew --repository "${TAP_NAME}")"
readonly TAP_ROOT
install -d -m 0755 "${TAP_ROOT}/Formula" "${TAP_ROOT}/Casks"

install_pinned_formula() {
  local token="$1"
  local expected_version="$2"
  local commit="$3"
  local source_path="$4"
  local source_sha256="$5"
  local source="${temporary_root}/${token//@/_}.rb"
  local target="${TAP_ROOT}/Formula/${token}.rb"
  local url="https://raw.githubusercontent.com/Homebrew/homebrew-core/${commit}/${source_path}"

  download_verified "${url}" "${source_sha256}" "${source}"
  python3 - "${source}" "${target}" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
marker = "  bottle do\n"
if source.count(marker) != 1:
    raise SystemExit("pinned Homebrew formula has an unexpected bottle contract")
# Homebrew core formulas can carry no_autobump!, but that publication
# directive is rejected in a temporary non-official tap. Remove only the
# metadata directive; the downloaded formula body and checksum remain bound.
autobump_lines = [
    line for line in source.splitlines(keepends=True)
    if line.startswith("  no_autobump!")
]
if len(autobump_lines) > 1:
    raise SystemExit("pinned Homebrew formula has an unexpected no_autobump contract")
if autobump_lines:
    # no_autobump! is official-tap publication metadata. Homebrew rejects it
    # in a local tap; removing it does not alter source or bottle identity.
    source = source.replace(autobump_lines[0], "", 1)
target = source.replace(
    marker,
    marker + '    root_url "https://ghcr.io/v2/homebrew/core"\n',
    1,
)
Path(sys.argv[2]).write_text(target, encoding="utf-8")
PY

  if brew list --formula --versions "${token}" >/dev/null 2>&1; then
    brew uninstall --formula --force --ignore-dependencies "${token}"
  fi
  if [[ "${token}" == "node" ]]; then
    # setup-node and the hosted image may leave a linked node@22/node@24
    # installation behind. The pinned custom-tap Node must own the PATH
    # symlinks without overwriting another formula's files.
    while IFS= read -r installed_formula; do
      case "${installed_formula}" in
        node|node@*) HOMEBREW_NO_AUTO_UPDATE=1 brew unlink "${installed_formula}" ;;
      esac
    done < <(brew list --formula)
  fi
  HOMEBREW_NO_AUTO_UPDATE=1 brew install --formula --force-bottle "${TAP_NAME}/${token}"
  if [[ "$(brew list --formula --versions "${token}")" != "${token} ${expected_version}" ]]; then
    printf 'Pinned Homebrew formula version mismatch for %s\n' "${token}" >&2
    exit 3
  fi
}

verify_pinned_ada_url_abi_link() {
  local root="$1"
  local versioned_library="$2"
  local abi_link="$3"
  local link_target
  local resolved_target
  if [[ ! -L "${abi_link}" ]]; then
    return 1
  fi
  link_target="$(readlink "${abi_link}")" || return 1
  if [[ "${link_target}" != "libada.3.4.4.dylib" ]]; then
    return 1
  fi
  resolved_target="$("${REALPATH_PATH}" "${abi_link}")" || return 1
  case "${resolved_target}" in
    "${root}"/*) ;;
    *) return 1 ;;
  esac
  [[ "${resolved_target}" == "${versioned_library}" ]]
}

verify_pinned_formula_opt_link() {
  local root="$1"
  local opt_link="$2"
  local resolved_target
  if [[ ! -L "${opt_link}" ]]; then
    return 1
  fi
  resolved_target="$("${REALPATH_PATH}" "${opt_link}")" || return 1
  [[ "${resolved_target}" == "${root}" ]]
}

install_pinned_ada_url() {
  install_pinned_formula \
    "ada-url" "3.4.4" \
    "98aa23ff4d1956be3df92906ff21b7e2b4c7a14b" \
    "Formula/a/ada-url.rb" \
    "db3cda12f2efe5c488b074bdab022a3a22db56700e8687473c8f6807963b02aa"
  readonly ADA_URL_ROOT="${HOMEBREW_CELLAR}/ada-url/3.4.4"
  readonly ADA_URL_LIBRARY="${ADA_URL_ROOT}/lib/libada.3.4.4.dylib"
  readonly ADA_URL_ABI_LINK="${ADA_URL_ROOT}/lib/libada.3.dylib"
  readonly ADA_URL_OPT_LINK="${HOMEBREW_PREFIX}/opt/ada-url"
  if [[ ! -f "${ADA_URL_LIBRARY}" || -L "${ADA_URL_LIBRARY}" \
    || "$(stat -f '%z' "${ADA_URL_LIBRARY}")" != "616512" \
    || "$(file_sha256 "${ADA_URL_LIBRARY}")" != "77917065434cb8263f1bd0768b0e54cda7793269be8a4d11d4bf72a67211881c" ]]; then
    printf 'Pinned ada-url identity does not provide the exact libada.3 closure.\n' >&2
    exit 3
  fi
  if ! verify_pinned_formula_opt_link "${ADA_URL_ROOT}" "${ADA_URL_OPT_LINK}"; then
    printf 'Pinned ada-url opt link escapes or drifts from the exact Cellar root.\n' >&2
    exit 3
  fi
  if ! verify_pinned_ada_url_abi_link \
      "${ADA_URL_ROOT}" "${ADA_URL_LIBRARY}" "${ADA_URL_ABI_LINK}"; then
    printf 'Pinned ada-url ABI link escapes or drifts from the exact library.\n' >&2
    exit 3
  fi
  if ! /usr/bin/codesign --verify --strict "${ADA_URL_LIBRARY}"; then
    printf 'Pinned ada-url library signature verification failed.\n' >&2
    exit 3
  fi
}

install_pinned_cask() {
  local token="$1"
  local expected_version="$2"
  local commit="$3"
  local source_path="$4"
  local source_sha256="$5"
  local source="${temporary_root}/${token}.rb"
  local target="${TAP_ROOT}/Casks/${token}.rb"
  local url="https://raw.githubusercontent.com/Homebrew/homebrew-cask/${commit}/${source_path}"

  download_verified "${url}" "${source_sha256}" "${source}"
  install -m 0444 "${source}" "${target}"
  if brew list --cask --versions "${token}" >/dev/null 2>&1; then
    brew uninstall --cask --force "${token}"
  fi
  HOMEBREW_NO_AUTO_UPDATE=1 brew install --cask "${TAP_NAME}/${token}"
  if [[ "$(brew list --cask --versions "${token}")" != "${token} ${expected_version}" ]]; then
    printf 'Pinned Homebrew cask version mismatch for %s\n' "${token}" >&2
    exit 3
  fi
}

install_pinned_uv() {
  install_pinned_formula \
    "uv" "0.11.16" \
    "b6942cd097e4bea3caf268ea8ff418b749f6d2f3" \
    "Formula/u/uv.rb" \
    "a85594f7cc529d80a545785cb31e684470d12e33f86808b8c2fe1574bae1f36d"

  # The hosted-runner closure binds the immutable arm64 Tahoe bottle receipt.
  # A developer workstation may contain a locally rebuilt or re-signed binary
  # with the same version string; that is a different receipt and is never
  # accepted here. Normalize only filesystem metadata on the disposable runner,
  # then verify the bottle bytes and version independently of Homebrew's state.
  chmod 0555 "${UV_PATH}"
  if [[ "$(stat -f '%u:%g' "${UV_PATH}")" != "501:80" ]]; then
    sudo chown 501:80 "${UV_PATH}"
  fi
  readonly expected_uv_version="uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)"
  readonly observed_uv_receipt="$(stat -f '%Lp:%u:%g:%l:%z' "${UV_PATH}")"
  readonly observed_uv_sha256="$(file_sha256 "${UV_PATH}")"
  readonly observed_uv_version="$("${UV_PATH}" --version)"
  if [[ "${observed_uv_receipt}" != "555:501:80:1:46508144" \
    || "${observed_uv_sha256}" != "96e422f83fd306848446170d97c1d1af8290f00e4aacfa7134e130280d573126" \
    || "${observed_uv_version}" != "${expected_uv_version}" ]]; then
    printf 'Pinned uv receipt mismatch: metadata=%s sha256=%s version=%s\n' \
      "${observed_uv_receipt}" "${observed_uv_sha256}" "${observed_uv_version}" >&2
    exit 3
  fi
}

if [[ "${CI_PROFILE}" == "typed-sql" || "${CI_PROFILE}" == "full" \
  || "${CI_PROFILE}" == "frontend-formal" ]]; then
  install_pinned_formula \
    "sqlite" "3.53.3" \
    "0394ff5fbc5b66a3c7e8787cdc26ae23d2d8a1aa" \
    "Formula/s/sqlite.rb" \
    "095e3e37a0e81c397362801a80c0d8420ca4d7f918b854926bc8da2c218abe4d"
fi

if [[ "${CI_PROFILE}" == "typed-sql" ]]; then
  install_pinned_uv
  install_pinned_formula \
    "python@3.14" "3.14.6" \
    "38adcf3b2e2f5f90f72fb559467495200b1ee8bb" \
    "Formula/p/python@3.14.rb" \
    "a658a88637d2d4668c7d98e0b32e3c38fc2e30695e614d061b7017b8d9b208b3"
  {
    printf '%s\n' "${HOMEBREW_CELLAR}/uv/0.11.16/bin"
    printf '%s\n' "$(brew --prefix python@3.14)/bin"
  } >>"${GITHUB_PATH}"
  if [[ "$("${UV_PATH}" --version)" != "uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)" ]]; then
    printf 'Pinned uv identity does not match the typed SQL runtime.\n' >&2
    exit 3
  fi
  "$(brew --prefix python@3.14)/bin/python3.14" - <<'PY'
import platform
import sqlite3

assert platform.machine() == "arm64", platform.machine()
assert platform.python_version() == "3.14.6", platform.python_version()
assert sqlite3.sqlite_version == "3.53.3", sqlite3.sqlite_version
PY
  exit 0
fi

if [[ "${CI_PROFILE}" == "frontend-formal" ]]; then
  # The Batch 32 receipt binds the verifier to the Homebrew Node 26.0.0
  # bottle and its /opt/homebrew Cellar identity. Install the complete named
  # dependency closure before the historical bottle so hosted-image updates
  # cannot silently substitute a newer Node binary.
  HOMEBREW_NO_AUTO_UPDATE=1 brew install \
    brotli c-ares hdrhistogram_c icu4c@78 libnghttp2 libnghttp3 \
    libngtcp2 libuv merve nbytes openssl@3 simdjson simdutf uvwasi zstd
  install_pinned_ada_url
  # Node 26.0.0 was built against llhttp 9.4.1. Homebrew's rolling hosted
  # image currently carries 9.4.2, whose ABI removed the symbol Node loads;
  # install the exact historical bottle from the same signed formula commit
  # before checking the Node executable.
  install_pinned_formula \
    "llhttp" "9.4.1" \
    "98aa23ff4d1956be3df92906ff21b7e2b4c7a14b" \
    "Formula/l/llhttp.rb" \
    "9ac45f03b3eb376fb6deb22eafea34e914b9f5f3cab1a80416d58b56ea8cdcfa"
  install_pinned_formula \
    "node" "26.0.0" \
    "98aa23ff4d1956be3df92906ff21b7e2b4c7a14b" \
    "Formula/n/node.rb" \
    "cd0800e004cdb76cebfdc6d0647ddfe7bfa38880152200a30366b822aa18a9ba"
  readonly FRONTEND_NODE="${HOMEBREW_CELLAR}/node/26.0.0/bin/node"
  if [[ ! -x "${FRONTEND_NODE}" \
    || "$(stat -f '%z' "${FRONTEND_NODE}")" != "68672" \
    || "$(file_sha256 "${FRONTEND_NODE}")" != "73cc3e9b5d2b1753ea3395a5bf39787ef85f20f048a0f0744761860b81b8fbdb" \
    || "$("${FRONTEND_NODE}" --version)" != "v26.0.0" ]]; then
    printf 'Pinned frontend Node identity does not match the formal receipt: path=%s bytes=%s sha256=%s version=%s\n' \
      "${FRONTEND_NODE}" "$(stat -f '%z' "${FRONTEND_NODE}" 2>/dev/null || true)" \
      "$(file_sha256 "${FRONTEND_NODE}")" \
      "$("${FRONTEND_NODE}" --version 2>&1 || true)" >&2
    exit 3
  fi
  printf '%s\n' "${HOMEBREW_PREFIX}/bin" >>"${GITHUB_PATH}"
  exit 0
fi

install_pinned_uv

if [[ "${CI_PROFILE}" == "full" || "${CI_PROFILE}" == "java-python" ]]; then
  : "${JAVA_HOME:?JAVA_HOME must be provided by actions/setup-java}"
  readonly TEMURIN_JAVA_HOME="$(cd "${JAVA_HOME}" && pwd -P)"
  readonly TEMURIN_JAVA_HOME_SUFFIX="Java_Temurin-Hotspot_jdk/21.0.11-10.0/arm64/Contents/Home"
  if [[ "${TEMURIN_JAVA_HOME}" != */${TEMURIN_JAVA_HOME_SUFFIX} ]]; then
    printf 'setup-java did not provide the pinned Temurin home: %s\n' "${TEMURIN_JAVA_HOME}" >&2
    exit 3
  fi
  readonly TEMURIN_JAVA_BUNDLE="$(cd "${TEMURIN_JAVA_HOME}/../.." && pwd -P)"
  readonly TEMURIN_JAVA_SHA256="afb8ed976e06d85c89192312923301959535169abe087d70166cd00fb96de2e5"
  readonly TEMURIN_JAVAC_SHA256="56d42d414a2dfb4ca26a67074ebc7c64271fcf37e5ca6f2d6db2f6c292b5daf1"
  readonly TEMURIN_JAVA_MODULES_SHA256="915c525cd0b9d4db404cdc2368bfb4f3e0ab2a6a598b2d6a76d932de19dd2d33"
  readonly TEMURIN_JAVA_JVM_SHA256="34bc0bc23d87abb85147409ccdbf604ccd3d2fe8b83ac567a966a5df8a81eded"
  readonly TEMURIN_JAVA_RELEASE_SHA256="5fccc331767cf526748f17402c7355efb0d1c24f397c49ff9836760f4a3f3d17"
  readonly TEMURIN_JAVA_CDHASH_FULL="e392fdd40bd00e2e6a6986716901ee08ad1e0200e65bdafab50f70554364a5a2"
  readonly TEMURIN_JAVA_VERSION="$(printf '%s\n' \
    'openjdk version "21.0.11" 2026-04-21 LTS' \
    'OpenJDK Runtime Environment Temurin-21.0.11+10 (build 21.0.11+10-LTS)' \
    'OpenJDK 64-Bit Server VM Temurin-21.0.11+10 (build 21.0.11+10-LTS, mixed mode, sharing)')"
  if [[ "$(file_sha256 "${TEMURIN_JAVA_HOME}/bin/java")" != "${TEMURIN_JAVA_SHA256}" \
    || "$(file_sha256 "${TEMURIN_JAVA_HOME}/bin/javac")" != "${TEMURIN_JAVAC_SHA256}" \
    || "$(file_sha256 "${TEMURIN_JAVA_HOME}/lib/modules")" != "${TEMURIN_JAVA_MODULES_SHA256}" \
    || "$(file_sha256 "${TEMURIN_JAVA_HOME}/lib/server/libjvm.dylib")" != "${TEMURIN_JAVA_JVM_SHA256}" \
    || "$(file_sha256 "${TEMURIN_JAVA_HOME}/release")" != "${TEMURIN_JAVA_RELEASE_SHA256}" \
    || "$("${TEMURIN_JAVA_HOME}/bin/java" -version 2>&1)" != "${TEMURIN_JAVA_VERSION}" \
    || "$("${TEMURIN_JAVA_HOME}/bin/javac" -version 2>&1)" != "javac 21.0.11" ]]; then
    printf 'Pinned Temurin Java identity mismatch.\n' >&2
    exit 3
  fi
  if ! /usr/bin/codesign --verify --deep --strict "${TEMURIN_JAVA_BUNDLE}"; then
    printf 'Pinned Temurin Java bundle signature verification failed.\n' >&2
    exit 3
  fi
  readonly TEMURIN_JAVA_SIGNATURE="$(/usr/bin/codesign -d --verbose=4 "${TEMURIN_JAVA_BUNDLE}" 2>&1)"
  if [[ "${TEMURIN_JAVA_SIGNATURE}" != *'Identifier=net.java.openjdk.jdk'* \
    || "${TEMURIN_JAVA_SIGNATURE}" != *'TeamIdentifier=JCDTMS22B4'* \
    || "${TEMURIN_JAVA_SIGNATURE}" != *"CandidateCDHashFull sha256=${TEMURIN_JAVA_CDHASH_FULL}"* ]]; then
    printf 'Pinned Temurin Java signed identity mismatch.\n' >&2
    exit 3
  fi
else
  install_pinned_formula \
    "openjdk@21" "21.0.11" \
    "c739c5820462b4ca246f217cbc164ce7348bc48a" \
    "Formula/o/openjdk@21.rb" \
    "748be615c1c7b6713143e88aa2895d93f6a1fbbb2ae17e6566cd38c869bad647"
fi

if [[ "${CI_PROFILE}" == "full" ]]; then
  # Node's fixed Mach-O receipt includes every non-system dynamic dependency.
  # Install the named closure before the historical Node bottle; the engine
  # hashes every resolved component and fails closed if any formula has drifted.
  HOMEBREW_NO_AUTO_UPDATE=1 brew install \
    brotli c-ares hdrhistogram_c icu4c@78 libnghttp2 libnghttp3 \
    libngtcp2 libuv merve nbytes openssl@3 simdjson simdutf uvwasi zstd
  install_pinned_ada_url
  install_pinned_formula \
    "llhttp" "9.4.1" \
    "98aa23ff4d1956be3df92906ff21b7e2b4c7a14b" \
    "Formula/l/llhttp.rb" \
    "9ac45f03b3eb376fb6deb22eafea34e914b9f5f3cab1a80416d58b56ea8cdcfa"
  install_pinned_formula \
    "dotnet" "10.0.301" \
    "12d2ab0af5e553745d065e02d444f8985983c03a" \
    "Formula/d/dotnet.rb" \
    "65854fa2f41c3b0fbaea531ed3e105676757a3f792330e84e8bc4b8393cde041"
  install_pinned_formula \
    "node" "26.0.0" \
    "98aa23ff4d1956be3df92906ff21b7e2b4c7a14b" \
    "Formula/n/node.rb" \
    "cd0800e004cdb76cebfdc6d0647ddfe7bfa38880152200a30366b822aa18a9ba"
  install_pinned_formula \
    "php" "8.5.9" \
    "484c7c82b30520d6e2213fa9e1cad855b0385dc1" \
    "Formula/p/php.rb" \
    "57d8566ea1cac7b67fb12b66eaa3a56bf82e5f2665a366c7b171020f44a1fe7d"
  install_pinned_cask \
    "flutter" "3.44.1" \
    "a2577b1c0ea25dd77e22a00515c8eb06d111ceff" \
    "Casks/f/flutter.rb" \
    "476d39d9cd9a9f2af485a61888dcdc646ca659b106b7d05a934e91efd3e62510"
fi

readonly CAPTURE_ROOT="${REPOSITORY_ROOT}/routes/cpp-to-java/certification/formal-artifacts/engine-sources/runtime"
readonly PYTHON_ARCHIVE_SHA256="22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84"
readonly PYTHON_ARCHIVE="${CAPTURE_ROOT}/python/sha256-${PYTHON_ARCHIVE_SHA256}.tar.gz"
readonly PYTHON_ARCHIVE_TARGET="${TOOLCHAIN_ROOT}/python-build-standalone/archives/sha256-${PYTHON_ARCHIVE_SHA256}.tar.gz"
readonly PYTHON_RUNTIME_PARENT="${TOOLCHAIN_ROOT}/python-build-standalone/runtimes/3.12.12+20260211-aarch64-apple-darwin/sha256-1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154"
readonly PYTHON_RUNTIME_TARGET="${PYTHON_RUNTIME_PARENT}/python"

if [[ ! -f "${PYTHON_ARCHIVE}" || -L "${PYTHON_ARCHIVE}" \
  || "$(file_sha256 "${PYTHON_ARCHIVE}")" != "${PYTHON_ARCHIVE_SHA256}" ]]; then
  printf 'Repository Python capture is missing or does not match its pinned digest.\n' >&2
  exit 3
fi
if [[ ! -e "${PYTHON_RUNTIME_TARGET}" ]]; then
  install -d -m 0755 "$(dirname "${PYTHON_ARCHIVE_TARGET}")" "${PYTHON_RUNTIME_PARENT}"
  install -m 0444 "${PYTHON_ARCHIVE}" "${PYTHON_ARCHIVE_TARGET}"
  python_entries="${temporary_root}/python-entries.txt"
  tar -tzf "${PYTHON_ARCHIVE}" >"${python_entries}"
  while IFS= read -r entry; do
    case "${entry}" in
      python|python/*) ;;
      *) printf 'Python capture contains an out-of-root entry: %s\n' "${entry}" >&2; exit 3 ;;
    esac
    case "/${entry}/" in
      *'/../'*|*'/./'*) printf 'Python capture contains an unsafe entry: %s\n' "${entry}" >&2; exit 3 ;;
    esac
  done <"${python_entries}"
  python_stage="${temporary_root}/python-stage"
  install -d -m 0755 "${python_stage}"
  tar -xzf "${PYTHON_ARCHIVE}" -C "${python_stage}"
  mv "${python_stage}/python" "${PYTHON_RUNTIME_TARGET}"
fi
if [[ -L "${PYTHON_RUNTIME_TARGET}" || ! -d "${PYTHON_RUNTIME_TARGET}" ]]; then
  printf 'Materialized Python runtime root is unavailable or unsafe.\n' >&2
  exit 3
fi
# The captured archive preserves its source modes, while the Batch 29 runtime
# manifest deliberately accepts only an owner-bound immutable tree.  Seal the
# disposable CI copy exactly like fresh_route_runtime._extract_python: retain
# executable intent, remove every write bit, and make all directories 0555.
find "${PYTHON_RUNTIME_TARGET}" -type f -perm -0100 -exec chmod 0555 {} +
find "${PYTHON_RUNTIME_TARGET}" -type f ! -perm -0100 -exec chmod 0444 {} +
find "${PYTHON_RUNTIME_TARGET}" -type d -exec chmod 0555 {} +

readonly TYPESCRIPT_CAPTURE_SHA256="61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
readonly TYPESCRIPT_CAPTURE="${CAPTURE_ROOT}/typescript/sha256-${TYPESCRIPT_CAPTURE_SHA256}"
readonly TYPESCRIPT_TARGET="${TOOLCHAIN_ROOT}/typescript/5.9.2/sha256-${TYPESCRIPT_CAPTURE_SHA256}"
if [[ "${CI_PROFILE}" == "full" || "${CI_PROFILE}" == "java-python" ]]; then
  if [[ ! -d "${TYPESCRIPT_CAPTURE}" || -L "${TYPESCRIPT_CAPTURE}" ]]; then
    printf 'Repository TypeScript capture is unavailable or unsafe.\n' >&2
    exit 3
  fi
  if [[ ! -e "${TYPESCRIPT_TARGET}" ]]; then
    install -d -m 0755 "$(dirname "${TYPESCRIPT_TARGET}")"
    cp -R "${TYPESCRIPT_CAPTURE}" "${TYPESCRIPT_TARGET}"
    install -d -m 0755 "${TYPESCRIPT_TARGET}/bin"
    printf '%s\n' '#!/usr/bin/env node' "require('../lib/tsc.js')" >"${TYPESCRIPT_TARGET}/bin/tsc"
    find "${TYPESCRIPT_TARGET}" -type f -exec chmod 0444 {} +
    chmod 0555 "${TYPESCRIPT_TARGET}/bin/tsc"
    find "${TYPESCRIPT_TARGET}" -type d -exec chmod 0555 {} +
  fi

  # Reuse the route runtime's exact inventory, byte, digest, ownership, mode,
  # and anti-race checks before exposing this closure to a later CI step.
  # This validates both a fresh copy and any pre-existing disposable-runner
  # cache; an incomplete, writable, or substituted tree fails closed here.
  PYTHONDONTWRITEBYTECODE=1 python3 - "${REPOSITORY_ROOT}" "${TYPESCRIPT_TARGET}" <<'PY'
import sys
from pathlib import Path

repository = Path(sys.argv[1])
target = Path(sys.argv[2])
sys.path.insert(0, str(repository / "scripts" / "batch29"))
import fresh_route_runtime  # noqa: E402

fresh_route_runtime._typescript_runtime_manifest(target)
PY
fi

if [[ "${CI_PROFILE}" == "full" ]]; then
  HOME="${PINNED_HOME}" \
  ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_PROJECT_SYNTHESIS_LOCAL_BIN="${PINNED_BIN}" \
  ELMOS_PROJECT_SYNTHESIS_INSTALL_ONLY="go,rust" \
    bash "${REPOSITORY_ROOT}/scripts/toolchains/install_project_synthesis_toolchains.sh"

  HOME="${PINNED_HOME}" \
  ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_JAVA21_DISTRIBUTION="temurin" \
  ELMOS_JAVA21_HOME="${TEMURIN_JAVA_HOME}" \
    bash "${REPOSITORY_ROOT}/scripts/toolchains/install_polyglot_route_toolchains.sh"
fi

{
  if [[ "${CI_PROFILE}" == "full" || "${CI_PROFILE}" == "java-python" ]]; then
    printf 'ELMOS_JAVA21_DISTRIBUTION=temurin\n'
    printf 'ELMOS_JAVA21_HOME=%s\n' "${TEMURIN_JAVA_HOME}"
  else
    printf 'ELMOS_JAVA21_DISTRIBUTION=homebrew\n'
    printf 'ELMOS_JAVA21_HOME=%s\n' "${HOMEBREW_CELLAR}/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home"
  fi
  printf 'ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT=%s\n' "${TOOLCHAIN_ROOT}"
  printf 'ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT=%s\n' "${TOOLCHAIN_ROOT}"
  printf 'ELMOS_POLYGLOT_ROUTE_HOMEBREW_PREFIX=%s\n' "${HOMEBREW_PREFIX}"
  printf 'ELMOS_BATCH29_PINNED_UV_PATH=%s\n' "${UV_PATH}"
  printf 'ELMOS_BATCH29_TOOLCHAIN_CACHE_ANCHOR=%s\n' "${PINNED_LOCAL}"
  printf 'ELMOS_POLYGLOT_ROUTE_CI_PROFILE=%s\n' "${CI_PROFILE}"
} >>"${GITHUB_ENV}"
if [[ "${CI_PROFILE}" == "full" || "${CI_PROFILE}" == "java-python" ]]; then
  printf '%s\n' "${HOMEBREW_CELLAR}/uv/0.11.16/bin" >>"${GITHUB_PATH}"
fi
if [[ "${CI_PROFILE}" == "full" ]]; then
  {
    printf '%s\n' "${HOMEBREW_PREFIX}/bin"
    printf '%s\n' "${PINNED_BIN}"
  } >>"${GITHUB_PATH}"
fi

if [[ "${CI_PROFILE}" == "full" || "${CI_PROFILE}" == "java-python" ]]; then
  "${TEMURIN_JAVA_HOME}/bin/java" -version
else
  "${HOMEBREW_CELLAR}/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home/bin/java" -version
fi
"${PYTHON_RUNTIME_TARGET}/bin/python3.12" --version
if [[ "${CI_PROFILE}" == "full" ]]; then
  "${HOMEBREW_CELLAR}/dotnet/10.0.301/libexec/dotnet" --version
  "${HOMEBREW_CELLAR}/node/26.0.0/bin/node" --version
  "${TOOLCHAIN_ROOT}/go/1.25.0/bin/go" version
  "${TOOLCHAIN_ROOT}/rust/1.89.0/rustup/toolchains/1.89.0-aarch64-apple-darwin/bin/rustc" --version
  "${HOMEBREW_CELLAR}/php/8.5.9/bin/php" --version | sed -n '1,2p'
  "${TOOLCHAIN_ROOT}/kotlin/2.2.20/bin/kotlinc" -version
  "${HOMEBREW_PREFIX}/share/flutter/bin/cache/dart-sdk/bin/dart" --version
fi
