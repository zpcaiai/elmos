#!/usr/bin/env python3
"""Launch authoritative Batch 29 route commands in a fresh locked uv venv."""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import posixpath
import shutil
import stat
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import cast

PINNED_UV_PATH = Path("/opt/homebrew/Cellar/uv/0.11.16/bin/uv")
PINNED_UV_SHA256 = (
    "sha256:d4182a7bba32f331b2c5a74568cf1c88aa50f31fe643a2c56118c6610db0aff0"
)
PINNED_UV_BYTES = 46_541_136
PINNED_UV_VERSION = "uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)"
PINNED_UV_MODE = 0o555
PINNED_UV_UID = 501
PINNED_UV_GID = 80
PINNED_UV_NLINK = 1
PYTHON_ARCHIVE_NAME = (
    "cpython-3.12.12+20260211-aarch64-apple-darwin-install_only_stripped.tar.gz"
)
PYTHON_ARCHIVE_SHA256 = (
    "22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84"
)
PYTHON_ARCHIVE_BYTES = 17_667_661
PYTHON_SOURCE_TREE_SHA256 = (
    "1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154"
)
PYTHON_SOURCE_TREE_RECORD_COUNT = 1_899
PYTHON_TREE_FILE_COUNT = 1_890
PYTHON_TREE_BYTES = 47_880_708
PYTHON_RUNTIME_TREE_SHA256 = (
    "49eb47a1e6f1a8803ef3686da328abf2e18f1d31b6447190c3455640e4df9adf"
)
PYTHON_TREE_SYMLINKS = {
    "bin/2to3": "2to3-3.12",
    "bin/idle3": "idle3.12",
    "bin/pydoc3": "pydoc3.12",
    "bin/python": "python3.12",
    "bin/python3": "python3.12",
    "bin/python3-config": "python3.12-config",
    "lib/pkgconfig/python3-embed.pc": "python-3.12-embed.pc",
    "lib/pkgconfig/python3.pc": "python-3.12.pc",
    "share/man/man1/python3.1": "python3.12.1",
}
TOOLCHAIN_CACHE_ANCHOR = Path("/Users/stephen/.local")
TOOLCHAIN_CACHE = TOOLCHAIN_CACHE_ANCHOR / "share" / "elmos" / "toolchains"
PYTHON_CACHE = TOOLCHAIN_CACHE / "python-build-standalone"
PYTHON_ARCHIVE_CACHE = (
    PYTHON_CACHE / "archives" / ("sha256-" + PYTHON_ARCHIVE_SHA256 + ".tar.gz")
)
PYTHON_CAPTURED_ARCHIVE_RELATIVE = (
    "runtime/python/sha256-" + PYTHON_ARCHIVE_SHA256 + ".tar.gz"
)
PYTHON_RUNTIME_ROOT = (
    PYTHON_CACHE
    / "runtimes"
    / "3.12.12+20260211-aarch64-apple-darwin"
    / ("sha256-" + PYTHON_SOURCE_TREE_SHA256)
    / "python"
)

