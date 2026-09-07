"""Security and determinism tests for the repository-owned package importer."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = ROOT / "tooling/integrate_polyglot_semantic_assurance_skills.py"


def _load_importer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("polyglot_secure_importer", IMPORTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fingerprint(root: Path) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        identity = (
            f"mode={stat.S_IMODE(metadata.st_mode):04o};uid={metadata.st_uid};"
            f"gid={metadata.st_gid};dev={metadata.st_dev};ino={metadata.st_ino};"
            f"nlink={metadata.st_nlink}"
        )
        if stat.S_ISLNK(metadata.st_mode):
            detail = f"SYMLINK;{identity};target={os.readlink(path)}"
        elif stat.S_ISDIR(metadata.st_mode):
            detail = f"DIRECTORY;{identity}"
        elif stat.S_ISREG(metadata.st_mode):
            detail = f"FILE;{identity};sha256={hashlib.sha256(path.read_bytes()).hexdigest()}"
        else:
            detail = f"SPECIAL:{stat.S_IFMT(metadata.st_mode)};{identity}"
        rows.append((path.relative_to(root).as_posix(), detail))
    return tuple(rows)


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree_with_hardlinks(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, copy_function=os.link)


def _detach_file(path: Path) -> None:
    content = path.read_bytes()
    mode = stat.S_IMODE(path.stat().st_mode)
    path.unlink()
    path.write_bytes(content)
    os.chmod(path, mode)


def _isolated_repository_view(
    destination: Path,
    importer: ModuleType,
    catalog: Mapping[str, Any],
) -> None:
    archive = next(path for path in importer.ARCHIVE_CANDIDATES if (ROOT / path).is_file())
    _copy_file(ROOT / archive, destination / archive)
    shutil.copytree(ROOT / importer.SOURCE_RELATIVE, destination / importer.SOURCE_RELATIVE)
    shutil.copytree(ROOT / importer.DOC_RELATIVE, destination / importer.DOC_RELATIVE)
    _copy_file(
        ROOT / "docs/semantic-assurance-expansion/installed-manifest.json",
        destination / "docs/semantic-assurance-expansion/installed-manifest.json",
    )
    _copy_file(
        ROOT / importer.ENGINE_RESOURCE_RELATIVE,
        destination / importer.ENGINE_RESOURCE_RELATIVE,
    )
    _copy_file(
        ROOT / importer.ENGINE_DIGEST_RELATIVE,
        destination / importer.ENGINE_DIGEST_RELATIVE,
    )
    catalog_names = {str(row["name"]) for row in catalog["skills"]}
    for name in sorted(catalog_names):
        for relative_root in (importer.WORKSPACE_RELATIVE, importer.RUNTIME_RELATIVE):
            _copy_tree_with_hardlinks(
                ROOT / relative_root / name,
                destination / relative_root / name,
            )
    semantic_manifest = json.loads(
        (ROOT / "docs/semantic-assurance-expansion/installed-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for name in semantic_manifest["installedNames"]:
        if name in catalog_names:
            continue
        for relative_root in (importer.WORKSPACE_RELATIVE, importer.RUNTIME_RELATIVE):
            _copy_tree_with_hardlinks(
                ROOT / relative_root / name,
                destination / relative_root / name,
            )


def _archive_path(root: Path, importer: ModuleType) -> Path:
    relative = next(path for path in importer.ARCHIVE_CANDIDATES if (root / path).is_file())
    return root / relative


def test_installed_catalog_binds_all_wrappers_and_collisions() -> None:
    importer = _load_importer()
    snapshot, catalog = importer.check_integration(ROOT)
    result = importer.validate_installed_integration(ROOT, snapshot, catalog)

    assert catalog["counts"]["skills"] == 300
    assert catalog["counts"]["repository_owned_wrappers"] == 167
    assert catalog["counts"]["collision_bindings"] == 133
    assert result == {
        "repository_owned_wrappers": 167,
        "collision_bindings": 133,
        "dual_root_bytes_equal": True,
        "generated_artifacts_digest_bound": True,
    }


def test_check_is_zero_write_and_wrapper_drift_fails_closed(tmp_path: Path) -> None:
    importer = _load_importer()
    _, catalog = importer.check_integration(ROOT)
    isolated = tmp_path / "repository"
    isolated.mkdir()
    _isolated_repository_view(isolated, importer, catalog)

    before = _fingerprint(isolated)
    importer.check_integration(isolated)
    assert _fingerprint(isolated) == before

    generated_name = next(
        str(row["name"])
        for row in catalog["skills"]
        if row["name"] not in importer.COLLISIONS
    )
    wrapper = isolated / importer.WORKSPACE_RELATIVE / generated_name / "SKILL.md"
    _detach_file(wrapper)
    wrapper.write_bytes(wrapper.read_bytes() + b"\n")
    with pytest.raises(importer.IntegrationError, match="workspace wrapper tree differs"):
        importer.check_integration(isolated)


def test_check_rejects_semantic_owner_manifest_drift(tmp_path: Path) -> None:
    importer = _load_importer()
    isolated = tmp_path / "repository"
    _, catalog = importer.check_integration(ROOT)
    _isolated_repository_view(isolated, importer, catalog)

    manifest_path = isolated / "docs/semantic-assurance-expansion/installed-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["packageId"] = "attacker-controlled-package"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="pinned owner manifest"):
        importer.check_integration(isolated)


def test_write_publishes_receipt_last_and_remains_checkable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = _load_importer()
    _, catalog = importer.check_integration(ROOT)
    isolated = tmp_path / "repository"
    isolated.mkdir()
    _isolated_repository_view(isolated, importer, catalog)

    replacements: list[tuple[str, str]] = []
    original_replace = importer._replace_at

    def observed_replace(
        source_parent_fd: int,
        source_name: str,
        destination_parent_fd: int,
        destination_name: str,
    ) -> None:
        original_replace(
            source_parent_fd,
            source_name,
            destination_parent_fd,
            destination_name,
        )
        replacements.append((source_name, destination_name))

    monkeypatch.setattr(importer, "_replace_at", observed_replace)
    importer.write_integration(isolated, _archive_path(isolated, importer))

    assert replacements[-1][1] == importer.RECEIPT_RELATIVE.name
    assert not any(path.name.startswith(importer.TX_PREFIX) for path in isolated.iterdir())
    importer.check_integration(isolated)


@pytest.mark.parametrize("interrupt", [False, True], ids=["oserror", "keyboard-interrupt"])
def test_failure_after_stage_publish_restores_current_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt: bool,
) -> None:
    importer = _load_importer()
    _, catalog = importer.check_integration(ROOT)
    isolated = tmp_path / "repository"
    isolated.mkdir()
    _isolated_repository_view(isolated, importer, catalog)

    receipt_path = isolated / importer.RECEIPT_RELATIVE
    before = _fingerprint(isolated)
    receipt_before = receipt_path.read_bytes()

    original_replace = importer._replace_at
    original_fsync = importer._fsync_dir_fd
    state = {"catalog_published": False, "failed": False}

    def observed_replace(
        source_parent_fd: int,
        source_name: str,
        destination_parent_fd: int,
        destination_name: str,
    ) -> None:
        original_replace(
            source_parent_fd,
            source_name,
            destination_parent_fd,
            destination_name,
        )
        if source_name == "docs-catalog" and destination_name == importer.CATALOG_RELATIVE.name:
            state["catalog_published"] = True

    def injected_fsync(descriptor: int) -> None:
        if state["catalog_published"] and not state["failed"]:
            state["failed"] = True
            if interrupt:
                raise KeyboardInterrupt
            raise OSError("injected directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(importer, "_replace_at", observed_replace)
    monkeypatch.setattr(importer, "_fsync_dir_fd", injected_fsync)
    expected_error: type[BaseException] = KeyboardInterrupt if interrupt else importer.IntegrationError
    with pytest.raises(expected_error):
        importer.write_integration(isolated, _archive_path(isolated, importer))

    assert receipt_path.read_bytes() == receipt_before
    assert _fingerprint(isolated) == before
    assert not any(path.name.startswith(importer.TX_PREFIX) for path in isolated.iterdir())


def test_write_rejects_symlink_ancestor_without_touching_outside(tmp_path: Path) -> None:
    importer = _load_importer()
    _, catalog = importer.check_integration(ROOT)
    isolated = tmp_path / "repository"
    isolated.mkdir()
    _isolated_repository_view(isolated, importer, catalog)

    outside = tmp_path / "outside"
    (outside / "skills").mkdir(parents=True)
    shutil.rmtree(isolated / ".agents")
    (isolated / ".agents").symlink_to(outside, target_is_directory=True)
    outside_before = _fingerprint(outside)

    with pytest.raises(importer.IntegrationError, match="symlink or non-directory component"):
        importer.write_integration(isolated, _archive_path(isolated, importer))
    assert _fingerprint(outside) == outside_before


def test_check_rejects_docs_ancestor_symlink_even_with_exact_outputs(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    _, catalog = importer.check_integration(ROOT)
    isolated = tmp_path / "repository"
    isolated.mkdir()
    _isolated_repository_view(isolated, importer, catalog)

    outside = tmp_path / "outside-docs"
    (isolated / "docs").rename(outside)
    (isolated / "docs").symlink_to(outside, target_is_directory=True)
    outside_before = _fingerprint(outside)

    with pytest.raises(importer.IntegrationError, match="symlink or non-directory component"):
        importer.check_integration(isolated)
    assert _fingerprint(outside) == outside_before


def test_dangling_collision_symlink_never_falls_back_to_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = _load_importer()
    relative = Path("collision-owner")
    (tmp_path / relative).symlink_to(tmp_path / "missing", target_is_directory=True)
    head_called = False

    def unexpected_head(*_args: object, **_kwargs: object) -> Mapping[str, bytes]:
        nonlocal head_called
        head_called = True
        return {"SKILL.md": b"wrong"}

    monkeypatch.setattr(importer, "_head_tree", unexpected_head)
    with pytest.raises(importer.IntegrationError, match="symlink"):
        importer._installed_or_head_tree(tmp_path, relative)
    assert head_called is False


def test_verify_archive_returns_the_same_bytes_that_were_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = _load_importer()
    archive = _archive_path(ROOT, importer)
    trusted = archive.read_bytes()
    calls = 0

    def exchanged_read(_path: Path, _label: str, _limit: int) -> bytes:
        nonlocal calls
        calls += 1
        return trusted if calls == 1 else b"unvalidated replacement"

    monkeypatch.setattr(importer, "_read_file", exchanged_read)
    assert importer.verify_archive(archive) == trusted
    assert calls == 1


def test_cleanup_rejects_replaced_transaction_symlink(tmp_path: Path) -> None:
    importer = _load_importer()
    repository = tmp_path / "repository"
    repository.mkdir()
    repository_fd = importer._open_absolute_directory_nofollow(repository, "test repository")
    transaction_name, transaction_fd, identity = importer._create_transaction(repository_fd)
    os.close(transaction_fd)

    transaction = repository / transaction_name
    displaced = repository / "displaced-transaction"
    transaction.rename(displaced)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    transaction.symlink_to(outside, target_is_directory=True)

    try:
        with pytest.raises(importer.IntegrationError, match="identity changed"):
            importer._safe_cleanup_transaction(repository_fd, transaction_name, identity)
        assert marker.read_text(encoding="utf-8") == "keep"
    finally:
        os.close(repository_fd)
