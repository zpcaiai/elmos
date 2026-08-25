"""Independent durable projections for requirement, fusion, and conflict Skills."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .canonical import canonical_digest, canonical_json, new_id, sha256_bytes, utc_now
from .content import (
    _with_authoritative_asset_bindings,
    build_source_provenance,
    detect_version_conflicts,
    extract_requirements,
    fuse_assets,
    normalize_content_ir,
)
from .errors import ConflictError, IntegrityError, NotFoundError, ValidationError
from .models import TenantContext

if TYPE_CHECKING:
    from .skill_runtime import RuntimeContext
    from .store import IntakeStore, LocalCasStore


CONTENT_PROJECTION_SKILLS = frozenset(
    {
        "elmos-unified-multimodal-content-ir",
        "elmos-source-anchor-and-provenance",
        "elmos-multimodal-requirement-extraction",
        "elmos-multi-asset-content-fusion",
        "elmos-document-version-and-conflict-detection",
    }
)

_SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS projection_versions (
 tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, projection_id TEXT NOT NULL,
 projection_key TEXT NOT NULL, kind TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0),
 actor_id TEXT NOT NULL, request_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 package_version TEXT NOT NULL, request_digest TEXT NOT NULL,
 source_binding_json TEXT NOT NULL, source_binding_digest TEXT NOT NULL,
 output_json TEXT NOT NULL, output_digest TEXT NOT NULL,
 review_state TEXT NOT NULL CHECK(review_state IN ('ACCEPTED','NEEDS_REVIEW')),
 human_review_link TEXT, created_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,project_id,projection_id),
 UNIQUE(tenant_id,project_id,kind,projection_key,version),
 UNIQUE(tenant_id,project_id,idempotency_key),
 CHECK(length(request_digest)=64), CHECK(length(source_binding_digest)=64),
 CHECK(length(output_digest)=64)
);
CREATE TABLE IF NOT EXISTS projection_heads (
 tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, kind TEXT NOT NULL,
 projection_key TEXT NOT NULL, projection_id TEXT NOT NULL, version INTEGER NOT NULL,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,project_id,kind,projection_key),
 FOREIGN KEY(tenant_id,project_id,projection_id)
   REFERENCES projection_versions(tenant_id,project_id,projection_id)
);
CREATE TABLE IF NOT EXISTS projection_outbox (
 tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, event_id TEXT NOT NULL,
 projection_id TEXT NOT NULL, event_type TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('PENDING','CLAIMED','DELIVERED','UNKNOWN')),
 claim_token_digest TEXT, attempt INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,project_id,event_id),
 UNIQUE(tenant_id,project_id,idempotency_key),
 CHECK(length(payload_digest)=64)
);
CREATE TRIGGER IF NOT EXISTS projection_versions_no_update BEFORE UPDATE ON projection_versions
BEGIN SELECT RAISE(ABORT,'projection versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS projection_versions_no_delete BEFORE DELETE ON projection_versions
BEGIN SELECT RAISE(ABORT,'projection versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS projection_outbox_binding_guard BEFORE UPDATE ON projection_outbox
WHEN OLD.tenant_id != NEW.tenant_id OR OLD.project_id != NEW.project_id
 OR OLD.event_id != NEW.event_id OR OLD.projection_id != NEW.projection_id
 OR OLD.event_type != NEW.event_type OR OLD.idempotency_key != NEW.idempotency_key
 OR OLD.payload_json != NEW.payload_json OR OLD.payload_digest != NEW.payload_digest
 OR OLD.created_at != NEW.created_at
BEGIN SELECT RAISE(ABORT,'projection outbox binding is immutable'); END;
COMMIT;
"""


