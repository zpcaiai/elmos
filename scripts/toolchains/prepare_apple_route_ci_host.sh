#!/usr/bin/env bash
set -euo pipefail

umask 077

readonly EXPECTED_IMAGE_OS="macos26"
readonly EXPECTED_IMAGE_VERSION="20260728.0273.1"
readonly EXPECTED_PRODUCT_VERSION="26.5.2"
readonly EXPECTED_BUILD_VERSION="25F84"
readonly EXPECTED_XCODE_VERSION="Xcode 26.6"
readonly EXPECTED_XCODE_BUILD="Build version 17F113"
readonly SOURCE_XCODE_APP="/Applications/Xcode_26.6.app"
readonly CANONICAL_XCODE_APP="/Applications/Xcode.app"
readonly SOURCE_DEVELOPER="${SOURCE_XCODE_APP}/Contents/Developer"
readonly CANONICAL_DEVELOPER="${CANONICAL_XCODE_APP}/Contents/Developer"
readonly SOURCE_SDK_DIRECTORY="${SOURCE_DEVELOPER}/Platforms/MacOSX.platform/Developer/SDKs"
readonly SOURCE_SDK_ALIAS="${SOURCE_SDK_DIRECTORY}/MacOSX26.5.sdk"
readonly SOURCE_SDK_TARGET="${SOURCE_SDK_DIRECTORY}/MacOSX.sdk"
readonly CANONICAL_SDK_DIRECTORY="${CANONICAL_DEVELOPER}/Platforms/MacOSX.platform/Developer/SDKs"
readonly CANONICAL_SDK_ALIAS="${CANONICAL_SDK_DIRECTORY}/MacOSX26.5.sdk"
readonly CANONICAL_SDK_TARGET="${CANONICAL_SDK_DIRECTORY}/MacOSX.sdk"

HOST_SYSTEM="$(/usr/bin/uname -s)"
readonly HOST_SYSTEM
HOST_MACHINE="$(/usr/bin/uname -m)"
readonly HOST_MACHINE
HOST_PRODUCT_VERSION="$(/usr/bin/sw_vers -productVersion)"
readonly HOST_PRODUCT_VERSION
HOST_BUILD_VERSION="$(/usr/bin/sw_vers -buildVersion)"
readonly HOST_BUILD_VERSION
if [[ "${HOST_SYSTEM}" != "Darwin" \
  || "${HOST_MACHINE}" != "arm64" \
  || "${GITHUB_ACTIONS:-}" != "true" \
  || "${RUNNER_ENVIRONMENT:-}" != "github-hosted" \
  || "${ImageOS:-}" != "${EXPECTED_IMAGE_OS}" \
  || "${ImageVersion:-}" != "${EXPECTED_IMAGE_VERSION}" \
  || "${HOST_PRODUCT_VERSION}" != "${EXPECTED_PRODUCT_VERSION}" \
  || "${HOST_BUILD_VERSION}" != "${EXPECTED_BUILD_VERSION}" ]]; then
  printf 'Refusing to prepare Apple route host outside the exact macos26 image.\n' >&2
  exit 2
fi
: "${RUNNER_TEMP:?RUNNER_TEMP must be provided by GitHub Actions}"
: "${GITHUB_ENV:?GITHUB_ENV must be provided by GitHub Actions}"

XCODE_VERSION_OUTPUT="$(/usr/bin/xcodebuild -version)"
readonly XCODE_VERSION_OUTPUT
EXPECTED_XCODE_OUTPUT="$(printf '%s\n%s' \
  "${EXPECTED_XCODE_VERSION}" "${EXPECTED_XCODE_BUILD}")"
readonly EXPECTED_XCODE_OUTPUT
if [[ "${XCODE_VERSION_OUTPUT}" != "${EXPECTED_XCODE_OUTPUT}" ]]; then
  printf 'Unexpected Xcode identity: %s\n' "${XCODE_VERSION_OUTPUT}" >&2
  exit 2
