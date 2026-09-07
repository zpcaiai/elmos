"""Adversarial ZIP, checksum, immutable extraction, and no-write tests."""

from __future__ import annotations

from dataclasses import replace
import io
from pathlib import Path
import stat
import struct
import warnings
import zipfile

import pytest

from tooling import integrate_commercial_capability_expansion_skills as importer


def _member(
    relative: str,
    content: bytes = b"bounded",
    *,
    raw_type: int = stat.S_IFREG,
    mode: int = 0o644,
    compression: int = zipfile.ZIP_DEFLATED,
) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(f"{importer.PACKAGE_DIRECTORY}/{relative}")
    info.create_system = 3
    info.external_attr = (raw_type | mode) << 16
    info.compress_type = compression
    return info, content


def _archive(*members: tuple[zipfile.ZipInfo, bytes]) -> bytes:
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w") as archive:
            for info, content in members:
                archive.writestr(info, content)
    return stream.getvalue()


def _set_encrypted_flag(payload: bytes) -> bytes:
    result = bytearray(payload)
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        position = 0
        while True:
            position = result.find(signature, position)
            if position < 0:
                break
            flags = struct.unpack_from("<H", result, position + flag_offset)[0]
            struct.pack_into("<H", result, position + flag_offset, flags | 0x1)
            position += 4
    return bytes(result)


def _corrupt_central_crc(payload: bytes) -> bytes:
    result = bytearray(payload)
    position = result.find(b"PK\x01\x02")
    assert position >= 0
    crc = struct.unpack_from("<I", result, position + 16)[0]
    struct.pack_into("<I", result, position + 16, crc ^ 0xFFFFFFFF)
    return bytes(result)


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "nested/../../escape",
        "/absolute",
        "windows\\escape",
        "./noncanonical",
    ],
)
def test_rejects_traversal_absolute_and_noncanonical_paths(name):
    info = zipfile.ZipInfo(f"{importer.PACKAGE_DIRECTORY}/{name}")
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    with pytest.raises(importer.IntegrationError):
        importer.scan_archive_bytes(_archive((info, b"x")))


def test_rejects_duplicate_member_names():
    duplicate = _member("README.md")
    with pytest.warns(UserWarning, match="Overlapped entries"):
        with pytest.raises(importer.IntegrationError, match="duplicate"):
            importer.scan_archive_bytes(_archive(duplicate, duplicate))


def test_rejects_unicode_nfc_and_casefold_collisions():
    decomposed = _member("cafe\N{COMBINING ACUTE ACCENT}.md")
    with pytest.raises(importer.IntegrationError, match="NFC"):
        importer.scan_archive_bytes(_archive(decomposed))

    with pytest.raises(importer.IntegrationError, match="casefold"):
        importer.scan_archive_bytes(
            _archive(_member("Alpha.md"), _member("alpha.md"))
        )


@pytest.mark.parametrize("raw_type", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR])
def test_rejects_symlink_and_special_members(raw_type):
    with pytest.raises(importer.IntegrationError, match="special"):
        importer.scan_archive_bytes(
            _archive(_member("unsafe", raw_type=raw_type, mode=0o777))
        )


def test_rejects_encrypted_members_before_reading_content():
    encrypted = _set_encrypted_flag(_archive(_member("encrypted.txt")))
    with pytest.raises(importer.IntegrationError, match="encrypted"):
        importer.scan_archive_bytes(encrypted)


def test_rejects_unsupported_compression():
    with pytest.raises(importer.IntegrationError, match="compression method"):
        importer.scan_archive_bytes(
            _archive(_member("stored.txt", compression=zipfile.ZIP_STORED))
        )


def test_rejects_oversized_member_and_compression_bomb():
    with pytest.raises(importer.IntegrationError, match="uncompressed-size"):
        importer.scan_archive_bytes(
            _archive(_member("large.bin", b"x" * (importer.MAX_MEMBER_BYTES + 1)))
        )
    with pytest.raises(importer.IntegrationError, match="compression-ratio"):
        importer.scan_archive_bytes(
            _archive(_member("bomb.bin", b"0" * 200_000))
        )


def test_rejects_total_uncompressed_size_limit(monkeypatch):
    monkeypatch.setattr(importer, "MAX_TOTAL_UNCOMPRESSED_BYTES", 1_000)
    moderately_compressible = bytes(range(256)) * 3
    with pytest.raises(importer.IntegrationError, match="total uncompressed-size"):
        importer.scan_archive_bytes(
            _archive(
                _member("first.bin", moderately_compressible),
                _member("second.bin", moderately_compressible),
            )
        )


