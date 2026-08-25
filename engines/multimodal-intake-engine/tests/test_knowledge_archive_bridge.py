from __future__ import annotations

import base64
import hashlib
import io
import json
import struct
import zipfile
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from elmos_multimodal_intake import TenantContext, ToolCapability, create_runtime
from elmos_multimodal_intake.archive_publication import ArchivePasswordLease
from elmos_multimodal_intake.cli import KnowledgeArchiveSkillBridge
from elmos_multimodal_intake.providers import CommandReceipt
from elmos_multimodal_intake.skill_runtime import SkillDispatcher


class CleanScanner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(self, **request: Any) -> CommandReceipt:
        self.calls.append(dict(request))
        return CommandReceipt(
            tool=str(request["tool"]),
            executable_sha256="a" * 64,
            exit_code=0,
            stdout=json.dumps({"verdict": "CLEAN", "findings": []}).encode("utf-8"),
            duration_ms=1,
            sandboxed=True,
            network_allowed=False,
        )


def _request(
    skill: str,
    operation: str,
    inputs: dict[str, Any],
    *,
    request_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "idempotency_key": f"idempotency-{request_id}",
        "trace_id": f"trace-{request_id}",
        "inputs": {**inputs, "operation": operation},
        "policy": {},
        "capabilities": {},
    }


def _zip_bytes(path: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(path, data)
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


class StaticPasswordProvider:
    def __init__(self, identity_digest: str = "b" * 64) -> None:
        self.calls: list[dict[str, Any]] = []
        self.identity_digest = identity_digest

    @property
    def execution_identity_digest(self) -> str:
        return self.identity_digest

    def resolve_archive_password(self, handle: str, **scope: Any) -> ArchivePasswordLease:
        self.calls.append({"handle": handle, **scope})
        return ArchivePasswordLease(
            secret=b"runtime-owned-password",
            receipt={
                "schema_version": "1.0.0",
                **scope,
                "handle_digest": f"sha256:{hashlib.sha256(handle.encode('utf-8')).hexdigest()}",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "revoked": False,
            },
        )


class FailingPasswordProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def execution_identity_digest(self) -> str:
        return "c" * 64

    def resolve_archive_password(self, handle: str, **scope: Any) -> ArchivePasswordLease:
        self.calls.append({"handle": handle, **scope})
        raise RuntimeError("injected secret-provider failure")


def _observe_cas_publications(runtime: Any) -> list[bool]:
    calls: list[bool] = []
    publish_generation = runtime.cas.publish_generation

    def observed_publish(*args: Any, **kwargs: Any) -> str:
        calls.append(True)
        return publish_generation(*args, **kwargs)

    runtime.cas.publish_generation = observed_publish
    return calls


def _bind_source(runtime: Any, context: TenantContext, digest: str) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    with runtime.store.transaction() as connection:
        connection.execute(
            "INSERT INTO input_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "session-source-1",
                context.tenant_id,
                context.project_id,
                context.actor_id,
                "PROJECT_PACKAGE",
                "READY",
                "bridge-source-session",
                "0" * 64,
                "trace-source-1",
                1,
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO input_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "asset-1",
                "session-source-1",
                context.tenant_id,
                context.project_id,
                "source.txt",
                "text/plain",
                "text/plain",
                "TEXT",
                len(digest),
                digest,
                digest,
                "READY",
                "ALLOW",
                None,
                1,
                now,
                now,
            ),
        )