TYPESCRIPT_VERSION = "5.9.2"
TYPESCRIPT_SOURCE_MANIFEST_SHA256 = (
    "61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
TYPESCRIPT_RUNTIME_MANIFEST_SHA256 = (
    "2157e43e757e433c733e144df7409a54f5040faa22af4a9b13de977a663fd939"
)
TYPESCRIPT_FILE_COUNT = 108
TYPESCRIPT_CLOSURE_BYTES = 19_067_381
TYPESCRIPT_CAPTURED_ROOT_RELATIVE = (
    "runtime/typescript/sha256-" + TYPESCRIPT_SOURCE_MANIFEST_SHA256
)
TYPESCRIPT_CACHE = TOOLCHAIN_CACHE / "typescript" / TYPESCRIPT_VERSION
TYPESCRIPT_RUNTIME_ROOT = (
    TYPESCRIPT_CACHE
    / ("sha256-" + TYPESCRIPT_SOURCE_MANIFEST_SHA256)
)
TYPESCRIPT_CORE_FILES = {
    "bin/tsc": (
        45,
        "8d5fa5bd883fec0979fc2004f1fe1d99aef40570155d550eadc0b03b55513bf0",
        0o555,
    ),
    "lib/tsc.js": (
        267,
        "2cffde0b8c6760dfb0b5b0382bbb7e00ba6a8b2d981b9205b256a700a481d983",
        0o444,
    ),
    "lib/_tsc.js": (
        6_211_917,
        "a040f97c9d0223f64c8ebc380c5e48eb7945f1142f7c1dc9c3ec4acdb6c1c613",
        0o444,
    ),
    "lib/typescript.js": (
        9_111_680,
        "e5f1f6b3e82228a89873cc7b941b2465185e839c0692860f83e3e63e53f94c2b",
        0o444,
    ),
    "package.json": (
        3_620,
        "5a0bb7f286c4b3f1413a42c05f902311b161f70e5f52d9da10490443bfd595a3",
        0o444,
    ),
    "LICENSE.txt": (
        9_197,
        "a7d00bfd54525bc694b6e32f64c7ebcf5e6b7ae3657be5cc12767bce74654a47",
        0o444,
    ),
}
TYPESCRIPT_LIBRARY_FILES = (
    "lib/lib.d.ts",
    "lib/lib.decorators.d.ts",
    "lib/lib.decorators.legacy.d.ts",
    "lib/lib.dom.asynciterable.d.ts",
    "lib/lib.dom.d.ts",
    "lib/lib.dom.iterable.d.ts",
    "lib/lib.es2015.collection.d.ts",
    "lib/lib.es2015.core.d.ts",
    "lib/lib.es2015.d.ts",
    "lib/lib.es2015.generator.d.ts",
    "lib/lib.es2015.iterable.d.ts",
    "lib/lib.es2015.promise.d.ts",
    "lib/lib.es2015.proxy.d.ts",
    "lib/lib.es2015.reflect.d.ts",
    "lib/lib.es2015.symbol.d.ts",
    "lib/lib.es2015.symbol.wellknown.d.ts",
    "lib/lib.es2016.array.include.d.ts",
    "lib/lib.es2016.d.ts",
    "lib/lib.es2016.full.d.ts",
    "lib/lib.es2016.intl.d.ts",
    "lib/lib.es2017.arraybuffer.d.ts",
    "lib/lib.es2017.d.ts",
    "lib/lib.es2017.date.d.ts",
    "lib/lib.es2017.full.d.ts",
    "lib/lib.es2017.intl.d.ts",
    "lib/lib.es2017.object.d.ts",
    "lib/lib.es2017.sharedmemory.d.ts",
    "lib/lib.es2017.string.d.ts",
    "lib/lib.es2017.typedarrays.d.ts",
    "lib/lib.es2018.asyncgenerator.d.ts",
    "lib/lib.es2018.asynciterable.d.ts",
    "lib/lib.es2018.d.ts",
    "lib/lib.es2018.full.d.ts",
    "lib/lib.es2018.intl.d.ts",
    "lib/lib.es2018.promise.d.ts",
    "lib/lib.es2018.regexp.d.ts",
    "lib/lib.es2019.array.d.ts",
    "lib/lib.es2019.d.ts",
    "lib/lib.es2019.full.d.ts",
    "lib/lib.es2019.intl.d.ts",
    "lib/lib.es2019.object.d.ts",
    "lib/lib.es2019.string.d.ts",
    "lib/lib.es2019.symbol.d.ts",
    "lib/lib.es2020.bigint.d.ts",
    "lib/lib.es2020.d.ts",
    "lib/lib.es2020.date.d.ts",
    "lib/lib.es2020.full.d.ts",
    "lib/lib.es2020.intl.d.ts",
    "lib/lib.es2020.number.d.ts",
    "lib/lib.es2020.promise.d.ts",
    "lib/lib.es2020.sharedmemory.d.ts",
    "lib/lib.es2020.string.d.ts",
    "lib/lib.es2020.symbol.wellknown.d.ts",
    "lib/lib.es2021.d.ts",
    "lib/lib.es2021.full.d.ts",
    "lib/lib.es2021.intl.d.ts",
    "lib/lib.es2021.promise.d.ts",
    "lib/lib.es2021.string.d.ts",
    "lib/lib.es2021.weakref.d.ts",
    "lib/lib.es2022.array.d.ts",
    "lib/lib.es2022.d.ts",
    "lib/lib.es2022.error.d.ts",
    "lib/lib.es2022.full.d.ts",
    "lib/lib.es2022.intl.d.ts",
    "lib/lib.es2022.object.d.ts",
    "lib/lib.es2022.regexp.d.ts",
    "lib/lib.es2022.string.d.ts",
    "lib/lib.es2023.array.d.ts",
    "lib/lib.es2023.collection.d.ts",
    "lib/lib.es2023.d.ts",
    "lib/lib.es2023.full.d.ts",
    "lib/lib.es2023.intl.d.ts",
    "lib/lib.es2024.arraybuffer.d.ts",
    "lib/lib.es2024.collection.d.ts",
    "lib/lib.es2024.d.ts",
    "lib/lib.es2024.full.d.ts",
    "lib/lib.es2024.object.d.ts",
    "lib/lib.es2024.promise.d.ts",
    "lib/lib.es2024.regexp.d.ts",
    "lib/lib.es2024.sharedmemory.d.ts",
    "lib/lib.es2024.string.d.ts",
    "lib/lib.es5.d.ts",
    "lib/lib.es6.d.ts",
    "lib/lib.esnext.array.d.ts",
    "lib/lib.esnext.collection.d.ts",
    "lib/lib.esnext.d.ts",
    "lib/lib.esnext.decorators.d.ts",
    "lib/lib.esnext.disposable.d.ts",
    "lib/lib.esnext.error.d.ts",
    "lib/lib.esnext.float16.d.ts",
    "lib/lib.esnext.full.d.ts",
    "lib/lib.esnext.intl.d.ts",
    "lib/lib.esnext.iterator.d.ts",
    "lib/lib.esnext.promise.d.ts",
    "lib/lib.esnext.sharedmemory.d.ts",
    "lib/lib.scripthost.d.ts",
    "lib/lib.webworker.asynciterable.d.ts",
    "lib/lib.webworker.d.ts",
    "lib/lib.webworker.importscripts.d.ts",
    "lib/lib.webworker.iterable.d.ts",
    "lib/tsserverlibrary.d.ts",
    "lib/typescript.d.ts",
)
TYPESCRIPT_FILES = tuple(sorted((*TYPESCRIPT_CORE_FILES, *TYPESCRIPT_LIBRARY_FILES)))
PROJECT_ENVIRONMENT_ENV = "UV_PROJECT_ENVIRONMENT"
CHILD_PROGRAM = r"""
import runpy
import sys
from pathlib import Path

script = Path(sys.argv[1]).resolve(strict=True)
arguments = sys.argv[2:]
sys.path.insert(0, str(script.parent))
sys.argv = [str(script), *arguments]
namespace = runpy.run_path(str(script), run_name="__elmos_batch29_fresh_child__")
main = namespace.get("main")
if not callable(main):
    raise SystemExit("Batch29 fresh child target has no callable main")
result = main()
raise SystemExit(result if isinstance(result, int) else 0)
"""


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_cache_directory(path: Path, *, create: bool = False) -> None:
    """Validate or create the fixed user-owned cache chain without symlinks."""

    anchor = TOOLCHAIN_CACHE_ANCHOR
    try:
        relative = path.relative_to(anchor)
    except ValueError as error:
        raise RuntimeError("Batch29 fixed toolchain cache path escapes") from error
    cursor = anchor
    for part in relative.parts:
        cursor = cursor / part
        if create and not cursor.exists():
            try:
                cursor.mkdir(mode=0o700)
            except FileExistsError:
                pass
        try:
            metadata = cursor.lstat()
        except OSError as error:
            raise RuntimeError(
                "Batch29 fixed toolchain cache is unavailable"
            ) from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise RuntimeError("Batch29 fixed toolchain cache path is unsafe")


@contextmanager
def _cache_lock(root: Path, name: str) -> Iterator[None]:
    _safe_cache_directory(root, create=True)
    lock = root / name
    try:
        descriptor = os.open(
            lock,
            os.O_CREAT
            | os.O_RDWR
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
        ):
            raise RuntimeError("Batch29 fixed toolchain cache lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as error:
        raise RuntimeError("Batch29 fixed toolchain cache lock failed") from error
    finally:
        if "descriptor" in locals():
            os.close(descriptor)


def _cleanup_partial_tree(root: Path) -> None:
    if not root.exists() or root.is_symlink():
        return
    for item in sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if item.is_dir() and not item.is_symlink():
            item.chmod(0o700)
        elif not item.is_symlink():
            item.chmod(0o600)
    root.chmod(0o700)
    shutil.rmtree(root)


def _bound_file_bytes(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> bytes:
    try:
        before = path.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened_before = os.fstat(descriptor)
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError as error:
        raise RuntimeError(
            f"Batch29 fixed asset is unavailable: {path.name}"
        ) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    content = b"".join(chunks)
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_size,
            opened_before.st_uid,
            opened_before.st_gid,
            opened_before.st_nlink,
            opened_before.st_mtime_ns,
        )
        or identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_size,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_nlink,
            opened_after.st_mtime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_nlink != 1
        or len(content) != expected_bytes
        or hashlib.sha256(content).hexdigest() != expected_sha256
    ):
        raise RuntimeError(f"Batch29 fixed asset identity mismatch: {path.name}")
    return content


def _captured_python_archive_bytes(root: Path, relative: str) -> bytes:
    """Read the one explicit route-local archive without ambient fallback."""

    if relative != PYTHON_CAPTURED_ARCHIVE_RELATIVE:
        raise RuntimeError("Batch29 captured Python archive path is not content-addressed")
    try:
        resolved_root = root.resolve(strict=True)
        root_before = root.lstat()
        if (
            root != resolved_root
            or stat.S_ISLNK(root_before.st_mode)
            or not stat.S_ISDIR(root_before.st_mode)
            or root_before.st_uid not in {0, os.getuid()}
            or stat.S_IMODE(root_before.st_mode) & 0o022
        ):
            raise RuntimeError("Batch29 captured Python archive root is unsafe")
        candidate = root / relative
        candidate.resolve(strict=True).relative_to(resolved_root)
        cursor = root
        chain_before: list[tuple[object, ...]] = []
        for part in PurePosixPath(relative).parts[:-1]:
            cursor = cursor / part
            metadata = cursor.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RuntimeError("Batch29 captured Python archive path is unsafe")
            chain_before.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                )
            )
        content = _bound_file_bytes(
            candidate,
            expected_bytes=PYTHON_ARCHIVE_BYTES,
            expected_sha256=PYTHON_ARCHIVE_SHA256,
        )
        root_after = root.lstat()
        chain_after = []
        cursor = root
        for part in PurePosixPath(relative).parts[:-1]:
            cursor = cursor / part
            metadata = cursor.lstat()
            chain_after.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                )
            )
    except OSError as error:
        raise RuntimeError("Batch29 captured Python archive is unavailable") from error
    if (
        (
            root_before.st_dev,
            root_before.st_ino,
            root_before.st_mode,
            root_before.st_uid,
            root_before.st_gid,
            root_before.st_mtime_ns,
        )
        != (
            root_after.st_dev,
            root_after.st_ino,
            root_after.st_mode,
            root_after.st_uid,
            root_after.st_gid,
            root_after.st_mtime_ns,
        )
        or chain_before != chain_after
    ):
        raise RuntimeError("Batch29 captured Python archive changed during verification")
    _verify_python_archive(content)
    return content