def test_rejects_crc_corruption():
    corrupted = _corrupt_central_crc(_archive(_member("crc.txt", b"crc-bound")))
    with pytest.raises(importer.IntegrationError, match="ZIP|CRC|unreadable"):
        importer.scan_archive_bytes(corrupted)


def test_sha256sums_requires_complete_non_self_coverage_and_exact_digests():
    a_digest = importer.sha256_bytes(b"a")
    complete = {
        "a.txt": importer.FilePayload(b"a"),
        "SHA256SUMS.txt": importer.FilePayload(
            f"{a_digest}  a.txt\n".encode("utf-8")
        ),
    }
    importer._validate_sha256sums(complete)

    missing = {**complete, "b.txt": importer.FilePayload(b"b")}
    with pytest.raises(importer.IntegrationError, match="cover every"):
        importer._validate_sha256sums(missing)

    wrong = dict(complete)
    wrong["a.txt"] = importer.FilePayload(b"changed")
    with pytest.raises(importer.IntegrationError, match="digest mismatch"):
        importer._validate_sha256sums(wrong)

    self_covered = dict(complete)
    self_covered["SHA256SUMS.txt"] = importer.FilePayload(
        complete["SHA256SUMS.txt"].content
        + f"{'0' * 64}  SHA256SUMS.txt\n".encode("utf-8")
    )
    with pytest.raises(importer.IntegrationError, match="self-checksum"):
        importer._validate_sha256sums(self_covered)


def test_immutable_extraction_is_idempotent_and_drift_fails_without_overwrite(tmp_path):
    tree = {
        "manifest.json": importer.FilePayload(b"original\n"),
        "nested/SKILL.md": importer.FilePayload(b"skill\n"),
    }
    destination = tmp_path / "immutable"
    assert (
        importer._publish_immutable_extraction(
            destination, tree, trusted_root=tmp_path
        )
        is True
    )
    assert (
        importer._publish_immutable_extraction(
            destination, tree, trusted_root=tmp_path
        )
        is False
    )
    changed = destination / "manifest.json"
    changed.write_bytes(b"drift\n")
    with pytest.raises(importer.IntegrationError, match="byte drift"):
        importer._publish_immutable_extraction(
            destination, tree, trusted_root=tmp_path
        )
    assert changed.read_bytes() == b"drift\n"


def test_successful_immutable_publish_preserves_cwd_repository_and_canary(tmp_path):
    cwd = Path.cwd()
    repository = importer.ROOT
    cwd_identity = (cwd.stat().st_dev, cwd.stat().st_ino)
    repository_identity = (repository.stat().st_dev, repository.stat().st_ino)
    repository_file = repository / "tooling" / Path(importer.COMPILER_RELATIVE).name
    repository_digest = importer.sha256_bytes(repository_file.read_bytes())
    canary = tmp_path / "canary"
    canary.mkdir()
    marker = canary / "must-survive.txt"
    marker.write_bytes(b"alive\n")
    destination = tmp_path / "immutable"
    tree = {"manifest.json": importer.FilePayload(b"published\n")}

    assert (
        importer._publish_immutable_extraction(
            destination, tree, trusted_root=tmp_path
        )
        is True
    )

    assert destination.joinpath("manifest.json").read_bytes() == b"published\n"
    assert marker.read_bytes() == b"alive\n"
    assert (cwd.stat().st_dev, cwd.stat().st_ino) == cwd_identity
    assert (repository.stat().st_dev, repository.stat().st_ino) == repository_identity
    assert importer.sha256_bytes(repository_file.read_bytes()) == repository_digest
    assert not list(tmp_path.glob(".immutable.stage-*"))


