"""Durable, tenant-scoped lifecycle for large project-package inputs."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from .canonical import MAX_SAFE_JSON_INTEGER, canonical_digest, canonical_json, new_id, utc_now
from .errors import ConflictError, IntegrityError, NotFoundError, ValidationError
from .models import TenantContext
from .projects import (
    build_repository_context_map,
    classify_project_entries,
    detect_project_profile,
    index_repository_symbols,
    normalize_relative_path,
)
from .skill_runtime import RuntimeContext
from .store import IntakeStore, LocalCasStore

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_ENTRIES = 100_000
_MAX_CHUNK = 1_000
_MAX_PAGE = 200
_MAX_METADATA_BYTES = 16 * 1024
_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
_MAX_PART_BYTES = 16 * 1024 * 1024
_MAX_PART_BASE64_CHARS = ((_MAX_PART_BYTES + 2) // 3) * 4
_ARTIFACT_HANDLERS: Mapping[str, tuple[str, Callable[[Mapping[str, Any]], dict[str, Any]]]] = {
    "elmos-project-root-language-framework-detection": ("PROJECT_PROFILE", detect_project_profile),
    "elmos-ignore-generated-vendored-file-classification": ("FILE_CLASSIFICATION", classify_project_entries),
    "elmos-repository-map-and-symbol-indexing": ("SYMBOL_INDEX", index_repository_symbols),
    "elmos-repository-context-map": ("CONTEXT_GRAPH", build_repository_context_map),
}


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = MAX_SAFE_JSON_INTEGER,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError("PROJECT_PACKAGE_INTEGER_INVALID", details={"field": field})
    return value


def _text(value: Any, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValidationError("PROJECT_PACKAGE_TEXT_INVALID", details={"field": field})
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValidationError("PROJECT_PACKAGE_TEXT_INVALID", details={"field": field}) from error
    if len(encoded) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValidationError("PROJECT_PACKAGE_TEXT_INVALID", details={"field": field})
    return value


def _json(value: Any, field: str, *, maximum: int) -> Any:
    try:
        encoded = canonical_json(value).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("PROJECT_PACKAGE_JSON_INVALID", details={"field": field}) from error
    if len(encoded) > maximum:
        raise ValidationError("PROJECT_PACKAGE_JSON_TOO_LARGE", details={"field": field})
    return value


def _normalize_entry(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValidationError("PROJECT_PACKAGE_ENTRY_INVALID")
    allowed = {"path", "kind", "byte_count", "content_digest", "role", "model_read_allowed", "metadata"}
    if set(raw) - allowed:
        raise ValidationError("PROJECT_PACKAGE_ENTRY_FIELDS_INVALID")
    path = normalize_relative_path(raw.get("path"))
    kind = str(raw.get("kind", "file")).lower()
    if kind not in {"file", "directory", "symlink", "hardlink", "special"}:
        raise ValidationError("PROJECT_PACKAGE_ENTRY_KIND_INVALID")
    byte_count = _integer(raw.get("byte_count", 0), "byte_count", maximum=4 * 1024 * 1024 * 1024)
    digest = raw.get("content_digest")
    if kind == "file":
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ValidationError("PROJECT_PACKAGE_CONTENT_DIGEST_INVALID")
    elif digest is not None:
        raise ValidationError("PROJECT_PACKAGE_CONTENT_DIGEST_INVALID")
    role = str(raw.get("role", "PRIMARY")).upper()
    if role not in {"PRIMARY", "REFERENCE", "IGNORE"}:
        raise ValidationError("PROJECT_PACKAGE_ROLE_INVALID")
    requested_model_read = raw.get("model_read_allowed", role != "IGNORE")
    if not isinstance(requested_model_read, bool):
        raise ValidationError("PROJECT_PACKAGE_MODEL_READ_INVALID")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValidationError("PROJECT_PACKAGE_METADATA_INVALID")
    _json(metadata, "metadata", maximum=_MAX_METADATA_BYTES)
    body = {
        "path": path, "kind": kind, "byte_count": byte_count,
        "content_digest": digest, "role": role,
        "model_read_allowed": False, "security_state": "UNSCANNED",
        "metadata": dict(metadata),
    }
    return {**body, "_requested_model_read": requested_model_read}


def _merkle_root(entries: Sequence[Mapping[str, Any]]) -> str:
    layer = [str(item["entry_digest"]) for item in entries]
    if not layer:
        return canonical_digest([])
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [
            hashlib.sha256(bytes.fromhex(layer[index]) + bytes.fromhex(layer[index + 1])).hexdigest()
            for index in range(0, len(layer), 2)
        ]
    return layer[0]


def _cursor(document: Mapping[str, Any]) -> str:
    return base64.urlsafe_b64encode(canonical_json(document).encode("utf-8")).decode("ascii").rstrip("=")


def _parse_cursor(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value or len(value) > 4096 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValidationError("PROJECT_PACKAGE_CURSOR_INVALID")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8", errors="strict")
        import json
        parsed = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValidationError("PROJECT_PACKAGE_CURSOR_INVALID") from error
    if not isinstance(parsed, dict) or set(parsed) != {"schema_version", "scope_digest", "collection_digest", "package_version", "offset"}:
        raise ValidationError("PROJECT_PACKAGE_CURSOR_INVALID")
    if canonical_json(parsed) != raw or parsed.get("schema_version") != "project-package-page-cursor-v1":
        raise ValidationError("PROJECT_PACKAGE_CURSOR_INVALID")
    return parsed


class ProjectPackageLifecycle:
    def __init__(self, store: IntakeStore, cas: LocalCasStore | None = None) -> None:
        self.store = store
        self.cas = cas

    @staticmethod
    def _scope(context: TenantContext) -> tuple[str, str]:
        return context.tenant_id, context.project_id

    def begin(self, context: TenantContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.store.require(context, self.store.WRITE)
        expected = _integer(payload.get("expected_entry_count"), "expected_entry_count", maximum=_MAX_ENTRIES)
        session_id = _text(payload.get("session_id", new_id("package")), "session_id", maximum=128)
        now = utc_now()
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM project_package_sessions WHERE tenant_id=? AND project_id=? AND session_id=?",
                (*self._scope(context), session_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO project_package_sessions(tenant_id,project_id,session_id,state,expected_entry_count,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (*self._scope(context), session_id, "OPEN", expected, context.actor_id, now, now),
                )
            elif int(existing["expected_entry_count"]) != expected:
                raise ConflictError("PROJECT_PACKAGE_SESSION_IDEMPOTENCY_CONFLICT")
        return self.status(context, session_id)

    def append(self, context: TenantContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.store.require(context, self.store.WRITE)
        session_id = _text(payload.get("session_id"), "session_id", maximum=128)
        chunk_index = _integer(payload.get("chunk_index"), "chunk_index")
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list) or not 1 <= len(raw_entries) <= _MAX_CHUNK:
            raise ValidationError("PROJECT_PACKAGE_CHUNK_SIZE_INVALID")
        entries = sorted((_normalize_entry(item) for item in raw_entries), key=lambda item: item["path"])
        if len({item["path"] for item in entries}) != len(entries):
            raise ValidationError("PROJECT_PACKAGE_CHUNK_PATH_COLLISION")
        now = utc_now()
        with self.store.transaction() as connection:
            for entry in entries:
                asset_id = entry["metadata"].get("asset_id")
                trusted = None
                if isinstance(asset_id, str) and entry["kind"] == "file":
                    trusted = connection.execute(
                        "SELECT status,security_decision,sha256 FROM input_assets WHERE tenant_id=? AND project_id=? AND asset_id=?",
                        (*self._scope(context), asset_id),
                    ).fetchone()
                content_digest = str(entry["content_digest"] or "")
                if (
                    trusted is not None
                    and trusted["status"] == "READY"
                    and trusted["security_decision"] == "ALLOW"
                    and content_digest == "sha256:" + str(trusted["sha256"])
                ):
                    entry["security_state"] = "CLEARED"
                    entry["model_read_allowed"] = bool(entry["_requested_model_read"]) and entry["role"] != "IGNORE"
                entry.pop("_requested_model_read", None)
                entry["entry_digest"] = canonical_digest(entry)
            chunk_digest = canonical_digest(entries)
            session = connection.execute(
                "SELECT * FROM project_package_sessions WHERE tenant_id=? AND project_id=? AND session_id=?",
                (*self._scope(context), session_id),
            ).fetchone()
            if session is None:
                raise NotFoundError("PROJECT_PACKAGE_SESSION_NOT_FOUND")
            existing = connection.execute(
                "SELECT chunk_digest FROM project_package_chunks WHERE tenant_id=? AND project_id=? AND session_id=? AND chunk_index=?",
                (*self._scope(context), session_id, chunk_index),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(str(existing["chunk_digest"]), chunk_digest):
                    raise ConflictError("PROJECT_PACKAGE_CHUNK_IDEMPOTENCY_CONFLICT")
                return self._status_row(session)
            if session["state"] not in {"OPEN", "PARTIAL"} or int(session["next_chunk_index"]) != chunk_index:
                raise ConflictError("PROJECT_PACKAGE_CHUNK_ORDER_CONFLICT")
            accepted = int(session["accepted_entry_count"]) + len(entries)
            if accepted > int(session["expected_entry_count"]) or accepted > _MAX_ENTRIES:
                raise ValidationError("PROJECT_PACKAGE_ENTRY_BUDGET_EXCEEDED")
            connection.execute(
                "INSERT INTO project_package_chunks VALUES(?,?,?,?,?,?,?,?)",
                (*self._scope(context), session_id, chunk_index, len(entries), chunk_digest, canonical_json(entries), now),
            )
            connection.execute(
                "UPDATE project_package_sessions SET state=?,accepted_entry_count=?,next_chunk_index=?,generation=generation+1,updated_at=? WHERE tenant_id=? AND project_id=? AND session_id=?",
                ("OPEN" if accepted == int(session["expected_entry_count"]) else "PARTIAL", accepted, chunk_index + 1, now, *self._scope(context), session_id),
            )
        return self.status(context, session_id)

    @staticmethod
    def _status_row(row: Any) -> dict[str, Any]:
        expected = int(row["expected_entry_count"])
        accepted = int(row["accepted_entry_count"])
        state = str(row["state"])
        return {
            "schema_version": "project-package-session-v1", "session_id": str(row["session_id"]),
            "state": state, "expected_entry_count": expected, "accepted_entry_count": accepted,
            "remaining_entry_count": expected - accepted, "next_chunk_index": int(row["next_chunk_index"]),
            "generation": int(row["generation"]), "package_version": row["manifest_version"],
            "manifest_digest": row["manifest_digest"], "merkle_root": row["merkle_root"],
            "complete": state == "FINALIZED" and accepted == expected,
        }

    def status(self, context: TenantContext, session_id: str) -> dict[str, Any]:
        self.store.require(context, self.store.READ)
        with self.store.read_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM project_package_sessions WHERE tenant_id=? AND project_id=? AND session_id=?",
                (*self._scope(context), _text(session_id, "session_id", maximum=128)),
            ).fetchone()
        if row is None:
            raise NotFoundError("PROJECT_PACKAGE_SESSION_NOT_FOUND")
        return self._status_row(row)

    def _entries_for_session(self, connection: Any, context: TenantContext, session_id: str) -> list[dict[str, Any]]:
        import json
        rows = connection.execute(
            "SELECT entries_json FROM project_package_chunks WHERE tenant_id=? AND project_id=? AND session_id=? ORDER BY chunk_index",
            (*self._scope(context), session_id),
        ).fetchall()
        entries = [item for row in rows for item in json.loads(str(row["entries_json"]))]
        entries.sort(key=lambda item: item["path"])
        if len({item["path"] for item in entries}) != len(entries):
            raise ConflictError("PROJECT_PACKAGE_PATH_COLLISION")
        return entries

    def finalize(self, context: TenantContext, session_id: str) -> dict[str, Any]:
        self.store.require(context, self.store.WRITE)
        session_id = _text(session_id, "session_id", maximum=128)
        now = utc_now()
        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM project_package_sessions WHERE tenant_id=? AND project_id=? AND session_id=?",
                (*self._scope(context), session_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("PROJECT_PACKAGE_SESSION_NOT_FOUND")
            if row["state"] == "FINALIZED":
                return self._status_row(row)
            if int(row["accepted_entry_count"]) != int(row["expected_entry_count"]):
                connection.execute(
                    "UPDATE project_package_sessions SET state='PARTIAL',updated_at=? WHERE tenant_id=? AND project_id=? AND session_id=?",
                    (now, *self._scope(context), session_id),
                )
                return {**self._status_row(row), "state": "PARTIAL", "complete": False}
            entries = self._entries_for_session(connection, context, session_id)
            merkle = _merkle_root(entries)
            parent = connection.execute(
                "SELECT package_version FROM project_package_versions WHERE tenant_id=? AND project_id=? AND state='ACTIVE'",
                self._scope(context),
            ).fetchone()
            version = 1 if parent is None else int(parent["package_version"]) + 1
            manifest = {"schema_version": "project-package-manifest-v2", "package_version": version, "parent_version": None if parent is None else int(parent["package_version"]), "entry_count": len(entries), "merkle_root": merkle, "entry_digests": [item["entry_digest"] for item in entries]}
            digest = canonical_digest(manifest)
            if parent is not None:
                connection.execute("UPDATE project_package_versions SET state='SUPERSEDED' WHERE tenant_id=? AND project_id=? AND package_version=?", (*self._scope(context), int(parent["package_version"])))
            connection.execute(
                "INSERT INTO project_package_versions VALUES(?,?,?,?,?,?,?,?,?,?)",
                (*self._scope(context), version, manifest["parent_version"], "ACTIVE", len(entries), digest, merkle, context.actor_id, now),
            )
            connection.executemany(
                """INSERT INTO project_package_entries(
                       tenant_id,project_id,package_version,path,entry_digest,
                       content_digest,byte_count,kind,role,model_read_allowed,
                       security_state,metadata_json,override_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(*self._scope(context), version, item["path"], item["entry_digest"], item["content_digest"] or "", item["byte_count"], item["kind"], item["role"], int(item["model_read_allowed"]), item["security_state"], canonical_json(item["metadata"]), 0) for item in entries],
            )
            connection.execute(
                "UPDATE project_package_sessions SET state='FINALIZED',manifest_version=?,manifest_digest=?,merkle_root=?,generation=generation+1,updated_at=? WHERE tenant_id=? AND project_id=? AND session_id=?",
                (version, digest, merkle, now, *self._scope(context), session_id),
            )
        return self.status(context, session_id)

    def page(self, context: TenantContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.store.require(context, self.store.READ)
        version = _integer(payload.get("package_version"), "package_version", minimum=1)
        limit = _integer(payload.get("limit", 100), "limit", minimum=1, maximum=_MAX_PAGE)
        scope_digest = canonical_digest({"tenant_id": context.tenant_id, "project_id": context.project_id})
        with self.store.read_transaction() as connection:
            version_row = connection.execute(
                "SELECT manifest_digest,entry_count FROM project_package_versions WHERE tenant_id=? AND project_id=? AND package_version=?",
                (*self._scope(context), version),
            ).fetchone()
            if version_row is None:
                raise NotFoundError("PROJECT_PACKAGE_VERSION_NOT_FOUND")
            collection_digest = str(version_row["manifest_digest"])
            cursor = payload.get("cursor")
            offset = 0
            if cursor is not None:
                parsed = _parse_cursor(cursor)
                if parsed["scope_digest"] != scope_digest or parsed["collection_digest"] != collection_digest or parsed["package_version"] != version:
                    raise ConflictError("PROJECT_PACKAGE_CURSOR_DRIFT")
                offset = _integer(parsed["offset"], "cursor.offset", maximum=_MAX_ENTRIES)
            rows = connection.execute(
                "SELECT * FROM project_package_entries WHERE tenant_id=? AND project_id=? AND package_version=? ORDER BY path LIMIT ? OFFSET ?",
                (*self._scope(context), version, limit + 1, offset),
            ).fetchall()
        items = [self._entry_row(row) for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            next_cursor = _cursor({"schema_version": "project-package-page-cursor-v1", "scope_digest": scope_digest, "collection_digest": collection_digest, "package_version": version, "offset": offset + limit})
        return {"schema_version": "project-package-page-v1", "package_version": version, "items": items, "next_cursor": next_cursor, "total": int(version_row["entry_count"]), "collection_digest": collection_digest}

    @staticmethod
    def _entry_row(row: Any) -> dict[str, Any]:
        import json
        return {"path": str(row["path"]), "kind": str(row["kind"]), "byte_count": int(row["byte_count"]), "content_digest": str(row["content_digest"]) or None, "entry_digest": str(row["entry_digest"]), "role": str(row["role"]), "model_read_allowed": bool(row["model_read_allowed"]), "security_state": str(row["security_state"]), "metadata": json.loads(str(row["metadata_json"])), "override_version": int(row["override_version"])}

    def diff(self, context: TenantContext, old_version: int, new_version: int) -> dict[str, Any]:
        self.store.require(context, self.store.READ)
        old_version = _integer(old_version, "old_version", minimum=1)
        new_version = _integer(new_version, "new_version", minimum=1)
        if old_version == new_version:
            raise ValidationError("PROJECT_PACKAGE_DIFF_VERSIONS_IDENTICAL")
        with self.store.read_transaction() as connection:
            def load(version: int) -> dict[str, str]:
                rows = connection.execute("SELECT path,entry_digest FROM project_package_entries WHERE tenant_id=? AND project_id=? AND package_version=?", (*self._scope(context), version)).fetchall()
                if not rows:
                    exists = connection.execute("SELECT 1 FROM project_package_versions WHERE tenant_id=? AND project_id=? AND package_version=?", (*self._scope(context), version)).fetchone()
                    if exists is None:
                        raise NotFoundError("PROJECT_PACKAGE_VERSION_NOT_FOUND")
                return {str(row["path"]): str(row["entry_digest"]) for row in rows}
            old, new = load(old_version), load(new_version)
        added = sorted(new.keys() - old.keys())
        removed = sorted(old.keys() - new.keys())
        changed = sorted(path for path in old.keys() & new.keys() if old[path] != new[path])
        body = {"schema_version": "project-package-diff-v1", "old_version": old_version, "new_version": new_version, "added": added, "removed": removed, "changed": changed}
        return {**body, "diff_digest": canonical_digest(body), "exact_versions": True}

    def upload(self, context: TenantContext, action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.store.require(context, self.store.WRITE if action != "status" else self.store.READ)
        session_id = _text(payload.get("session_id"), "session_id", maximum=128)
        path = normalize_relative_path(payload.get("path")) if action != "status" or payload.get("path") is not None else None
        now = utc_now()
        if action in {"negotiate", "confirm_part"} and self.cas is None:
            raise ValidationError("PROJECT_PACKAGE_CAS_REQUIRED")
        part_data: bytes | None = None
        part_digest: str | None = None
        if action == "confirm_part":
            encoded = payload.get("data_base64")
            if not isinstance(encoded, str) or not encoded or len(encoded) > _MAX_PART_BASE64_CHARS:
                raise ValidationError("PROJECT_PACKAGE_PART_BASE64_INVALID")
            try:
                part_data = base64.b64decode(encoded.encode("ascii"), validate=True)
            except (UnicodeEncodeError, binascii.Error, ValueError) as error:
                raise ValidationError("PROJECT_PACKAGE_PART_BASE64_INVALID") from error
            if base64.b64encode(part_data).decode("ascii") != encoded:
                raise ValidationError("PROJECT_PACKAGE_PART_BASE64_INVALID")
            part_digest = "sha256:" + hashlib.sha256(part_data).hexdigest()
            declared_bytes = _integer(payload.get("byte_count"), "byte_count", maximum=_MAX_PART_BYTES)
            declared_digest = _text(payload.get("part_digest"), "part_digest", maximum=71)
            if len(part_data) != declared_bytes:
                raise ValidationError("PROJECT_PACKAGE_PART_SIZE_MISMATCH")
            if _DIGEST.fullmatch(declared_digest) is None or not hmac.compare_digest(part_digest, declared_digest):
                raise ValidationError("PROJECT_PACKAGE_PART_DIGEST_MISMATCH")
        with self.store.transaction() as connection:
            session = connection.execute("SELECT 1 FROM project_package_sessions WHERE tenant_id=? AND project_id=? AND session_id=?", (*self._scope(context), session_id)).fetchone()
            if session is None:
                raise NotFoundError("PROJECT_PACKAGE_SESSION_NOT_FOUND")
            if action == "negotiate":
                byte_count = _integer(payload.get("byte_count"), "byte_count", maximum=4 * 1024 * 1024 * 1024)
                digest = _text(payload.get("content_digest"), "content_digest", maximum=71)
                if _DIGEST.fullmatch(digest) is None:
                    raise ValidationError("PROJECT_PACKAGE_CONTENT_DIGEST_INVALID")
                part_size = _integer(payload.get("part_size", 1024 * 1024), "part_size", minimum=65536, maximum=16 * 1024 * 1024)
                total = math.ceil(byte_count / part_size) if byte_count else 0
                existing_file = connection.execute(
                    "SELECT byte_count,content_digest,part_size,total_parts FROM project_package_upload_files WHERE tenant_id=? AND project_id=? AND session_id=? AND path=?",
                    (*self._scope(context), session_id, path),
                ).fetchone()
                declaration = (byte_count, digest, part_size, total)
                if existing_file is not None and declaration != (
                    int(existing_file["byte_count"]), str(existing_file["content_digest"]),
                    int(existing_file["part_size"]), int(existing_file["total_parts"]),
                ):
                    raise ConflictError("PROJECT_PACKAGE_UPLOAD_NEGOTIATION_CONFLICT")
                if total == 0:
                    empty_digest = "sha256:" + hashlib.sha256(b"").hexdigest()
                    if not hmac.compare_digest(digest, empty_digest):
                        raise ValidationError("PROJECT_PACKAGE_CONTENT_DIGEST_MISMATCH")
                    assert self.cas is not None
                    self.cas.put_bytes(context.tenant_id, b"", digest)
                connection.execute("INSERT OR IGNORE INTO project_package_upload_files VALUES(?,?,?,?,?,?,?,?,?,?)", (*self._scope(context), session_id, path, byte_count, digest, part_size, total, 0, "NEGOTIATED" if total else "COMPLETE"))
            elif action == "confirm_part":
                part_number = _integer(payload.get("part_number"), "part_number")
                assert part_data is not None and part_digest is not None
                byte_count = len(part_data)
                digest = part_digest
                file_row = connection.execute("SELECT * FROM project_package_upload_files WHERE tenant_id=? AND project_id=? AND session_id=? AND path=?", (*self._scope(context), session_id, path)).fetchone()
                if file_row is None or part_number >= int(file_row["total_parts"]):
                    raise ValidationError("PROJECT_PACKAGE_PART_NOT_NEGOTIATED")
                expected_part_bytes = (
                    int(file_row["part_size"])
                    if part_number < int(file_row["total_parts"]) - 1
                    else int(file_row["byte_count"]) - int(file_row["part_size"]) * (int(file_row["total_parts"]) - 1)
                )
                if byte_count != expected_part_bytes:
                    raise ValidationError("PROJECT_PACKAGE_PART_SIZE_MISMATCH")
                existing = connection.execute("SELECT part_digest,byte_count FROM project_package_upload_parts WHERE tenant_id=? AND project_id=? AND session_id=? AND path=? AND part_number=?", (*self._scope(context), session_id, path, part_number)).fetchone()
                if existing is not None and (existing["part_digest"] != digest or int(existing["byte_count"]) != byte_count):
                    raise ConflictError("PROJECT_PACKAGE_PART_IDEMPOTENCY_CONFLICT")
                assert self.cas is not None
                self.cas.put_bytes(context.tenant_id, part_data, part_digest)
                connection.execute("INSERT OR IGNORE INTO project_package_upload_parts VALUES(?,?,?,?,?,?,?,?)", (*self._scope(context), session_id, path, part_number, byte_count, digest, now))
                confirmed = int(connection.execute("SELECT COUNT(*) FROM project_package_upload_parts WHERE tenant_id=? AND project_id=? AND session_id=? AND path=?", (*self._scope(context), session_id, path)).fetchone()[0])
                connection.execute("UPDATE project_package_upload_files SET confirmed_parts=?,state='PARTIAL' WHERE tenant_id=? AND project_id=? AND session_id=? AND path=?", (confirmed, *self._scope(context), session_id, path))
            elif action != "status":
                raise ValidationError("PROJECT_PACKAGE_UPLOAD_ACTION_INVALID")
        if action == "confirm_part":
            assert path is not None and self.cas is not None
            cas = self.cas
            with self.store.read_transaction() as connection:
                file_row = connection.execute("SELECT * FROM project_package_upload_files WHERE tenant_id=? AND project_id=? AND session_id=? AND path=?", (*self._scope(context), session_id, path)).fetchone()
                part_rows = connection.execute("SELECT part_number,byte_count,part_digest FROM project_package_upload_parts WHERE tenant_id=? AND project_id=? AND session_id=? AND path=? ORDER BY part_number", (*self._scope(context), session_id, path)).fetchall()
            if file_row is not None and len(part_rows) == int(file_row["total_parts"]):
                expected_numbers = list(range(int(file_row["total_parts"])))
                if [int(row["part_number"]) for row in part_rows] != expected_numbers:
                    raise IntegrityError("PROJECT_PACKAGE_PART_SEQUENCE_INVALID")

                def chunks() -> Iterator[bytes]:
                    for row in part_rows:
                        yield cas.read_bytes(
                            context.tenant_id,
                            str(row["part_digest"]),
                            maximum_bytes=_MAX_PART_BYTES,
                            expected_size=int(row["byte_count"]),
                        )

                self.cas.put_stream(
                    context.tenant_id,
                    str(file_row["content_digest"]),
                    int(file_row["byte_count"]),
                    chunks(),
                )
                with self.store.transaction() as connection:
                    current = connection.execute("SELECT COUNT(*) FROM project_package_upload_parts WHERE tenant_id=? AND project_id=? AND session_id=? AND path=?", (*self._scope(context), session_id, path)).fetchone()
                    if current is None or int(current[0]) != int(file_row["total_parts"]):
                        raise ConflictError("PROJECT_PACKAGE_UPLOAD_CHANGED_DURING_FINALIZE")
                    connection.execute("UPDATE project_package_upload_files SET confirmed_parts=?,state='COMPLETE' WHERE tenant_id=? AND project_id=? AND session_id=? AND path=?", (len(part_rows), *self._scope(context), session_id, path))
        with self.store.read_transaction() as connection:
            rows = connection.execute("SELECT * FROM project_package_upload_files WHERE tenant_id=? AND project_id=? AND session_id=? AND (? IS NULL OR path=?) ORDER BY path LIMIT 1001", (*self._scope(context), session_id, path, path)).fetchall()
        files = [{"path": str(row["path"]), "byte_count": int(row["byte_count"]), "content_digest": str(row["content_digest"]), "part_size": int(row["part_size"]), "total_parts": int(row["total_parts"]), "confirmed_parts": int(row["confirmed_parts"]), "state": str(row["state"]), "server_confirmed": True, "final_cas_digest": str(row["content_digest"]) if str(row["state"]) == "COMPLETE" else None} for row in rows]
        complete = bool(files) and all(item["state"] == "COMPLETE" for item in files)
        return {"schema_version": "project-package-upload-status-v1", "session_id": session_id, "state": "COMPLETE" if complete else "PARTIAL", "complete": complete, "files": files[:1000], "truncated": len(files) > 1000}

    def override(self, context: TenantContext, payload: Mapping[str, Any], *, undo: bool) -> dict[str, Any]:
        self.store.require(context, self.store.WRITE)
        version = _integer(payload.get("package_version"), "package_version", minimum=1)
        path = normalize_relative_path(payload.get("path"))
        expected = _integer(payload.get("expected_override_version"), "expected_override_version")
        reason = _text(payload.get("reason"), "reason", maximum=2000)
        now, audit_id = utc_now(), new_id("override")
        with self.store.transaction() as connection:
            row = connection.execute("SELECT * FROM project_package_entries WHERE tenant_id=? AND project_id=? AND package_version=? AND path=?", (*self._scope(context), version, path)).fetchone()
            if row is None:
                raise NotFoundError("PROJECT_PACKAGE_ENTRY_NOT_FOUND")
            if int(row["override_version"]) != expected:
                raise ConflictError("PROJECT_PACKAGE_OVERRIDE_VERSION_CONFLICT")
            prior_role, prior_read = str(row["role"]), bool(row["model_read_allowed"])
            undone_id = None
            if undo:
                undone_id = _text(payload.get("audit_id"), "audit_id", maximum=128)
                audit = connection.execute("SELECT * FROM project_package_override_audit WHERE audit_id=? AND tenant_id=? AND project_id=? AND package_version=? AND path=? AND audit_kind='OVERRIDE'", (undone_id, *self._scope(context), version, path)).fetchone()
                if audit is None or connection.execute("SELECT 1 FROM project_package_override_audit WHERE undone_audit_id=?", (undone_id,)).fetchone() is not None:
                    raise ConflictError("PROJECT_PACKAGE_OVERRIDE_UNDO_INVALID")
                role, model_read = str(audit["prior_role"]), bool(audit["prior_model_read_allowed"])
            else:
                role = str(payload.get("role", prior_role)).upper()
                model_read = payload.get("model_read_allowed", prior_read)
                if role not in {"PRIMARY", "REFERENCE", "IGNORE"} or not isinstance(model_read, bool):
                    raise ValidationError("PROJECT_PACKAGE_OVERRIDE_INVALID")
            if role == "IGNORE":
                model_read = False
            if str(row["security_state"]) != "CLEARED" and model_read:
                raise ValidationError("PROJECT_PACKAGE_SECURITY_ISOLATION_NOT_OVERRIDABLE")
            new_version = expected + 1
            connection.execute("UPDATE project_package_entries SET role=?,model_read_allowed=?,override_version=? WHERE tenant_id=? AND project_id=? AND package_version=? AND path=?", (role, int(model_read), new_version, *self._scope(context), version, path))
            connection.execute("INSERT INTO project_package_override_audit VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (audit_id, *self._scope(context), version, path, "UNDO" if undo else "OVERRIDE", prior_role, int(prior_read), role, int(model_read), expected, new_version, reason, context.actor_id, undone_id, now))
            updated = connection.execute("SELECT * FROM project_package_entries WHERE tenant_id=? AND project_id=? AND package_version=? AND path=?", (*self._scope(context), version, path)).fetchone()
        return {"entry": self._entry_row(updated), "audit_id": audit_id, "audit_kind": "UNDO" if undo else "OVERRIDE"}

    def artifact(self, skill: str, ctx: RuntimeContext, payload: Mapping[str, Any], action: str) -> dict[str, Any]:
        context = TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)
        self.store.require(context, self.store.WRITE if action in {"rebuild", "rollback"} else self.store.READ)
        kind, handler = _ARTIFACT_HANDLERS[skill]
        version = _integer(payload.get("package_version"), "package_version", minimum=1)
        if action == "rebuild":
            source_input = payload.get("source_input")
            if not isinstance(source_input, Mapping):
                raise ValidationError("PROJECT_PACKAGE_ARTIFACT_INPUT_INVALID")
            request = {"schema_version": "1.0", "request_id": ctx.request_id, "tenant_id": ctx.tenant_id, "project_id": ctx.project_id, "actor_id": ctx.actor_id, "inputs": dict(source_input), "idempotency_key": ctx.idempotency_key, "trace_id": ctx.trace_id, "policy": dict(ctx.policy), "capabilities": dict(ctx.capabilities)}
            result = handler(request)
            artifact = result.get("outputs", {})
            if not isinstance(artifact, Mapping):
                raise IntegrityError("PROJECT_PACKAGE_ARTIFACT_RESULT_INVALID")
            _json(artifact, "artifact", maximum=_MAX_ARTIFACT_BYTES)
            state = "ACTIVE" if result.get("state") == "SUCCEEDED" else "PARTIAL"
            if kind == "SYMBOL_INDEX" and any(str(item).lower() not in {"python", "py"} for item in source_input.get("languages", []) if isinstance(item, str)):
                state = "PARTIAL"
            input_digest, artifact_digest, now = canonical_digest({"package_version": version, "source_input": source_input}), canonical_digest(artifact), utc_now()
            with self.store.transaction() as connection:
                package = connection.execute("SELECT manifest_digest FROM project_package_versions WHERE tenant_id=? AND project_id=? AND package_version=?", (*self._scope(context), version)).fetchone()
                if package is None:
                    raise NotFoundError("PROJECT_PACKAGE_VERSION_NOT_FOUND")
                latest = connection.execute("SELECT COALESCE(MAX(artifact_version),0) FROM project_package_artifacts WHERE tenant_id=? AND project_id=? AND package_version=? AND artifact_kind=?", (*self._scope(context), version, kind)).fetchone()[0]
                connection.execute("UPDATE project_package_artifacts SET state='SUPERSEDED' WHERE tenant_id=? AND project_id=? AND package_version=? AND artifact_kind=? AND state='ACTIVE'", (*self._scope(context), version, kind))
                connection.execute("INSERT INTO project_package_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (*self._scope(context), version, kind, int(latest) + 1, "ACTIVE", state, input_digest, artifact_digest, canonical_json(artifact), context.actor_id, now))
            return {"artifact_kind": kind, "artifact_version": int(latest) + 1, "state": state, "package_version": version, "package_manifest_digest": str(package["manifest_digest"]), "artifact_digest": artifact_digest, "artifact": dict(artifact), "repository_content_executed": False}
        if action == "rollback":
            target = _integer(payload.get("artifact_version"), "artifact_version", minimum=1)
            with self.store.transaction() as connection:
                row = connection.execute("SELECT * FROM project_package_artifacts WHERE tenant_id=? AND project_id=? AND package_version=? AND artifact_kind=? AND artifact_version=?", (*self._scope(context), version, kind, target)).fetchone()
                if row is None:
                    raise NotFoundError("PROJECT_PACKAGE_ARTIFACT_NOT_FOUND")
                connection.execute("UPDATE project_package_artifacts SET state='ROLLED_BACK' WHERE tenant_id=? AND project_id=? AND package_version=? AND artifact_kind=? AND state='ACTIVE'", (*self._scope(context), version, kind))
                new_version = int(connection.execute("SELECT COALESCE(MAX(artifact_version),0)+1 FROM project_package_artifacts WHERE tenant_id=? AND project_id=? AND package_version=? AND artifact_kind=?", (*self._scope(context), version, kind)).fetchone()[0])
                connection.execute("INSERT INTO project_package_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (*self._scope(context), version, kind, new_version, "ACTIVE", row["result_state"], row["input_digest"], row["artifact_digest"], row["artifact_json"], context.actor_id, utc_now()))
            action = "status"
        if action != "status":
            raise ValidationError("PROJECT_PACKAGE_ARTIFACT_ACTION_INVALID")
        with self.store.read_transaction() as connection:
            row = connection.execute("SELECT * FROM project_package_artifacts WHERE tenant_id=? AND project_id=? AND package_version=? AND artifact_kind=? AND state='ACTIVE'", (*self._scope(context), version, kind)).fetchone()
        if row is None:
            raise NotFoundError("PROJECT_PACKAGE_ARTIFACT_NOT_FOUND")
        import json
        return {"artifact_kind": kind, "artifact_version": int(row["artifact_version"]), "state": str(row["result_state"]), "package_version": version, "artifact_digest": str(row["artifact_digest"]), "artifact": json.loads(str(row["artifact_json"])), "repository_content_executed": False}


class ProjectPackageLifecycleBridge:
    SKILLS = frozenset({
        "elmos-repository-context-map", "elmos-folder-tree-input",
        "elmos-resumable-multi-file-folder-upload", "elmos-project-package-manifest",
        "elmos-project-root-language-framework-detection",
        "elmos-ignore-generated-vendored-file-classification",
        "elmos-repository-map-and-symbol-indexing",
        "elmos-project-package-version-and-incremental-update",
        "elmos-project-package-preview-and-review-ui",
    })

    def __init__(self, store: IntakeStore, cas: LocalCasStore | None = None) -> None:
        self.lifecycle = ProjectPackageLifecycle(store, cas)

    @staticmethod
    def _envelope(state: str, code: str, outputs: Mapping[str, Any]) -> dict[str, Any]:
        return {"state": state, "code": code, "outputs": dict(outputs), "metrics": {}, "retryable": False}

    def handle(self, skill_name: str, ctx: RuntimeContext, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if skill_name not in self.SKILLS:
            raise ValidationError("PROJECT_PACKAGE_SKILL_INVALID")
        action = str(payload.get("lifecycle_action") or payload.get("operation") or "").lower()
        context = TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)
        if skill_name == "elmos-folder-tree-input":
            if action == "begin":
                output = self.lifecycle.begin(context, payload)
            elif action == "append":
                output = self.lifecycle.append(context, payload)
            elif action == "finalize":
                output = self.lifecycle.finalize(
                    context,
                    _text(payload.get("session_id"), "session_id", maximum=128),
                )
            elif action == "status":
                output = self.lifecycle.status(
                    context,
                    _text(payload.get("session_id"), "session_id", maximum=128),
                )
            elif action == "page":
                output = self.lifecycle.page(context, payload)
            else:
                raise ValidationError("PROJECT_PACKAGE_LIFECYCLE_ACTION_INVALID")
        elif skill_name == "elmos-resumable-multi-file-folder-upload":
            output = self.lifecycle.upload(context, action, payload)
        elif skill_name == "elmos-project-package-manifest":
            if action == "finalize":
                output = self.lifecycle.finalize(
                    context,
                    _text(payload.get("session_id"), "session_id", maximum=128),
                )
            elif action == "page":
                output = self.lifecycle.page(context, payload)
            elif action == "diff":
                output = self.lifecycle.diff(
                    context,
                    _integer(payload.get("old_version"), "old_version", minimum=1),
                    _integer(payload.get("new_version"), "new_version", minimum=1),
                )
            else:
                raise ValidationError("PROJECT_PACKAGE_LIFECYCLE_ACTION_INVALID")
        elif skill_name == "elmos-project-package-version-and-incremental-update":
            if action != "diff":
                raise ValidationError("PROJECT_PACKAGE_EXACT_DIFF_REQUIRED")
            output = self.lifecycle.diff(
                context,
                _integer(payload.get("old_version"), "old_version", minimum=1),
                _integer(payload.get("new_version"), "new_version", minimum=1),
            )
        elif skill_name == "elmos-project-package-preview-and-review-ui":
            if action == "page":
                output = self.lifecycle.page(context, payload)
            elif action == "override":
                output = self.lifecycle.override(context, payload, undo=False)
            elif action == "undo":
                output = self.lifecycle.override(context, payload, undo=True)
            else:
                raise ValidationError("PROJECT_PACKAGE_PREVIEW_ACTION_INVALID")
        else:
            output = self.lifecycle.artifact(skill_name, ctx, payload, action)
        state = str(output.get("state", "SUCCEEDED"))
        public_state = "PARTIAL" if state == "PARTIAL" or output.get("complete") is False else "SUCCEEDED"
        return self._envelope(public_state, "PROJECT_PACKAGE_LIFECYCLE_" + action.upper(), output)


__all__ = ["ProjectPackageLifecycle", "ProjectPackageLifecycleBridge"]