def test_durable_storage_memory_and_archive_bridges_use_runtime_owned_state(
    tmp_path: Path,
) -> None:
    scanner = CleanScanner()
    runtime = create_runtime(
        tmp_path / "intake.sqlite3",
        tmp_path / "cas",
        sandbox_executor=scanner,
        provisioned_tools={
            ToolCapability.MALWARE_SCAN: {
                "path": "/opt/elmos/bin/elmos-malware-scan",
                "sha256": "a" * 64,
            }
        },
    )
    context = TenantContext("tenant-a", "project-a", "actor-a")
    runtime.store.bootstrap_project(context)
    bridge = KnowledgeArchiveSkillBridge(runtime)
    cas_publish_calls = _observe_cas_publications(runtime)
    dispatcher = SkillDispatcher()
    for skill in (
        "elmos-storage-index-and-retrieval",
        "elmos-project-memory-and-retrieval",
        "elmos-secure-zip-tar-extraction",
    ):
        dispatcher.register_bridge(skill, bridge)

    text = "durable retrieval evidence"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    _bind_source(runtime, context, digest)
    indexed = dispatcher.dispatch(
        "elmos-storage-index-and-retrieval",
        _request(
            "elmos-storage-index-and-retrieval",
            "upsert",
            {
                "branch": "main",
                "package_version": "package-v1",
                "document_id": "document-1",
                "text": text,
                "content_digest": digest,
                "source_digest": digest,
                "source_anchor": {"asset_id": "asset-1"},
                "required_permissions": ["intake:read"],
                "expected_version": 0,
            },
            request_id="storage-upsert",
        ),
    )
    assert indexed["state"] == "SUCCEEDED"
    assert indexed["code"] == "KNOWLEDGE_DOCUMENT_PERSISTED"
    assert indexed["outputs"]["persisted"] is True

    retrieved = dispatcher.dispatch(
        "elmos-storage-index-and-retrieval",
        _request(
            "elmos-storage-index-and-retrieval",
            "query",
            {
                "branch": "main",
                "package_version": "package-v1",
                "query": "retrieval",
            },
            request_id="storage-query",
        ),
    )
    assert retrieved["state"] == "PARTIAL"
    assert retrieved["code"] == "LOCAL_LEXICAL_RETRIEVAL_COMPLETED"
    assert retrieved["outputs"]["results"][0]["document_id"] == "document-1"
    assert retrieved["outputs"]["vector_execution"] == "NOT_RUN"

    memory = dispatcher.dispatch(
        "elmos-project-memory-and-retrieval",
        _request(
            "elmos-project-memory-and-retrieval",
            "write",
            {
                "branch": "main",
                "package_version": "package-v1",
                "memory_key": "decision.storage",
                "value": {"mode": "durable"},
                "source_digest": digest,
                "source_anchor": {"asset_id": "asset-1"},
                "required_permissions": ["intake:read"],
                "expected_version": 0,
                "memory_kind": "DECISION",
            },
            request_id="memory-write",
        ),
    )
    assert memory["state"] == "SUCCEEDED"
    assert memory["outputs"]["persisted"] is True

    archive_data = _zip_bytes("src/main.py", b"print('safe')\n")
    archive_request = _request(
        "elmos-secure-zip-tar-extraction",
        "publish",
        {
            "format": "zip",
            "archive_bytes_b64": base64.b64encode(archive_data).decode("ascii"),
        },
        request_id="archive-publish",
    )
    published = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        archive_request,
    )
    assert published["state"] == "SUCCEEDED"
    assert published["code"] == "ARCHIVE_PUBLISHED_TO_TENANT_CAS"
    assert published["outputs"]["host_paths_returned"] is False
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1
    entry = published["outputs"]["entries"][0]
    assert runtime.cas.read_generation_bytes(
        "tenant-a",
        published["outputs"]["generation_digest"],
        entry["content_digest"],
    ) == b"print('safe')\n"

    replayed = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        {**archive_request, "trace_id": "trace-archive-publish-replay"},
    )
    assert replayed["state"] == published["state"]
    assert replayed["code"] == published["code"]
    assert replayed["outputs"] == published["outputs"]
    assert replayed["metrics"] == published["metrics"]
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1

    missing_parent = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        _request(
            "elmos-secure-zip-tar-extraction",
            "expand_nested",
            {
                "format": "zip",
                "archive_bytes_b64": base64.b64encode(archive_data).decode("ascii"),
            },
            request_id="archive-nested-missing-parent",
        ),
    )
    assert missing_parent["state"] == "BLOCKED"
    assert missing_parent["code"] == "ARCHIVE_PARENT_LINEAGE_REQUIRED"
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1

    conflict = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        _request(
            "elmos-secure-zip-tar-extraction",
            "publish",
            {
                "format": "zip",
                "archive_bytes_b64": base64.b64encode(
                    _zip_bytes("src/main.py", b"print('different')\n")
                ).decode("ascii"),
            },
            request_id="archive-publish",
        ),
    )
    assert conflict["state"] == "BLOCKED"
    assert conflict["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1

    policy_conflict = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        {
            **archive_request,
            "policy": {"archive": {"max_entries": 1}},
            "trace_id": "trace-archive-policy-conflict",
        },
    )
    assert policy_conflict["state"] == "BLOCKED"
    assert policy_conflict["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"

    capability_conflict = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        {
            **archive_request,
            "capabilities": {"archive_publication": "runtime-owned"},
            "trace_id": "trace-archive-capability-conflict",
        },
    )
    assert capability_conflict["state"] == "BLOCKED"
    assert capability_conflict["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1

    missing_key_request = _request(
        "elmos-secure-zip-tar-extraction",
        "publish",
        {
            "format": "zip",
            "archive_bytes_b64": base64.b64encode(archive_data).decode("ascii"),
        },
        request_id="archive-missing-key",
    )
    missing_key_request.pop("idempotency_key")
    missing_key = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        missing_key_request,
    )
    assert missing_key["state"] == "BLOCKED"
    assert missing_key["code"] == "PERSISTENT_IDEMPOTENCY_KEY_REQUIRED"
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1
    runtime.close()


