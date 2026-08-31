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
for command_name in brew chmod curl git install mv python3 shasum stat sudo tar; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required host command is unavailable: %s\n' "${command_name}" >&2
    exit 2
  fi
done

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

  # Batch 29 binds the exact Homebrew bottle and its filesystem receipt.
  # GitHub image ownership can differ from the captured receipt even when the
  # bottle bytes are identical, so normalize only this immutable executable on
  # the disposable hosted runner and then verify every bound field fail-closed.
  chmod 0555 "${UV_PATH}"
  if [[ "$(stat -f '%u:%g' "${UV_PATH}")" != "501:80" ]]; then
    sudo chown 501:80 "${UV_PATH}"
  fi
  readonly expected_uv_version="uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)"
  readonly observed_uv_receipt="$(stat -f '%Lp:%u:%g:%l:%z' "${UV_PATH}")"
  readonly observed_uv_sha256="$(file_sha256 "${UV_PATH}")"
  readonly observed_uv_version="$("${UV_PATH}" --version)"
  if [[ "${observed_uv_receipt}" != "555:501:80:1:46541136" \
    || "${observed_uv_sha256}" != "d4182a7bba32f331b2c5a74568cf1c88aa50f31fe643a2c56118c6610db0aff0" \
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
    ada-url brotli c-ares hdrhistogram_c icu4c@78 libnghttp2 libnghttp3 \
    libngtcp2 libuv llhttp merve nbytes openssl@3 simdjson simdutf uvwasi zstd
  install_pinned_formula \
    "node" "26.0.0" \
    "98aa23ff4d1956be3df92906ff21b7e2b4c7a14b" \
    "Formula/n/node.rb" \
    "cd0800e004cdb76cebfdc6d0647ddfe7bfa38880152200a30366b822aa18a9ba"
  readonly FRONTEND_NODE="${HOMEBREW_CELLAR}/node/26.0.0/bin/node"
  if [[ ! -x "${FRONTEND_NODE}" \
    || "$(file_sha256 "${FRONTEND_NODE}")" != "73cc3e9b5d2b1753ea3395a5bf39787ef85f20f048a0f0744761860b81b8fbdb" \
    || "$("${FRONTEND_NODE}" --version)" != "v26.0.0" ]]; then
    printf 'Pinned frontend Node identity does not match the formal receipt.\n' >&2
    exit 3
  fi
  printf '%s\n' "${HOMEBREW_PREFIX}/bin" >>"${GITHUB_PATH}"
  exit 0
fi

install_pinned_uv

install_pinned_formula \
  "openjdk@21" "21.0.11" \
  "c739c5820462b4ca246f217cbc164ce7348bc48a" \
  "Formula/o/openjdk@21.rb" \
  "748be615c1c7b6713143e88aa2895d93f6a1fbbb2ae17e6566cd38c869bad647"

if [[ "${CI_PROFILE}" == "full" ]]; then
  # Node's fixed Mach-O receipt includes every non-system dynamic dependency.
  # Install the named closure before the historical Node bottle; the engine
  # hashes every resolved component and fails closed if any formula has drifted.
  HOMEBREW_NO_AUTO_UPDATE=1 brew install \
    ada-url brotli c-ares hdrhistogram_c icu4c@78 libnghttp2 libnghttp3 \
    libngtcp2 libuv llhttp merve nbytes openssl@3 simdjson simdutf uvwasi zstd
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

readonly TYPESCRIPT_CAPTURE_SHA256="61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
readonly TYPESCRIPT_CAPTURE="${CAPTURE_ROOT}/typescript/sha256-${TYPESCRIPT_CAPTURE_SHA256}"
readonly TYPESCRIPT_TARGET="${TOOLCHAIN_ROOT}/typescript/5.9.2/sha256-${TYPESCRIPT_CAPTURE_SHA256}"
if [[ "${CI_PROFILE}" == "full" ]]; then
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

  HOME="${PINNED_HOME}" \
  ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_PROJECT_SYNTHESIS_LOCAL_BIN="${PINNED_BIN}" \
  ELMOS_PROJECT_SYNTHESIS_INSTALL_ONLY="go,rust" \
    bash "${REPOSITORY_ROOT}/scripts/toolchains/install_project_synthesis_toolchains.sh"

  HOME="${PINNED_HOME}" \
  ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_JAVA21_HOME="${HOMEBREW_CELLAR}/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home" \
    bash "${REPOSITORY_ROOT}/scripts/toolchains/install_polyglot_route_toolchains.sh"
fi

{
  printf 'ELMOS_JAVA21_HOME=%s\n' "${HOMEBREW_CELLAR}/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home"
  printf 'ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT=%s\n' "${TOOLCHAIN_ROOT}"
  printf 'ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT=%s\n' "${TOOLCHAIN_ROOT}"
  printf 'ELMOS_POLYGLOT_ROUTE_HOMEBREW_PREFIX=%s\n' "${HOMEBREW_PREFIX}"
  printf 'ELMOS_BATCH29_PINNED_UV_PATH=%s\n' "${UV_PATH}"
  printf 'ELMOS_BATCH29_TOOLCHAIN_CACHE_ANCHOR=%s\n' "${PINNED_LOCAL}"
} >>"${GITHUB_ENV}"
if [[ "${CI_PROFILE}" == "java-python" ]]; then
  printf '%s\n' "${HOMEBREW_CELLAR}/uv/0.11.16/bin" >>"${GITHUB_PATH}"
fi
if [[ "${CI_PROFILE}" == "full" ]]; then
  {
    printf '%s\n' "${HOMEBREW_PREFIX}/bin"
    printf '%s\n' "${PINNED_BIN}"
  } >>"${GITHUB_PATH}"
fi

"${HOMEBREW_CELLAR}/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home/bin/java" -version
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
