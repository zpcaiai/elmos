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
REALPATH_PATH="$(command -v realpath)"
readonly REALPATH_PATH
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
HOMEBREW_PREFIX="$(brew --prefix)"
readonly HOMEBREW_PREFIX
HOMEBREW_CELLAR="$(brew --cellar)"
readonly HOMEBREW_CELLAR
readonly UV_PATH="${HOMEBREW_CELLAR}/uv/0.11.16/bin/uv"
readonly TAP_NAME="elmos/pinned-route-ci"
readonly CI_PROFILE="${ELMOS_POLYGLOT_ROUTE_CI_PROFILE:-full}"
temporary_root="$(mktemp -d "${RUNNER_TEMP}/elmos-route-ci-toolchains.XXXXXX")"

case "${CI_PROFILE}" in
  full|frontend-formal|java-python|typed-sql) ;;
  *) printf 'Unknown ELMOS_POLYGLOT_ROUTE_CI_PROFILE: %s\n' "${CI_PROFILE}" >&2; exit 2 ;;
esac
case "${CI_PROFILE}" in
  full)
    host_identity="${ImageOS:-}|${ImageVersion:-}|$(sw_vers -productVersion)|$(sw_vers -buildVersion)"
    if [[ "$(uname -m)" != "arm64" ]]; then
      printf 'The full pinned Node closure requires a GitHub macos26 arm64 image.\n' >&2
      exit 2
    fi
    case "${host_identity}" in
      "macos26|20260728.0273.1|26.5.2|25F84"|\
      "macos26|20260831.0337.3|26.6.2|25G83") ;;
      *)
        printf 'The full pinned Node closure requires an allowlisted exact GitHub macos26 image.\n' >&2
        exit 2
        ;;
    esac
    if [[ "${ELMOS_APPLE_ROUTE_XCODE_SEALED:-}" != "1" \
      || "${ELMOS_APPLE_ROUTE_XCODE_PHYSICAL:-}" != "/Applications/Xcode.app" \
      || -z "${TMPDIR:-}" ]]; then
      printf 'The full route profile requires the prepared Apple host seal and private TMPDIR.\n' >&2
      exit 2
    fi
    python3 -I -B - "${RUNNER_TEMP}" "${TMPDIR}" <<'PY'
import os
import stat
import subprocess
import sys
from pathlib import Path

runner_temp = Path(sys.argv[1]).resolve(strict=True)
private = Path(sys.argv[2])
metadata = private.lstat()
applications = Path("/Applications")
source_xcode = applications / "Xcode_26.6.app"
canonical_xcode = applications / "Xcode.app"
developer = canonical_xcode / "Contents/Developer"
sdk_directory = (
    developer / "Platforms/MacOSX.platform/Developer/SDKs"
)
sdk_alias = sdk_directory / "MacOSX26.5.sdk"
sdk_target = sdk_directory / "MacOSX.sdk"
applications_metadata = applications.lstat()
xcode_metadata = canonical_xcode.lstat()
sdk_alias_metadata = sdk_alias.lstat()
sdk_target_metadata = sdk_target.lstat()
if (
    private != runner_temp / "elmos-route-private-tmp"
    or private.resolve(strict=True) != private
    or not stat.S_ISDIR(metadata.st_mode)
    or metadata.st_uid != os.getuid()
    or metadata.st_gid != os.getgid()
    or stat.S_IMODE(metadata.st_mode) != 0o700
    or applications.resolve(strict=True) != applications
    or stat.S_ISLNK(applications_metadata.st_mode)
    or not stat.S_ISDIR(applications_metadata.st_mode)
    or applications_metadata.st_uid != 0
    or applications_metadata.st_gid != 0
    or stat.S_IMODE(applications_metadata.st_mode) != 0o755
    or source_xcode.exists()
    or source_xcode.is_symlink()
    or canonical_xcode.resolve(strict=True) != canonical_xcode
    or stat.S_ISLNK(xcode_metadata.st_mode)
    or not stat.S_ISDIR(xcode_metadata.st_mode)
    or xcode_metadata.st_uid != 0
    or xcode_metadata.st_gid != 0
    or stat.S_IMODE(xcode_metadata.st_mode) & 0o022
    or not stat.S_ISLNK(sdk_alias_metadata.st_mode)
    or sdk_alias_metadata.st_uid != 0
    or sdk_alias_metadata.st_gid != 0
    or os.readlink(sdk_alias) != "MacOSX.sdk"
    or sdk_alias.resolve(strict=True) != sdk_target
    or stat.S_ISLNK(sdk_target_metadata.st_mode)
    or not stat.S_ISDIR(sdk_target_metadata.st_mode)
    or sdk_target_metadata.st_uid != 0
    or sdk_target_metadata.st_gid != 0
    or stat.S_IMODE(sdk_target_metadata.st_mode) & 0o022
):
    raise SystemExit("prepared Apple route host identity is invalid")
environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"}
selected = subprocess.run(
    ["/usr/bin/xcode-select", "-p"],
    check=True,
    capture_output=True,
    text=True,
    env=environment,
).stdout.strip()
version = subprocess.run(
    ["/usr/bin/xcodebuild", "-version"],
    check=True,
    capture_output=True,
    text=True,
    env=environment,
).stdout
if selected != str(developer) or version != "Xcode 26.6\nBuild version 17F113\n":
    raise SystemExit("prepared Apple route selection is invalid")
PY
    NON_ROOT_XCODE_ENTRY="$(/usr/bin/find /Applications/Xcode.app -xdev \
      \( ! -user root -o ! -group wheel \) -print -quit)"
    readonly NON_ROOT_XCODE_ENTRY
    if [[ -n "${NON_ROOT_XCODE_ENTRY}" ]]; then
      printf 'The prepared Xcode tree contains an unsealed entry: %s\n' \
        "${NON_ROOT_XCODE_ENTRY}" >&2
      exit 2
    fi
    ;;
  frontend-formal)
    host_identity="${ImageOS:-}|${ImageVersion:-}|$(sw_vers -productVersion)|$(sw_vers -buildVersion)"
    case "${host_identity}" in
      "macos15|20260727.0256.1|15.7.7|24G720"|\
      "macos15|20260829.0321.1|15.7.9|24G830") ;;
      *)
        printf 'The frontend formal Node closure requires an allowlisted exact GitHub macos15 image.\n' >&2
        exit 2
        ;;
    esac
    if [[ "$(uname -m)" != "arm64" ]]; then
      printf 'The frontend formal Node closure requires arm64.\n' >&2
      exit 2
    fi
    ;;
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
  python3 - "${source}" "${target}" "${token}" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
token = sys.argv[3]
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
# OpenSSL 3.6.3 uses the current Homebrew `symlink(..., overwrite: true)`
# post-install DSL, while the rolling macOS 26 image can still carry a brew
# version that rejects that keyword. A fresh, force-bottle install has no
# destination to overwrite, so remove only this digest-bound compatibility
# keyword and fail if the pinned formula's exact statement ever changes.
openssl_overwrite = (
    '    symlink "{{etc}}/ca-certificates/cert.pem", '
    '"{{pkgetc}}/cert.pem", overwrite: true\n'
)
if token == "openssl@3":
    if source.count(openssl_overwrite) != 1:
        raise SystemExit("pinned OpenSSL formula has an unexpected symlink contract")
    source = source.replace(openssl_overwrite, openssl_overwrite.replace(", overwrite: true", ""), 1)
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
    local installed_formula_inventory
    installed_formula_inventory="$(brew list --formula)"
    readonly installed_formula_inventory
    while IFS= read -r installed_formula; do
      case "${installed_formula}" in
        node|node@*) HOMEBREW_NO_AUTO_UPDATE=1 brew unlink "${installed_formula}" ;;
      esac
    done <<<"${installed_formula_inventory}"
  fi
  HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_UPGRADE=1 \
    brew install --formula --force-bottle "${TAP_NAME}/${token}"
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