def test_archive_bridge_replay_does_not_repeat_password_scanner_or_cas_effects(
    tmp_path: Path,
) -> None:
    scanner = CleanScanner()
    password_provider = StaticPasswordProvider()
    database = tmp_path / "encrypted-intake.sqlite3"
    cas_root = tmp_path / "encrypted-cas"
    runtime = create_runtime(
        database,
        cas_root,
        sandbox_executor=scanner,
        provisioned_tools={
            ToolCapability.MALWARE_SCAN: {
                "path": "/opt/elmos/bin/elmos-malware-scan",
                "sha256": "a" * 64,
            }
        },
        archive_password_provider=password_provider,
    )
    runtime.store.bootstrap_project(TenantContext("tenant-a", "project-a", "actor-a"))
    bridge = KnowledgeArchiveSkillBridge(runtime)
    cas_publish_calls = _observe_cas_publications(runtime)
    dispatcher = SkillDispatcher()
    dispatcher.register_bridge("elmos-secure-zip-tar-extraction", bridge)
    archive_data = _encrypted_zip(
        "secret.txt",
        b"tenant secret channel payload",
        b"runtime-owned-password",
    )
    archive_request = _request(
        "elmos-secure-zip-tar-extraction",
        "publish",
        {
            "format": "zip",
            "archive_bytes_b64": base64.b64encode(archive_data).decode("ascii"),
            "password_handle": "password-handle-1",
        },
        request_id="archive-encrypted-success",
    )

    published = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        archive_request,
    )
    assert published["state"] == "SUCCEEDED"
    assert published["code"] == "ARCHIVE_PUBLISHED_TO_TENANT_CAS"
    assert len(password_provider.calls) == 1
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1

    replayed = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        {**archive_request, "trace_id": "trace-archive-encrypted-replay"},
    )
    assert replayed["state"] == published["state"]
    assert replayed["code"] == published["code"]
    assert replayed["outputs"] == published["outputs"]
    assert replayed["metrics"] == published["metrics"]
    assert len(password_provider.calls) == 1
    assert len(scanner.calls) == 2
    assert len(cas_publish_calls) == 1
    runtime.close()

    tool_drift_scanner = CleanScanner()
    tool_drift_password_provider = StaticPasswordProvider()
    tool_drift_runtime = create_runtime(
        database,
        cas_root,
        sandbox_executor=tool_drift_scanner,
        provisioned_tools={
            ToolCapability.MALWARE_SCAN: {
                "path": "/opt/elmos/bin/elmos-malware-scan",
                "sha256": "d" * 64,
            }
        },
        archive_password_provider=tool_drift_password_provider,
    )
    tool_drift_bridge = KnowledgeArchiveSkillBridge(tool_drift_runtime)
    tool_drift_cas_calls = _observe_cas_publications(tool_drift_runtime)
    tool_drift_dispatcher = SkillDispatcher()
    tool_drift_dispatcher.register_bridge(
        "elmos-secure-zip-tar-extraction",
        tool_drift_bridge,
    )
    tool_drift = tool_drift_dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        {**archive_request, "trace_id": "trace-tool-environment-drift"},
    )
    assert tool_drift["state"] == "BLOCKED"
    assert tool_drift["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"
    assert tool_drift_scanner.calls == []
    assert tool_drift_password_provider.calls == []
    assert tool_drift_cas_calls == []
    tool_drift_runtime.close()

    password_drift_scanner = CleanScanner()
    password_drift_provider = StaticPasswordProvider(identity_digest="e" * 64)
    password_drift_runtime = create_runtime(
        database,
        cas_root,
        sandbox_executor=password_drift_scanner,
        provisioned_tools={
            ToolCapability.MALWARE_SCAN: {
                "path": "/opt/elmos/bin/elmos-malware-scan",
                "sha256": "a" * 64,
            }
        },
        archive_password_provider=password_drift_provider,
    )
    password_drift_bridge = KnowledgeArchiveSkillBridge(password_drift_runtime)
    password_drift_cas_calls = _observe_cas_publications(password_drift_runtime)
    password_drift_dispatcher = SkillDispatcher()
    password_drift_dispatcher.register_bridge(
        "elmos-secure-zip-tar-extraction",
        password_drift_bridge,
    )
    password_drift = password_drift_dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        {**archive_request, "trace_id": "trace-password-provider-drift"},
    )
    assert password_drift["state"] == "BLOCKED"
    assert password_drift["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"
    assert password_drift_scanner.calls == []
    assert password_drift_provider.calls == []
    assert password_drift_cas_calls == []
    password_drift_runtime.close()


def test_archive_bridge_secret_provider_exception_is_terminal_reconciliation(
    tmp_path: Path,
) -> None:
    scanner = CleanScanner()
    password_provider = FailingPasswordProvider()
    runtime = create_runtime(
        tmp_path / "failed-secret-intake.sqlite3",
        tmp_path / "failed-secret-cas",
        sandbox_executor=scanner,
        provisioned_tools={
            ToolCapability.MALWARE_SCAN: {
                "path": "/opt/elmos/bin/elmos-malware-scan",
                "sha256": "a" * 64,
            }
        },
        archive_password_provider=password_provider,
    )
    runtime.store.bootstrap_project(TenantContext("tenant-a", "project-a", "actor-a"))
    bridge = KnowledgeArchiveSkillBridge(runtime)
    cas_publish_calls = _observe_cas_publications(runtime)
    dispatcher = SkillDispatcher()
    dispatcher.register_bridge("elmos-secure-zip-tar-extraction", bridge)
    archive_data = _encrypted_zip(
        "secret.txt",
        b"provider failure payload",
        b"runtime-owned-password",
    )
    archive_request = _request(
        "elmos-secure-zip-tar-extraction",
        "publish",
        {
            "format": "zip",
            "archive_bytes_b64": base64.b64encode(archive_data).decode("ascii"),
            "password_handle": "password-handle-1",
        },
        request_id="archive-secret-provider-failure",
    )

    blocked = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        archive_request,
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED"
    assert blocked["retryable"] is False
    assert blocked["outputs"]["publication_state"] == "RECONCILIATION_REQUIRED"
    assert blocked["outputs"]["reconciliation_state"] == "REQUIRED"
    assert blocked["outputs"]["external_effects"] == {
        "scanner_invoked": True,
        "password_provider_invoked": True,
        "cas_publish_invoked": False,
    }
    assert len(password_provider.calls) == 1
    assert len(scanner.calls) == 1
    assert cas_publish_calls == []

    replayed = dispatcher.dispatch(
        "elmos-secure-zip-tar-extraction",
        {**archive_request, "trace_id": "trace-secret-provider-failure-replay"},
    )
    assert replayed["state"] == blocked["state"]
    assert replayed["code"] == blocked["code"]
    assert replayed["outputs"] == blocked["outputs"]
    assert replayed["metrics"] == blocked["metrics"]
    assert len(password_provider.calls) == 1
    assert len(scanner.calls) == 1
    assert cas_publish_calls == []
    runtime.close()
