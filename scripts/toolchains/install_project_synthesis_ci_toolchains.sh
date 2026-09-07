#!/usr/bin/env bash
set -euo pipefail

umask 022

readonly MAVEN_VERSION="3.9.10"
readonly MAVEN_SHA512="4ef617e421695192a3e9a53b3530d803baf31f4269b26f9ab6863452d833da5530a4d04ed08c36490ad0f141b55304bceed58dbf44821153d94ae9abf34d0e1b"
readonly PHP_VERSION="8.4.12"
readonly PHP_SHA256="c1b7978cbb5054eed6c749bde4444afc16a3f2268101fb70a7d5d9b1083b12ad"
readonly POSTGRES_VERSION="17.5"
readonly POSTGRES_SHA256="730bfef34b03825c051ae0fc37542c8be26b55a44e472369221afd397196e303"
readonly BUILD_JOBS="${ELMOS_PROJECT_SYNTHESIS_BUILD_JOBS:-2}"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  printf 'This CI installer supports only Linux x86_64.\n' >&2
  exit 2
fi
case "${BUILD_JOBS}" in
  [1-8]) ;;
  *) printf 'ELMOS_PROJECT_SYNTHESIS_BUILD_JOBS must be an integer from 1 through 8.\n' >&2; exit 2 ;;