verify_pinned_ada_url_library_identity() {
  local library="$1"
  local byte_count
  local sha256
  if [[ ! -f "${library}" || -L "${library}" ]]; then
    return 1
  fi
  byte_count="$(stat -f '%z' "${library}")" || return 1
  sha256="$(file_sha256 "${library}")" || return 1
  case "${byte_count}:${sha256}" in
    "616512:77917065434cb8263f1bd0768b0e54cda7793269be8a4d11d4bf72a67211881c")
      printf '%s\n' "homebrew-node26-libada-77917065434c-616512"
      ;;
    "613248:e4b04b323411a5ca0f06086ad54378f21d02831fb571f09ea61db8f20dfdedc4")
      printf '%s\n' "homebrew-node26-libada-e4b04b323411-613248"
      ;;
    "598704:b39ba5c76cfa9e8d7a37b51daf937414316b671f51360daae62b9885e9d089f8")
      printf '%s\n' "homebrew-node26-libada-b39ba5c76cfa-598704"
      ;;
    *) return 1 ;;
  esac
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
  local ada_url_library_profile
  if ! ada_url_library_profile="$(
      verify_pinned_ada_url_library_identity "${ADA_URL_LIBRARY}"
    )"; then
    local observed_byte_count
    local observed_sha256
    observed_byte_count="$(stat -f '%z' "${ADA_URL_LIBRARY}")" || exit 3
    observed_sha256="$(file_sha256 "${ADA_URL_LIBRARY}")" || exit 3
    printf 'Pinned ada-url identity does not provide the exact libada.3 closure: observed %s:%s.\n' \
      "${observed_byte_count}" "${observed_sha256}" >&2
    exit 3
  fi
  printf 'Pinned ada-url installed library profile: %s\n' \
    "${ada_url_library_profile}"
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

verify_pinned_node26_component() {
  local path="$1"
  local expected_mode="$2"
  local expected_bytes="$3"
  local expected_sha256="$4"
  local observed
  if [[ ! -f "${path}" || -L "${path}" \
    || "$("${REALPATH_PATH}" "${path}")" != "${path}" ]]; then
    printf 'Pinned Node closure component is unavailable or unsafe: %s\n' \
      "${path}" >&2
    exit 3
  fi
  observed="$(stat -f '%Lp:%u:%g:%l:%z' "${path}")"
  if [[ "${observed}" != "${expected_mode}:501:80:1:${expected_bytes}" \
    || "$(file_sha256 "${path}")" != "${expected_sha256}" ]]; then
    printf 'Pinned Node closure component identity mismatch: %s (%s)\n' \
      "${path}" "${observed}" >&2
    exit 3
  fi
}

verify_pinned_node26_formula() {
  local token="$1"
  local version="$2"
  local root="${HOMEBREW_CELLAR}/${token}/${version}"
  if [[ "$(brew list --formula --versions "${token}")" != "${token} ${version}" \
    || ! -d "${root}" || -L "${root}" ]]; then
    printf 'Pinned Node dependency formula identity mismatch: %s %s\n' \
      "${token}" "${version}" >&2
    exit 3
  fi
  if ! verify_pinned_formula_opt_link \
      "${root}" "${HOMEBREW_PREFIX}/opt/${token}"; then
    printf 'Pinned Node dependency formula identity mismatch: %s %s\n' \
      "${token}" "${version}" >&2
    exit 3
  fi
}

install_pinned_sqlite() {
  install_pinned_formula \
    "sqlite" "3.53.3" \
    "0394ff5fbc5b66a3c7e8787cdc26ae23d2d8a1aa" \
    "Formula/s/sqlite.rb" \
    "095e3e37a0e81c397362801a80c0d8420ca4d7f918b854926bc8da2c218abe4d"
}

