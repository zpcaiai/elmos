from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import sqlite3
import struct
import tarfile
import zipfile
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

import pytest

import elmos_multimodal_intake.archive_publication as archive_publication
from elmos_multimodal_intake._migrations import migrate_connection
from elmos_multimodal_intake.archive_publication import ArchivePasswordLease, publish_archive_to_cas
from elmos_multimodal_intake.canonical import canonical_json, sha256_bytes
from elmos_multimodal_intake.errors import IntegrityError, NotFoundError
from elmos_multimodal_intake.models import ResultStatus
from elmos_multimodal_intake.projects import ProjectContractError, extract_archive_safely
from elmos_multimodal_intake.providers import (
    CommandReceipt,
    ExternalToolProvider,
    ProviderResult,
    ToolCapability,
)
from elmos_multimodal_intake.store import IntakeStore, LocalCasStore


class SequenceScanner:
    def __init__(self, verdicts: list[str] | None = None) -> None:
        self.verdicts = list(verdicts or [])
        self.calls: list[dict[str, Any]] = []

    def execute(self, **request: Any) -> CommandReceipt:
        self.calls.append(dict(request))
        verdict = self.verdicts.pop(0) if self.verdicts else "CLEAN"
        return CommandReceipt(
            tool=str(request["tool"]),
            executable_sha256="a" * 64,
            exit_code=0,
            stdout=json.dumps({"verdict": verdict, "findings": []}, separators=(",", ":")).encode(),
            duration_ms=1,
            sandboxed=True,
            network_allowed=False,
        )


class FailingScanner:
    def execute(self, **request: Any) -> CommandReceipt:
        raise RuntimeError("scanner outcome unavailable")


class TamperingProvider:
    def __init__(self, mutate: Callable[[dict[str, Any], dict[str, Any]], None]) -> None:
        self.delegate = _provider(SequenceScanner())
        self.mutate = mutate

    def run(self, *args: Any, **kwargs: Any) -> ProviderResult:
        result = self.delegate.run(*args, **kwargs)
        payload = dict(result.payload)
        receipt = dict(result.receipt)
        self.mutate(payload, receipt)
        return ProviderResult(
            status=ResultStatus.PASSED,
            capability=ToolCapability.MALWARE_SCAN,
            payload=payload,
            receipt=receipt,
        )

    def verify_issued_result(self, result: ProviderResult) -> bool:
        return self.delegate.verify_issued_result(result)


class StaticPasswordProvider:
    def __init__(self, **receipt_overrides: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self.receipt_overrides = receipt_overrides

    def resolve_archive_password(self, handle: str, **scope: Any) -> ArchivePasswordLease:
        self.calls.append({"handle": handle, **scope})
        assert handle == "password-handle-1"
        assert scope == {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "job_id": "archive-job-1",
            "purpose": "ARCHIVE_ZIP_DECRYPT",
        }
        receipt = {
            "schema_version": "1.0.0",
            **scope,
            "handle_digest": f"sha256:{sha256_bytes(handle.encode('utf-8'))}",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "revoked": False,
            **self.receipt_overrides,
        }
        return ArchivePasswordLease(secret=b"runtime-owned-password", receipt=receipt)


class NakedPasswordProvider:
    def resolve_archive_password(self, handle: str, **scope: Any) -> bytes:
        del handle, scope
        return b"runtime-owned-password"


class FailingGeneratedObjectCas(LocalCasStore):
    def publish_generation(self, tenant_id: str, generation_digest: str, objects: Any) -> str:
        rewritten = []
        for index, (digest, size, chunks) in enumerate(objects):
            if index == 1:
                def fail(source: Any = chunks) -> Any:
                    for chunk in source:
                        yield chunk
                        raise OSError("injected generation write failure")

                chunks = fail()
            rewritten.append((digest, size, chunks))
        return super().publish_generation(tenant_id, generation_digest, rewritten)


def _provider(scanner: Any | None) -> ExternalToolProvider:
    return ExternalToolProvider(
        scanner,
        {
            ToolCapability.MALWARE_SCAN: {
                "path": "/opt/elmos/bin/elmos-malware-scan",
                "sha256": "a" * 64,
            }
        }
        if scanner is not None
        else {},
    )


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries:
            archive.writestr(path, content)
    return buffer.getvalue()


def _zipcrypto_encrypt(data: bytes, password: bytes) -> bytes:
    crc_table: list[int] = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = value >> 1 ^ (0xEDB88320 if value & 1 else 0)
        crc_table.append(value)
    keys = [0x12345678, 0x23456789, 0x34567890]

    def update_keys(value: int) -> None:
        keys[0] = keys[0] >> 8 ^ crc_table[(keys[0] ^ value) & 0xFF]
        keys[1] = (keys[1] + (keys[0] & 0xFF)) & 0xFFFFFFFF
        keys[1] = (keys[1] * 134775813 + 1) & 0xFFFFFFFF
        keys[2] = keys[2] >> 8 ^ crc_table[(keys[2] ^ (keys[1] >> 24)) & 0xFF]

    for value in password:
        update_keys(value)
    encrypted = bytearray()
    for value in data:
        temporary = (keys[2] | 2) & 0xFFFFFFFF
        encrypted.append(value ^ ((temporary * (temporary ^ 1) >> 8) & 0xFF))
        update_keys(value)
    return bytes(encrypted)


def _encrypted_zip(path: str, content: bytes, password: bytes) -> bytes:
    """Build one deterministic traditional-PKZIP entry for secret-channel tests."""

    filename = path.encode("ascii")
    checksum = zlib.crc32(content) & 0xFFFFFFFF
    encryption_header = bytes(range(11)) + bytes([checksum >> 24])
    encrypted_payload = _zipcrypto_encrypt(encryption_header + content, password)
    flags = 0x1
    compressed_size = len(encrypted_payload)
    local_header = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        flags,
        zipfile.ZIP_STORED,
        0,
        0,
        checksum,
        compressed_size,
        len(content),
        len(filename),
        0,
    )
    central_header = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        20,
        20,
        flags,
        zipfile.ZIP_STORED,
        0,
        0,
        checksum,
        compressed_size,
        len(content),
        len(filename),
        0,
        0,
        0,
        0,
        0,
        0,
    )
    local_record = local_header + filename + encrypted_payload
    central_record = central_header + filename
    end_record = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        1,
        1,
        len(central_record),
        len(local_record),
        0,
    )
    return local_record + central_record + end_record


