from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from elmos_polyglot_route import toolchains
from elmos_polyglot_route.models import RouteError


def _tree_identity(
    root: Path,
    sha256: str,
    record_count: int,
    file_count: int,
    directory_count: int,
    byte_count: int,
) -> dict[str, object]:
    return {
        "root": str(root),
        "sha256": sha256,
        "record_count": record_count,
        "file_count": file_count,
        "directory_count": directory_count,
        "bytes": byte_count,
    }


@pytest.mark.parametrize("language", ["go", "rust", "python"])
def test_real_fixed_user_toolchains_work_without_ambient_path(
    language: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    selected = toolchains.exact_toolchain(language)  # type: ignore[arg-type]

    assert Path(selected.executable).is_relative_to(
        toolchains.configured_polyglot_toolchain_root()
    )
    assert selected.executable_sha256
    assert selected.profile
    assert any(item.endswith("=NOT_RUN") for item in selected.profile)


def test_complete_tree_verifier_rejects_a_self_consistent_forgery() -> None:
    forged = _tree_identity(Path("/fixed/go"), "f" * 64, 1, 1, 0, 7)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_GO_TREE_MISMATCH"):
        toolchains._verify_qualified_tree_manifest(
            forged,
            expected_root=Path("/fixed/go"),
            expected_sha256="0" * 64,
            expected_record_count=1,
            expected_file_count=1,
            expected_directory_count=0,
            expected_bytes=7,
            failure="EXACT_TOOLCHAIN_GO_TREE_MISMATCH",
        )


def test_go_tree_verifier_rejects_same_version_content_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged = _tree_identity(
        toolchains._EXPECTED_GO_ROOT,
        "a" * 64,
        toolchains._EXPECTED_GO_TREE_RECORD_COUNT,
        toolchains._EXPECTED_GO_TREE_FILE_COUNT,
        toolchains._EXPECTED_GO_TREE_DIRECTORY_COUNT,
        toolchains._EXPECTED_GO_TREE_BYTES,
    )
    monkeypatch.setattr(toolchains, "_qualified_tree_manifest", lambda *args, **kwargs: forged)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_GO_TREE_MISMATCH"):
        toolchains._go_tree_identity()


@pytest.mark.parametrize("drift", ["wrapper", "sysroot"])
def test_rust_rejects_wrapper_or_sysroot_tree_drift(
    drift: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrappers = _tree_identity(
        toolchains._EXPECTED_RUST_WRAPPER_ROOT,
        toolchains._EXPECTED_RUST_WRAPPER_TREE_SHA256,
        toolchains._EXPECTED_RUST_WRAPPER_TREE_RECORD_COUNT,
        toolchains._EXPECTED_RUST_WRAPPER_TREE_FILE_COUNT,
        toolchains._EXPECTED_RUST_WRAPPER_TREE_DIRECTORY_COUNT,
        toolchains._EXPECTED_RUST_WRAPPER_TREE_BYTES,
    )
    sysroot = _tree_identity(
        toolchains._EXPECTED_RUST_SYSROOT,
        toolchains._EXPECTED_RUST_SYSROOT_TREE_SHA256,
        toolchains._EXPECTED_RUST_SYSROOT_TREE_RECORD_COUNT,
        toolchains._EXPECTED_RUST_SYSROOT_TREE_FILE_COUNT,
        toolchains._EXPECTED_RUST_SYSROOT_TREE_DIRECTORY_COUNT,
        toolchains._EXPECTED_RUST_SYSROOT_TREE_BYTES,
    )
    selected = wrappers if drift == "wrapper" else sysroot
    selected["sha256"] = "b" * 64

    def manifest(root: Path, *_args: object, **_kwargs: object) -> dict[str, object]:
        return wrappers if root == toolchains._EXPECTED_RUST_WRAPPER_ROOT else sysroot

    monkeypatch.setattr(toolchains, "_qualified_tree_manifest", manifest)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_RUST_.*_TREE_MISMATCH"):
        toolchains._rust_tree_identities()


def test_rust_rejects_real_compiler_content_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        toolchains._EXPECTED_RUST_EXECUTABLE: (
            toolchains._EXPECTED_RUST_EXECUTABLE_SHA256,
            toolchains._EXPECTED_RUST_EXECUTABLE_BYTES,
        ),
        toolchains._EXPECTED_RUST_CARGO: (
            toolchains._EXPECTED_RUST_CARGO_SHA256,
            toolchains._EXPECTED_RUST_CARGO_BYTES,
        ),
        toolchains._EXPECTED_RUST_SETTINGS: (
            toolchains._EXPECTED_RUST_SETTINGS_SHA256,
            toolchains._EXPECTED_RUST_SETTINGS_BYTES,
        ),
        toolchains._EXPECTED_RUST_RUSTUP: (
            toolchains._EXPECTED_RUST_RUSTUP_SHA256,
            toolchains._EXPECTED_RUST_RUSTUP_BYTES,
        ),
    }

    def binding(path: Path, *_args: object, **_kwargs: object) -> dict[str, str | int]:
        digest, byte_count = expected[path]
        if path == toolchains._EXPECTED_RUST_EXECUTABLE:
            digest = "c" * 64
        return {"sha256": digest, "bytes": byte_count}

    monkeypatch.setattr(toolchains, "_qualified_file_record", binding)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_RUST_AUXILIARY_MISMATCH"):
        toolchains._rust_auxiliary_bindings()


def test_python_tree_verifier_rejects_archive_consistent_runtime_drift() -> None:
    forged = {
        "root": str(toolchains._EXPECTED_PYTHON_ROOT),
        "sha256": "d" * 64,
        "record_count": toolchains._EXPECTED_PYTHON_RUNTIME_RECORD_COUNT,
        "file_count": toolchains._EXPECTED_PYTHON_RUNTIME_FILE_COUNT,
        "bytes": toolchains._EXPECTED_PYTHON_RUNTIME_BYTES,
        "symlinks": copy.deepcopy(toolchains._EXPECTED_PYTHON_SYMLINKS),
    }

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_PYTHON_TREE_MISMATCH"):
        toolchains._verify_python_runtime_tree(forged)


def test_python_source_archive_receipt_is_capture_ready() -> None:
    receipt = toolchains.python_source_archive_receipt()

    assert receipt == {
        "schema_version": 1,
        "source_path": str(toolchains._EXPECTED_PYTHON_ARCHIVE),
        "capture_relative_path": toolchains._EXPECTED_PYTHON_CAPTURE_RELATIVE,
        "sha256": toolchains._EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256,
        "bytes": toolchains._EXPECTED_PYTHON_SOURCE_ARCHIVE_BYTES,
        "mode": "0444",
        "uid": os.getuid(),
        "gid": toolchains._EXPECTED_PYTHON_ARCHIVE.lstat().st_gid,
        "nlink": 1,
        "source_tree_sha256": toolchains._EXPECTED_PYTHON_SOURCE_TREE_SHA256,
        "source_tree_record_count": toolchains._EXPECTED_PYTHON_RUNTIME_RECORD_COUNT,
        "source_tree_file_count": toolchains._EXPECTED_PYTHON_RUNTIME_FILE_COUNT,
        "source_tree_bytes": toolchains._EXPECTED_PYTHON_RUNTIME_BYTES,
    }


def test_fixed_selector_rejects_retargeting(tmp_path: Path) -> None:
    anchor = tmp_path / "local"
    binary = anchor / "share" / "toolchain" / "bin"
    public = anchor / "bin"
    binary.mkdir(parents=True)
    public.mkdir()
    expected = binary / "expected"
    replacement = binary / "replacement"
    expected.write_bytes(b"expected")
    replacement.write_bytes(b"replacement")
    declared = public / "compiler"
    declared.symlink_to(replacement)

    with pytest.raises(RouteError, match="TEST_SELECTOR_UNSAFE"):
        toolchains._qualified_fixed_symlink(
            declared,
            anchor=anchor,
            expected_target=str(expected),
            expected_resolved=expected,
            failure="TEST_SELECTOR_UNSAFE",
        )


@pytest.mark.parametrize("unsafe_kind", ["symlink", "writable", "hardlink"])
def test_file_binding_rejects_symlink_writable_or_hardlinked_content(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    original = root / "original"
    original.write_bytes(b"fixed")
    candidate = original
    if unsafe_kind == "symlink":
        candidate = root / "candidate"
        candidate.symlink_to(original.name)
    elif unsafe_kind == "writable":
        original.chmod(0o666)
    else:
        os.link(original, root / "second-link")

    with pytest.raises(RouteError, match="TEST_FILE_UNSAFE"):
        toolchains._qualified_file_record(candidate, root, "TEST_FILE_UNSAFE")


def test_typescript_closure_is_detached_from_live_frontend_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    closure = toolchains._typescript_compiler_closure()
    toolchains._verify_typescript_compiler_closure(closure)
    receipt = toolchains.typescript_parser_receipt()
    capture = toolchains.typescript_compiler_capture_receipt()

    assert closure["sha256"] == toolchains._EXPECTED_TYPESCRIPT_CLOSURE_SHA256
    assert str(toolchains.REPOSITORY_ROOT) not in str(closure["manifest"])
    assert capture["capture_relative_path"] == (
        toolchains._EXPECTED_TYPESCRIPT_CAPTURE_RELATIVE
    )
    assert capture["source_root"] == str(toolchains._EXPECTED_TYPESCRIPT_ROOT)
    assert capture["source_manifest_sha256"] == (
        toolchains._EXPECTED_TYPESCRIPT_SOURCE_MANIFEST_SHA256
    )
    assert capture["runtime_manifest_sha256"] == (
        toolchains._EXPECTED_TYPESCRIPT_RUNTIME_MANIFEST_SHA256
    )
    assert capture["file_count"] == 108
    assert len(capture["files"]) == 108
    assert any(
        item["path"] == "lib/lib.es2022.full.d.ts"
        for item in capture["files"]
    )
    assert receipt == {
        "schema_version": 1,
        "path": str(toolchains._EXPECTED_TYPESCRIPT_PARSER),
        "sha256": toolchains._EXPECTED_TYPESCRIPT_PARSER_SHA256,
        "bytes": toolchains._EXPECTED_TYPESCRIPT_PARSER_BYTES,
        "mode": "0444",
        "uid": os.getuid(),
        "gid": toolchains._EXPECTED_TYPESCRIPT_PARSER.lstat().st_gid,
        "nlink": 1,
        "compiler_root": str(toolchains._EXPECTED_TYPESCRIPT_ROOT),
        "compiler_closure_sha256": toolchains._EXPECTED_TYPESCRIPT_CLOSURE_SHA256,
        "compiler_closure_file_count": toolchains._EXPECTED_TYPESCRIPT_CLOSURE_FILE_COUNT,
        "compiler_closure_bytes": toolchains._EXPECTED_TYPESCRIPT_CLOSURE_BYTES,
        "semantic_soundness": "NOT_RUN",
    }