def _safe_python_member(name: str) -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise RuntimeError("Batch29 Python archive path is invalid")
    parts = PurePosixPath(name.rstrip("/")).parts
    if (
        len(parts) < 2
        or parts[0] != "python"
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise RuntimeError("Batch29 Python archive root is invalid")
    return PurePosixPath(*parts[1:]).as_posix()


def _python_archive_inventory(content: bytes) -> dict[str, object]:
    records: list[dict[str, object]] = []
    names: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as bundle:
            for member in bundle.getmembers():
                relative = _safe_python_member(member.name)
                if relative in names:
                    raise RuntimeError("Batch29 Python archive contains duplicates")
                names.add(relative)
                if member.isfile():
                    stream = bundle.extractfile(member)
                    if stream is None:
                        raise RuntimeError("Batch29 Python archive file is unreadable")
                    file_content = stream.read()
                    records.append(
                        {
                            "bytes": len(file_content),
                            "kind": "file",
                            "mode": f"{member.mode:04o}",
                            "path": relative,
                            "sha256": "sha256:"
                            + hashlib.sha256(file_content).hexdigest(),
                        }
                    )
                elif member.issym():
                    target = member.linkname
                    resolved_target = posixpath.normpath(
                        posixpath.join(posixpath.dirname(relative), target)
                    )
                    if (
                        not target
                        or "\\" in target
                        or target.startswith("/")
                        or resolved_target == ".."
                        or resolved_target.startswith("../")
                    ):
                        raise RuntimeError("Batch29 Python archive symlink escapes")
                    records.append(
                        {
                            "kind": "symlink",
                            "mode": f"{member.mode:04o}",
                            "path": relative,
                            "target": target,
                        }
                    )
                elif member.isdir():
                    records.append(
                        {
                            "kind": "directory",
                            "mode": f"{member.mode:04o}",
                            "path": relative,
                        }
                    )
                else:
                    raise RuntimeError("Batch29 Python archive contains a special file")
    except (OSError, tarfile.TarError) as error:
        raise RuntimeError("Batch29 Python archive is invalid") from error
    records.sort(key=lambda item: str(item["path"]))
    return {
        "sha256": _canonical_digest(records),
        "record_count": len(records),
        "file_count": sum(item["kind"] == "file" for item in records),
        "bytes": sum(cast(int, item.get("bytes", 0)) for item in records),
        "symlinks": {
            str(item["path"]): str(item["target"])
            for item in records
            if item["kind"] == "symlink"
        },
    }


def _verify_python_archive(content: bytes) -> None:
    inventory = _python_archive_inventory(content)
    expected: dict[str, object] = {
        "sha256": PYTHON_SOURCE_TREE_SHA256,
        "record_count": PYTHON_SOURCE_TREE_RECORD_COUNT,
        "file_count": PYTHON_TREE_FILE_COUNT,
        "bytes": PYTHON_TREE_BYTES,
        "symlinks": PYTHON_TREE_SYMLINKS,
    }
    if inventory != expected:
        raise RuntimeError("Batch29 Python archive inventory mismatch")


def _extract_python(content: bytes, destination: Path) -> None:
    destination.mkdir(mode=0o700)
    symlinks: list[tuple[str, str]] = []
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as bundle:
        for member in bundle.getmembers():
            relative = _safe_python_member(member.name)
            target = destination / relative
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                stream = bundle.extractfile(member)
                if stream is None:
                    raise RuntimeError("Batch29 Python archive file is unreadable")
                with target.open("xb") as output:
                    shutil.copyfileobj(stream, output, length=1024 * 1024)
                target.chmod(0o555 if member.mode & 0o111 else 0o444)
            elif member.issym():
                symlinks.append((relative, member.linkname))
        for relative, link_target in symlinks:
            target = destination / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.symlink_to(link_target)
        for directory in sorted(
            (item for item in destination.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            directory.chmod(0o555)
    destination.chmod(0o555)


def _python_runtime_manifest(root: Path) -> dict[str, object]:
    records: list[dict[str, object]] = []
    symlinks: dict[str, str] = {}
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Batch29 Python runtime root is unsafe")
    root_metadata = root.lstat()
    if (
        root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o555
    ):
        raise RuntimeError("Batch29 Python runtime root is not read-only")
    for item in sorted(
        root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()
    ):
        relative = item.relative_to(root).as_posix()
        metadata = item.lstat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
            raise RuntimeError("Batch29 Python runtime metadata is unsafe")
        if stat.S_ISDIR(metadata.st_mode):
            if stat.S_IMODE(metadata.st_mode) != 0o555:
                raise RuntimeError("Batch29 Python runtime directory is writable")
            continue
        if stat.S_ISLNK(metadata.st_mode):
            target = os.readlink(item)
            if item.resolve(strict=True) != (item.parent / target).resolve(
                strict=True
            ) or not item.resolve().is_relative_to(root):
                raise RuntimeError("Batch29 Python runtime symlink escapes")
            symlinks[relative] = target
            records.append({"path": relative, "kind": "symlink", "target": target})
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) not in {0o444, 0o555}
        ):
            raise RuntimeError("Batch29 Python runtime file is unsafe")
        content = _bound_file_bytes(
            item,
            expected_bytes=metadata.st_size,
            expected_sha256=hashlib.sha256(item.read_bytes()).hexdigest(),
        )
        records.append(
            {
                "path": relative,
                "kind": "file",
                "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    identity = {
        "sha256": _canonical_digest({"records": records}),
        "record_count": len(records),
        "file_count": sum(item["kind"] == "file" for item in records),
        "bytes": sum(cast(int, item.get("bytes", 0)) for item in records),
        "symlinks": symlinks,
    }
    if identity != {
        "sha256": PYTHON_RUNTIME_TREE_SHA256,
        "record_count": PYTHON_SOURCE_TREE_RECORD_COUNT,
        "file_count": PYTHON_TREE_FILE_COUNT,
        "bytes": PYTHON_TREE_BYTES,
        "symlinks": PYTHON_TREE_SYMLINKS,
    }:
        raise RuntimeError("Batch29 Python runtime tree mismatch")
    return identity


def _prepare_python_runtime(
    *,
    captured_archive_root: Path | None = None,
    captured_archive_relative: str | None = None,
) -> Path:
    """Materialize the fixed archive into one owner-private read-only cache."""

    if (captured_archive_root is None) != (captured_archive_relative is None):
        raise RuntimeError("Batch29 captured Python archive input is incomplete")
    with _cache_lock(PYTHON_CACHE, ".materialize.lock"):
        _safe_cache_directory(PYTHON_ARCHIVE_CACHE.parent, create=True)
        _safe_cache_directory(PYTHON_RUNTIME_ROOT.parent, create=True)
        captured_content = (
            _captured_python_archive_bytes(
                captured_archive_root,
                captured_archive_relative,
            )
            if captured_archive_root is not None
            and captured_archive_relative is not None
            else None
        )
        if PYTHON_ARCHIVE_CACHE.exists():
            archive_content = _bound_file_bytes(
                PYTHON_ARCHIVE_CACHE,
                expected_bytes=PYTHON_ARCHIVE_BYTES,
                expected_sha256=PYTHON_ARCHIVE_SHA256,
            )
        else:
            if captured_content is None:
                raise RuntimeError(
                    "Batch29 captured Python archive is required for first materialization"
                )
            archive_content = captured_content
            temporary_archive = PYTHON_ARCHIVE_CACHE.with_suffix(".partial")
            created_temporary_archive = False
            try:
                with temporary_archive.open("xb") as output:
                    created_temporary_archive = True
                    output.write(archive_content)
                temporary_archive.chmod(0o444)
                os.replace(temporary_archive, PYTHON_ARCHIVE_CACHE)
            finally:
                if created_temporary_archive and temporary_archive.exists():
                    temporary_archive.unlink()
        _verify_python_archive(archive_content)
        if not PYTHON_RUNTIME_ROOT.exists():
            try:
                _extract_python(archive_content, PYTHON_RUNTIME_ROOT)
                _python_runtime_manifest(PYTHON_RUNTIME_ROOT)
            except BaseException:
                _cleanup_partial_tree(PYTHON_RUNTIME_ROOT)
                raise
        _python_runtime_manifest(PYTHON_RUNTIME_ROOT)
    return PYTHON_RUNTIME_ROOT / "bin" / "python3.12"


def _typescript_expected_mode(relative: str) -> int:
    core = TYPESCRIPT_CORE_FILES.get(relative)
    return core[2] if core is not None else 0o444


def _typescript_tree_inventory(
    root: Path,
    *,
    runtime: bool,
) -> tuple[tuple[object, ...], tuple[tuple[object, ...], ...]]:
    """Bind the exact two-directory TypeScript package layout."""

    try:
        if root.resolve(strict=True) != root:
            raise RuntimeError("Batch29 TypeScript tree root is unsafe")
        descendants = sorted(
            root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
        )
        root_metadata = root.lstat()
    except OSError as error:
        raise RuntimeError("Batch29 TypeScript tree is unavailable") from error
    expected_mode = 0o555 if runtime else None
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(root_metadata.st_mode) & 0o022
        or (
            expected_mode is not None
            and stat.S_IMODE(root_metadata.st_mode) != expected_mode
        )
    ):
        raise RuntimeError("Batch29 TypeScript tree root is unsafe")
    directories: list[tuple[object, ...]] = []
    files: set[str] = set()
    for item in descendants:
        relative = item.relative_to(root).as_posix()
        metadata = item.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            if (
                metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
                or (
                    expected_mode is not None
                    and stat.S_IMODE(metadata.st_mode) != expected_mode
                )
            ):
                raise RuntimeError("Batch29 TypeScript tree directory is unsafe")
            directories.append(
                (
                    relative,
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                )
            )
        elif stat.S_ISREG(metadata.st_mode):
            files.add(relative)
        else:
            raise RuntimeError("Batch29 TypeScript tree contains a special file")
    if {str(item[0]) for item in directories} != {"bin", "lib"}:
        raise RuntimeError("Batch29 TypeScript directory inventory mismatch")
    if files != set(TYPESCRIPT_FILES):
        raise RuntimeError("Batch29 TypeScript runtime file inventory mismatch")
    root_identity = (
        root_metadata.st_dev,
        root_metadata.st_ino,
        root_metadata.st_mode,
        root_metadata.st_uid,
        root_metadata.st_gid,
        root_metadata.st_mtime_ns,
    )
    return root_identity, tuple(directories)


def _typescript_file_snapshot(
    path: Path,
    *,
    expected_mode: int | None,
) -> tuple[bytes, int]:
    try:
        before = path.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened_before = os.fstat(descriptor)
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError as error:
        raise RuntimeError(
            f"Batch29 TypeScript file is unavailable: {path.name}"
        ) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    content = b"".join(chunks)
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_size,
            opened_before.st_uid,
            opened_before.st_gid,
            opened_before.st_nlink,
            opened_before.st_mtime_ns,
        )
        or identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_size,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_nlink,
            opened_after.st_mtime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_nlink != 1
        or len(content) != after.st_size
        or (
            expected_mode is not None
            and stat.S_IMODE(after.st_mode) != expected_mode
        )
    ):
        raise RuntimeError(f"Batch29 TypeScript file is unsafe: {path.name}")
    return content, stat.S_IMODE(after.st_mode)


