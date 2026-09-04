#!/usr/bin/env bash
set -euo pipefail

umask 022

readonly GO_VERSION="1.25.0"
readonly GO_SHA256="544932844156d8172f7a28f77f2ac9c15a23046698b6243f633b0a0b00c0749c"
readonly GRADLE_VERSION="8.14.3"
readonly GRADLE_SHA256="bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531"
readonly PHP_VERSION="8.4.12"
readonly PHP_SHA256="c1b7978cbb5054eed6c749bde4444afc16a3f2268101fb70a7d5d9b1083b12ad"
readonly RUST_VERSION="1.89.0"
readonly RUSTUP_VERSION="1.29.0"
readonly RUSTUP_SHA256="aeb4105778ca1bd3c6b0e75768f581c656633cd51368fa61289b6a71696ac7e1"

readonly TOOLCHAIN_ROOT="${ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT:-${HOME}/.local/share/elmos/toolchains}"
readonly LOCAL_BIN="${ELMOS_PROJECT_SYNTHESIS_LOCAL_BIN:-${HOME}/.local/bin}"
readonly BUILD_JOBS="${ELMOS_PROJECT_SYNTHESIS_BUILD_JOBS:-2}"
readonly INSTALL_ONLY="${ELMOS_PROJECT_SYNTHESIS_INSTALL_ONLY:-go,gradle,php,rust}"