install_pinned_node26_closure() {
  local profile="$1"
  local hdrhistogram_version
  case "${profile}" in
    tahoe) hdrhistogram_version="0.11.10" ;;
    sequoia) hdrhistogram_version="0.11.9" ;;
    *) printf 'Unknown pinned Node closure profile: %s\n' "${profile}" >&2; exit 3 ;;
  esac
  # Every non-system Mach-O dependency is installed from a checksum-bound
  # historical formula.  Homebrew's rolling core state is never allowed to
  # choose the Node runtime closure.
  install_pinned_formula \
    "fmt" "12.2.0" \
    "e34551f96be34710e1367f3fc359cd0dfb824175" \
    "Formula/f/fmt.rb" \
    "570147f9c574cc37eb0d03c79c3ab72219c10bf25c02b125e15794ff8df2d5c8"
  install_pinned_formula \
    "ca-certificates" "2026-08-13" \
    "ec405c5d64256f8ac26539983cb763114f4bf28c" \
    "Formula/c/ca-certificates.rb" \
    "268c54e7f54e318a1a31c8bcc5248fac3dca69a15eaa67c48d7b5336977a7e5d"
  install_pinned_formula \
    "readline" "8.3.3" \
    "0b3a005714b3c03cc4480d22ac96873cc7878d1b" \
    "Formula/r/readline.rb" \
    "103ccb91886fbf3ea74f18a5e3103269d6de5ade7dfc42cd7a3b021f9f90d794"
  install_pinned_formula \
    "lz4" "1.10.0" \
    "ba5f440dac7b251bb7a5fe0f907bdec7dabc521e" \
    "Formula/l/lz4.rb" \
    "befc4a1ead0d44e71245e1e90efcf232ff53a144016daa7ae3af316fffd604c6"
  install_pinned_formula \
    "xz" "5.8.3" \
    "3e79661f1e8b06e03247ec7c17b5919c6dc01f16" \
    "Formula/x/xz.rb" \
    "921db7ab1bdeb7b163d1167289602bc6a9ce36b6c36a1c6c41db725b70780514"
  install_pinned_formula \
    "brotli" "1.2.0" \
    "aa668fe77a827131cc33f49e6b008fc8eaf8e299" \
    "Formula/b/brotli.rb" \
    "1c32f38ce41b1b812e4ca7e10de5a2fcbe6af0fe97c1b51a13206d2dac296f6f"
  install_pinned_formula \
    "c-ares" "1.34.8" \
    "296b34f5c1f787794c8c44025a42d758a9ab93dd" \
    "Formula/c/c-ares.rb" \
    "ffb9deb66a92eafe54f56fd5377167eade77f3f8154eb0f711e0c1ef7acf2de6"
  if [[ "${profile}" == "tahoe" ]]; then
    install_pinned_formula \
      "hdrhistogram_c" "0.11.10" \
      "1e0add8e14c88a53a1331e2a7182ae6c770fb80d" \
      "Formula/h/hdrhistogram_c.rb" \
      "a7d9faf35413ba6004834e96c80256c49baaab6457820099e4ef82a0601416f6"
  else
    install_pinned_formula \
      "hdrhistogram_c" "0.11.9" \
      "391df221f58d84744523a0b02f4f723aa965fa4a" \
      "Formula/h/hdrhistogram_c.rb" \
      "8b9124c84378b8d6f93ed12fadc58d69b2b3e48e18f3acd3da9fb4c63b771179"
  fi
  install_pinned_formula \
    "icu4c@78" "78.3" \
    "01ff7565fafd47a00156aed4f668df9b2e28bd7d" \
    "Formula/i/icu4c@78.rb" \
    "7a814b2501490211646830c381f8c565c9281982fd56f093e4836fa8b6209177"
  install_pinned_formula \
    "libnghttp2" "1.69.0" \
    "7d6232c8cf03a649bf9c53bf222963819a5a4e9f" \
    "Formula/lib/libnghttp2.rb" \
    "8bcff8d4606c7d90c62a36925dcd2eda1488a1b6f65e59252010a8aaaccda79c"
  install_pinned_formula \
    "libnghttp3" "1.18.0" \
    "54dcaee26dfbb4bde8f648cb0b7e705c1466eaf8" \
    "Formula/lib/libnghttp3.rb" \
    "1a1ad3dcb395427220bc04e5e4c08e4972ffe382475965c991a23049dfb14f4d"
  install_pinned_formula \
    "libuv" "1.52.1" \
    "6f5fbc6144ba19af5ad45284a41e07da0b89ee19" \
    "Formula/lib/libuv.rb" \
    "14a4e73f13dccf5e8f3ca2dbe762e293561112c3f6c57eb1f1fcaae471090270"
  install_pinned_formula \
    "nbytes" "0.1.4" \
    "5a884875fcc142465b254e9a3354223524287e06" \
    "Formula/n/nbytes.rb" \
    "40bfe63190c8e3001e72823c58132b216c1a6ce1fed7e8363e3ee15a17839810"
  install_pinned_sqlite
  install_pinned_formula \
    "openssl@3" "3.6.3" \
    "ac0bc95fef0e5aed25b3662f6271020410cfbc3d" \
    "Formula/o/openssl@3.rb" \
    "2df2729c060ea67e06801020f2a700fef3d095319102ac9bb2dc6a9e4fd97154"
  install_pinned_formula \
    "libngtcp2" "1.25.0" \
    "088a2a1154c01224ff3effa87633908e28087007" \
    "Formula/lib/libngtcp2.rb" \
    "97adc2220050013e6264b9c2eb517dd383150818ff45936b9d1d919ce4ac358a"
  install_pinned_formula \
    "simdjson" "4.6.4" \
    "7f9cf3dbae617176b54d3d77bb239f62038514ae" \
    "Formula/s/simdjson.rb" \
    "ea813373ee9b95c6562dc686c7252df6c2933030bff6b1ffa3cccc039c422ac6"
  install_pinned_formula \
    "simdutf" "9.0.0" \
    "2764564107e887eeee53cd6d495f55ec3267dcfd" \
    "Formula/s/simdutf.rb" \
    "0df322cac370f8ab202be9f2483f69190e454409901f93bb709a02cfef140cfa"
  install_pinned_formula \
    "merve" "1.2.2_1" \
    "f9b0388698d085a1077a37eecc65ab0dab69d28a" \
    "Formula/m/merve.rb" \
    "3fd11bdf8ec7d76c8f25028a8222e70e22b99cd7f3cf0ca0f075ae3f45a908ff"
  install_pinned_formula \
    "uvwasi" "0.0.23" \
    "91ee0f5a25fbc9a0769cf40cc80b6239d84b1544" \
    "Formula/u/uvwasi.rb" \
    "9506603963768fc229d0dc0455bbb969cb9a9e08a64de2733908284238d9057f"
  install_pinned_formula \
    "zstd" "1.5.7_1" \
    "23f2c8d3be8ba7061d749d8827d5f26e838e8cbf" \
    "Formula/z/zstd.rb" \
    "78f2f803f82b99c7504995e2cf49ed62d9ce926b89fe02bbfefe54c5a5578aa6"
  install_pinned_ada_url
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

  while IFS='|' read -r token version; do
    verify_pinned_node26_formula "${token}" "${version}"
  done <<EOF