def _generation_manifest(
    descriptors: list[tuple[str, int]],
) -> tuple[str, bytes]:
    binding = {
        "schema_version": "1.0.0",
        "kind": "ATOMIC_CAS_GENERATION_MANIFEST",
        "scope_digest": f"sha256:{sha256_bytes(b'test-scope')}",
        "manifest_digest": f"sha256:{descriptors[0][0]}",
        "publication_receipt_digest": f"sha256:{descriptors[-1][0]}",
        "objects": [
            {"digest": f"sha256:{digest}", "byte_count": byte_count}
            for digest, byte_count in sorted(descriptors)
        ],
    }
    data = canonical_json(binding).encode("utf-8")
    return sha256_bytes(data), data


def _tar(entries: list[tuple[str, bytes]], mode: str = "w") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        for path, content in entries:
            info = tarfile.TarInfo(path)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _request(data: bytes, archive_format: str, **inputs: Any) -> dict[str, Any]:
    return {
        "inputs": {
            "format": archive_format,
            "archive_bytes_b64": base64.b64encode(data).decode("ascii"),
            **inputs,
        }
    }


def _publish(
    root: Path,
    data: bytes,
    archive_format: str,
    scanner: Any | None,
    *,
    cas: LocalCasStore | None = None,
    password_provider: Any | None = None,
    **inputs: Any,
) -> tuple[dict[str, Any], LocalCasStore]:
    target = cas or LocalCasStore(root / "cas")
    result = publish_archive_to_cas(
        _request(data, archive_format, **inputs),
        providers=_provider(scanner),
        cas=target,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-job-1",
        password_provider=password_provider,
    )
    return result, target


def _read_json(cas: LocalCasStore, generation: str, digest: str) -> dict[str, Any]:
    return json.loads(
        cas.read_generation_bytes(
            "tenant-a",
            generation.removeprefix("sha256:"),
            digest.removeprefix("sha256:"),
        ).decode("utf-8")
    )


def _readable_cas_files(cas: LocalCasStore) -> list[Path]:
    tenant_root = Path(cas.root) / "tenants"
    return sorted(path for path in tenant_root.rglob("*") if path.is_file()) if tenant_root.exists() else []


def test_safe_zip_is_scanned_before_deterministic_tenant_cas_publication(tmp_path: Path) -> None:
    payload = b"print('safe')\n"
    archive = _zip([("src/main.py", payload)])
    scanner = SequenceScanner()
    first, cas = _publish(tmp_path, archive, "zip", scanner)
    second, _ = _publish(tmp_path, archive, "zip", scanner, cas=cas)

    assert first["state"] == "SUCCEEDED"
    assert first["code"] == "ARCHIVE_PUBLISHED_TO_TENANT_CAS"
    assert len(scanner.calls) == 4  # original plus entry, for both idempotent requests
    assert first["outputs"]["manifest_digest"] == second["outputs"]["manifest_digest"]
    assert first["outputs"]["publication_receipt_digest"] == second["outputs"]["publication_receipt_digest"]
    assert first["outputs"]["published_object_count"] == 7
    assert first["outputs"]["host_paths_returned"] is False
    assert first["outputs"]["raw_content_returned"] is False

    entry = first["outputs"]["entries"][0]
    assert entry["path"] == "src/main.py"
    generation = first["outputs"]["generation_digest"]
    assert cas.read_generation_bytes("tenant-a", generation, entry["content_digest"]) == payload
    with pytest.raises(NotFoundError):
        cas.read_bytes("tenant-a", entry["content_digest"])
    with pytest.raises(NotFoundError):
        cas.read_generation_bytes("tenant-b", generation, entry["content_digest"])
    manifest = _read_json(cas, generation, first["outputs"]["manifest_digest"])
    generation_manifest = _read_json(
        cas,
        generation,
        first["outputs"]["generation_manifest_digest"],
    )
    assert manifest["entries"] == first["outputs"]["entries"]
    assert generation_manifest["manifest_digest"] == first["outputs"]["manifest_digest"]
    assert generation_manifest["publication_receipt_digest"] == first["outputs"]["publication_receipt_digest"]
    assert "host_path" not in json.dumps(manifest)
    assert "/opt/elmos" not in json.dumps(manifest)
    assert "print('safe')" not in json.dumps(manifest)