case "${TOOLCHAIN_ROOT}" in
  /*) ;;
  *) printf 'ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT must be absolute\n' >&2; exit 2 ;;
esac
case "${LOCAL_BIN}" in
  /*) ;;
  *) printf 'ELMOS_PROJECT_SYNTHESIS_LOCAL_BIN must be absolute\n' >&2; exit 2 ;;
esac
case "${BUILD_JOBS}" in
  [1-8]) ;;
  *) printf 'ELMOS_PROJECT_SYNTHESIS_BUILD_JOBS must be an integer from 1 through 8\n' >&2; exit 2 ;;
esac
case ",${INSTALL_ONLY}," in
  *,go,*|*,gradle,*|*,php,*|*,rust,*) ;;
  *) printf 'ELMOS_PROJECT_SYNTHESIS_INSTALL_ONLY must select at least one known tool\n' >&2; exit 2 ;;
esac
if [[ ",${INSTALL_ONLY}," == *',,'* ]]; then
  printf 'ELMOS_PROJECT_SYNTHESIS_INSTALL_ONLY contains an empty selector\n' >&2
  exit 2
fi
IFS=',' read -r -a selected_tools <<<"${INSTALL_ONLY}"
for selected_tool in "${selected_tools[@]}"; do
  case "${selected_tool}" in
    go|gradle|php|rust) ;;
    *) printf 'Unknown project-synthesis tool selector: %s\n' "${selected_tool}" >&2; exit 2 ;;
  esac
done
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  printf 'This exact installer currently supports only Darwin arm64\n' >&2
  exit 2
fi
for command_name in curl shasum tar unzip make xcrun; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required host command is unavailable: %s\n' "${command_name}" >&2
    exit 2
  fi
done
xcrun --find clang >/dev/null

mkdir -p "${TOOLCHAIN_ROOT}" "${LOCAL_BIN}"
temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/elmos-project-toolchains.XXXXXX")"
cleanup() {
  rm -rf -- "${temporary_root}"
}
trap cleanup EXIT

download_verified() {
  local url="$1"
  local expected="$2"
  local destination="$3"
  local actual
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
    --output "${destination}" "${url}"
  actual="$(shasum -a 256 "${destination}" | awk '{print $1}')"
  if [[ "${actual}" != "${expected}" ]]; then
    printf 'Checksum mismatch for %s: expected %s, observed %s\n' \
      "${url}" "${expected}" "${actual}" >&2
    exit 3
  fi
}

require_new_target() {
  local target="$1"
  if [[ -e "${target}" || -L "${target}" ]]; then
    printf 'Refusing to overwrite a non-matching toolchain target: %s\n' "${target}" >&2
    exit 3
  fi
  mkdir -p "$(dirname "${target}")"
}

link_if_available() {
  local name="$1"
  local source="$2"
  local target="${LOCAL_BIN}/${name}"
  if [[ -L "${target}" && "$(readlink "${target}")" == "${source}" ]]; then
    return
  fi
  if [[ -e "${target}" || -L "${target}" ]]; then
    printf 'Keeping existing local command instead of overwriting it: %s\n' "${target}"
    return
  fi
  ln -s "${source}" "${target}"
}

install_go() {
  local target="${TOOLCHAIN_ROOT}/go/${GO_VERSION}"
  if [[ -x "${target}/bin/go" ]] && "${target}/bin/go" version | grep -q "go${GO_VERSION}"; then
    printf 'Go %s already installed\n' "${GO_VERSION}"
  else
    require_new_target "${target}"
    local archive="${temporary_root}/go.tar.gz"
    local unpack="${temporary_root}/go-unpack"
    mkdir -p "${unpack}"
    download_verified \
      "https://go.dev/dl/go${GO_VERSION}.darwin-arm64.tar.gz" \
      "${GO_SHA256}" \
      "${archive}"
    tar -xzf "${archive}" -C "${unpack}"
    mv "${unpack}/go" "${target}"
  fi
  link_if_available "go" "${target}/bin/go"
  link_if_available "gofmt" "${target}/bin/gofmt"
}

install_gradle() {
  local target="${TOOLCHAIN_ROOT}/gradle/${GRADLE_VERSION}"
  if [[ -x "${target}/bin/gradle" ]] \
    && "${target}/bin/gradle" --version | grep -q "Gradle ${GRADLE_VERSION}"; then
    printf 'Gradle %s already installed\n' "${GRADLE_VERSION}"
  else
    require_new_target "${target}"
    local archive="${temporary_root}/gradle.zip"
    local unpack="${temporary_root}/gradle-unpack"
    mkdir -p "${unpack}"
    download_verified \
      "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
      "${GRADLE_SHA256}" \
      "${archive}"
    unzip -q "${archive}" -d "${unpack}"
    mv "${unpack}/gradle-${GRADLE_VERSION}" "${target}"
  fi
  link_if_available "gradle-${GRADLE_VERSION}" "${target}/bin/gradle"
}

resolve_libpq_prefix() {
  local candidate
  for candidate in \
    "$(brew --prefix libpq 2>/dev/null || true)" \
    "$(brew --prefix postgresql@17 2>/dev/null || true)" \
    "/usr/local" \
    "/usr"; do
    [[ -n "${candidate}" ]] || continue
    if [[ -x "${candidate}/bin/pg_config" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  printf 'Cannot build PHP with pdo_pgsql: no libpq prefix containing bin/pg_config was found.\n' >&2
  printf '%s\n' "Install it first, e.g. \`brew install libpq\`." >&2
  return 1
}

resolve_openssl_prefix() {
  # The production profile verifies RS256 bearer tokens. `--disable-all` drops
  # ext/openssl, and this build has neither gmp nor bcmath, so without the
  # extension there is no workable way to check an RSA signature in PHP.
  local candidate
  for candidate in \
    "$(brew --prefix openssl@3 2>/dev/null || true)" \
    "$(brew --prefix openssl 2>/dev/null || true)" \
    "/usr/local" \
    "/usr"; do
    [[ -n "${candidate}" ]] || continue
    if [[ -f "${candidate}/lib/pkgconfig/openssl.pc" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  printf 'Cannot build PHP with openssl: no prefix containing lib/pkgconfig/openssl.pc was found.\n' >&2
  printf '%s\n' "Install it first, e.g. \`brew install openssl@3\`." >&2
  return 1
}

# Extensions the generated production profile actually calls into. The guard
# below checks every one of them, so a build that silently drops any is
# rejected instead of failing later inside a generated workspace.
readonly PHP_REQUIRED_EXTENSIONS=(pdo_pgsql openssl hash json)

php_missing_extensions() {
  local binary="$1" extension missing=()
  for extension in "${PHP_REQUIRED_EXTENSIONS[@]}"; do
    "${binary}" -m | grep -qix "${extension}" || missing+=("${extension}")
  done
  printf '%s' "${missing[*]}"
}

install_php() {
  local target="${TOOLCHAIN_ROOT}/php/${PHP_VERSION}"
  if [[ -x "${target}/bin/php" ]] \
    && "${target}/bin/php" --version | grep -q "^PHP ${PHP_VERSION}"; then
    local missing
    missing="$(php_missing_extensions "${target}/bin/php")"
    if [[ -n "${missing}" ]]; then
      printf 'PHP %s is installed at %s but is missing required extensions: %s\n' \
        "${PHP_VERSION}" "${target}" "${missing}" >&2
      printf 'Remove it and re-run this script to rebuild with them:\n' >&2
      printf '  rm -rf %s\n' "${target}" >&2
      exit 3
    fi
    printf 'PHP %s already installed\n' "${PHP_VERSION}"
  else
    require_new_target "${target}"
    local LIBPQ_PREFIX OPENSSL_PREFIX
    LIBPQ_PREFIX="$(resolve_libpq_prefix)"
    OPENSSL_PREFIX="$(resolve_openssl_prefix)"
    printf 'Building PHP %s against libpq at %s and openssl at %s\n' \
      "${PHP_VERSION}" "${LIBPQ_PREFIX}" "${OPENSSL_PREFIX}"
    local archive="${temporary_root}/php.tar.xz"
    local source_root="${temporary_root}/php-${PHP_VERSION}"
    local stage="${temporary_root}/php-stage"
    download_verified \
      "https://www.php.net/distributions/php-${PHP_VERSION}.tar.xz" \
      "${PHP_SHA256}" \
      "${archive}"
    tar -xJf "${archive}" -C "${temporary_root}"
    (
      cd "${source_root}"
      # ext/openssl is located through pkg-config, so the prefix has to be on
      # PKG_CONFIG_PATH rather than passed as a --with argument value.
      PKG_CONFIG_PATH="${OPENSSL_PREFIX}/lib/pkgconfig:${PKG_CONFIG_PATH:-}" \
      ./configure \
        --prefix="${stage}" \
        --disable-all \
        --enable-cli \
        --disable-cgi \
        --disable-phpdbg \
        --without-pear \
        --enable-pdo \
        --with-pdo-pgsql="${LIBPQ_PREFIX}" \
        --with-openssl
      make -j"${BUILD_JOBS}"
      make install
    )
    mv "${stage}" "${target}"
  fi
  link_if_available "php" "${target}/bin/php"
}

write_rust_wrapper() {
  local target="$1"
  local command_name="$2"
  local wrapper="${target}/bin/${command_name}"
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'wrapper_path="$0"' \
    'case "${wrapper_path}" in' \
    '  */*) ;;' \
    '  *) wrapper_path="$(command -v "${wrapper_path}")" ;;' \
    'esac' \
    'while [ -L "${wrapper_path}" ]; do' \
    '  wrapper_dir="${wrapper_path%/*}"' \
    '  link_target="$(/usr/bin/readlink "${wrapper_path}")"' \
    '  case "${link_target}" in' \
    '    /*) wrapper_path="${link_target}" ;;' \
    '    *) wrapper_path="${wrapper_dir}/${link_target}" ;;' \
    '  esac' \
    'done' \
    'wrapper_dir="${wrapper_path%/*}"' \
    'wrapper_dir="$(CDPATH= cd -P -- "${wrapper_dir}" && pwd)"' \
    'toolchain_root="${wrapper_dir%/*}"' \
    'export RUSTUP_HOME="${toolchain_root}/rustup"' \
    'export CARGO_HOME="${toolchain_root}/cargo"' \
    "exec \"\${toolchain_root}/cargo/bin/${command_name}\" \"\$@\"" \
    >"${wrapper}"
  chmod 0755 "${wrapper}"
}

install_rust() {
  local target="${TOOLCHAIN_ROOT}/rust/${RUST_VERSION}"
  if [[ -x "${target}/bin/rustc" && -x "${target}/bin/cargo" ]] \
    && "${target}/bin/rustc" --version | grep -q "^rustc ${RUST_VERSION}" \
    && "${target}/bin/cargo" --version | grep -q "^cargo ${RUST_VERSION}"; then
    printf 'Rust and Cargo %s already installed\n' "${RUST_VERSION}"
  else
    require_new_target "${target}"
    local rustup_init="${temporary_root}/rustup-init"
    local stage="${temporary_root}/rust-stage"
    download_verified \
      "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/aarch64-apple-darwin/rustup-init" \
      "${RUSTUP_SHA256}" \
      "${rustup_init}"
    chmod 0755 "${rustup_init}"
    mkdir -p "${stage}/bin"
    RUSTUP_HOME="${stage}/rustup" CARGO_HOME="${stage}/cargo" \
      "${rustup_init}" -y --no-modify-path --profile minimal \
      --default-host aarch64-apple-darwin --default-toolchain "${RUST_VERSION}"
    RUSTUP_HOME="${stage}/rustup" CARGO_HOME="${stage}/cargo" \
      "${stage}/cargo/bin/rustup" component add \
      --toolchain "${RUST_VERSION}" clippy rustfmt
    write_rust_wrapper "${stage}" "rustc"
    write_rust_wrapper "${stage}" "cargo"
    write_rust_wrapper "${stage}" "rustup"
    mv "${stage}" "${target}"
  fi
  link_if_available "rustc" "${target}/bin/rustc"
  link_if_available "cargo" "${target}/bin/cargo"
  link_if_available "rustup" "${target}/bin/rustup"
}

if [[ ",${INSTALL_ONLY}," == *',go,'* ]]; then
  install_go
  "${TOOLCHAIN_ROOT}/go/${GO_VERSION}/bin/go" version
fi
if [[ ",${INSTALL_ONLY}," == *',gradle,'* ]]; then
  install_gradle
  "${TOOLCHAIN_ROOT}/gradle/${GRADLE_VERSION}/bin/gradle" --version | sed -n '1,6p'
fi
if [[ ",${INSTALL_ONLY}," == *',php,'* ]]; then
  install_php
  "${TOOLCHAIN_ROOT}/php/${PHP_VERSION}/bin/php" --version | sed -n '1,2p'
fi
if [[ ",${INSTALL_ONLY}," == *',rust,'* ]]; then
  install_rust
  "${TOOLCHAIN_ROOT}/rust/${RUST_VERSION}/bin/rustc" --version
  "${TOOLCHAIN_ROOT}/rust/${RUST_VERSION}/bin/cargo" --version
fi
printf 'Exact Project Synthesis toolchains are installed under %s\n' "${TOOLCHAIN_ROOT}"