def _typescript_tree_snapshot(
    root: Path,
    *,
    runtime: bool,
) -> tuple[dict[str, bytes], dict[str, object]]:
    before = _typescript_tree_inventory(root, runtime=runtime)
    contents: dict[str, bytes] = {}
    source_records: list[dict[str, object]] = []
    runtime_records: list[dict[str, object]] = []
    for relative in TYPESCRIPT_FILES:
        mode = _typescript_expected_mode(relative) if runtime else None
        content, observed_mode = _typescript_file_snapshot(
            root / relative,
            expected_mode=mode,
        )
        digest = hashlib.sha256(content).hexdigest()
        core = TYPESCRIPT_CORE_FILES.get(relative)
        if core is not None and (len(content), digest) != core[:2]:
            raise RuntimeError(
                f"Batch29 TypeScript core identity mismatch: {relative}"
            )
        contents[relative] = content
        source_records.append(
            {"path": relative, "bytes": len(content), "sha256": digest}
        )
        runtime_records.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": digest,
                "mode": f"{observed_mode:04o}",
            }
        )
    after = _typescript_tree_inventory(root, runtime=runtime)
    if before != after:
        raise RuntimeError("Batch29 TypeScript tree changed during verification")
    source_identity = {
        "sha256": _canonical_digest({"files": source_records}),
        "file_count": len(source_records),
        "bytes": sum(cast(int, item["bytes"]) for item in source_records),
    }
    if source_identity != {
        "sha256": TYPESCRIPT_SOURCE_MANIFEST_SHA256,
        "file_count": TYPESCRIPT_FILE_COUNT,
        "bytes": TYPESCRIPT_CLOSURE_BYTES,
    }:
        raise RuntimeError("Batch29 TypeScript source manifest mismatch")
    identity = source_identity
    if runtime:
        identity = {
            "sha256": _canonical_digest({"files": runtime_records}),
            "file_count": len(runtime_records),
            "bytes": sum(cast(int, item["bytes"]) for item in runtime_records),
        }
        if identity != {
            "sha256": TYPESCRIPT_RUNTIME_MANIFEST_SHA256,
            "file_count": TYPESCRIPT_FILE_COUNT,
            "bytes": TYPESCRIPT_CLOSURE_BYTES,
        }:
            raise RuntimeError("Batch29 TypeScript runtime manifest mismatch")
    return contents, identity