esac
: "${RUNNER_TEMP:?RUNNER_TEMP must be provided by the CI runner}"
: "${GITHUB_PATH:?GITHUB_PATH must be provided by the CI runner}"
case "${RUNNER_TEMP}" in
  /*) ;;
  *) printf 'RUNNER_TEMP must be absolute.\n' >&2; exit 2 ;;
esac
case "${GITHUB_PATH}" in
  /*) ;;
  *) printf 'GITHUB_PATH must be absolute.\n' >&2; exit 2 ;;
esac

for command_name in curl sha256sum sha512sum tar make gcc pkg-config; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required host command is unavailable: %s\n' "${command_name}" >&2
    exit 2
  fi
done

readonly TOOLCHAIN_ROOT="${RUNNER_TEMP}/elmos-project-synthesis-toolchains"
if [[ -L "${TOOLCHAIN_ROOT}" || ( -e "${TOOLCHAIN_ROOT}" && ! -d "${TOOLCHAIN_ROOT}" ) ]]; then
  printf 'Unsafe CI toolchain root: %s\n' "${TOOLCHAIN_ROOT}" >&2
  exit 3
fi
mkdir -p "${TOOLCHAIN_ROOT}"
temporary_root="$(mktemp -d "${RUNNER_TEMP}/elmos-project-synthesis-build.XXXXXX")"
cleanup() {
  rm -rf -- "${temporary_root}"
}
trap cleanup EXIT

download_verified() {
  local url="$1"
  local algorithm="$2"
  local expected="$3"
  local destination="$4"
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
    --output "${destination}" "${url}"
  case "${algorithm}" in
    sha256) printf '%s  %s\n' "${expected}" "${destination}" | sha256sum --check --status ;;
    sha512) printf '%s  %s\n' "${expected}" "${destination}" | sha512sum --check --status ;;
    *) printf 'Unsupported checksum algorithm: %s\n' "${algorithm}" >&2; return 2 ;;
  esac
}

require_new_target() {
  local target="$1"
  if [[ -e "${target}" || -L "${target}" ]]; then
    printf 'Refusing to overwrite a non-matching CI toolchain: %s\n' "${target}" >&2
    exit 3
  fi
  mkdir -p "$(dirname "${target}")"
}

install_maven() {
  local target="${TOOLCHAIN_ROOT}/maven/${MAVEN_VERSION}"
  if [[ -x "${target}/bin/mvn" ]] \
    && "${target}/bin/mvn" --version | grep -q "^Apache Maven ${MAVEN_VERSION}"; then
    return
  fi
  require_new_target "${target}"
  local archive="${temporary_root}/apache-maven.tar.gz"
  local unpack="${temporary_root}/maven-unpack"
  mkdir -p "${unpack}"
  download_verified \
    "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
    sha512 "${MAVEN_SHA512}" "${archive}"
  tar -xzf "${archive}" -C "${unpack}"
  mv "${unpack}/apache-maven-${MAVEN_VERSION}" "${target}"
}

install_php() {
  local target="${TOOLCHAIN_ROOT}/php/${PHP_VERSION}"
  if [[ -x "${target}/bin/php" ]] \
    && "${target}/bin/php" --version | grep -q "^PHP ${PHP_VERSION}" \
    && "${target}/bin/php" -m | grep -qix pdo_pgsql \
    && "${target}/bin/php" -m | grep -qix openssl; then
    return
  fi
  require_new_target "${target}"
  local archive="${temporary_root}/php.tar.xz"
  local source_root="${temporary_root}/php-${PHP_VERSION}"
  download_verified \
    "https://www.php.net/distributions/php-${PHP_VERSION}.tar.xz" \
    sha256 "${PHP_SHA256}" "${archive}"
  tar -xJf "${archive}" -C "${temporary_root}"
  (
    cd "${source_root}"
    ./configure \
      --prefix="${target}" \
      --disable-all \
      --enable-cli \
      --disable-cgi \
      --disable-phpdbg \
      --without-pear \
      --enable-pdo \
      --with-pdo-pgsql \
      --with-openssl
    make -j"${BUILD_JOBS}"
    make install
  )
}

install_postgresql() {
  local target="${TOOLCHAIN_ROOT}/postgresql/${POSTGRES_VERSION}"
  if [[ -x "${target}/bin/postgres" ]] \
    && "${target}/bin/postgres" --version | grep -q "^postgres (PostgreSQL) ${POSTGRES_VERSION}$"; then
    return
  fi
  require_new_target "${target}"
  local archive="${temporary_root}/postgresql.tar.gz"
  local source_root="${temporary_root}/postgresql-${POSTGRES_VERSION}"
  download_verified \
    "https://ftp.postgresql.org/pub/source/v${POSTGRES_VERSION}/postgresql-${POSTGRES_VERSION}.tar.gz" \
    sha256 "${POSTGRES_SHA256}" "${archive}"
  tar -xzf "${archive}" -C "${temporary_root}"
  (
    cd "${source_root}"
    ./configure \
      --prefix="${target}" \
      --without-icu \
      --without-readline \
      --without-zlib
    make -j"${BUILD_JOBS}"
    make install
  )
}

install_maven
install_php
install_postgresql

"${TOOLCHAIN_ROOT}/maven/${MAVEN_VERSION}/bin/mvn" --version | sed -n '1,2p'
"${TOOLCHAIN_ROOT}/php/${PHP_VERSION}/bin/php" --version | sed -n '1,2p'
for extension in pdo_pgsql openssl hash json; do
  if ! "${TOOLCHAIN_ROOT}/php/${PHP_VERSION}/bin/php" -m | grep -qix "${extension}"; then
    printf 'PHP %s is missing required extension: %s\n' "${PHP_VERSION}" "${extension}" >&2
    exit 3
  fi
done
"${TOOLCHAIN_ROOT}/postgresql/${POSTGRES_VERSION}/bin/postgres" --version
for postgres_tool in postgres initdb pg_ctl createdb psql; do
  if [[ ! -x "${TOOLCHAIN_ROOT}/postgresql/${POSTGRES_VERSION}/bin/${postgres_tool}" ]]; then
    printf 'PostgreSQL %s is missing required tool: %s\n' "${POSTGRES_VERSION}" "${postgres_tool}" >&2
    exit 3
  fi
done

{
  printf '%s\n' "${TOOLCHAIN_ROOT}/maven/${MAVEN_VERSION}/bin"
  printf '%s\n' "${TOOLCHAIN_ROOT}/php/${PHP_VERSION}/bin"
  printf '%s\n' "${TOOLCHAIN_ROOT}/postgresql/${POSTGRES_VERSION}/bin"
} >>"${GITHUB_PATH}"