fi

SELECTED_DEVELOPER="$(/usr/bin/xcode-select -p)"
readonly SELECTED_DEVELOPER
RESOLVED_DEVELOPER="$(/usr/bin/python3 -I -B -c \
  'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' \
  "${SELECTED_DEVELOPER}")"
readonly RESOLVED_DEVELOPER
if [[ "${RESOLVED_DEVELOPER}" != "${SOURCE_DEVELOPER}" \
  || ! -d "${SOURCE_XCODE_APP}" \
  || -L "${SOURCE_XCODE_APP}" \
  || ! -L "${CANONICAL_XCODE_APP}" ]]; then
  printf 'Selected Xcode is not the exact physical hosted image bundle.\n' >&2
  exit 2
fi
XCODE_ALIAS_RESOLVED="$(/usr/bin/python3 -I -B -c \
  'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' \
  "${CANONICAL_XCODE_APP}")"
readonly XCODE_ALIAS_RESOLVED
XCODE_ALIAS_TARGET="$(/usr/bin/readlink "${CANONICAL_XCODE_APP}")"
readonly XCODE_ALIAS_TARGET
if [[ "${XCODE_ALIAS_TARGET}" != "${SOURCE_XCODE_APP}" ]]; then
  printf 'Unexpected Xcode alias target.\n' >&2
  exit 2
fi
if [[ "${XCODE_ALIAS_RESOLVED}" != "${SOURCE_XCODE_APP}" ]]; then
  printf 'Xcode alias does not resolve to the selected physical bundle.\n' >&2
  exit 2
fi

SOURCE_SDK_ALIAS_TARGET="$(/usr/bin/readlink "${SOURCE_SDK_ALIAS}")"
readonly SOURCE_SDK_ALIAS_TARGET
if [[ ! -L "${SOURCE_SDK_ALIAS}" \
  || "${SOURCE_SDK_ALIAS_TARGET}" != "MacOSX.sdk" \
  || ! -d "${SOURCE_SDK_TARGET}" \
  || -L "${SOURCE_SDK_TARGET}" ]]; then
  printf 'Hosted SDK alias is not the exact relative MacOSX26.5.sdk contract.\n' >&2
  exit 2
fi
SDK_ALIAS_RESOLVED="$(/usr/bin/python3 -I -B -c \
  'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' \
  "${SOURCE_SDK_ALIAS}")"
readonly SDK_ALIAS_RESOLVED
if [[ "${SDK_ALIAS_RESOLVED}" != "${SOURCE_SDK_TARGET}" ]]; then
  printf 'Hosted SDK alias resolves outside its exact physical target.\n' >&2
  exit 2
fi

# The exact hosted image starts with /Applications owned by root:admin and
# group-writable.  Once host identity and both Xcode entries are known, close
# that parent rename boundary through its no-follow directory descriptor.
/usr/bin/sudo /usr/bin/python3 -I -B - <<'PY'
import os
import stat
from pathlib import Path

path = Path("/Applications")
metadata = path.lstat()
if (
    path.resolve(strict=True) != path
    or stat.S_ISLNK(metadata.st_mode)
    or not stat.S_ISDIR(metadata.st_mode)
    or (
        (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode))
        not in {(0, 80, 0o775), (0, 0, 0o755)}
    )
):
    raise SystemExit("unexpected /Applications identity")
descriptor = os.open(
    path,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
)
try:
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
        raise SystemExit("/Applications changed before sealing")
    os.fchown(descriptor, 0, 0)
    os.fchmod(descriptor, 0o755)
    sealed = os.fstat(descriptor)
finally:
    os.close(descriptor)
if (
    sealed.st_uid != 0
    or sealed.st_gid != 0
    or stat.S_IMODE(sealed.st_mode) != 0o755
    or path.resolve(strict=True) != path
):
    raise SystemExit("/Applications seal failed")
PY