def _typescript_runtime_manifest(root: Path) -> dict[str, object]:
    return _typescript_tree_snapshot(root, runtime=True)[1]


def _captured_typescript_snapshot(root: Path, relative: str) -> dict[str, bytes]:
    """Read the explicit route-local compiler closure without ambient fallback."""

    if relative != TYPESCRIPT_CAPTURED_ROOT_RELATIVE:
        raise RuntimeError("Batch29 captured TypeScript path is not content-addressed")
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError("Batch29 captured TypeScript path is invalid")
    try:
        resolved_root = root.resolve(strict=True)
        root_before = root.lstat()
        if (
            root != resolved_root
            or stat.S_ISLNK(root_before.st_mode)
            or not stat.S_ISDIR(root_before.st_mode)
            or root_before.st_uid not in {0, os.getuid()}
            or stat.S_IMODE(root_before.st_mode) & 0o022
        ):
            raise RuntimeError("Batch29 captured TypeScript root is unsafe")
        candidate = root.joinpath(*parts)
        candidate.resolve(strict=True).relative_to(resolved_root)
        cursor = root
        chain_before: list[tuple[object, ...]] = []
        for part in parts[:-1]:
            cursor = cursor / part
            metadata = cursor.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RuntimeError("Batch29 captured TypeScript path is unsafe")
            chain_before.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                )
            )
        contents, _identity = _typescript_tree_snapshot(candidate, runtime=False)
        root_after = root.lstat()
        chain_after: list[tuple[object, ...]] = []
        cursor = root
        for part in parts[:-1]:
            cursor = cursor / part
            metadata = cursor.lstat()
            chain_after.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                )
            )
    except OSError as error:
        raise RuntimeError("Batch29 captured TypeScript closure is unavailable") from error
    if (
        (
            root_before.st_dev,
            root_before.st_ino,
            root_before.st_mode,
            root_before.st_uid,
            root_before.st_gid,
            root_before.st_mtime_ns,
        )
        != (
            root_after.st_dev,
            root_after.st_ino,
            root_after.st_mode,
            root_after.st_uid,
            root_after.st_gid,
            root_after.st_mtime_ns,
        )
        or chain_before != chain_after
    ):
        raise RuntimeError("Batch29 captured TypeScript closure changed")
    return contents