def test_immutable_publish_final_window_swap_is_quarantined(tmp_path, monkeypatch):
    destination = tmp_path / "immutable"
    canary = tmp_path / "canary.txt"
    canary.write_bytes(b"alive\n")
    displaced = tmp_path / "displaced-real-stage"
    real_rename = importer._rename_noreplace_syscall
    injected = False

    def swap_stage_then_rename(source_fd, source_name, destination_fd, destination_name):
        nonlocal injected
        if not injected and source_name.startswith(".immutable.stage-"):
            injected = True
            stage = tmp_path / source_name
            stage.rename(displaced)
            stage.mkdir()
            (stage / "must-survive.txt").write_bytes(b"unknown\n")
        return real_rename(source_fd, source_name, destination_fd, destination_name)

    monkeypatch.setattr(importer, "_rename_noreplace_syscall", swap_stage_then_rename)
    with pytest.raises(importer.IntegrationError, match="quarantine retained"):
        importer._publish_immutable_extraction(
            destination,
            {"manifest.json": importer.FilePayload(b"published\n")},
            trusted_root=tmp_path,
        )

    quarantines = list(tmp_path.glob(".immutable.quarantine-container-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "payload/must-survive.txt").read_bytes() == b"unknown\n"
    assert (displaced / "manifest.json").read_bytes() == b"published\n"
    assert not destination.exists()
    assert canary.read_bytes() == b"alive\n"


def test_successful_atomic_replacement_preserves_cwd_repository_and_canary(tmp_path):
    cwd = Path.cwd()
    repository = importer.ROOT
    cwd_identity = (cwd.stat().st_dev, cwd.stat().st_ino)
    repository_identity = (repository.stat().st_dev, repository.stat().st_ino)
    canary = tmp_path / "canary"
    canary.mkdir()
    marker = canary / "must-survive.txt"
    marker.write_bytes(b"alive\n")
    destination = tmp_path / "managed"
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"old\n")
    tree = {
        "new.txt": importer.FilePayload(b"new\n"),
        "nested/value.txt": importer.FilePayload(b"value\n"),
    }

    importer._atomic_replace_tree(
        destination,
        tree,
        trusted_root=tmp_path,
        expected_existing={"old.txt": importer.FilePayload(b"old\n")},
    )

    importer._assert_tree_bytes(destination, tree, "test replacement")
    assert marker.read_bytes() == b"alive\n"
    assert (cwd.stat().st_dev, cwd.stat().st_ino) == cwd_identity
    assert (repository.stat().st_dev, repository.stat().st_ino) == repository_identity
    assert not list(tmp_path.glob(".managed.stage-*"))
    assert not list(tmp_path.glob(".managed.backup-container-*"))


def test_tree_publish_final_window_swap_restores_original_and_retains_unknown(
    tmp_path, monkeypatch
):
    destination = tmp_path / "managed"
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"old\n")
    canary = tmp_path / "canary.txt"
    canary.write_bytes(b"alive\n")
    displaced = tmp_path / "displaced-real-stage"
    real_rename = importer._rename_noreplace_syscall
    injected = False

    def swap_stage_then_rename(source_fd, source_name, destination_fd, destination_name):
        nonlocal injected
        if not injected and source_name.startswith(".managed.stage-"):
            injected = True
            stage = tmp_path / source_name
            stage.rename(displaced)
            stage.mkdir()
            (stage / "must-survive.txt").write_bytes(b"unknown\n")
        return real_rename(source_fd, source_name, destination_fd, destination_name)

    monkeypatch.setattr(importer, "_rename_noreplace_syscall", swap_stage_then_rename)
    with pytest.raises(importer.IntegrationError, match="quarantine retained"):
        importer._atomic_replace_tree(
            destination,
            {"new.txt": importer.FilePayload(b"new\n")},
            trusted_root=tmp_path,
            expected_existing={"old.txt": importer.FilePayload(b"old\n")},
        )

    assert (destination / "old.txt").read_bytes() == b"old\n"
    quarantines = list(tmp_path.glob(".managed.quarantine-container-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "payload/must-survive.txt").read_bytes() == b"unknown\n"
    assert (displaced / "new.txt").read_bytes() == b"new\n"
    assert canary.read_bytes() == b"alive\n"


def test_tree_restore_final_window_swap_retains_unknown_and_original(
    tmp_path, monkeypatch
):
    destination = tmp_path / "managed"
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"old\n")
    canary = tmp_path / "canary.txt"
    canary.write_bytes(b"alive\n")
    displaced_original = tmp_path / "displaced-original"
    real_rename = importer._rename_noreplace_syscall
    real_assert_tree = importer._assert_tree_bytes
    injected_restore = False
    injected_failure = False

    def fail_after_verified_publish(root, expected, label):
        nonlocal injected_failure
        real_assert_tree(root, expected, label)
        if not injected_failure and label.startswith("published wrapper"):
            injected_failure = True
            raise importer.IntegrationError("injected post-publish failure")

    def swap_previous_then_restore(source_fd, source_name, destination_fd, destination_name):
        nonlocal injected_restore
        if not injected_restore and source_name == "previous" and destination_name == "managed":
            injected_restore = True
            backup = next(tmp_path.glob(".managed.backup-container-*"))
            previous = backup / "previous"
            previous.rename(displaced_original)
            previous.mkdir()
            (previous / "must-survive.txt").write_bytes(b"unknown\n")
        return real_rename(source_fd, source_name, destination_fd, destination_name)

    monkeypatch.setattr(importer, "_assert_tree_bytes", fail_after_verified_publish)
    monkeypatch.setattr(importer, "_rename_noreplace_syscall", swap_previous_then_restore)
    with pytest.raises(importer.IntegrationError, match="restore moved an unexpected inode"):
        importer._atomic_replace_tree(
            destination,
            {"new.txt": importer.FilePayload(b"new\n")},
            trusted_root=tmp_path,
            expected_existing={"old.txt": importer.FilePayload(b"old\n")},
        )

    assert (displaced_original / "old.txt").read_bytes() == b"old\n"
    quarantines = list(tmp_path.glob(".managed.quarantine-container-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "payload/must-survive.txt").read_bytes() == b"unknown\n"
    assert not destination.exists()
    assert canary.read_bytes() == b"alive\n"


def test_atomic_replacement_rejects_same_inode_content_mutation(tmp_path, monkeypatch):
    destination = tmp_path / "managed"
    destination.mkdir()
    current = destination / "old.txt"
    current.write_bytes(b"old\n")
    original_write_staged_tree = importer._write_staged_tree

    def write_stage_then_mutate(*args, **kwargs):
        capability = original_write_staged_tree(*args, **kwargs)
        current.write_bytes(b"concurrent mutation\n")
        return capability

    monkeypatch.setattr(importer, "_write_staged_tree", write_stage_then_mutate)
    with pytest.raises(importer.IntegrationError, match="byte drift"):
        importer._atomic_replace_tree(
            destination,
            {"new.txt": importer.FilePayload(b"new\n")},
            trusted_root=tmp_path,
            expected_existing={"old.txt": importer.FilePayload(b"old\n")},
        )

    assert current.read_bytes() == b"concurrent mutation\n"
    assert not (destination / "new.txt").exists()
    assert not list(tmp_path.glob(".managed.stage-*"))


def test_atomic_replacement_rejects_rename_symlink_swap(tmp_path, monkeypatch):
    destination = tmp_path / "managed"
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"old\n")
    canary = tmp_path / "canary"
    canary.mkdir()
    marker = canary / "must-survive.txt"
    marker.write_bytes(b"alive\n")
    displaced = tmp_path / "displaced-managed"
    original_write_staged_tree = importer._write_staged_tree

    def write_stage_then_swap(*args, **kwargs):
        capability = original_write_staged_tree(*args, **kwargs)
        destination.rename(displaced)
        destination.symlink_to(canary, target_is_directory=True)
        return capability

    monkeypatch.setattr(importer, "_write_staged_tree", write_stage_then_swap)
    with pytest.raises(importer.IntegrationError, match="real directory|symlink"):
        importer._atomic_replace_tree(
            destination,
            {"new.txt": importer.FilePayload(b"new\n")},
            trusted_root=tmp_path,
            expected_existing={"old.txt": importer.FilePayload(b"old\n")},
        )

    assert destination.is_symlink()
    assert (displaced / "old.txt").read_bytes() == b"old\n"
    assert marker.read_bytes() == b"alive\n"
    assert not list(tmp_path.glob(".managed.stage-*"))


def test_managed_file_cas_rejects_same_inode_mutation(tmp_path):
    output = tmp_path / "catalog.json"
    output.write_bytes(b"prevalidated\n")
    expected = importer._snapshot_managed_file(
        output, trusted_root=tmp_path, label="test catalog"
    )
    output.write_bytes(b"concurrent mutation\n")

    with pytest.raises(importer.IntegrationError, match="changed after prevalidation"):
        importer._atomic_write_file(
            output,
            b"new output\n",
            trusted_root=tmp_path,
            expected_previous=expected,
        )

    assert output.read_bytes() == b"concurrent mutation\n"


def test_managed_file_no_replace_publish_preserves_canary_and_cleans_backup(tmp_path):
    output = tmp_path / "catalog.json"
    output.write_bytes(b"old output\n")
    expected = importer._snapshot_managed_file(
        output, trusted_root=tmp_path, label="test catalog"
    )
    canary = tmp_path / "canary.txt"
    canary.write_bytes(b"alive\n")

    importer._atomic_write_file(
        output,
        b"new output\n",
        trusted_root=tmp_path,
        expected_previous=expected,
    )

    assert output.read_bytes() == b"new output\n"
    assert canary.read_bytes() == b"alive\n"
    assert not list(tmp_path.glob(".catalog.json.stage-*"))
    assert not list(tmp_path.glob(".catalog.json.backup-container-*"))
    assert not list(tmp_path.glob(".*.quarantine-container-*"))


def test_managed_file_backup_no_replace_retains_concurrent_payload(tmp_path, monkeypatch):
    output = tmp_path / "catalog.json"
    output.write_bytes(b"old output\n")
    expected = importer._snapshot_managed_file(
        output, trusted_root=tmp_path, label="test catalog"
    )
    canary = tmp_path / "canary.txt"
    canary.write_bytes(b"alive\n")
    real_rename = importer._rename_noreplace_syscall
    injected = False

    def inject_backup_payload(source_fd, source_name, destination_fd, destination_name):
        nonlocal injected
        if not injected and source_name == "catalog.json" and destination_name == "previous":
            injected = True
            backup = next(tmp_path.glob(".catalog.json.backup-container-*"))
            (backup / "previous").write_bytes(b"unknown\n")
        return real_rename(source_fd, source_name, destination_fd, destination_name)

    monkeypatch.setattr(importer, "_rename_noreplace_syscall", inject_backup_payload)
    with pytest.raises(importer.IntegrationError, match="backup appeared concurrently"):
        importer._atomic_write_file(
            output,
            b"new output\n",
            trusted_root=tmp_path,
            expected_previous=expected,
        )

    backups = list(tmp_path.glob(".catalog.json.backup-container-*"))
    assert len(backups) == 1
    assert (backups[0] / "previous").read_bytes() == b"unknown\n"
    assert output.read_bytes() == b"old output\n"
    assert canary.read_bytes() == b"alive\n"


def test_managed_file_no_replace_publish_never_overwrites_unknown_swap(
    tmp_path, monkeypatch
):
    output = tmp_path / "catalog.json"
    output.write_bytes(b"prevalidated\n")
    expected = importer._snapshot_managed_file(
        output, trusted_root=tmp_path, label="test catalog"
    )
    real_link = importer.os.link
    injected = False

    def inject_competing_destination(*args, **kwargs):
        nonlocal injected
        if not injected:
            injected = True
            output.write_bytes(b"unknown concurrent writer\n")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(importer.os, "link", inject_competing_destination)
    with pytest.raises(importer.IntegrationError, match="no-replace publish"):
        importer._atomic_write_file(
            output,
            b"new output\n",
            trusted_root=tmp_path,
            expected_previous=expected,
        )

    assert output.read_bytes() == b"unknown concurrent writer\n"
    backups = list(tmp_path.glob(".catalog.json.backup-container-*"))
    assert len(backups) == 1
    assert (backups[0] / "previous").read_bytes() == b"prevalidated\n"


def test_cleanup_capability_rejects_inode_drift_without_deleting_target(tmp_path):
    with importer._trusted_root_lock(tmp_path, exclusive=True) as root_lock:
        capability = importer._create_temporary_directory(
            tmp_path,
            ".owned.stage-",
            trusted_root=tmp_path,
            root_lock=root_lock,
        )
        marker = capability.path / "must-survive.txt"
        marker.write_bytes(b"alive\n")
        forged = replace(capability, inode=capability.inode + 1)

        with pytest.raises(importer.IntegrationError, match="inode changed"):
            importer._cleanup_temporary_path(forged)

        assert marker.read_bytes() == b"alive\n"
        importer._cleanup_temporary_path(capability)
        assert not capability.path.exists()


def test_cleanup_quarantine_no_replace_retains_concurrent_payload(tmp_path, monkeypatch):
    with importer._trusted_root_lock(tmp_path, exclusive=True) as root_lock:
        capability = importer._create_temporary_directory(
            tmp_path,
            ".owned.stage-",
            trusted_root=tmp_path,
            root_lock=root_lock,
        )
        (capability.path / "source.txt").write_bytes(b"source\n")
        real_rename = importer._rename_noreplace_syscall
        injected = False

        def inject_payload(source_fd, source_name, destination_fd, destination_name):
            nonlocal injected
            if not injected and destination_name == "payload":
                injected = True
                quarantine = next(
                    tmp_path.glob(
                        f".{importer.PACKAGE_NAME}.quarantine-container-*"
                    )
                )
                (quarantine / "payload").write_bytes(b"unknown\n")
            return real_rename(source_fd, source_name, destination_fd, destination_name)

        monkeypatch.setattr(importer, "_rename_noreplace_syscall", inject_payload)
        with pytest.raises(importer.IntegrationError, match="payload appeared concurrently"):
            importer._cleanup_temporary_path(capability)

        quarantines = list(
            tmp_path.glob(f".{importer.PACKAGE_NAME}.quarantine-container-*")
        )
        assert len(quarantines) == 1
        assert (quarantines[0] / "payload").read_bytes() == b"unknown\n"
        assert (capability.path / "source.txt").read_bytes() == b"source\n"


def test_cleanup_capability_rejects_symlink_swap_without_following_it(tmp_path):
    with importer._trusted_root_lock(tmp_path, exclusive=True) as root_lock:
        capability = importer._create_temporary_directory(
            tmp_path,
            ".owned.stage-",
            trusted_root=tmp_path,
            root_lock=root_lock,
        )
        displaced = tmp_path / "displaced"
        capability.path.rename(displaced)
        canary = tmp_path / "canary"
        canary.mkdir()
        marker = canary / "must-survive.txt"
        marker.write_bytes(b"alive\n")
        capability.path.symlink_to(canary, target_is_directory=True)

        with pytest.raises(importer.IntegrationError, match="symlink"):
            importer._cleanup_temporary_path(capability)

        assert marker.read_bytes() == b"alive\n"
        assert displaced.is_dir()


def test_cleanup_quarantine_basename_swap_never_deletes_replacement(
    tmp_path, monkeypatch
):
    with importer._trusted_root_lock(tmp_path, exclusive=True) as root_lock:
        capability = importer._create_temporary_directory(
            tmp_path,
            ".owned.stage-",
            trusted_root=tmp_path,
            root_lock=root_lock,
        )
        (capability.path / "temporary.txt").write_bytes(b"temporary\n")
        captured = {}
        original_create = importer._create_temporary_directory
        original_delete = importer._delete_quarantined_payload

        def capture_quarantine(*args, **kwargs):
            created = original_create(*args, **kwargs)
            if created.prefix.endswith(".quarantine-container-"):
                captured["quarantine"] = created
            return created

        def delete_then_swap(quarantine_fd, source_capability):
            original_delete(quarantine_fd, source_capability)
            quarantine = captured["quarantine"]
            displaced = tmp_path / "displaced-quarantine"
            quarantine.path.rename(displaced)
            quarantine.path.mkdir()
            (quarantine.path / "must-survive.txt").write_bytes(b"alive\n")

        monkeypatch.setattr(
            importer, "_create_temporary_directory", capture_quarantine
        )
        monkeypatch.setattr(importer, "_delete_quarantined_payload", delete_then_swap)

        with pytest.raises(importer.IntegrationError, match="quarantine inode changed"):
            importer._cleanup_temporary_path(capability)

        replacement = captured["quarantine"].path
        assert (replacement / "must-survive.txt").read_bytes() == b"alive\n"
        assert (tmp_path / "displaced-quarantine").is_dir()


def test_cleanup_capability_cannot_be_minted_for_cwd_or_repository_root():
    protected_paths = {Path.cwd(), importer.ROOT}
    for protected in protected_paths:
        with importer._trusted_root_lock(
            protected.parent, exclusive=True
        ) as root_lock:
            with pytest.raises(
                importer.IntegrationError,
                match="current working directory|repository root",
            ):
                importer._capture_temporary_path(
                    protected,
                    parent=protected.parent,
                    prefix=".unsafe.stage-",
                    kind="directory",
                    trusted_root=protected.parent,
                    root_lock=root_lock,
                )


def test_staged_tree_rejects_traversal_without_touching_canary(tmp_path):
    marker = tmp_path / "must-survive.txt"
    marker.write_bytes(b"alive\n")

    with pytest.raises(importer.IntegrationError, match="unsafe generated tree"):
        importer._publish_immutable_extraction(
            tmp_path / "immutable",
            {"../must-survive.txt": importer.FilePayload(b"overwritten\n")},
            trusted_root=tmp_path,
        )

    assert marker.read_bytes() == b"alive\n"
    assert not (tmp_path / "immutable").exists()
    assert not list(tmp_path.glob(".immutable.stage-*"))


def test_tree_inventory_rejects_multi_gigabyte_sparse_extra_without_reading(
    tmp_path, monkeypatch
):
    root = tmp_path / "managed"
    root.mkdir()
    (root / "expected.txt").write_bytes(b"expected\n")
    extra = root / "huge-extra.bin"
    with extra.open("wb") as handle:
        handle.truncate(4 * 1024 * 1024 * 1024)
    real_read = importer.os.read
    expected_inode = (root / "expected.txt").stat().st_ino
    read_inodes: list[int] = []

    def track_read(descriptor, count):
        read_inodes.append(importer.os.fstat(descriptor).st_ino)
        return real_read(descriptor, count)

    monkeypatch.setattr(importer.os, "read", track_read)
    with pytest.raises(importer.IntegrationError, match="extra entry.*huge-extra"):
        importer._classify_wrapper_destination(
            root,
            {"expected.txt": importer.FilePayload(b"expected\n")},
            {"SKILL.md": importer.FilePayload(b"legacy\n")},
        )

    assert extra.stat().st_size == 4 * 1024 * 1024 * 1024
    assert extra.stat().st_ino not in read_inodes
    assert set(read_inodes).issubset({expected_inode})


def test_tree_reader_rejects_concurrent_file_to_symlink_swap(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    root.mkdir()
    managed = root / "expected.txt"
    managed.write_bytes(b"expected\n")
    displaced = tmp_path / "displaced-expected"
    canary = tmp_path / "canary.txt"
    canary.write_bytes(b"alive\n")
    real_open_child = importer._open_bound_child
    injected = False

    def swap_before_open(parent_fd, name, *, expected, directory, label):
        nonlocal injected
        if not injected and not directory and name == "expected.txt":
            injected = True
            managed.rename(displaced)
            managed.symlink_to(canary)
        return real_open_child(
            parent_fd,
            name,
            expected=expected,
            directory=directory,
            label=label,
        )

    monkeypatch.setattr(importer, "_open_bound_child", swap_before_open)
    with pytest.raises(importer.IntegrationError, match="cannot open bound"):
        importer._assert_tree_bytes(
            root,
            {"expected.txt": importer.FilePayload(b"expected\n")},
            "concurrent swap",
        )

    assert managed.is_symlink()
    assert displaced.read_bytes() == b"expected\n"
    assert canary.read_bytes() == b"alive\n"


def test_tree_reader_rejects_concurrent_directory_inventory_drift(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    root.mkdir()
    expected = root / "expected.txt"
    expected.write_bytes(b"expected\n")
    real_open_child = importer._open_bound_child
    injected = False

    def add_entry_before_file_open(parent_fd, name, *, expected, directory, label):
        nonlocal injected
        if not injected and not directory:
            injected = True
            (root / "concurrent-extra.txt").write_bytes(b"unknown\n")
        return real_open_child(
            parent_fd,
            name,
            expected=expected,
            directory=directory,
            label=label,
        )

    monkeypatch.setattr(importer, "_open_bound_child", add_entry_before_file_open)
    with pytest.raises(importer.IntegrationError, match="extra entry|directory.*changed"):
        importer._assert_tree_bytes(
            root,
            {"expected.txt": importer.FilePayload(b"expected\n")},
            "concurrent directory drift",
        )

    assert expected.read_bytes() == b"expected\n"
    assert (root / "concurrent-extra.txt").read_bytes() == b"unknown\n"


@pytest.mark.parametrize("label", ["compiled catalog", "qualification receipt"])
def test_managed_json_reader_rejects_oversize_sparse_file(tmp_path, label):
    managed = tmp_path / ("catalog.json" if label == "compiled catalog" else "receipt.json")
    with managed.open("wb") as handle:
        handle.truncate(importer.MAX_MANAGED_OUTPUT_BYTES + 1)

    with pytest.raises(importer.IntegrationError, match="exceeds.*read bound"):
        importer._bounded_stable_read_file(
            managed,
            max_bytes=importer.MAX_MANAGED_OUTPUT_BYTES,
            label=label,
        )


def test_existing_receipt_time_treats_oversize_receipt_as_untrusted(tmp_path):
    receipt = tmp_path / "receipt.json"
    with receipt.open("wb") as handle:
        handle.truncate(importer.MAX_MANAGED_OUTPUT_BYTES + 1)
    assert importer._existing_receipt_time(receipt, {"schema_version": "2.0.0"}) is None


def test_cli_rejects_non_allowlisted_output_before_archive_read(tmp_path, monkeypatch):
    monkeypatch.setattr(
        importer,
        "read_pinned_archive",
        lambda _path: pytest.fail("archive must not be read before path authority"),
    )
    args = importer.build_parser().parse_args(
        ["--target-dir", str(tmp_path / "arbitrary-output")]
    )

    with pytest.raises(importer.IntegrationError, match="--target-dir.*repository-owned"):
        importer.run(args)

    assert list(tmp_path.iterdir()) == []


def test_managed_layout_rejects_overlapping_paths_without_writes(tmp_path):
    source = tmp_path / "source"
    with pytest.raises(importer.IntegrationError, match="must not overlap"):
        importer._validate_managed_layout(
            trusted_root=tmp_path,
            source_path=source,
            catalog_path=source / "catalog.json",
            receipt_path=tmp_path / "receipt.json",
            workspace_root=tmp_path / "workspace",
            runtime_root=tmp_path / "runtime",
        )
    assert list(tmp_path.iterdir()) == []


def test_managed_layout_rejects_symlink_ancestry_without_touching_canary(tmp_path):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    marker = real_parent / "must-survive.txt"
    marker.write_bytes(b"alive\n")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(importer.IntegrationError, match="symlink ancestry"):
        importer._validate_managed_layout(
            trusted_root=tmp_path,
            source_path=linked_parent / "source",
            catalog_path=tmp_path / "catalog.json",
            receipt_path=tmp_path / "receipt.json",
            workspace_root=tmp_path / "workspace",
            runtime_root=tmp_path / "runtime",
        )

    assert marker.read_bytes() == b"alive\n"


def test_managed_layout_rejects_hardlinked_output_file(tmp_path):
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(b"catalog\n")
    alias = tmp_path / "catalog-alias.json"
    alias.hardlink_to(catalog)

    with pytest.raises(importer.IntegrationError, match="hard-linked"):
        importer._validate_managed_layout(
            trusted_root=tmp_path,
            source_path=tmp_path / "source",
            catalog_path=catalog,
            receipt_path=tmp_path / "receipt.json",
            workspace_root=tmp_path / "workspace",
            runtime_root=tmp_path / "runtime",
        )

    assert catalog.read_bytes() == b"catalog\n"
    assert alias.read_bytes() == b"catalog\n"


def test_destination_drift_is_rejected_before_any_integration_write(tmp_path):
    archive = importer.resolve_archive()
    package = importer.validate_package(importer.read_pinned_archive(archive))
    source = tmp_path / "source"
    catalog = tmp_path / "docs" / "catalog.json"
    receipt = tmp_path / "docs" / "receipt.json"
    workspace = tmp_path / "workspace"
    runtime = tmp_path / "runtime"
    projection = importer.compile_projection(
        package,
        archive_path=archive,
        source_path=source,
        catalog_path=catalog,
        receipt_path=receipt,
        workspace_root=workspace,
        runtime_root=runtime,
    )
    foreign = workspace / importer.MASTER_SKILL_NAME
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("foreign\n", encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="drift|foreign ownership"):
        importer.install_projection(
            package,
            projection,
            trusted_root=tmp_path,
            source_path=source,
            catalog_path=catalog,
            receipt_path=receipt,
            workspace_root=workspace,
            runtime_root=runtime,
        )
    assert not source.exists()
    assert not catalog.exists()
    assert not receipt.exists()
    assert not runtime.exists()
    assert (foreign / "SKILL.md").read_text(encoding="utf-8") == "foreign\n"


def test_check_failure_is_read_only_and_creates_no_paths(tmp_path):
    archive = importer.resolve_archive()
    package = importer.validate_package(importer.read_pinned_archive(archive))
    source = tmp_path / "source"
    catalog = tmp_path / "catalog.json"
    receipt = tmp_path / "receipt.json"
    workspace = tmp_path / "workspace"
    runtime = tmp_path / "runtime"
    projection = importer.compile_projection(
        package,
        archive_path=archive,
        source_path=source,
        catalog_path=catalog,
        receipt_path=receipt,
        workspace_root=workspace,
        runtime_root=runtime,
    )
    with pytest.raises(importer.IntegrationError):
        importer.check_projection(
            package,
            projection,
            trusted_root=tmp_path,
            source_path=source,
            catalog_path=catalog,
            receipt_path=receipt,
            workspace_root=workspace,
            runtime_root=runtime,
        )
    assert list(tmp_path.iterdir()) == []