fmt|12.2.0
ca-certificates|2026-08-13
readline|8.3.3
lz4|1.10.0
xz|5.8.3
brotli|1.2.0
c-ares|1.34.8
hdrhistogram_c|${hdrhistogram_version}
icu4c@78|78.3
libnghttp2|1.69.0
libnghttp3|1.18.0
libngtcp2|1.25.0
libuv|1.52.1
merve|1.2.2_1
nbytes|0.1.4
openssl@3|3.6.3
simdjson|4.6.4
simdutf|9.0.0
sqlite|3.53.3
uvwasi|0.0.23
zstd|1.5.7_1
ada-url|3.4.4
llhttp|9.4.1
node|26.0.0
EOF

  if [[ "${profile}" == "tahoe" ]]; then
    while IFS='|' read -r path mode byte_count digest; do
      verify_pinned_node26_component \
        "${HOMEBREW_CELLAR}/${path}" "${mode}" "${byte_count}" "${digest}"
    done <<'EOF'
ada-url/3.4.4/lib/libada.3.4.4.dylib|444|598704|b39ba5c76cfa9e8d7a37b51daf937414316b671f51360daae62b9885e9d089f8
brotli/1.2.0/lib/libbrotlicommon.1.2.0.dylib|444|150128|eb4c35c72adfea50045e0901767820b32a6b434685c0a4753ca9d3f9b389e44f
brotli/1.2.0/lib/libbrotlidec.1.2.0.dylib|444|70128|d3e0c23866ac9123a56ff28b71ad5e0b9ccc4207f5ef56751898f5294e7eaa8b
brotli/1.2.0/lib/libbrotlienc.1.2.0.dylib|444|639056|122dd455fc4419510078c302675aa31cc4eb6a16e029e0fc96bf3798388a07c9
c-ares/1.34.8/lib/libcares.2.19.7.dylib|444|227136|380a4b57ed007eecfd8b31d27feb3ea4749125e49780f8ca55dceb6112993c77
hdrhistogram_c/0.11.10/lib/libhdr_histogram.6.3.3.dylib|444|57920|90286f692dd222d09642670523a5ef978f14b553614e6fa2d550dcb179e0d39c
icu4c@78/78.3/lib/libicudata.78.3.dylib|444|33371136|cd7bfc3af59bc6766d4fa50c7afe50b2ec009dd665b23bcc6b467978e22acf77
icu4c@78/78.3/lib/libicui18n.78.3.dylib|444|3168704|b950df7ced46bf344ed5970c50a3c751f310ad61c4a1ec170a748127aea84bf0
icu4c@78/78.3/lib/libicuuc.78.3.dylib|444|1859408|a78b3424a391c7afad52c0d69df9cdb7818b6c20f909a14d193ae0c66a5c1119
libnghttp2/1.69.0/lib/libnghttp2.14.dylib|444|184240|9e14b36e03a09a83341d716f5bc38ed1be5ef2ec74ba4c19fb20a5962615c
libnghttp3/1.18.0/lib/libnghttp3.9.9.0.dylib|444|183968|67b632b1abcb414c15ace565a5cf37a44d1a46f87fa9d65d1346b70adc94a448
libngtcp2/1.25.0/lib/libngtcp2.16.dylib|444|349904|2321f690a5ac5d3a859638ed28f58cf08fb3ce844ff9fa5fac7d2a0c2b9be0e7
libuv/1.52.1/lib/libuv.1.0.0.dylib|444|189408|c56f794e7c9dbcf8c45fba6109836196263a4d5e95936eee7601593532c6cfe9
llhttp/9.4.1/lib/libllhttp.9.4.1.dylib|444|77664|96cc6a6e381e5abc70e6763aa087ea5c43929a1aa257979d6a9e0c4ede1f3368
merve/1.2.2_1/lib/libmerve.1.2.2.dylib|444|77776|cda7651d81af902d5964705451e7bcb3c4769a971e793b33472ccf6c07e2dc58
nbytes/0.1.4/lib/libnbytes.dylib|444|35136|b063a6b50d0982379e5a78fa22904e9299ac0048d82cae4f90bd4ad11fa40f65
node/26.0.0/bin/node|555|50672|542a44a023d27e626d79fbd646f3e2b898bd291b96028b3644795f21b5a43bc9
node/26.0.0/lib/libnode.147.dylib|444|70661840|980e876ab7f53bacc6262e77c4ac96f60ca3bac4dd241b0cc6cdc945c4ecaf88
openssl@3/3.6.3/lib/libcrypto.3.dylib|444|4856256|a12805a18cd5e4f733fa8727b91afa08b587f9da5a760517cd79cb508a3a3f71
openssl@3/3.6.3/lib/libssl.3.dylib|444|872080|ffd8ac6981000def0928367924b6cb1e7a98712efbc06e2a2f3f750138bd89ca
simdjson/4.6.4/lib/libsimdjson.33.0.0.dylib|444|95296|031cfb565154f822e33b9227ef392c257260c5ebb8fbfc9f317c56be82bfa16a
simdutf/9.0.0/lib/libsimdutf.34.0.0.dylib|444|222064|2abb9e7c8fb437094c5488f74408f7dd0a7b20a16e5c871a877d60e14f53ee36
sqlite/3.53.3/lib/libsqlite3.3.53.3.dylib|444|1276320|ae5d701ec1fe829883496a1c21d3f929bc7c3565f2edf3079ce54f978b44cb7f
uvwasi/0.0.23/lib/libuvwasi.dylib|444|65616|60a4e2eb2e2ea432d38730c41816ca032b7c45b0fb713c0649cb1fed1a8691f9
zstd/1.5.7_1/lib/libzstd.1.5.7.dylib|444|635328|602d50cbe6fad0f0da6d1b73284ae3f75316015aea482ebd55614b6df2406b43
EOF
  fi
}