def _prepare_typescript_runtime(
    *,
    captured_root: Path | None = None,
    captured_relative: str | None = None,
) -> Path:
    """Materialize the exact TypeScript compiler and full stdlib closure."""

    if (captured_root is None) != (captured_relative is None):
        raise RuntimeError("Batch29 captured TypeScript input is incomplete")
    with _cache_lock(TYPESCRIPT_CACHE, ".materialize.lock"):
        _safe_cache_directory(TYPESCRIPT_RUNTIME_ROOT.parent, create=True)
        captured = (
            _captured_typescript_snapshot(captured_root, captured_relative)
            if captured_root is not None and captured_relative is not None
            else None
        )
        if not TYPESCRIPT_RUNTIME_ROOT.exists():
            if captured is None:
                raise RuntimeError(
                    "Batch29 captured TypeScript closure is required for first materialization"
                )
            try:
                TYPESCRIPT_RUNTIME_ROOT.mkdir(mode=0o700)
                for relative in TYPESCRIPT_FILES:
                    target = TYPESCRIPT_RUNTIME_ROOT / relative
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with target.open("xb") as output:
                        output.write(captured[relative])
                    target.chmod(_typescript_expected_mode(relative))
                for directory in sorted(
                    (
                        item
                        for item in TYPESCRIPT_RUNTIME_ROOT.rglob("*")
                        if item.is_dir()
                    ),
                    key=lambda item: len(item.parts),
                    reverse=True,
                ):
                    directory.chmod(0o555)
                TYPESCRIPT_RUNTIME_ROOT.chmod(0o555)
                _typescript_runtime_manifest(TYPESCRIPT_RUNTIME_ROOT)
            except BaseException:
                _cleanup_partial_tree(TYPESCRIPT_RUNTIME_ROOT)
                raise
        _typescript_runtime_manifest(TYPESCRIPT_RUNTIME_ROOT)
    return TYPESCRIPT_RUNTIME_ROOT / "bin" / "tsc"


