"""Integrity contract for the engine-owned TypeScript parser asset."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parents[1] / "native" / "javascript" / "vendor" / "typescript-5.9.2"
EXPECTED_FILES = {
    "LICENSE.txt": (9197, "a7d00bfd54525bc694b6e32f64c7ebcf5e6b7ae3657be5cc12767bce74654a47"),
    "package.json": (3620, "5a0bb7f286c4b3f1413a42c05f902311b161f70e5f52d9da10490443bfd595a3"),
    "typescript.js": (9111680, "e5f1f6b3e82228a89873cc7b941b2465185e839c0692860f83e3e63e53f94c2b"),
}
MANIFEST_BYTES = 931
MANIFEST_SHA256 = "e42b0b7a74a8b6532fb3edc39135776b9ee81e93aea0157a5e0c1c80ac44b073"


def _stable_file_identity(path: Path) -> tuple[int, ...]:
    metadata = path.lstat()
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


def _read_bound_regular_file(path: Path) -> bytes:
    before = _stable_file_identity(path)
    metadata = path.lstat()
    assert stat.S_ISREG(metadata.st_mode)
    assert not path.is_symlink()
    assert metadata.st_nlink == 1
    assert metadata.st_uid == os.getuid()
    assert not stat.S_IMODE(metadata.st_mode) & 0o022
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened_before = os.fstat(descriptor)
        content = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            content.extend(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = _stable_file_identity(path)
    for opened in (opened_before, opened_after):
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_nlink,
            opened.st_uid,
            opened.st_gid,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        assert opened_identity == before
    assert before == after
    return bytes(content)


def test_typescript_parser_asset_is_exact_and_self_describing() -> None:
    root_metadata = VENDOR_ROOT.lstat()
    assert stat.S_ISDIR(root_metadata.st_mode)
    assert not VENDOR_ROOT.is_symlink()
    assert root_metadata.st_uid == os.getuid()
    assert not stat.S_IMODE(root_metadata.st_mode) & 0o022
    assert {path.name for path in VENDOR_ROOT.iterdir()} == {
        "asset-manifest.json",
        *EXPECTED_FILES,
    }
    manifest_path = VENDOR_ROOT / "asset-manifest.json"
    manifest_bytes = _read_bound_regular_file(manifest_path)
    assert len(manifest_bytes) == MANIFEST_BYTES
    assert hashlib.sha256(manifest_bytes).hexdigest() == MANIFEST_SHA256
    manifest = json.loads(manifest_bytes)
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["asset_id"] == "typescript-parser-5.9.2"
    assert manifest["package"] == {
        "name": "typescript",
        "version": "5.9.2",
        "license": "Apache-2.0",
        "repository": "https://github.com/microsoft/TypeScript.git",
        "registry_tarball": "https://registry.npmjs.org/typescript/-/typescript-5.9.2.tgz",
        "registry_integrity": (
            "sha512-CWBzXQrc/qOkhidw1OzBTQuYRbfyxDXJMVJ1XNwUHGROVmuaeiEm3OslpZ1RV96d7SKKjZKrSJu3+t/xlw3R9A=="
        ),
    }
    declared = {item["path"]: (item["bytes"], item["sha256"]) for item in manifest["files"]}
    assert declared == {name: (byte_count, f"sha256:{digest}") for name, (byte_count, digest) in EXPECTED_FILES.items()}

    contents: dict[str, bytes] = {}
    for name, (byte_count, digest) in EXPECTED_FILES.items():
        content = _read_bound_regular_file(VENDOR_ROOT / name)
        assert len(content) == byte_count
        assert hashlib.sha256(content).hexdigest() == digest
        contents[name] = content

    package = json.loads(contents["package.json"])
    assert package["name"] == "typescript"
    assert package["version"] == "5.9.2"
    assert package["license"] == "Apache-2.0"