def test_missing_scanner_keeps_every_object_out_of_readable_cas(tmp_path: Path) -> None:
    result, cas = _publish(tmp_path, _zip([("safe.txt", b"safe")]), "zip", None)

    assert result["state"] == "PARTIAL"
    assert result["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"
    assert result["outputs"]["publication_state"] == "NEEDS_REVIEW"
    assert result["outputs"]["scanner_status"] == "NOT_RUN"
    assert result["outputs"]["readable_cas_objects"] == []
    assert _readable_cas_files(cas) == []


def test_failed_scanner_keeps_every_object_out_of_readable_cas(tmp_path: Path) -> None:
    result, cas = _publish(
        tmp_path,
        _zip([("safe.txt", b"safe")]),
        "zip",
        FailingScanner(),
    )

    assert result["state"] == "PARTIAL"
    assert result["outputs"]["publication_state"] == "NEEDS_REVIEW"
    assert result["outputs"]["scanner_status"] == "NEEDS_REVIEW"
    assert result["outputs"]["scanner_code"] == "SANDBOX_EXECUTION_FAILED"
    assert _readable_cas_files(cas) == []


def test_non_clean_entry_blocks_the_whole_set_before_any_cas_write(tmp_path: Path) -> None:
    scanner = SequenceScanner(["CLEAN", "CLEAN", "MALICIOUS"])
    result, cas = _publish(
        tmp_path,
        _zip([("one.txt", b"one"), ("two.txt", b"two")]),
        "zip",
        scanner,
    )

    assert result["state"] == "PARTIAL"
    assert result["code"] == "ARCHIVE_ENTRY_MALWARE_CLEARANCE_REQUIRED"
    assert result["outputs"]["failed_entry"] == "two.txt"
    assert result["outputs"]["scanner_code"] == "MALWARE_SCAN_NOT_CLEAN"
    assert len(scanner.calls) == 3
    assert _readable_cas_files(cas) == []


def test_case_unicode_collision_and_quota_fail_after_original_clearance(tmp_path: Path) -> None:
    collision_scanner = SequenceScanner()
    collision, collision_cas = _publish(
        tmp_path / "collision",
        _zip([("Readme.txt", b"one"), ("README.TXT", b"two")]),
        "zip",
        collision_scanner,
    )
    assert collision["state"] == "BLOCKED"
    assert collision["code"] == "ARCHIVE_EXTRACTION_BLOCKED"
    assert len(collision_scanner.calls) == 1
    assert _readable_cas_files(collision_cas) == []

    quota_scanner = SequenceScanner()
    quota_cas = LocalCasStore(tmp_path / "quota" / "cas")
    quota = publish_archive_to_cas(
        {
            **_request(_zip([("large.bin", b"1234")]), "zip"),
            "policy": {
                "archive": {
                    "max_entry_uncompressed_bytes": 3,
                    "max_total_uncompressed_bytes": 3,
                    "version": "test-tight-1",
                }
            },
        },
        providers=_provider(quota_scanner),
        cas=quota_cas,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-job-1",
    )
    assert quota["state"] == "BLOCKED"
    assert len(quota_scanner.calls) == 1
    assert _readable_cas_files(quota_cas) == []


def test_tar_link_is_blocked_after_original_scan_and_raw_password_before_scanner(tmp_path: Path) -> None:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as archive:
        link = tarfile.TarInfo("unsafe-link")
        link.type = tarfile.SYMTYPE
        link.linkname = "target"
        archive.addfile(link)
    tar_scanner = SequenceScanner()
    tar_result, tar_cas = _publish(tmp_path / "tar", tar_buffer.getvalue(), "tar", tar_scanner)
    assert tar_result["state"] == "BLOCKED"
    assert len(tar_scanner.calls) == 1
    assert _readable_cas_files(tar_cas) == []

    password_scanner = SequenceScanner()
    password_result, password_cas = _publish(
        tmp_path / "password",
        _zip([("safe.txt", b"safe")]),
        "zip",
        password_scanner,
        password="untrusted-secret",
    )
    assert password_result["state"] == "BLOCKED"
    assert password_result["code"] == "ARCHIVE_PASSWORD_SECRET_CHANNEL_REQUIRED"
    assert password_scanner.calls == []
    assert _readable_cas_files(password_cas) == []


def test_tar_tgz_and_gzip_publish_through_the_same_clean_receipt_boundary(tmp_path: Path) -> None:
    cases = [
        ("tar", _tar([("src/a.txt", b"a")], "w"), {}),
        ("tgz", _tar([("src/a.txt", b"a")], "w:gz"), {}),
        ("gzip", gzip.compress(b"single"), {"output_name": "single.txt"}),
    ]
    for index, (archive_format, data, inputs) in enumerate(cases):
        scanner = SequenceScanner()
        result, cas = _publish(tmp_path / str(index), data, archive_format, scanner, **inputs)
        assert result["state"] == "SUCCEEDED"
        assert len(scanner.calls) == 2
        assert len(result["outputs"]["entries"]) == 1
        assert _readable_cas_files(cas)


def test_mid_publication_failure_rolls_new_objects_out_of_readable_cas(tmp_path: Path) -> None:
    cas = FailingGeneratedObjectCas(tmp_path / "cas")
    result, _ = _publish(
        tmp_path,
        _zip([("safe.txt", b"safe")]),
        "zip",
        SequenceScanner(),
        cas=cas,
    )

    assert result["state"] == "FAILED"
    assert result["code"] == "ARCHIVE_CAS_PUBLICATION_FAILED"
    assert result["outputs"]["readable_generation_state"] == "UNKNOWN"
    assert _readable_cas_files(cas) == []


def test_generation_is_invisible_until_the_complete_object_set_is_renamed(tmp_path: Path) -> None:
    cas = LocalCasStore(tmp_path / "cas")
    payload = b"complete-generation-payload"
    object_digest = hashlib.sha256(payload).hexdigest()
    generation_digest, generation_manifest = _generation_manifest(
        [(object_digest, len(payload))]
    )
    paused = Event()
    release = Event()
    failures: list[BaseException] = []

    def chunks() -> Any:
        yield payload[:8]
        paused.set()
        assert release.wait(timeout=5)
        yield payload[8:]

    def publish() -> None:
        try:
            cas.publish_generation(
                "tenant-a",
                generation_digest,
                [
                    (object_digest, len(payload), chunks()),
                    (generation_digest, len(generation_manifest), (generation_manifest,)),
                ],
            )
        except BaseException as exc:  # capture the worker outcome for the assertion thread
            failures.append(exc)

    worker = Thread(target=publish)
    worker.start()
    assert paused.wait(timeout=5)
    assert not cas.generation_path_for("tenant-a", generation_digest).exists()
    with pytest.raises(NotFoundError):
        cas.read_generation_bytes("tenant-a", generation_digest, object_digest)
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert failures == []
    assert cas.read_generation_bytes("tenant-a", generation_digest, object_digest) == payload


def test_generation_read_rejects_canonical_index_membership_tampering(tmp_path: Path) -> None:
    cas = LocalCasStore(tmp_path / "cas")
    payload = b"generation-payload"
    object_digest = sha256_bytes(payload)
    generation_digest, generation_manifest = _generation_manifest(
        [(object_digest, len(payload))]
    )
    cas.publish_generation(
        "tenant-a",
        generation_digest,
        [
            (object_digest, len(payload), (payload,)),
            (generation_digest, len(generation_manifest), (generation_manifest,)),
        ],
    )

    generation_path = cas.generation_path_for("tenant-a", generation_digest)
    extra = b"index-only-object"
    extra_digest = sha256_bytes(extra)
    extra_path = generation_path / "objects" / extra_digest[:2] / extra_digest
    extra_path.parent.mkdir(parents=True, exist_ok=True)
    extra_path.write_bytes(extra)
    index_path = generation_path / ".generation.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["objects"].append({"digest": extra_digest, "byte_count": len(extra)})
    index["objects"].sort(key=lambda item: item["digest"])
    index_path.write_text(canonical_json(index), encoding="utf-8")

    with pytest.raises(IntegrityError):
        cas.read_generation_bytes("tenant-a", generation_digest, object_digest)


def test_generation_publish_rejects_unbound_generation_digest(tmp_path: Path) -> None:
    cas = LocalCasStore(tmp_path / "cas")
    payload = b"unbound-generation-payload"
    object_digest = sha256_bytes(payload)
    generation_digest = sha256_bytes(b"not-a-generation-manifest")

    with pytest.raises(IntegrityError):
        cas.publish_generation(
            "tenant-a",
            generation_digest,
            [(object_digest, len(payload), (payload,))],
        )
    assert not cas.generation_path_for("tenant-a", generation_digest).exists()


def test_pure_domain_extract_is_only_a_non_published_preview() -> None:
    result = extract_archive_safely(_request(_zip([("safe.txt", b"safe")]), "zip"))

    assert result["state"] == "PARTIAL"
    assert result["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"
    assert result["outputs"]["parser_execution"] == "NOT_RUN"
    assert result["outputs"]["objects"] == []
    assert result["outputs"]["publication_state"] == "NOT_RUN"
    assert result["outputs"]["readable_cas_objects"] == []


def test_parser_is_never_reached_when_original_scanner_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_parser(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("complex archive parser was reached before clearance")

    monkeypatch.setattr(archive_publication, "_preflight_zip", forbidden_parser)
    result, _ = _publish(tmp_path, _zip([("safe.txt", b"safe")]), "zip", None)
    assert result["state"] == "PARTIAL"
    assert result["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"


def test_outer_signature_must_match_declared_format_and_start_at_byte_zero(tmp_path: Path) -> None:
    data = _zip([("safe.txt", b"safe")])
    for index, (declared, archive) in enumerate((("tar", data), ("zip", b"MZ" + data))):
        scanner = SequenceScanner()
        result, cas = _publish(tmp_path / str(index), archive, declared, scanner)
        assert result["state"] == "BLOCKED"
        assert result["code"] == "ARCHIVE_FORMAT_SIGNATURE_MISMATCH"
        assert scanner.calls == []
        assert _readable_cas_files(cas) == []


def test_zip_compression_method_and_file_directory_conflicts_fail_closed(tmp_path: Path) -> None:
    unsupported = io.BytesIO()
    with zipfile.ZipFile(unsupported, "w", compression=zipfile.ZIP_BZIP2) as archive:
        archive.writestr("payload.bin", b"payload")
    unsupported_scanner = SequenceScanner()
    unsupported_result, _ = _publish(
        tmp_path / "compression",
        unsupported.getvalue(),
        "zip",
        unsupported_scanner,
    )
    assert unsupported_result["state"] == "BLOCKED"
    assert len(unsupported_scanner.calls) == 1

    conflict_scanner = SequenceScanner()
    conflict_result, _ = _publish(
        tmp_path / "ancestor",
        _zip([("A", b"file"), ("a/b.txt", b"child")]),
        "zip",
        conflict_scanner,
    )
    assert conflict_result["state"] == "BLOCKED"
    assert len(conflict_scanner.calls) == 1


@pytest.mark.parametrize(
    "path",
    ["NUL", "file:ads", "name.", "name ", "safe/CON.txt", "safe/\u202eevil.txt", "bad\udcff"],
)
def test_nonportable_and_invalid_unicode_entry_paths_are_rejected(path: str) -> None:
    with pytest.raises(ProjectContractError):
        archive_publication.normalize_relative_path(path)


def test_nested_archive_is_detected_from_bytes_not_extension_and_not_expanded(tmp_path: Path) -> None:
    nested = _zip([("inside.txt", b"inside")])
    scanner = SequenceScanner()
    result, cas = _publish(
        tmp_path,
        _zip([("renamed.bin", nested)]),
        "zip",
        scanner,
    )
    assert result["state"] == "SUCCEEDED"
    assert len(scanner.calls) == 2
    entry = result["outputs"]["entries"][0]
    assert entry["media_type"] == "application/zip"
    assert entry["nested_archive"] is True
    assert entry["nested_container"] == "zip"
    assert entry["nested_archive_state"] == "PRESERVED_NOT_EXPANDED"
    assert entry["nested_depth_observed"] == 1
    assert entry["contained_nested_depth_state"] == "NOT_INSPECTED_OPAQUE_CONTAINER"
    assert cas.read_generation_bytes(
        "tenant-a",
        result["outputs"]["generation_digest"],
        entry["content_digest"],
    ) == nested

    blocked_cas = LocalCasStore(tmp_path / "blocked-cas")
    blocked = publish_archive_to_cas(
        {
            **_request(_zip([("renamed.bin", nested)]), "zip"),
            "policy": {"archive": {"max_nested_depth": 0, "version": "no-nesting-1"}},
        },
        providers=_provider(SequenceScanner()),
        cas=blocked_cas,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-job-1",
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "ARCHIVE_NESTED_DEPTH_LIMIT"
    assert _readable_cas_files(blocked_cas) == []


def test_unencrypted_zip_never_touches_password_provider(tmp_path: Path) -> None:
    scanner = SequenceScanner()
    password_provider = StaticPasswordProvider()
    result, _ = _publish(
        tmp_path,
        _zip([("safe.txt", b"safe")]),
        "zip",
        scanner,
        password_provider=password_provider,
        password_handle="password-handle-1",
    )
    assert result["state"] == "SUCCEEDED"
    assert password_provider.calls == []
    serialized = json.dumps(result, sort_keys=True)
    assert "password-handle-1" not in serialized
    assert "runtime-owned-password" not in serialized

    without_provider, _ = _publish(
        tmp_path / "missing-provider",
        _zip([("safe.txt", b"safe")]),
        "zip",
        SequenceScanner(),
        password_handle="password-handle-1",
    )
    assert without_provider["state"] == "SUCCEEDED"


def test_encrypted_zip_resolves_exact_scoped_lease_without_persisting_secret(tmp_path: Path) -> None:
    provider = StaticPasswordProvider()
    result, _ = _publish(
        tmp_path,
        _encrypted_zip("safe.txt", b"safe", b"runtime-owned-password"),
        "zip",
        SequenceScanner(),
        password_provider=provider,
        password_handle="password-handle-1",
    )

    assert result["state"] == "SUCCEEDED"
    assert provider.calls == [
        {
            "handle": "password-handle-1",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "job_id": "archive-job-1",
            "purpose": "ARCHIVE_ZIP_DECRYPT",
        }
    ]
    serialized = json.dumps(result, sort_keys=True)
    assert "password-handle-1" not in serialized
    assert "runtime-owned-password" not in serialized

    missing, _ = _publish(
        tmp_path / "missing-provider",
        _encrypted_zip("safe.txt", b"safe", b"runtime-owned-password"),
        "zip",
        SequenceScanner(),
        password_handle="password-handle-1",
    )
    assert missing["state"] == "BLOCKED"
    assert missing["code"] == "ARCHIVE_PASSWORD_SECRET_CHANNEL_REQUIRED"


@pytest.mark.parametrize(
    "receipt_overrides",
    [
        {"tenant_id": "tenant-b"},
        {"project_id": "project-b"},
        {"job_id": "archive-job-2"},
        {"purpose": "OTHER_PURPOSE"},
        {"handle_digest": f"sha256:{'b' * 64}"},
        {"expires_at": "2000-01-01T00:00:00+00:00"},
        {"expires_at": "2999-01-01T00:00:00+00:00"},
        {"revoked": True},
    ],
)
def test_encrypted_zip_rejects_unscoped_expired_or_revoked_password_lease(
    tmp_path: Path,
    receipt_overrides: dict[str, Any],
) -> None:
    result, cas = _publish(
        tmp_path,
        _encrypted_zip("safe.txt", b"safe", b"runtime-owned-password"),
        "zip",
        SequenceScanner(),
        password_provider=StaticPasswordProvider(**receipt_overrides),
        password_handle="password-handle-1",
    )

    assert result["state"] == "BLOCKED"
    assert result["code"] == "ARCHIVE_PASSWORD_LEASE_INVALID"
    assert _readable_cas_files(cas) == []


def test_encrypted_zip_rejects_naked_password_bytes_without_scope_receipt(tmp_path: Path) -> None:
    result, cas = _publish(
        tmp_path,
        _encrypted_zip("safe.txt", b"safe", b"runtime-owned-password"),
        "zip",
        SequenceScanner(),
        password_provider=NakedPasswordProvider(),
        password_handle="password-handle-1",
    )

    assert result["state"] == "BLOCKED"
    assert result["code"] == "ARCHIVE_PASSWORD_LEASE_INVALID"
    assert _readable_cas_files(cas) == []


def test_scanner_hmac_is_instance_bound_while_persisted_binding_is_deterministic() -> None:
    data = b"same-byte-bound-input"
    first_provider = _provider(SequenceScanner())
    second_provider = _provider(SequenceScanner())
    first = first_provider.run(
        ToolCapability.MALWARE_SCAN,
        data,
        "application/octet-stream",
        job_id="archive-job-1",
        stage="archive-original",
    )
    second = second_provider.run(
        ToolCapability.MALWARE_SCAN,
        data,
        "application/octet-stream",
        job_id="archive-job-1",
        stage="archive-original",
    )

    assert first_provider.verify_issued_result(first) is True
    assert second_provider.verify_issued_result(first) is False
    assert first.receipt["executable"] == "elmos-malware-scan"
    assert "/" not in first.receipt["executable"]
    assert "\\" not in first.receipt["executable"]
    assert first_provider.verify_issued_result(
        ProviderResult(
            status=first.status,
            capability=first.capability,
            payload=first.payload,
            warnings=("tampered",),
            receipt=first.receipt,
        )
    ) is False
    tampered_receipt = dict(first.receipt)
    tampered_receipt["executable"] = "/private/scanner/elmos-malware-scan"
    assert first_provider.verify_issued_result(
        ProviderResult(
            status=first.status,
            capability=first.capability,
            payload=first.payload,
            receipt=tampered_receipt,
        )
    ) is False
    assert first.receipt["provider_auth_tag"] != second.receipt["provider_auth_tag"]
    first_binding, first_reason = archive_publication._scanner_binding(
        first_provider,
        first,
        data=data,
        media_type="application/octet-stream",
        job_id="archive-job-1",
        stage="archive-original",
    )
    second_binding, second_reason = archive_publication._scanner_binding(
        second_provider,
        second,
        data=data,
        media_type="application/octet-stream",
        job_id="archive-job-1",
        stage="archive-original",
    )
    assert first_reason == second_reason == "CLEAN"
    assert first_binding == second_binding


def test_private_provider_policy_binds_exact_path_while_public_receipt_does_not() -> None:
    class PathEchoingScanner(SequenceScanner):
        def execute(self, **request: Any) -> CommandReceipt:
            received = super().execute(**request)
            return CommandReceipt(
                tool=received.tool,
                executable_sha256=received.executable_sha256,
                exit_code=received.exit_code,
                stdout=received.stdout,
                stderr_summary="/private/host-a/elmos-malware-scan: diagnostic",
                duration_ms=received.duration_ms,
                sandboxed=received.sandboxed,
                network_allowed=received.network_allowed,
                completed_at=received.completed_at,
            )

    scanner = PathEchoingScanner()
    first = ExternalToolProvider(
        scanner,
        {
            ToolCapability.MALWARE_SCAN: {
                "path": "/private/host-a/elmos-malware-scan",
                "sha256": "a" * 64,
            }
        },
    )
    second = ExternalToolProvider(
        scanner,
        {
            ToolCapability.MALWARE_SCAN: {
                "path": "/private/host-b/elmos-malware-scan",
                "sha256": "a" * 64,
            }
        },
    )

    assert first.invocation_policy_digest(ToolCapability.MALWARE_SCAN) != (
        second.invocation_policy_digest(ToolCapability.MALWARE_SCAN)
    )
    assert first.execution_environment_digest != second.execution_environment_digest
    result = first.run(
        ToolCapability.MALWARE_SCAN,
        b"path-private",
        "application/octet-stream",
        job_id="archive-job-path-private",
        stage="archive-original",
    )
    assert first.verify_issued_result(result) is True
    assert result.receipt["executable"] == "elmos-malware-scan"
    assert "/private/host-a" not in canonical_json(dict(result.receipt))
    assert str(result.receipt["stderr_summary"]).startswith("sha256:")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload, receipt: payload.__setitem__("unexpected", True),
        lambda payload, receipt: receipt.__setitem__("unexpected", True),
        lambda payload, receipt: receipt.__setitem__("input_sha256", "b" * 64),
        lambda payload, receipt: receipt.__setitem__("input_bytes", 0),
        lambda payload, receipt: receipt.__setitem__("media_type", "application/octet-stream"),
        lambda payload, receipt: receipt.__setitem__("job_id", "other-job"),
        lambda payload, receipt: receipt.__setitem__("stage", "other-stage"),
        lambda payload, receipt: receipt.__setitem__("stdout_sha256", "b" * 64),
        lambda payload, receipt: receipt.__setitem__("policy_sha256", "b" * 64),
        lambda payload, receipt: receipt.__setitem__(
            "executable", "/private/tampered/elmos-malware-scan"
        ),
        lambda payload, receipt: receipt.__setitem__("argv", ["--unsafe"]),
        lambda payload, receipt: receipt.__setitem__("sandboxed", 1),
        lambda payload, receipt: receipt.__setitem__("network_allowed", 0),
        lambda payload, receipt: receipt.__setitem__("started_at", "2999-01-01T00:00:00+00:00"),
        lambda payload, receipt: receipt.__setitem__("provider_auth_tag", "0" * 64),
    ],
)
def test_scanner_payload_and_receipt_tampering_never_grants_clearance(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    cas = LocalCasStore(tmp_path / "cas")
    result = publish_archive_to_cas(
        _request(_zip([("safe.txt", b"safe")]), "zip"),
        providers=TamperingProvider(mutation),  # type: ignore[arg-type]
        cas=cas,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-job-1",
    )
    assert result["state"] == "PARTIAL"
    assert result["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"
    assert result["outputs"]["readable_cas_objects"] == []
    assert _readable_cas_files(cas) == []


def _archive_parent_binding(result: dict[str, Any], entry_index: int = 0) -> dict[str, str]:
    entry = result["outputs"]["entries"][entry_index]
    return {
        "parent_archive_digest": result["outputs"]["archive_digest"],
        "parent_entry_digest": entry["content_digest"],
        "parent_entry_receipt_digest": entry["entry_receipt_digest"],
        "parent_generation_digest": result["outputs"]["generation_digest"],
    }


def test_v17_archive_expansion_lineage_migration_is_mirrored_and_upgradeable(
    tmp_path: Path,
) -> None:
    engine_root = Path(__file__).resolve().parents[1]
    source = engine_root / "migrations" / "017_archive_expansion_lineage.sql"
    packaged = (
        engine_root
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "017_archive_expansion_lineage.sql"
    )
    assert source.read_bytes() == packaged.read_bytes()
    sql = source.read_text(encoding="utf-8")
    assert "CREATE TABLE archive_expansion_roots" in sql
    assert "CREATE TABLE archive_expansion_nodes" in sql
    assert "CREATE TABLE archive_expansion_entries" in sql
    assert "PRAGMA user_version = 17" in sql

    connection = sqlite3.connect(tmp_path / "upgrade-v16-v17.sqlite3", isolation_level=None)
    try:
        assert migrate_connection(connection, target_version=16) == 16
        assert migrate_connection(connection, target_version=17) == 17
    finally:
        connection.close()


def test_nested_expansions_share_one_durable_global_budget_and_replay_does_not_charge(
    tmp_path: Path,
) -> None:
    grandchild = _zip([("leaf.txt", b"leaf")])
    child = _zip([("grandchild.bin", grandchild)])
    outer = _zip([("child.bin", child)])
    policy = {
        "archive": {
            "max_entries": 2,
            "max_nested_depth": 3,
            "version": "nested-global-1",
        }
    }
    store = IntakeStore(tmp_path / "intake.sqlite3")
    cas = LocalCasStore(tmp_path / "cas")
    scanner = SequenceScanner()

    root = publish_archive_to_cas(
        {**_request(outer, "zip"), "policy": policy},
        providers=_provider(scanner),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-root",
    )
    child_request = {
        **_request(child, "zip", archive_parent=_archive_parent_binding(root)),
        "policy": policy,
    }
    nested = publish_archive_to_cas(
        child_request,
        providers=_provider(scanner),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-child",
    )
    replay = publish_archive_to_cas(
        child_request,
        providers=_provider(scanner),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-child",
    )

    assert root["state"] == nested["state"] == replay["state"] == "SUCCEEDED"
    assert nested["outputs"]["archive_root_digest"] == root["outputs"]["archive_root_digest"]
    assert nested["outputs"]["archive_depth"] == 1
    assert nested["outputs"]["archive_budget"]["consumed_entries"] == 2
    assert replay["outputs"]["archive_budget"]["consumed_entries"] == 2
    assert replay["outputs"]["generation_digest"] == nested["outputs"]["generation_digest"]

    scanner_calls_before_limit = len(scanner.calls)
    blocked = publish_archive_to_cas(
        {
            **_request(
                grandchild,
                "zip",
                archive_parent=_archive_parent_binding(nested),
            ),
            "policy": policy,
        },
        providers=_provider(scanner),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-grandchild",
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "ARCHIVE_GLOBAL_BUDGET_EXCEEDED"
    assert len(scanner.calls) == scanner_calls_before_limit
    store.close()


def test_nested_lineage_is_scope_and_digest_bound_and_requires_durable_store(
    tmp_path: Path,
) -> None:
    child = _zip([("leaf.txt", b"leaf")])
    outer = _zip([("child.bin", child)])
    store = IntakeStore(tmp_path / "intake.sqlite3")
    cas = LocalCasStore(tmp_path / "cas")
    policy = {"archive": {"max_nested_depth": 2, "version": "lineage-1"}}
    root = publish_archive_to_cas(
        {**_request(outer, "zip"), "policy": policy},
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-root",
    )
    parent = _archive_parent_binding(root)

    missing_store = publish_archive_to_cas(
        {**_request(child, "zip", archive_parent=parent), "policy": policy},
        providers=_provider(SequenceScanner()),
        cas=cas,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-child-no-store",
    )
    cross_tenant = publish_archive_to_cas(
        {**_request(child, "zip", archive_parent=parent), "policy": policy},
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-b",
        project_id="project-a",
        job_id="archive-child-cross-tenant",
    )
    tampered_parent = {**parent, "parent_entry_receipt_digest": "sha256:" + "b" * 64}
    tampered = publish_archive_to_cas(
        {**_request(child, "zip", archive_parent=tampered_parent), "policy": policy},
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-child-tampered",
    )
    policy_drift = publish_archive_to_cas(
        {
            **_request(child, "zip", archive_parent=parent),
            "policy": {"archive": {"max_nested_depth": 1, "version": "lineage-drift"}},
        },
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-child-policy-drift",
    )

    assert missing_store["code"] == "ARCHIVE_LINEAGE_STORE_REQUIRED"
    assert cross_tenant["code"] == "ARCHIVE_PARENT_LINEAGE_INVALID"
    assert tampered["code"] == "ARCHIVE_PARENT_LINEAGE_INVALID"
    assert policy_drift["code"] == "ARCHIVE_ROOT_POLICY_MISMATCH"
    store.close()


def test_concurrent_nested_siblings_cannot_oversubscribe_the_root_entry_budget(
    tmp_path: Path,
) -> None:
    child_a = _zip([("a.txt", b"a")])
    child_b = _zip([("b.txt", b"b")])
    outer = _zip([("child-a.bin", child_a), ("child-b.bin", child_b)])
    policy = {
        "archive": {
            "max_entries": 3,
            "max_nested_depth": 2,
            "version": "nested-concurrency-1",
        }
    }
    store = IntakeStore(tmp_path / "intake.sqlite3")
    cas = LocalCasStore(tmp_path / "cas")
    root = publish_archive_to_cas(
        {**_request(outer, "zip"), "policy": policy},
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-root",
    )
    children = {entry["path"]: entry for entry in root["outputs"]["entries"]}
    barrier = Event()
    results: list[dict[str, Any]] = []

    def expand(path: str, data: bytes, job_id: str) -> None:
        entry = children[path]
        parent = {
            "parent_archive_digest": root["outputs"]["archive_digest"],
            "parent_entry_digest": entry["content_digest"],
            "parent_entry_receipt_digest": entry["entry_receipt_digest"],
            "parent_generation_digest": root["outputs"]["generation_digest"],
        }
        barrier.wait()
        results.append(
            publish_archive_to_cas(
                {**_request(data, "zip", archive_parent=parent), "policy": policy},
                providers=_provider(SequenceScanner()),
                cas=cas,
                store=store,
                tenant_id="tenant-a",
                project_id="project-a",
                job_id=job_id,
            )
        )

    threads = [
        Thread(target=expand, args=("child-a.bin", child_a, "archive-child-a")),
        Thread(target=expand, args=("child-b.bin", child_b, "archive-child-b")),
    ]
    for thread in threads:
        thread.start()
    barrier.set()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert sorted(result["state"] for result in results) == ["BLOCKED", "SUCCEEDED"]
    assert {result["code"] for result in results} == {
        "ARCHIVE_GLOBAL_BUDGET_EXCEEDED",
        "ARCHIVE_PUBLISHED_TO_TENANT_CAS",
    }
    succeeded = next(result for result in results if result["state"] == "SUCCEEDED")
    assert succeeded["outputs"]["archive_budget"]["consumed_entries"] == 3
    store.close()


def test_nested_actual_bytes_are_charged_to_the_root_remaining_budget(
    tmp_path: Path,
) -> None:
    child = _zip([("leaf.txt", b"leaf")])
    outer = _zip([("child.bin", child)])
    policy = {
        "archive": {
            "max_total_uncompressed_bytes": len(child) + len(b"leaf") - 1,
            "max_nested_depth": 2,
            "version": "nested-byte-budget-1",
        }
    }
    store = IntakeStore(tmp_path / "intake.sqlite3")
    cas = LocalCasStore(tmp_path / "cas")
    root = publish_archive_to_cas(
        {**_request(outer, "zip"), "policy": policy},
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-root",
    )
    blocked = publish_archive_to_cas(
        {
            **_request(child, "zip", archive_parent=_archive_parent_binding(root)),
            "policy": policy,
        },
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-child",
    )
    assert root["state"] == "SUCCEEDED"
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "ARCHIVE_GLOBAL_BUDGET_EXCEEDED"
    store.close()


def test_nested_depth_is_absolute_from_the_persisted_root_not_reset_per_call(
    tmp_path: Path,
) -> None:
    grandchild = _zip([("leaf.txt", b"leaf")])
    child = _zip([("grandchild.bin", grandchild)])
    outer = _zip([("child.bin", child)])
    policy = {
        "archive": {
            "max_entries": 10,
            "max_nested_depth": 1,
            "version": "absolute-depth-1",
        }
    }
    store = IntakeStore(tmp_path / "intake.sqlite3")
    cas = LocalCasStore(tmp_path / "cas")
    root = publish_archive_to_cas(
        {**_request(outer, "zip"), "policy": policy},
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-root",
    )
    blocked = publish_archive_to_cas(
        {
            **_request(child, "zip", archive_parent=_archive_parent_binding(root)),
            "policy": policy,
        },
        providers=_provider(SequenceScanner()),
        cas=cas,
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-child",
    )
    assert root["state"] == "SUCCEEDED"
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "ARCHIVE_NESTED_DEPTH_LIMIT"
    store.close()


def test_archive_budget_tampering_is_rejected_on_store_reopen(tmp_path: Path) -> None:
    store = IntakeStore(tmp_path / "intake.sqlite3")
    publish_archive_to_cas(
        _request(_zip([("safe.txt", b"safe")]), "zip"),
        providers=_provider(SequenceScanner()),
        cas=LocalCasStore(tmp_path / "cas"),
        store=store,
        tenant_id="tenant-a",
        project_id="project-a",
        job_id="archive-root",
    )
    store.close()
    with sqlite3.connect(tmp_path / "intake.sqlite3", isolation_level=None) as connection:
        connection.execute("DROP TRIGGER archive_expansion_roots_guard_update")
        connection.execute(
            "UPDATE archive_expansion_roots SET consumed_entries = consumed_entries + 1"
        )

    with pytest.raises(IntegrityError) as rejected:
        IntakeStore(tmp_path / "intake.sqlite3")
    assert rejected.value.code == "ARCHIVE_EXPANSION_STATE_INVALID"