def _repository_root(script: Path) -> Path:
    resolved = script.resolve(strict=True)
    candidate = resolved.parents[2]
    project = candidate / "engines" / "polyglot-route-engine"
    if (
        not (project / "pyproject.toml").is_file()
        or not (project / "uv.lock").is_file()
    ):
        raise RuntimeError("Batch29 repository route-engine project is missing")
    return candidate


def _pinned_uv() -> Path:
    def bind() -> tuple[object, ...]:
        expected = PINNED_UV_PATH
        cursor = Path("/")
        chain: list[tuple[object, ...]] = []
        try:
            for part in expected.parent.parts[1:]:
                cursor = cursor / part
                metadata = cursor.lstat()
                below_cellar = cursor.is_relative_to(
                    Path("/opt/homebrew/Cellar")
                ) and cursor != Path("/opt/homebrew/Cellar")
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or not stat.S_ISDIR(metadata.st_mode)
                    or metadata.st_uid not in {0, os.getuid()}
                    or (below_cellar and stat.S_IMODE(metadata.st_mode) & 0o022)
                ):
                    raise RuntimeError("Batch29 pinned uv path chain is unsafe")
                chain.append(
                    (
                        str(cursor),
                        metadata.st_dev,
                        metadata.st_ino,
                        metadata.st_mode,
                        metadata.st_uid,
                        metadata.st_gid,
                        metadata.st_mtime_ns,
                    )
                )
            before = expected.lstat()
            if expected.resolve(strict=True) != expected:
                raise RuntimeError("Batch29 pinned uv origin mismatch")
            flags = (
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(expected, flags)
            try:
                opened_before = os.fstat(descriptor)
                digest = hashlib.sha256()
                byte_count = 0
                while chunk := os.read(descriptor, 1024 * 1024):
                    digest.update(chunk)
                    byte_count += len(chunk)
                opened_after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            after = expected.lstat()
        except OSError as error:
            raise RuntimeError("Batch29 pinned uv is unavailable") from error
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_uid,
            before.st_gid,
            before.st_nlink,
            before.st_mtime_ns,
        )
        if (
            identity
            != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_size,
                after.st_uid,
                after.st_gid,
                after.st_nlink,
                after.st_mtime_ns,
            )
            or identity
            != (
                opened_before.st_dev,
                opened_before.st_ino,
                opened_before.st_mode,
                opened_before.st_size,
                opened_before.st_uid,
                opened_before.st_gid,
                opened_before.st_nlink,
                opened_before.st_mtime_ns,
            )
            or identity
            != (
                opened_after.st_dev,
                opened_after.st_ino,
                opened_after.st_mode,
                opened_after.st_size,
                opened_after.st_uid,
                opened_after.st_gid,
                opened_after.st_nlink,
                opened_after.st_mtime_ns,
            )
            or not stat.S_ISREG(after.st_mode)
            or stat.S_IMODE(after.st_mode) != PINNED_UV_MODE
            or after.st_uid != PINNED_UV_UID
            or after.st_gid != PINNED_UV_GID
            or after.st_nlink != PINNED_UV_NLINK
            or byte_count != PINNED_UV_BYTES
            or "sha256:" + digest.hexdigest() != PINNED_UV_SHA256
        ):
            raise RuntimeError("Batch29 pinned uv bytes/metadata/digest mismatch")
        return (*chain, str(expected), *identity, byte_count, digest.hexdigest())

    before = bind()
    expected = PINNED_UV_PATH
    environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(expected.parent) + os.pathsep + os.defpath,
        "UV_NO_CONFIG": "1",
    }
    result = subprocess.run(
        [str(expected), "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env=environment,
    )
    if result.returncode != 0 or result.stdout.strip() != PINNED_UV_VERSION:
        raise RuntimeError("Batch29 pinned uv version mismatch")
    if bind() != before:
        raise RuntimeError("Batch29 pinned uv changed during verification")
    return expected


def run_in_fresh_locked_runtime(
    script: Path,
    argv: list[str],
    *,
    captured_python_archive_root: Path | None = None,
    captured_python_archive_relative: str | None = None,
    captured_typescript_root: Path | None = None,
    captured_typescript_relative: str | None = None,
) -> int:
    """Always execute ``script.main`` inside a newly resolved locked venv."""

    repository = _repository_root(script)
    project = repository / "engines" / "polyglot-route-engine"
    uv = _pinned_uv()
    python = _prepare_python_runtime(
        captured_archive_root=captured_python_archive_root,
        captured_archive_relative=captured_python_archive_relative,
    )
    _prepare_typescript_runtime(
        captured_root=captured_typescript_root,
        captured_relative=captured_typescript_relative,
    )
    with tempfile.TemporaryDirectory(
        prefix="elmos-batch29-fresh-route-runtime-"
    ) as temporary:
        runtime_root = Path(temporary).resolve(strict=True)
        runtime_root.chmod(0o700)
        project_environment = runtime_root / ".venv"
        environment = {
            key: os.environ[key]
            for key in ("HOME", "TMPDIR", "TZ")
            if key in os.environ
        }
        environment.update(
            {
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": str(uv.parent) + os.pathsep + os.defpath,
                "PYTHONNOUSERSITE": "1",
                "UV_NO_CONFIG": "1",
                "UV_OFFLINE": "1",
                "UV_PYTHON_DOWNLOADS": "never",
                PROJECT_ENVIRONMENT_ENV: str(project_environment),
            }
        )
        completed = subprocess.run(
            [
                str(uv),
                "--project",
                str(project),
                "run",
                "--locked",
                "--offline",
                "--no-python-downloads",
                "--python",
                str(python),
                "python",
                "-c",
                CHILD_PROGRAM,
                str(script.resolve(strict=True)),
                *argv,
            ],
            cwd=Path.cwd(),
            env=environment,
            check=False,
        )
        return completed.returncode