install_pinned_node26_sequoia_closure() {
  # Reuse the exact 23 common formulas but select the Sequoia-only
  # hdrhistogram 0.11.9 closure.  The recursive runtime preflight remains the
  # authority for the complete Mach-O/content profile.
  install_pinned_node26_closure sequoia
}

preflight_exact_route_toolchain() {
  local language="$1"
  HOME="${PINNED_HOME}" \
  ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT="${TOOLCHAIN_ROOT}" \
  ELMOS_POLYGLOT_ROUTE_HOMEBREW_PREFIX="${HOMEBREW_PREFIX}" \
  PYTHONDONTWRITEBYTECODE=1 \
    python3 -I -B - "${REPOSITORY_ROOT}" "${language}" <<'PY'
from pathlib import Path
import sys

repository = Path(sys.argv[1]).resolve(strict=True)
language = sys.argv[2]
if language not in {"javascript", "typescript"}:
    raise SystemExit(f"unsupported exact toolchain preflight: {language}")
sys.path.insert(0, str(repository / "engines" / "polyglot-route-engine" / "src"))

from elmos_polyglot_route import toolchains  # noqa: E402

receipt = toolchains.exact_toolchain(language)
if receipt.language != language or not Path(receipt.executable).is_absolute():
    raise SystemExit(f"invalid exact toolchain preflight receipt: {language}")
print(f"exact-toolchain-preflight={language}:{receipt.version}")
PY
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
  HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_UPGRADE=1 \
    brew install --cask "${TAP_NAME}/${token}"
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
  observed_uv_receipt="$(stat -f '%Lp:%u:%g:%l:%z' "${UV_PATH}")"
  readonly observed_uv_receipt
  observed_uv_sha256="$(file_sha256 "${UV_PATH}")"
  readonly observed_uv_sha256
  observed_uv_version="$("${UV_PATH}" --version)"
  readonly observed_uv_version
  if [[ "${observed_uv_receipt}" != "555:501:80:1:46508144" \
    || "${observed_uv_sha256}" != "96e422f83fd306848446170d97c1d1af8290f00e4aacfa7134e130280d573126" \
    || "${observed_uv_version}" != "${expected_uv_version}" ]]; then
    printf 'Pinned uv receipt mismatch: metadata=%s sha256=%s version=%s\n' \
      "${observed_uv_receipt}" "${observed_uv_sha256}" "${observed_uv_version}" >&2
    exit 3
  fi
}