def _required(value: Any, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ValidationError("CONTENT_PROJECTION_FIELD_INVALID", f"{field} is required")
    return value


def _digest_text(value: str) -> str:
    return "sha256:" + sha256_bytes(value.encode("utf-8"))


def _contains_authority(value: Any) -> bool:
    forbidden = {"approval", "approved", "approval_state", "verified", "verification", "resolution", "resolution_decision", "automatic_resolution_applied"}
    if isinstance(value, Mapping):
        return bool(forbidden & {str(key).lower() for key in value}) or any(
            _contains_authority(item) for item in value.values()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_authority(item) for item in value)
    return False


class ContentProjectionStore:
    """Content-minimized SQLite ledger with scoped immutable projection versions."""

    def __init__(self, path: str | Path) -> None:
        self.path = self._secure_database(Path(path).expanduser())
        self._lock = threading.RLock()
        self._closed = False
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.path,
                timeout=5,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            journal_mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
            if journal_mode != "wal":
                raise IntegrityError("CONTENT_PROJECTION_WAL_REQUIRED")
            connection.execute("PRAGMA wal_autocheckpoint=1000")
            connection.execute("PRAGMA synchronous=FULL")
            self._connection = connection
            self._connection.executescript(_SCHEMA)
            self._validate_schema()
            self._validate_database_file(self.path)
        except Exception:
            if connection is not None:
                connection.close()
            raise

    @staticmethod
    def _secure_directory(path: Path) -> Path:
        if not path.is_absolute() or path == Path(path.anchor):
            raise ValidationError("CONTENT_PROJECTION_STORAGE_PATH_INVALID")
        existed = path.exists() or path.is_symlink()
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not existed:
                path.chmod(0o700)
            metadata = path.lstat()
        except OSError as error:
            raise ValidationError("CONTENT_PROJECTION_STORAGE_PATH_INVALID") from error
        wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode) or wrong_owner or metadata.st_mode & 0o077:
            raise ValidationError("CONTENT_PROJECTION_STORAGE_PERMISSIONS_INVALID")
        return path

    @staticmethod
    def _validate_database_file(path: Path) -> None:
        try:
            metadata = path.lstat()
        except OSError as error:
            raise ValidationError("CONTENT_PROJECTION_DATABASE_INVALID") from error
        wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ValidationError("CONTENT_PROJECTION_DATABASE_INVALID")
        if wrong_owner or metadata.st_mode & 0o077:
            raise ValidationError("CONTENT_PROJECTION_DATABASE_PERMISSIONS_INVALID")

    @classmethod
    def _secure_database(cls, path: Path) -> Path:
        if not path.is_absolute() or path == Path(path.anchor) or path.is_symlink():
            raise ValidationError("CONTENT_PROJECTION_DATABASE_INVALID")
        cls._secure_directory(path.parent)
        if not path.exists():
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags, 0o600)
            except OSError as error:
                raise ValidationError("CONTENT_PROJECTION_DATABASE_INVALID") from error
            else:
                os.close(descriptor)
        cls._validate_database_file(path)
        return path

    def _validate_schema(self) -> None:
        expected = {
            "projection_versions": ("tenant_id","project_id","projection_id","projection_key","kind","version","actor_id","request_id","idempotency_key","package_version","request_digest","source_binding_json","source_binding_digest","output_json","output_digest","review_state","human_review_link","created_at"),
            "projection_heads": ("tenant_id","project_id","kind","projection_key","projection_id","version","updated_at"),
            "projection_outbox": ("tenant_id","project_id","event_id","projection_id","event_type","idempotency_key","payload_json","payload_digest","state","claim_token_digest","attempt","created_at","updated_at"),
        }
        for table, columns in expected.items():
            actual = tuple(str(row["name"]) for row in self._connection.execute(f"PRAGMA table_info({table})"))
            if actual != columns:
                raise IntegrityError("CONTENT_PROJECTION_SCHEMA_INVALID")

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    @staticmethod
    def _scope(context: TenantContext) -> tuple[str, str]:
        return context.tenant_id, context.project_id

    def persist(
        self,
        context: TenantContext,
        *,
        kind: str,
        projection_key: str,
        request_id: str,
        idempotency_key: str,
        package_version: str,
        request_digest: str,
        source_bindings: list[dict[str, Any]],
        output: Mapping[str, Any],
        review_state: str,
        human_review_link: str | None,
    ) -> tuple[dict[str, Any], bool]:
        binding_digest = canonical_digest(source_bindings)
        output_digest = canonical_digest(output)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT * FROM projection_versions WHERE tenant_id=? AND project_id=? AND idempotency_key=?",
                    (*self._scope(context), idempotency_key),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["kind"] != kind
                        or existing["projection_key"] != projection_key
                        or existing["request_digest"] != request_digest
                        or existing["source_binding_digest"] != binding_digest
                        or existing["output_digest"] != output_digest
                    ):
                        raise ConflictError("CONTENT_PROJECTION_IDEMPOTENCY_CONFLICT")
                    materialized = self._materialize(existing)
                    self._connection.execute("COMMIT")
                    return materialized, True
                head = self._connection.execute(
                    "SELECT version FROM projection_heads WHERE tenant_id=? AND project_id=? AND kind=? AND projection_key=?",
                    (*self._scope(context), kind, projection_key),
                ).fetchone()
                version = int(head["version"]) + 1 if head else 1
                projection_id = new_id("projection")
                now = utc_now()
                self._connection.execute(
                    "INSERT INTO projection_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*self._scope(context), projection_id, projection_key, kind, version, context.actor_id, request_id, idempotency_key, package_version, request_digest, canonical_json(source_bindings), binding_digest, canonical_json(output), output_digest, review_state, human_review_link, now),
                )
                self._connection.execute(
                    """INSERT INTO projection_heads VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(tenant_id,project_id,kind,projection_key) DO UPDATE SET
                         projection_id=excluded.projection_id,version=excluded.version,updated_at=excluded.updated_at""",
                    (*self._scope(context), kind, projection_key, projection_id, version, now),
                )
                event = {"projection_id": projection_id, "kind": kind, "version": version, "output_digest": output_digest, "review_state": review_state}
                self._connection.execute(
                    "INSERT INTO projection_outbox VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*self._scope(context), new_id("projection-event"), projection_id, f"content_projection.{kind.lower()}.versioned", f"projection:{idempotency_key}", canonical_json(event), canonical_digest(event), "PENDING", None, 0, now, now),
                )
                row = self._connection.execute(
                    "SELECT * FROM projection_versions WHERE tenant_id=? AND project_id=? AND projection_id=?",
                    (*self._scope(context), projection_id),
                ).fetchone()
                self._connection.execute("COMMIT")
                return self._materialize(row), False
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _materialize(row: sqlite3.Row) -> dict[str, Any]:
        source_json = str(row["source_binding_json"])
        output_json = str(row["output_json"])
        sources = json.loads(source_json)
        output = json.loads(output_json)
        if canonical_digest(sources) != row["source_binding_digest"] or canonical_digest(output) != row["output_digest"]:
            raise IntegrityError("CONTENT_PROJECTION_TAMPERED")
        return {**dict(row), "source_bindings": sources, "output": output}

    def get(self, context: TenantContext, projection_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM projection_versions WHERE tenant_id=? AND project_id=? AND projection_id=?",
                (*self._scope(context), projection_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("CONTENT_PROJECTION_NOT_FOUND")
        return self._materialize(row)

    def history(self, context: TenantContext, *, kind: str, projection_key: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM projection_versions WHERE tenant_id=? AND project_id=?
                     AND kind=? AND projection_key=? ORDER BY version DESC""",
                (*self._scope(context), kind, projection_key),
            ).fetchall()
        return [self._materialize(row) for row in rows]

    def claim_outbox(self, context: TenantContext, *, worker_token: str) -> dict[str, Any] | None:
        token_digest = canonical_digest({"worker_token": _required(worker_token, "worker_token")})
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """SELECT * FROM projection_outbox WHERE tenant_id=? AND project_id=?
                         AND state IN ('PENDING','UNKNOWN') ORDER BY created_at,event_id LIMIT 1""",
                    self._scope(context),
                ).fetchone()
                if row is None:
                    self._connection.execute("COMMIT")
                    return None
                self._connection.execute(
                    """UPDATE projection_outbox SET state='CLAIMED',claim_token_digest=?,attempt=attempt+1,updated_at=?
                       WHERE tenant_id=? AND project_id=? AND event_id=?""",
                    (token_digest, utc_now(), *self._scope(context), row["event_id"]),
                )
                claimed = self._connection.execute(
                    "SELECT * FROM projection_outbox WHERE tenant_id=? AND project_id=? AND event_id=?",
                    (*self._scope(context), row["event_id"]),
                ).fetchone()
                self._connection.execute("COMMIT")
                return dict(claimed)
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def finish_outbox(self, context: TenantContext, *, event_id: str, worker_token: str, outcome: str) -> None:
        state = outcome.upper()
        if state not in {"DELIVERED", "UNKNOWN"}:
            raise ValidationError("CONTENT_PROJECTION_OUTBOX_OUTCOME_INVALID")
        token_digest = canonical_digest({"worker_token": _required(worker_token, "worker_token")})
        with self._lock:
            updated = self._connection.execute(
                """UPDATE projection_outbox SET state=?,claim_token_digest=NULL,updated_at=?
                   WHERE tenant_id=? AND project_id=? AND event_id=? AND state='CLAIMED' AND claim_token_digest=?""",
                (state, utc_now(), *self._scope(context), event_id, token_digest),
            ).rowcount
        if updated != 1:
            raise ConflictError("CONTENT_PROJECTION_OUTBOX_CLAIM_LOST")


class ContentProjectionBridge:
    """Bind content operations to trusted assets and persist durable projections."""

    _AUTHORITATIVE_FUNCTIONS = {
        "elmos-unified-multimodal-content-ir": normalize_content_ir,
        "elmos-source-anchor-and-provenance": build_source_provenance,
    }
    _COMMITTED_ASSET_STATES = frozenset(
        {"UPLOADED", "PROCESSING", "READY", "NEEDS_REVIEW"}
    )

    _FUNCTIONS = {
        "elmos-multimodal-requirement-extraction": ("REQUIREMENT", extract_requirements),
        "elmos-multi-asset-content-fusion": ("FUSION", fuse_assets),
        "elmos-document-version-and-conflict-detection": ("CONFLICT", detect_version_conflicts),
    }

    def __init__(
        self,
        store: ContentProjectionStore,
        intake_store: "IntakeStore | None" = None,
        cas: "LocalCasStore | None" = None,
    ) -> None:
        self.store = store
        self.intake_store = intake_store
        self.cas = cas

    @staticmethod
    def _context(ctx: "RuntimeContext") -> TenantContext:
        return TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)

    @staticmethod
    def _request(ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "actor_id": ctx.actor_id,
            "request_id": ctx.request_id,
            "inputs": dict(payload),
            "policy": dict(ctx.policy),
            "capabilities": dict(ctx.capabilities),
        }

    @staticmethod
    def _result_envelope(result: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "state": str(result.get("state", "PARTIAL")),
            "code": str(result.get("code", "CONTENT_AUTHORITY_REQUIRED")),
            "outputs": dict(result.get("outputs", {})),
            "metrics": dict(result.get("metrics", {})),
            "retryable": False,
        }

    @staticmethod
    def _normalized_anchors(
        skill_name: str,
        result: Mapping[str, Any],
    ) -> list[Mapping[str, Any]]:
        outputs = result.get("outputs", {})
        if not isinstance(outputs, Mapping):
            raise IntegrityError("CONTENT_AUTHORITY_RESULT_INVALID")
        if skill_name == "elmos-source-anchor-and-provenance":
            source_anchors = outputs.get("anchors", [])
            if not isinstance(source_anchors, list):
                raise IntegrityError("CONTENT_AUTHORITY_RESULT_INVALID")
            return [anchor for anchor in source_anchors if isinstance(anchor, Mapping)]
        blocks = outputs.get("blocks", [])
        if not isinstance(blocks, list):
            raise IntegrityError("CONTENT_AUTHORITY_RESULT_INVALID")
        block_anchors: list[Mapping[str, Any]] = []
        for block in blocks:
            if not isinstance(block, Mapping):
                raise IntegrityError("CONTENT_AUTHORITY_RESULT_INVALID")
            raw_anchors = block.get("anchors")
            if not isinstance(raw_anchors, list):
                raise IntegrityError("CONTENT_AUTHORITY_RESULT_INVALID")
            for anchor in raw_anchors:
                if isinstance(anchor, Mapping):
                    block_anchors.append(anchor)
        return block_anchors

    def _handle_authoritative(
        self,
        skill_name: str,
        ctx: "RuntimeContext",
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        function = self._AUTHORITATIVE_FUNCTIONS[skill_name]
        request = self._request(ctx, payload)
        preliminary = function(request)
        if preliminary.get("state") == "BLOCKED" or self.intake_store is None:
            return self._result_envelope(preliminary)

        bindings: set[tuple[str, int, str]] = set()
        context = self._context(ctx)
        for anchor in self._normalized_anchors(skill_name, preliminary):
            asset_id = str(anchor["asset_id"])
            try:
                asset = self.intake_store.get_asset(context, asset_id)
            except NotFoundError:
                # Do not disclose whether the supplied identifier exists in a
                # different tenant/project.  An unresolvable anchor stays unbound.
                continue
            if (
                asset.sha256 is not None
                and asset.cas_digest is not None
                and asset.sha256 != asset.cas_digest
            ):
                raise IntegrityError("SOURCE_ANCHOR_ASSET_DIGEST_INCONSISTENT")
            if (
                asset.status.value in self._COMMITTED_ASSET_STATES
                and asset.sha256 is not None
                and asset.cas_digest == asset.sha256
                and asset.version == anchor["asset_version"]
                and "sha256:" + asset.sha256 == anchor["asset_digest"]
            ):
                if self.cas is None:
                    continue
                try:
                    measured_size = sum(
                        len(chunk)
                        for chunk in self.cas.iter_bytes(
                            context.tenant_id,
                            asset.sha256,
                        )
                    )
                except NotFoundError:
                    # Missing tenant-private bytes are indistinguishable from an
                    # unresolved asset to an untrusted caller and cannot confer
                    # source authority.
                    continue
                if measured_size != asset.byte_size:
                    # The CAS digest is valid but its trusted metadata binding
                    # is corrupt.  Do not quarantine valid shared CAS bytes on
                    # the strength of inconsistent database metadata.
                    raise IntegrityError("SOURCE_ANCHOR_ASSET_SIZE_INCONSISTENT")
                bindings.add((asset.asset_id, asset.version, "sha256:" + asset.sha256))

        authoritative_request = _with_authoritative_asset_bindings(request, bindings)
        return self._result_envelope(function(authoritative_request))

    @staticmethod
    def _host_package(ctx: "RuntimeContext", payload: Mapping[str, Any]) -> tuple[str, dict[str, Mapping[str, Any]]]:
        package = ctx.capabilities.get("content_projection_package")
        package_version = payload.get("package_version")
        if (
            not isinstance(package, Mapping)
            or package.get("verified") is not True
            or package.get("tenant_id") != ctx.tenant_id
            or package.get("project_id") != ctx.project_id
            or package.get("package_version") != package_version
        ):
            raise ValidationError("CONTENT_PROJECTION_PACKAGE_UNTRUSTED")
        sources = package.get("sources")
        if not isinstance(sources, list):
            raise ValidationError("CONTENT_PROJECTION_PACKAGE_UNTRUSTED")
        binding = {"tenant_id": ctx.tenant_id, "project_id": ctx.project_id, "package_version": package_version, "sources": sources}
        if str(package.get("registry_digest", "")).removeprefix("sha256:") != canonical_digest(binding):
            raise IntegrityError("CONTENT_PROJECTION_PACKAGE_DIGEST_MISMATCH")
        index: dict[str, Mapping[str, Any]] = {}
        for source in sources:
            if not isinstance(source, Mapping):
                raise ValidationError("CONTENT_PROJECTION_SOURCE_BINDING_INVALID")
            source_id = _required(source.get("source_id"), "source_id")
            if source_id in index:
                raise ValidationError("CONTENT_PROJECTION_SOURCE_BINDING_DUPLICATE")
            index[source_id] = source
        return str(package_version), index

    @staticmethod
    def _bindings(skill: str, payload: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        if skill.endswith("requirement-extraction"):
            items, id_field = payload.get("sources", []), "source_id"
        elif skill.endswith("content-fusion"):
            items, id_field = payload.get("assets", []), "asset_id"
        else:
            items, id_field = payload.get("claims", []), "claim_id"
        if not isinstance(items, list) or not items:
            raise ValidationError("CONTENT_PROJECTION_INPUT_EMPTY")
        result: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise ValidationError("CONTENT_PROJECTION_INPUT_INVALID")
            source_id = _required(item.get(id_field) or (f"claim_{index + 1:06d}" if id_field == "claim_id" else None), id_field)
            trusted = registry.get(source_id)
            if trusted is None:
                raise ValidationError("CONTENT_PROJECTION_SOURCE_UNBOUND")
            if skill.endswith("requirement-extraction"):
                content_digest = _digest_text(_required(item.get("text"), "source.text", 1_000_000))
                anchor = item.get("anchor")
                version = anchor.get("asset_version", 1) if isinstance(anchor, Mapping) else None
            elif skill.endswith("content-fusion"):
                content_digest = str(item.get("content_digest", ""))
                anchor = {"anchor_ids": item.get("anchor_ids", [])}
                version = item.get("version", 1)
            else:
                content_digest = "sha256:" + canonical_digest({"subject": item.get("subject"), "value": item.get("value")})
                anchor = item.get("anchor")
                version = item.get("version", 1)
            provenance_digest = "sha256:" + canonical_digest(anchor)
            required_binding = {
                "source_id": source_id,
                "content_digest": content_digest,
                "provenance_digest": provenance_digest,
                "version": version,
            }
            if any(trusted.get(key) != value for key, value in required_binding.items()):
                raise IntegrityError("CONTENT_PROJECTION_SOURCE_BINDING_MISMATCH")
            result.append(required_binding)
        return sorted(result, key=lambda item: item["source_id"])

    def handle(self, skill_name: str, ctx: "RuntimeContext", payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if skill_name in self._AUTHORITATIVE_FUNCTIONS:
            return self._handle_authoritative(skill_name, ctx, payload)
        if skill_name not in self._FUNCTIONS:
            raise ValidationError("CONTENT_PROJECTION_SKILL_UNSUPPORTED")
        if _contains_authority(payload):
            return {"state": "BLOCKED", "code": "CONTENT_PROJECTION_AUTHORITY_INPUT_UNTRUSTED", "outputs": {"review_state": "NEEDS_REVIEW"}, "metrics": {}, "retryable": False}
        kind, function = self._FUNCTIONS[skill_name]
        package_version, registry = self._host_package(ctx, payload)
        bindings = self._bindings(skill_name, payload, registry)
        request = self._request(ctx, payload)
        result = function(request)
        if result.get("state") == "BLOCKED":
            return {"state": "BLOCKED", "code": str(result.get("code")), "outputs": dict(result.get("outputs", {})), "metrics": dict(result.get("metrics", {})), "retryable": False}
        output = dict(result.get("outputs", {}))
        low_confidence = any(
            isinstance(item, Mapping) and float(item.get("confidence", 1.0)) < float(ctx.policy.get("content_projection_min_confidence", 0.8))
            for key in ("requirements", "groups", "conflicts") for item in output.get(key, [])
        )
        critical_conflict = kind == "CONFLICT" and bool(output.get("conflicts"))
        needs_review = result.get("state") == "PARTIAL" or low_confidence or critical_conflict
        review_link = None
        review_links = ctx.capabilities.get("human_review_links")
        projection_key = _required(payload.get("projection_key", payload.get("task_id", ctx.request_id)), "projection_key")
        if isinstance(review_links, Mapping) and review_links.get("tenant_id") == ctx.tenant_id and review_links.get("project_id") == ctx.project_id:
            link = review_links.get("links", {}).get(projection_key) if isinstance(review_links.get("links"), Mapping) else None
            review_link = str(link) if isinstance(link, str) and link else None
        review_state = "NEEDS_REVIEW" if needs_review else "ACCEPTED"
        if review_state == "NEEDS_REVIEW":
            output["review_state"] = "NEEDS_REVIEW"
            output["human_review_link"] = review_link
        request_digest = canonical_digest({"skill": skill_name, "payload": payload, "package_version": package_version})
        record, replay = self.store.persist(
            self._context(ctx), kind=kind, projection_key=projection_key,
            request_id=ctx.request_id, idempotency_key=_required(ctx.idempotency_key, "idempotency_key"),
            package_version=package_version, request_digest=request_digest,
            source_bindings=bindings, output=output, review_state=review_state,
            human_review_link=review_link,
        )
        output.update({"projection_id": record["projection_id"], "projection_version": record["version"], "package_version": package_version, "source_binding_digest": record["source_binding_digest"], "idempotent_replay": replay, "outbox_state": "PENDING"})
        return {"state": "PARTIAL" if needs_review else str(result.get("state", "SUCCEEDED")), "code": str(result.get("code")), "outputs": output, "metrics": dict(result.get("metrics", {})), "retryable": False}
