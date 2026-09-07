"""Fail-closed group normalization for private JavaScript/TypeScript roots."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from elmos_polyglot_route import native
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.toolchains import ExactToolchain

FAILURES = (
    "JAVASCRIPT_ANALYZER_SNAPSHOT_UNSAFE",
    "TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE",
)


def _assign_mismatched_inherited_group(root: Path) -> int:
    for group in os.getgroups():
        if group == os.getgid():
            continue
        try:
            os.chown(root, -1, group)
        except OSError:
            continue
        if root.lstat().st_gid == group:
            return group
    pytest.skip("the test account has no assignable supplementary group")


@pytest.mark.parametrize("failure", FAILURES)
def test_private_analyzer_root_normalizes_inherited_mismatched_gid(
    tmp_path: Path,
    failure: str,
) -> None:
    root = tmp_path / failure.lower()
    root.mkdir(mode=0o700)
    inherited_group = _assign_mismatched_inherited_group(root)
    before = root.lstat()

    native._normalize_private_analyzer_root_group(root, failure=failure)

    after = root.lstat()
    assert inherited_group != os.getgid()
    assert after.st_gid == os.getgid()
    assert stat.S_IMODE(after.st_mode) == 0o700
    assert (after.st_dev, after.st_ino, after.st_uid) == (
        before.st_dev,
        before.st_ino,
        before.st_uid,
    )


@pytest.mark.parametrize("failure", FAILURES)
def test_private_analyzer_root_rejects_symlink_before_fchown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    root = tmp_path / "root"
    root.symlink_to(target, target_is_directory=True)
    called = False

    def forbidden_fchown(descriptor: int, uid: int, gid: int) -> None:
        nonlocal called
        del descriptor, uid, gid
        called = True

    monkeypatch.setattr(native.os, "fchown", forbidden_fchown)

    with pytest.raises(RouteError, match=f"^{failure}$"):
        native._normalize_private_analyzer_root_group(root, failure=failure)

    assert not called


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("tamper", ["mode", "symlink", "replacement", "fchown-error"])
def test_private_analyzer_root_rejects_fchown_time_tamper_and_integrity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    tamper: str,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    displaced = tmp_path / "displaced"
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    real_fchown = os.fchown

    def tampering_fchown(descriptor: int, uid: int, gid: int) -> None:
        if tamper == "fchown-error":
            raise PermissionError("simulated group-normalization denial")
        real_fchown(descriptor, uid, gid)
        candidate = root
        if tamper == "mode":
            candidate.chmod(0o755)
        elif tamper == "symlink":
            candidate.rename(displaced)
            candidate.symlink_to(outside, target_is_directory=True)
        else:
            candidate.rename(displaced)
            candidate.mkdir(mode=0o700)
            os.chown(candidate, uid, gid)

    monkeypatch.setattr(native.os, "fchown", tampering_fchown)

    with pytest.raises(RouteError, match=f"^{failure}$"):
        native._normalize_private_analyzer_root_group(root, failure=failure)


@pytest.mark.parametrize("failure", FAILURES)
def test_private_analyzer_root_path_swap_never_chowns_symlink_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    root_before = root.lstat()
    displaced = tmp_path / "displaced"
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    target_before = target.lstat()
    real_fchown = os.fchown
    changed_inode: tuple[int, int] | None = None

    def swapping_fchown(descriptor: int, uid: int, gid: int) -> None:
        nonlocal changed_inode
        root.rename(displaced)
        root.symlink_to(target, target_is_directory=True)
        opened = os.fstat(descriptor)
        changed_inode = (opened.st_dev, opened.st_ino)
        real_fchown(descriptor, uid, gid)

    monkeypatch.setattr(native.os, "fchown", swapping_fchown)

    with pytest.raises(RouteError, match=f"^{failure}$"):
        native._normalize_private_analyzer_root_group(root, failure=failure)

    target_after = target.lstat()
    assert changed_inode == (root_before.st_dev, root_before.st_ino)
    assert changed_inode != (target_before.st_dev, target_before.st_ino)
    assert (
        target_after.st_dev,
        target_after.st_ino,
        target_after.st_mode,
        target_after.st_uid,
        target_after.st_gid,
        target_after.st_nlink,
        target_after.st_size,
        target_after.st_mtime_ns,
        target_after.st_ctime_ns,
    ) == (
        target_before.st_dev,
        target_before.st_ino,
        target_before.st_mode,
        target_before.st_uid,
        target_before.st_gid,
        target_before.st_nlink,
        target_before.st_size,
        target_before.st_mtime_ns,
        target_before.st_ctime_ns,
    )


def test_javascript_runner_reaches_private_root_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mjs"
    source.write_text("export function value() { return 1; }\n", encoding="utf-8")
    toolchain = ExactToolchain(
        language="javascript",
        version="test",
        executable="/nonexistent/node",
    )
    observed: list[tuple[Path, str]] = []

    monkeypatch.setattr(native, "javascript_esm_descriptor", lambda _source: None)
    monkeypatch.setattr(native, "_javascript_analyzer_inputs", lambda *_args: ({}, {}))
    monkeypatch.setattr(native, "_verify_trusted_javascript_toolchain", lambda _toolchain: {})

    def reached(root: Path, *, failure: str) -> None:
        observed.append((root, failure))
        assert root == root.resolve(strict=True)
        assert stat.S_IMODE(root.lstat().st_mode) == 0o700
        raise RouteError("TEST_JAVASCRIPT_ROOT_NORMALIZATION_REACHED")

    monkeypatch.setattr(native, "_normalize_private_analyzer_root_group", reached)

    with pytest.raises(RouteError, match="^TEST_JAVASCRIPT_ROOT_NORMALIZATION_REACHED$"):
        native._run_trusted_javascript_analyzer(toolchain, source, "--inventory")

    assert len(observed) == 1
    assert observed[0][1] == "JAVASCRIPT_ANALYZER_SNAPSHOT_UNSAFE"


def test_typescript_runner_reaches_private_root_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.ts"
    source.write_text("export function value(): number { return 1; }\n", encoding="utf-8")
    toolchain = ExactToolchain(
        language="typescript",
        version="test",
        executable="/nonexistent/node",
    )
    observed: list[tuple[Path, str]] = []

    monkeypatch.setattr(native, "typescript_parser_receipt", lambda: {})
    monkeypatch.setattr(native, "_validated_typescript_parser_receipt", lambda receipt: receipt)
    monkeypatch.setattr(native, "_typescript_toolchain_binding", lambda *_args: {})
    monkeypatch.setattr(native, "_typescript_analyzer_inputs", lambda *_args: ({}, {}))

    def reached(root: Path, *, failure: str) -> None:
        observed.append((root, failure))
        assert root == root.resolve(strict=True)
        assert stat.S_IMODE(root.lstat().st_mode) == 0o700
        raise RouteError("TEST_TYPESCRIPT_ROOT_NORMALIZATION_REACHED")

    monkeypatch.setattr(native, "_normalize_private_analyzer_root_group", reached)

    with pytest.raises(RouteError, match="^TEST_TYPESCRIPT_ROOT_NORMALIZATION_REACHED$"):
        native._run_trusted_typescript_analyzer(toolchain, source, "--inventory")

    assert len(observed) == 1
    assert observed[0][1] == "TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE"