verify_xcode_tree() {
  /usr/bin/python3 -I -B - "$1" "$2" <<'PY'
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
ownership = sys.argv[2]
if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
    raise SystemExit("no-follow directory traversal is unavailable")
root_metadata = root.lstat()
if (
    ownership not in {"unsealed", "sealed"}
    or root.resolve(strict=True) != root
    or stat.S_ISLNK(root_metadata.st_mode)
    or not stat.S_ISDIR(root_metadata.st_mode)
    or stat.S_IMODE(root_metadata.st_mode) & 0o022
):
    raise SystemExit("unsafe Xcode tree root")


def identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def validate_ownership(metadata: os.stat_result, relative: Path) -> None:
    if ownership == "sealed":
        if metadata.st_uid != 0 or metadata.st_gid != 0:
            raise SystemExit(f"non-root Xcode entry: {relative}")
    elif metadata.st_uid not in {0, os.getuid()} or metadata.st_gid not in {
        0,
        os.getgid(),
        20,
        80,
    }:
        raise SystemExit(f"unexpected Xcode entry owner: {relative}")


if ownership == "sealed":
    if root_metadata.st_uid != 0 or root_metadata.st_gid != 0:
        raise SystemExit("non-root Xcode tree root")
elif root_metadata.st_uid not in {0, os.getuid()} or root_metadata.st_gid not in {
    0,
    os.getgid(),
    20,
    80,
}:
    raise SystemExit("unexpected Xcode tree root owner")
root_device = root_metadata.st_dev
entry_count = 0
regular_links: Counter[tuple[int, int]] = Counter()
regular_nlinks: dict[tuple[int, int], int] = {}
digest = hashlib.sha256()
digest.update(
    json.dumps(
        {
            "path": ".",
            "kind": "directory",
            "device": root_metadata.st_dev,
            "inode": root_metadata.st_ino,
            "mode": stat.S_IMODE(root_metadata.st_mode),
            "nlink": root_metadata.st_nlink,
            "bytes": root_metadata.st_size,
            "target": None,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
)
digest.update(b"\n")
flags = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | os.O_DIRECTORY
    | os.O_NOFOLLOW
)
root_descriptor = os.open(root, flags)
stack: list[tuple[int, Path]] = [(root_descriptor, Path("."))]
try:
    if identity(os.fstat(root_descriptor)) != identity(root_metadata):
        raise SystemExit("Xcode tree root changed while opened")
    while stack:
        directory_descriptor, relative_directory = stack.pop()
        try:
            directory_metadata = os.fstat(directory_descriptor)
            if (
                not stat.S_ISDIR(directory_metadata.st_mode)
                or directory_metadata.st_dev != root_device
            ):
                raise SystemExit("Xcode directory crosses device boundary")
            with os.scandir(directory_descriptor) as scanner:
                names = sorted((entry.name for entry in scanner), reverse=True)
            for name in names:
                metadata = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                entry_count += 1
                if entry_count > 1_000_000 or metadata.st_dev != root_device:
                    raise SystemExit("Xcode tree exceeds entry/device boundary")
                relative = relative_directory / name
                mode = stat.S_IMODE(metadata.st_mode)
                if stat.S_ISLNK(metadata.st_mode):
                    kind = "symlink"
                    target = os.readlink(name, dir_fd=directory_descriptor)
                elif stat.S_ISDIR(metadata.st_mode):
                    kind = "directory"
                    target = None
                    if mode & 0o022:
                        raise SystemExit(f"writable Xcode directory: {relative}")
                    child_descriptor = os.open(
                        name,
                        flags,
                        dir_fd=directory_descriptor,
                    )
                    try:
                        if identity(os.fstat(child_descriptor)) != identity(metadata):
                            raise SystemExit(
                                f"Xcode directory changed while opened: {relative}"
                            )
                    except BaseException:
                        os.close(child_descriptor)
                        raise
                    stack.append((child_descriptor, relative))
                elif stat.S_ISREG(metadata.st_mode):
                    kind = "regular"
                    target = None
                    if mode & 0o022:
                        raise SystemExit(f"writable Xcode file: {relative}")
                    file_identity = (metadata.st_dev, metadata.st_ino)
                    regular_links[file_identity] += 1
                    regular_nlinks[file_identity] = metadata.st_nlink
                else:
                    raise SystemExit(f"unsupported Xcode entry type: {relative}")
                validate_ownership(metadata, relative)
                digest.update(
                    json.dumps(
                        {
                            "path": relative.as_posix(),
                            "kind": kind,
                            "device": metadata.st_dev,
                            "inode": metadata.st_ino,
                            "mode": mode,
                            "nlink": metadata.st_nlink,
                            "bytes": metadata.st_size,
                            "target": target,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                digest.update(b"\n")
        finally:
            os.close(directory_descriptor)
finally:
    for pending_descriptor, _relative in stack:
        os.close(pending_descriptor)
root_after = root.lstat()
if identity(root_after) != identity(root_metadata) or root.resolve(strict=True) != root:
    raise SystemExit("Xcode tree root changed during traversal")
if any(regular_links[identity] != nlink for identity, nlink in regular_nlinks.items()):
    raise SystemExit("Xcode regular-file hard link escapes the bundle")
print(f"sha256:{digest.hexdigest()}:{entry_count}:{root_device}:{root_metadata.st_ino}")
PY
}

XCODE_TREE_BEFORE="$(verify_xcode_tree "${SOURCE_XCODE_APP}" unsealed)"
readonly XCODE_TREE_BEFORE
if [[ -z "${XCODE_TREE_BEFORE}" ]]; then
  printf 'Xcode pre-seal inventory is empty.\n' >&2
  exit 3
fi
/usr/bin/sudo /usr/sbin/chown -R -P -x 0:0 "${SOURCE_XCODE_APP}"
/usr/bin/sudo /usr/sbin/chown -h 0:0 "${CANONICAL_XCODE_APP}"
XCODE_TREE_AFTER="$(verify_xcode_tree "${SOURCE_XCODE_APP}" sealed)"
readonly XCODE_TREE_AFTER
if [[ "${XCODE_TREE_AFTER}" != "${XCODE_TREE_BEFORE}" ]]; then
  printf 'Xcode tree changed while ownership was sealed.\n' >&2
  exit 3
fi

# The exact hosted image exposes Xcode.app as a symlink, while the runtime
# verifier deliberately rejects a symlink anywhere in the compiler directory
# chain.  Seal both directory entries across signature verification, then let a
# root helper recheck that exact seal before it removes only the known alias and
# renames the physical bundle within /Applications.  rename(2) cannot replace a
# symlink with a directory directly on macOS.  This disposable-host
# normalization changes no bundle bytes or internal link targets.
xcode_entry_identity() {
  /usr/bin/python3 -I -B - \
    "${SOURCE_XCODE_APP}" "${CANONICAL_XCODE_APP}" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

source = Path(sys.argv[1])
canonical = Path(sys.argv[2])
parent = source.parent


def identity(path: Path) -> dict[str, int]:
    value = path.lstat()
    return {
        "dev": value.st_dev,
        "ino": value.st_ino,
        "mode": value.st_mode,
        "nlink": value.st_nlink,
        "uid": value.st_uid,
        "gid": value.st_gid,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }


parent_metadata = parent.lstat()
source_metadata = source.lstat()
canonical_metadata = canonical.lstat()
raw_target = os.readlink(canonical)
if (
    source != Path("/Applications/Xcode_26.6.app")
    or canonical != Path("/Applications/Xcode.app")
    or stat.S_ISLNK(parent_metadata.st_mode)
    or not stat.S_ISDIR(parent_metadata.st_mode)
    or parent_metadata.st_uid != 0
    or parent_metadata.st_gid != 0
    or stat.S_IMODE(parent_metadata.st_mode) != 0o755
    or stat.S_ISLNK(source_metadata.st_mode)
    or not stat.S_ISDIR(source_metadata.st_mode)
    or source_metadata.st_uid != 0
    or source_metadata.st_gid != 0
    or stat.S_IMODE(source_metadata.st_mode) & 0o022
    or source_metadata.st_dev != parent_metadata.st_dev
    or not stat.S_ISLNK(canonical_metadata.st_mode)
    or canonical_metadata.st_nlink != 1
    or canonical_metadata.st_uid != 0
    or canonical_metadata.st_gid != 0
    or raw_target != "/Applications/Xcode_26.6.app"
    or source.resolve(strict=True) != source
    or canonical.resolve(strict=True) != source
):
    raise SystemExit("unsafe hosted Xcode source or alias identity")
print(
    json.dumps(
        {
            "parent": identity(parent),
            "source": identity(source),
            "canonical": identity(canonical),
            "canonical_raw_target": raw_target,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY
}

XCODE_ENTRY_IDENTITY_BEFORE="$(xcode_entry_identity)"
readonly XCODE_ENTRY_IDENTITY_BEFORE
/usr/bin/codesign --verify --deep --strict "${SOURCE_XCODE_APP}"
XCODE_ENTRY_IDENTITY_AFTER="$(xcode_entry_identity)"
readonly XCODE_ENTRY_IDENTITY_AFTER
if [[ "${XCODE_ENTRY_IDENTITY_AFTER}" != "${XCODE_ENTRY_IDENTITY_BEFORE}" ]]; then
  printf 'Hosted Xcode entries changed during signature verification.\n' >&2
  exit 3
fi
SOURCE_XCODE_DEVICE="$(/usr/bin/stat -f '%d' "${SOURCE_XCODE_APP}")"
readonly SOURCE_XCODE_DEVICE
APPLICATIONS_DEVICE="$(/usr/bin/stat -f '%d' /Applications)"
readonly APPLICATIONS_DEVICE
if [[ "${SOURCE_XCODE_DEVICE}" != "${APPLICATIONS_DEVICE}" ]]; then
  printf 'Xcode source and canonical parent are not on the same filesystem.\n' >&2
  exit 3
fi
/usr/bin/sudo /usr/bin/python3 -I -B - \
  "${SOURCE_XCODE_APP}" "${CANONICAL_XCODE_APP}" \
  "${XCODE_ENTRY_IDENTITY_AFTER}" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

source = Path(sys.argv[1])
canonical = Path(sys.argv[2])
expected = json.loads(sys.argv[3])
parent = source.parent


def identity(path: Path) -> dict[str, int]:
    value = path.lstat()
    return {
        "dev": value.st_dev,
        "ino": value.st_ino,
        "mode": value.st_mode,
        "nlink": value.st_nlink,
        "uid": value.st_uid,
        "gid": value.st_gid,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }


observed = {
    "parent": identity(parent),
    "source": identity(source),
    "canonical": identity(canonical),
    "canonical_raw_target": os.readlink(canonical),
}
source_metadata = source.lstat()
canonical_metadata = canonical.lstat()
parent_metadata = parent.lstat()
if (
    source != Path("/Applications/Xcode_26.6.app")
    or canonical != Path("/Applications/Xcode.app")
    or observed != expected
    or stat.S_ISLNK(source_metadata.st_mode)
    or not stat.S_ISDIR(source_metadata.st_mode)
    or not stat.S_ISLNK(canonical_metadata.st_mode)
    or canonical_metadata.st_nlink != 1
    or parent_metadata.st_uid != 0
    or parent_metadata.st_gid != 0
    or stat.S_IMODE(parent_metadata.st_mode) != 0o755
    or os.readlink(canonical) != "/Applications/Xcode_26.6.app"
    or source.resolve(strict=True) != source
    or canonical.resolve(strict=True) != source
    or source_metadata.st_dev != parent.lstat().st_dev
):
    raise SystemExit("hosted Xcode entries drifted before normalization")

parent_descriptor = os.open(
    parent,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
)
try:
    parent_opened = os.fstat(parent_descriptor)
    parent_opened_identity = {
        "dev": parent_opened.st_dev,
        "ino": parent_opened.st_ino,
        "mode": parent_opened.st_mode,
        "nlink": parent_opened.st_nlink,
        "uid": parent_opened.st_uid,
        "gid": parent_opened.st_gid,
        "size": parent_opened.st_size,
        "mtime_ns": parent_opened.st_mtime_ns,
        "ctime_ns": parent_opened.st_ctime_ns,
    }
    if identity(parent) != expected["parent"] or parent_opened_identity != expected["parent"]:
        raise SystemExit("/Applications identity drifted before normalization")
    os.unlink(canonical.name, dir_fd=parent_descriptor)
    try:
        os.stat(canonical.name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise SystemExit("Xcode alias still exists after exact unlink")
    os.rename(
        source.name,
        canonical.name,
        src_dir_fd=parent_descriptor,
        dst_dir_fd=parent_descriptor,
    )
    normalized_opened = os.stat(
        canonical.name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    try:
        os.stat(source.name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise SystemExit("Xcode source still exists after atomic rename")
    if (
        not stat.S_ISDIR(normalized_opened.st_mode)
        or normalized_opened.st_dev != expected["source"]["dev"]
        or normalized_opened.st_ino != expected["source"]["ino"]
    ):
        raise SystemExit("atomic Xcode rename changed the source directory identity")
finally:
    os.close(parent_descriptor)

normalized = canonical.lstat()
if (
    source.exists()
    or source.is_symlink()
    or stat.S_ISLNK(normalized.st_mode)
    or not stat.S_ISDIR(normalized.st_mode)
    or normalized.st_dev != expected["source"]["dev"]
    or normalized.st_ino != expected["source"]["ino"]
    or canonical.resolve(strict=True) != canonical
):
    raise SystemExit("physical Xcode normalization postcondition failed")
PY
XCODE_TREE_NORMALIZED="$(verify_xcode_tree "${CANONICAL_XCODE_APP}" sealed)"
readonly XCODE_TREE_NORMALIZED
if [[ "${XCODE_TREE_NORMALIZED}" != "${XCODE_TREE_AFTER}" ]]; then
  printf 'Xcode inode/tree summary changed during physical normalization.\n' >&2
  exit 3
fi
/usr/bin/sudo /usr/bin/xcode-select -s "${CANONICAL_DEVELOPER}"

/usr/bin/codesign --verify --deep --strict "${CANONICAL_XCODE_APP}"

XCODE_TREE_VERIFIED="$(verify_xcode_tree "${CANONICAL_XCODE_APP}" sealed)"
readonly XCODE_TREE_VERIFIED
if [[ "${XCODE_TREE_VERIFIED}" != "${XCODE_TREE_BEFORE}" ]]; then
  printf 'Canonical Xcode tree changed across sealing, normalization, or signature verification.\n' >&2
  exit 3
fi

NON_ROOT_XCODE_ENTRY="$(/usr/bin/find "${CANONICAL_XCODE_APP}" -xdev \
  \( ! -user root -o ! -group wheel \) -print -quit)"
readonly NON_ROOT_XCODE_ENTRY
APPLICATIONS_SEAL="$(/usr/bin/stat -f '%Lp:%u:%g' /Applications)"
readonly APPLICATIONS_SEAL
CANONICAL_XCODE_OWNER="$(/usr/bin/stat -f '%u:%g' "${CANONICAL_XCODE_APP}")"
readonly CANONICAL_XCODE_OWNER
SELECTED_DEVELOPER_AFTER="$(/usr/bin/xcode-select -p)"
readonly SELECTED_DEVELOPER_AFTER
CANONICAL_SDK_ALIAS_TARGET_AFTER="$(/usr/bin/readlink "${CANONICAL_SDK_ALIAS}")"
readonly CANONICAL_SDK_ALIAS_TARGET_AFTER
CANONICAL_SDK_RESOLVED_AFTER="$(/usr/bin/python3 -I -B -c \
  'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' \
  "${CANONICAL_SDK_ALIAS}")"
readonly CANONICAL_SDK_RESOLVED_AFTER
XCODE_VERSION_OUTPUT_AFTER="$(/usr/bin/xcodebuild -version)"
readonly XCODE_VERSION_OUTPUT_AFTER
if [[ -n "${NON_ROOT_XCODE_ENTRY}" \
  || -L /Applications \
  || "${APPLICATIONS_SEAL}" != "755:0:0" \
  || -e "${SOURCE_XCODE_APP}" \
  || -L "${SOURCE_XCODE_APP}" \
  || ! -d "${CANONICAL_XCODE_APP}" \
  || -L "${CANONICAL_XCODE_APP}" \
  || "${CANONICAL_XCODE_OWNER}" != "0:0" \
  || "${SELECTED_DEVELOPER_AFTER}" != "${CANONICAL_DEVELOPER}" \
  || "${CANONICAL_SDK_ALIAS_TARGET_AFTER}" != "MacOSX.sdk" \
  || "${CANONICAL_SDK_RESOLVED_AFTER}" != "${CANONICAL_SDK_TARGET}" \
  || ! -d "${CANONICAL_SDK_TARGET}" \
  || -L "${CANONICAL_SDK_TARGET}" \
  || "${XCODE_VERSION_OUTPUT_AFTER}" != "${EXPECTED_XCODE_OUTPUT}" ]]; then
  printf 'Root-owned Xcode closure seal verification failed: %s\n' \
    "${NON_ROOT_XCODE_ENTRY}" >&2
  exit 3
fi

PRIVATE_TMP="$(/usr/bin/python3 -I -B - "${RUNNER_TEMP}" <<'PY'
import os
import stat
import sys
from pathlib import Path

raw = Path(sys.argv[1])
physical = raw.resolve(strict=True)
metadata = physical.lstat()
if (
    not physical.is_absolute()
    or stat.S_ISLNK(metadata.st_mode)
    or not stat.S_ISDIR(metadata.st_mode)
    or metadata.st_uid not in {0, os.getuid()}
    or stat.S_IMODE(metadata.st_mode) & 0o022
):
    raise SystemExit("RUNNER_TEMP is not a trusted physical directory")
private = physical / "elmos-route-private-tmp"
private.mkdir(mode=0o700)
observed = private.lstat()
if (
    private.resolve(strict=True) != private
    or not stat.S_ISDIR(observed.st_mode)
    or observed.st_uid != os.getuid()
    or observed.st_gid != os.getgid()
    or stat.S_IMODE(observed.st_mode) != 0o700
):
    raise SystemExit("private route temp root was not created securely")
print(private)
PY
)"
readonly PRIVATE_TMP
if [[ -z "${PRIVATE_TMP}" ]]; then
  printf 'Prepared route temp root is empty.\n' >&2
  exit 3
fi
printf '%s\n' \
  "TMPDIR=${PRIVATE_TMP}" \
  "ELMOS_APPLE_ROUTE_XCODE_SEALED=1" \
  "ELMOS_APPLE_ROUTE_XCODE_PHYSICAL=${CANONICAL_XCODE_APP}" \
  "ELMOS_APPLE_ROUTE_XCODE_TREE_IDENTITY=${XCODE_TREE_VERIFIED}" \
  >>"${GITHUB_ENV}"
printf 'APPLE_ROUTE_HOST_PREPARED image=%s xcode=%s sdk=%s tmp=%s\n' \
  "${ImageVersion}" "${CANONICAL_XCODE_APP}" "${CANONICAL_SDK_TARGET}" "${PRIVATE_TMP}"
