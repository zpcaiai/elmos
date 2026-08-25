"""Cache control-plane HTTP API.

Implements the operations declared in ``openapi/cache-control-plane.openapi.yaml``
on the standard library, so the control plane has no framework dependency and
contract tests can run against an in-memory adapter and a real server alike.

Cross-cutting rules, enforced here rather than per handler:

* every mutating operation requires an ``Idempotency-Key``; a replay with the
  same request body returns the original response instead of acting twice, and
  a replay with a *different* body is a conflict, not a silent overwrite;
* blob uploads are digest-addressed and reject mismatched content;
* run and workspace mutations require an expected version and/or lease epoch;
* destructive GC and purge operations are dry-run by default and emit an
  auditable plan.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .action_cache import ActionCache, CommitRequest, LookupRequest
from .canonical import digest_of, require_digest
from .cas import ContentAddressableStore
from .checkpoint import CheckpointService
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .enums import CacheMode, RunStatus, TrustNamespace, ValidationLevel
from .errors import (
    ElmosCacheError,
    IdempotencyConflict,
    NotFound,
    Unsupported,
)
from .gc import GarbageCollector
from .manifests import ActionResultManifest, ExecutionMetrics
from .publish import TreePublisher
from .staging import Workspace

SCHEMA_VERSION = "1.0.0"
API_VERSION = "v1"
MAX_PAGE_SIZE = 500


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    body: dict[str, Any] | bytes | None = None
    headers: Mapping[str, str] = ()  # type: ignore[assignment]
    query: Mapping[str, str] = ()  # type: ignore[assignment]

    def header(self, name: str) -> str | None:
        for key, value in dict(self.headers).items():
            if key.lower() == name.lower():
                return value
        return None

    def param(self, name: str, default: str | None = None) -> str | None:
        return dict(self.query).get(name, default)

    def json(self) -> dict[str, Any]:
        if isinstance(self.body, dict):
            return self.body
        if isinstance(self.body, bytes):
            loaded = json.loads(self.body.decode("utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        return {}


@dataclass(frozen=True)
class Response:
    status: int
    body: dict[str, Any] | bytes
    headers: dict[str, str] = None  # type: ignore[assignment]

    def with_headers(self, **extra: str) -> Response:
        merged = dict(self.headers or {})
        merged.update(extra)
        return Response(self.status, self.body, merged)

    def json(self) -> dict[str, Any]:
        if isinstance(self.body, dict):
            return self.body
        raise Unsupported("response body is not JSON")


Handler = Callable[[Request, dict[str, str]], Response]

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CacheControlPlane:
    """Routing, idempotency, pagination and error mapping."""

    def __init__(
        self,
        store: MetadataStore,
        cas: ContentAddressableStore,
        tenant_id: str,
        action_cache: ActionCache | None = None,
        workspaces: Mapping[str, Workspace] | None = None,
        publishers: Mapping[str, TreePublisher] | None = None,
        checkpoints: Mapping[str, CheckpointService] | None = None,
        clock: Clock = SYSTEM_CLOCK,
        trust_namespace: TrustNamespace = TrustNamespace.BRANCH,
    ) -> None:
        self.store = store
        self.cas = cas
        self.tenant_id = tenant_id
        self.action_cache = action_cache or ActionCache(store, cas, clock)
        self.workspaces = dict(workspaces or {})
        self.publishers = dict(publishers or {})
        self.checkpoints = dict(checkpoints or {})
        self.clock = clock
        self.trust_namespace = trust_namespace
        self._routes: list[tuple[str, re.Pattern[str], Handler]] = []
        self._register_routes()

    # -- routing ----------------------------------------------------------
    def route(self, method: str, template: str, handler: Handler) -> None:
        pattern = re.compile(
            "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", template) + "$"
        )
        self._routes.append((method.upper(), pattern, handler))

    def _register_routes(self) -> None:
        self.route("GET", "/cache/actions/{actionKey}", self.lookup_action)
        self.route("PUT", "/cache/actions/{actionKey}", self.commit_action)
        self.route("HEAD", "/blobs/{digest}", self.blob_exists)
        self.route("GET", "/blobs/{digest}", self.get_blob)
        self.route("PUT", "/blobs/{digest}", self.put_blob)
        self.route("POST", "/runs", self.create_run)
        self.route("GET", "/runs", self.list_runs)
        self.route("GET", "/runs/{runId}", self.get_run)
        self.route("POST", "/runs/{runId}/resume", self.resume_run)
        self.route("POST", "/runs/{runId}/staged-files", self.reserve_staged_file)
        self.route("POST", "/runs/{runId}/staged-files/{stagedFileId}/start", self.start_staged_write)
        self.route("POST", "/runs/{runId}/staged-files/{stagedFileId}/seal", self.seal_staged_file)
        self.route("POST", "/runs/{runId}/staged-files/{stagedFileId}/promote", self.promote_staged_file)
        self.route("GET", "/runs/{runId}/staged-files", self.list_staged_files)
        self.route("POST", "/runs/{runId}/checkpoints", self.commit_checkpoint)
        self.route("GET", "/runs/{runId}/checkpoints", self.list_checkpoints)
        self.route("POST", "/runs/{runId}/publish", self.publish_tree)
        self.route("POST", "/gc/plans", self.create_gc_plan)
        self.route("POST", "/gc/plans/{planId}/apply", self.apply_gc_plan)
        self.route("GET", "/status", self.status)

    def handle(self, request: Request) -> Response:
        """Dispatch with idempotency replay and structured error mapping."""
        idempotency_key = request.header("Idempotency-Key")
        if request.method.upper() in MUTATING_METHODS:
            if not idempotency_key:
                return _error(
                    400,
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "mutating operations require an Idempotency-Key header",
                )
            replay = self._replay(request, idempotency_key)
            if replay is not None:
                return replay

        for method, pattern, handler in self._routes:
            if method != request.method.upper():
                continue
            match = pattern.match(request.path)
            if match is None:
                continue
            try:
                response = handler(request, match.groupdict())
            except ElmosCacheError as exc:
                return _error(exc.http_status, exc.code, exc.message, exc.details)
            except Exception as exc:  # noqa: BLE001 - never leak a traceback
                return _error(500, "INTERNAL", type(exc).__name__)
            if request.method.upper() in MUTATING_METHODS and idempotency_key and response.status < 400:
                self._remember(request, idempotency_key, response)
            return response.with_headers(**{"X-Elmos-Api-Version": API_VERSION})
        return _error(404, "NOT_FOUND", f"no route for {request.method} {request.path}")

    def _idempotency_operation(self, request: Request) -> str:
        return f"{request.method.upper()} {request.path}"

    def _replay(self, request: Request, key: str) -> Response | None:
        payload = _request_payload(request)
        try:
            stored = self.store.replay_idempotent(
                self.tenant_id, key, self._idempotency_operation(request), payload
            )
        except IdempotencyConflict as exc:
            return _error(exc.http_status, exc.code, exc.message, exc.details)
        if stored is None:
            return None
        return Response(
            int(stored.get("status", 200)),
            stored.get("body", {}),
            {"Idempotent-Replay": "true"},
        )

    def _remember(self, request: Request, key: str, response: Response) -> None:
        payload = _request_payload(request)
        body = response.body if isinstance(response.body, dict) else {"binary": True}
        self.store.remember_idempotent(
            self.tenant_id,
            key,
            self._idempotency_operation(request),
            payload,
            {"status": response.status, "body": body},
        )

    # -- action cache -----------------------------------------------------
    def lookup_action(self, request: Request, params: dict[str, str]) -> Response:
        action_key = _normalize_digest(params["actionKey"])
        minimum = ValidationLevel(request.param("minimumValidation", "TEST_VERIFIED") or "TEST_VERIFIED")
        result = self.action_cache.lookup(
            LookupRequest(
                tenant_id=self.tenant_id,
                action_key=action_key,
                trust_namespace=TrustNamespace(
                    request.param("trustNamespace", str(self.trust_namespace)) or "branch"
                ),
                minimum_validation=minimum,
                mode=CacheMode(request.param("mode", "read-write") or "read-write"),
            )
        )
        if not result.hit:
            return Response(
                404,
                {
                    "hit": False,
                    "miss_reasons": [str(reason) for reason in result.reasons],
                    "detail": result.detail,
                },
            )
        return Response(
            200,
            {
                "hit": True,
                "action_key": action_key,
                "result_manifest_digest": result.result_digest,
                "result": result.result,
                "validation_level": str(result.entry.validation_level) if result.entry else None,
            },
        )

    def commit_action(self, request: Request, params: dict[str, str]) -> Response:
        action_key = _normalize_digest(params["actionKey"])
        payload = request.json()
        metrics = payload.get("metrics", {})
        manifest = ActionResultManifest(
            action_key=action_key,
            stage_id=payload["stage_id"],
            stage_version=payload["stage_version"],
            output_artifacts=tuple(payload.get("output_artifacts", ())),
            required_outputs=tuple(payload.get("required_outputs", ())),
            tree_ref=payload.get("tree_ref"),
            metrics=ExecutionMetrics(
                wall_ms=int(metrics.get("wall_ms", 0)),
                cpu_ms=int(metrics.get("cpu_ms", 0)),
                compiler_ms=int(metrics.get("compiler_ms", 0)),
                model_tokens=int(metrics.get("model_tokens", 0)),
            ),
            determinism=payload.get("determinism", "DETERMINISTIC"),
        )
        with self.store.transaction():
            result = self.action_cache.commit(
                CommitRequest(
                    tenant_id=self.tenant_id,
                    action_key=action_key,
                    manifest=manifest,
                    trust_namespace=TrustNamespace(payload.get("trust_namespace", str(self.trust_namespace))),
                    validation_level=ValidationLevel(payload.get("validation_level", "UNVERIFIED")),
                    producer_identity=payload.get("producer_identity", "unknown"),
                    provenance_digest=payload.get("provenance_digest"),
                    expires_at=payload.get("expires_at"),
                )
            )
        return Response(
            201 if result.committed else 409,
            {"committed": result.committed, "result_manifest_digest": result.result_digest},
        )

    # -- blobs ------------------------------------------------------------
    def blob_exists(self, request: Request, params: dict[str, str]) -> Response:
        digest = _normalize_digest(params["digest"])
        if not self.cas.contains(digest):
            return Response(404, {})
        info = self.cas.info(digest)
        return Response(200, {}).with_headers(
            **{"Content-Length": str(info.size), "X-Elmos-Digest": digest}
        )

    def get_blob(self, request: Request, params: dict[str, str]) -> Response:
        digest = _normalize_digest(params["digest"])
        data = self.cas.get_bytes(digest, verify=True)
        return Response(200, data, {"Content-Type": "application/octet-stream", "X-Elmos-Digest": digest})

    def put_blob(self, request: Request, params: dict[str, str]) -> Response:
        digest = _normalize_digest(params["digest"])
        body = request.body
        if not isinstance(body, bytes):
            return _error(400, "SCHEMA_INVALID", "blob upload requires a binary body")
        # Digest-addressed: mismatched content is rejected, not stored.
        stored = self.cas.put_bytes(body, expected_digest=digest)
        with self.store.transaction():
            self.store.register_artifact(
                self.tenant_id,
                stored,
                size_bytes=len(body),
                media_type=request.header("Content-Type") or "application/octet-stream",
                artifact_kind=request.param("artifactKind", "blob") or "blob",
            )
        return Response(201, {"digest": stored, "size": len(body)})

    # -- runs -------------------------------------------------------------
    def create_run(self, request: Request, params: dict[str, str]) -> Response:
        payload = request.json()
        with self.store.transaction():
            self.store.ensure_project(self.tenant_id, payload["project_id"])
            snapshot_id = self.store.record_snapshot(
                self.tenant_id,
                payload["project_id"],
                require_digest(payload["source_snapshot"]),
                require_digest(payload.get("snapshot_manifest", payload["source_snapshot"])),
                payload.get("policy_version", "elmos.snapshot-policy/1.0.0"),
            )
            run = self.store.create_run(
                payload["run_id"],
                self.tenant_id,
                payload["project_id"],
                snapshot_id,
                payload.get("pipeline_version", SCHEMA_VERSION),
                payload.get("source_profile"),
                payload.get("target_profile"),
            )
        return Response(201, _run_dict(run))

    def get_run(self, request: Request, params: dict[str, str]) -> Response:
        run = self.store.get_run(params["runId"])
        nodes = [
            {
                "node_id": node.node_id,
                "attempt": node.attempt,
                "status": str(node.status),
                "lease_epoch": node.lease_epoch,
                "action_key": node.action_key,
            }
            for node in self.store.list_nodes(run.run_id)
        ]
        return Response(200, {**_run_dict(run), "nodes": nodes})

    def list_runs(self, request: Request, params: dict[str, str]) -> Response:
        status = request.param("status")
        statuses = [RunStatus(status)] if status else None
        runs = self.store.list_runs(self.tenant_id, statuses)
        return _paginate(request, [_run_dict(run) for run in runs], "run_id")

    def resume_run(self, request: Request, params: dict[str, str]) -> Response:
        run_id = params["runId"]
        payload = request.json()
        expected = payload.get("expected_version")
        run = self.store.get_run(run_id)
        if expected is not None and int(expected) != run.version:
            return _error(
                409, "VERSION_CONFLICT", "run version conflict", {"expected": expected, "actual": run.version}
            )
        workspace = self.workspaces.get(run_id)
        summary: dict[str, Any] = {}
        with self.store.transaction():
            if workspace is not None:
                summary = workspace.recover()
            self.store.transition_run(run_id, RunStatus.RUNNING, run.version)
        return Response(200, {"run_id": run_id, "recovery": summary})

    # -- staged files -----------------------------------------------------
    def _workspace(self, run_id: str) -> Workspace:
        workspace = self.workspaces.get(run_id)
        if workspace is None:
            raise NotFound("no workspace is registered for this run", run_id=run_id)
        return workspace

    def reserve_staged_file(self, request: Request, params: dict[str, str]) -> Response:
        payload = request.json()
        workspace = self._workspace(params["runId"])
        with self.store.transaction():
            record = workspace.reserve(
                payload["node_id"],
                int(payload.get("attempt", 1)),
                payload["logical_path"],
                int(payload["lease_epoch"]),
                media_type=payload.get("media_type"),
                artifact_kind=payload.get("artifact_kind"),
                action_key=payload.get("action_key"),
                overwrite_policy=payload.get("overwrite_policy", "reject"),
                expected_size=payload.get("expected_size"),
            )
        return Response(201, _staged_dict(record))

    def start_staged_write(self, request: Request, params: dict[str, str]) -> Response:
        record = self.store.get_staged_file(params["stagedFileId"])
        return Response(
            200,
            {
                "staged_file_id": record.staged_file_id,
                "upload_token": digest_of(
                    {"staged_file_id": record.staged_file_id, "version": record.version}
                ),
                "version": record.version,
                "lease_epoch": record.lease_epoch,
            },
        )

    def seal_staged_file(self, request: Request, params: dict[str, str]) -> Response:
        workspace = self._workspace(params["runId"])
        record = self.store.get_staged_file(params["stagedFileId"])
        payload = request.json()
        content = payload.get("content_digest")
        blob = payload.get("blob")
        if blob is None and content is None:
            return _error(400, "SCHEMA_INVALID", "seal requires content_digest or blob")
        data = (
            bytes.fromhex(blob)
            if isinstance(blob, str)
            else self.cas.get_bytes(require_digest(str(content)))
        )
        with self.store.transaction():
            sealed = workspace.write_and_seal(
                record, data, int(payload["lease_epoch"]), expected_digest=content
            )
        return Response(200, _staged_dict(sealed))

    def promote_staged_file(self, request: Request, params: dict[str, str]) -> Response:
        workspace = self._workspace(params["runId"])
        record = self.store.get_staged_file(params["stagedFileId"])
        with self.store.transaction():
            promoted = workspace.promote(record)
        return Response(200, _staged_dict(promoted))

    def list_staged_files(self, request: Request, params: dict[str, str]) -> Response:
        records = self.store.list_staged_files(params["runId"])
        return _paginate(request, [_staged_dict(record) for record in records], "staged_file_id")

    # -- checkpoints ------------------------------------------------------
    def commit_checkpoint(self, request: Request, params: dict[str, str]) -> Response:
        service = self.checkpoints.get(params["runId"])
        if service is None:
            raise NotFound("no checkpoint service for this run", run_id=params["runId"])
        return _error(501, "UNSUPPORTED", "checkpoint commit requires an authenticated worker lease")

    def list_checkpoints(self, request: Request, params: dict[str, str]) -> Response:
        records = self.store.list_checkpoints(params["runId"])
        return _paginate(
            request,
            [
                {
                    "checkpoint_id": record.checkpoint_id,
                    "node_id": record.node_id,
                    "attempt": record.attempt,
                    "sequence": record.sequence,
                    "status": str(record.status),
                    "manifest_digest": record.manifest_digest,
                    "journal_sequence": record.journal_sequence,
                }
                for record in records
            ],
            "checkpoint_id",
        )

    # -- publication ------------------------------------------------------
    def publish_tree(self, request: Request, params: dict[str, str]) -> Response:
        run_id = params["runId"]
        publisher = self.publishers.get(run_id)
        workspace = self.workspaces.get(run_id)
        if publisher is None or workspace is None:
            raise NotFound("no publisher is registered for this run", run_id=run_id)
        payload = request.json()
        level = ValidationLevel(payload.get("validation_level", "UNVERIFIED"))
        with self.store.transaction():
            tree = publisher.build_tree_manifest(workspace.publishable(), validation_level=level)
            candidate = publisher.materialize(tree)
            if payload.get("dry_run", False):
                return Response(200, {"dry_run": True, "tree_digest": tree.root_digest})
            result = publisher.publish(candidate, None if level is ValidationLevel.UNVERIFIED else None)
        return Response(
            200,
            {
                "tree_digest": result.tree_digest,
                "previous_tree_digest": result.previous_tree_digest,
                "retained": list(result.retained),
            },
        )

    # -- gc ---------------------------------------------------------------
    def create_gc_plan(self, request: Request, params: dict[str, str]) -> Response:
        collector = GarbageCollector(self.store, self.cas, self.tenant_id, clock=self.clock)
        with self.store.transaction():
            plan = collector.plan()
        # Destructive operations default to a plan, never an immediate delete.
        return Response(201, {"dry_run": True, **plan.to_dict()})

    def apply_gc_plan(self, request: Request, params: dict[str, str]) -> Response:
        payload = request.json()
        if not payload.get("confirm", False):
            return _error(
                400, "CONFIRMATION_REQUIRED", "applying a GC plan requires confirm=true"
            )
        collector = GarbageCollector(self.store, self.cas, self.tenant_id, clock=self.clock)
        with self.store.transaction():
            collector.approve(params["planId"])
            outcome = collector.apply(params["planId"])
        return Response(200, outcome)

    # -- status -----------------------------------------------------------
    def status(self, request: Request, params: dict[str, str]) -> Response:
        return Response(
            200,
            {
                "api_version": API_VERSION,
                "schema_version": SCHEMA_VERSION,
                "tenant_id": self.tenant_id,
                "cas": self.cas.accounting(),
                "action_cache": self.action_cache.statistics(self.tenant_id),
                "runs": len(self.store.list_runs(self.tenant_id)),
            },
        )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _request_payload(request: Request) -> dict[str, Any]:
    """Idempotency fingerprint of a request body, JSON or binary."""
    if isinstance(request.body, bytes):
        return {"bytes": digest_of(str(len(request.body)))}
    return request.json()


def _error(status: int, code: str, message: str, details: Mapping[str, Any] | None = None) -> Response:
    return Response(status, {"code": code, "message": message, "details": dict(details or {})})


def _normalize_digest(value: str) -> str:
    candidate = value if value.startswith("sha256:") else f"sha256:{value}"
    return require_digest(candidate)


def _run_dict(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "tenant_id": run.tenant_id,
        "project_id": run.project_id,
        "status": str(run.status),
        "version": run.version,
        "journal_sequence": run.journal_sequence,
        "published_tree_digest": run.published_tree_digest,
        "evidence_bundle_digest": run.evidence_bundle_digest,
    }


def _staged_dict(record: Any) -> dict[str, Any]:
    return {
        "staged_file_id": record.staged_file_id,
        "run_id": record.run_id,
        "node_id": record.node_id,
        "attempt": record.attempt,
        "logical_path": record.logical_path,
        "file_class": str(record.file_class),
        "status": str(record.status),
        "version": record.version,
        "lease_epoch": record.lease_epoch,
        "digest": record.digest,
        "artifact_digest": record.artifact_digest,
        "actual_size": record.actual_size,
        "validation_level": str(record.validation_level),
    }


def _paginate(request: Request, items: Sequence[dict[str, Any]], sort_key: str) -> Response:
    """Stable cursor pagination over a deterministic sort key."""
    limit = min(int(request.param("limit", "100") or 100), MAX_PAGE_SIZE)
    cursor = request.param("cursor")
    ordered = sorted(items, key=lambda item: str(item.get(sort_key, "")))
    start = 0
    if cursor:
        for index, item in enumerate(ordered):
            if str(item.get(sort_key, "")) > cursor:
                start = index
                break
        else:
            start = len(ordered)
    page = ordered[start : start + limit]
    next_cursor = str(page[-1].get(sort_key)) if len(page) == limit and page else None
    return Response(200, {"items": page, "next_cursor": next_cursor, "total": len(ordered)})


# --------------------------------------------------------------------------
# WSGI adapter
# --------------------------------------------------------------------------
def wsgi_app(plane: CacheControlPlane) -> Callable[[dict[str, Any], Callable[..., Any]], Iterable[bytes]]:
    """Expose the control plane as a WSGI application."""

    def application(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        from urllib.parse import parse_qsl

        length = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ["wsgi.input"].read(length) if length else b""
        content_type = environ.get("CONTENT_TYPE", "")
        body: dict[str, Any] | bytes | None
        if raw and "json" in content_type:
            body = json.loads(raw.decode("utf-8"))
        else:
            body = raw or None
        headers = {
            key[5:].replace("_", "-").title(): value
            for key, value in environ.items()
            if key.startswith("HTTP_")
        }
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(
            method=environ["REQUEST_METHOD"],
            path=environ.get("PATH_INFO", "/"),
            body=body,
            headers=headers,
            query=dict(parse_qsl(environ.get("QUERY_STRING", ""))),
        )
        response = plane.handle(request)
        payload = (
            response.body
            if isinstance(response.body, bytes)
            else json.dumps(response.body, sort_keys=True).encode("utf-8")
        )
        out_headers = list((response.headers or {}).items())
        if not isinstance(response.body, bytes):
            out_headers.append(("Content-Type", "application/json"))
        out_headers.append(("Content-Length", str(len(payload))))
        start_response(f"{response.status} ", out_headers)
        return [payload]

    return application