if [[ "${CI_PROFILE}" == "typed-sql" ]]; then
  install_pinned_sqlite
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
  install_pinned_node26_sequoia_closure
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
  preflight_exact_route_toolchain javascript
  printf '%s\n' "${HOMEBREW_PREFIX}/bin" >>"${GITHUB_PATH}"
  exit 0
fi

install_pinned_uv

if [[ "${CI_PROFILE}" == "full" || "${CI_PROFILE}" == "java-python" ]]; then
  : "${JAVA_HOME:?JAVA_HOME must be provided by actions/setup-java}"
  TEMURIN_JAVA_HOME="$(cd "${JAVA_HOME}" && pwd -P)"
  readonly TEMURIN_JAVA_HOME
  case "${TEMURIN_JAVA_HOME}" in
    */Java_Temurin-Hotspot_jdk/21.0.11-10.0/arm64/Contents/Home|\
    */Java_Temurin-Hotspot_jdk/21.0.11-10.0.LTS/arm64/Contents/Home) ;;
    *)
    printf 'setup-java did not provide the pinned Temurin home: %s\n' "${TEMURIN_JAVA_HOME}" >&2
    exit 3
      ;;
  esac
  TEMURIN_JAVA_BUNDLE="$(cd "${TEMURIN_JAVA_HOME}/../.." && pwd -P)"
  readonly TEMURIN_JAVA_BUNDLE
  readonly TEMURIN_JAVA_SHA256="afb8ed976e06d85c89192312923301959535169abe087d70166cd00fb96de2e5"
  readonly TEMURIN_JAVAC_SHA256="56d42d414a2dfb4ca26a67074ebc7c64271fcf37e5ca6f2d6db2f6c292b5daf1"
  readonly TEMURIN_JAVA_MODULES_SHA256="915c525cd0b9d4db404cdc2368bfb4f3e0ab2a6a598b2d6a76d932de19dd2d33"
  readonly TEMURIN_JAVA_JVM_SHA256="34bc0bc23d87abb85147409ccdbf604ccd3d2fe8b83ac567a966a5df8a81eded"
  readonly TEMURIN_JAVA_RELEASE_SHA256="5fccc331767cf526748f17402c7355efb0d1c24f397c49ff9836760f4a3f3d17"
  readonly TEMURIN_JAVA_CDHASH_FULL="e392fdd40bd00e2e6a6986716901ee08ad1e0200e65bdafab50f70554364a5a2"
  TEMURIN_JAVA_VERSION="$(printf '%s\n' \
    'openjdk version "21.0.11" 2026-04-21 LTS' \
    'OpenJDK Runtime Environment Temurin-21.0.11+10 (build 21.0.11+10-LTS)' \
    'OpenJDK 64-Bit Server VM Temurin-21.0.11+10 (build 21.0.11+10-LTS, mixed mode, sharing)')"
  readonly TEMURIN_JAVA_VERSION
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
  TEMURIN_JAVA_SIGNATURE="$(/usr/bin/codesign -d --verbose=4 "${TEMURIN_JAVA_BUNDLE}" 2>&1)"
  readonly TEMURIN_JAVA_SIGNATURE
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
  install_pinned_node26_closure tahoe
  install_pinned_formula \
    "dotnet" "10.0.301" \
    "12d2ab0af5e553745d065e02d444f8985983c03a" \
    "Formula/d/dotnet.rb" \
    "65854fa2f41c3b0fbaea531ed3e105676757a3f792330e84e8bc4b8393cde041"
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

  # Do not publish PATH or environment bindings until the repository-owned
  # selectors have re-read the entire Node closure and TypeScript compiler
  # tree, executed the exact runtimes, and observed stable pre/post identities.
  preflight_exact_route_toolchain javascript
  preflight_exact_route_toolchain typescript
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
