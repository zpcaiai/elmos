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

import base64
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .action_cache import ActionCache, CommitRequest, LookupResult
from .affinity import AffinityAuthorizationResolver, AttestedAffinityRegistry
from .canonical import digest_of, require_digest, sha256_bytes
from .cas import ContentAddressableStore
from .checkpoint import CheckpointService
from .clock import SYSTEM_CLOCK, Clock
from .db import IdempotencyClaim, MetadataStore
from .enums import (
    ArtifactStorageState,
    CacheMode,
    RunStatus,
    TrustNamespace,
    ValidationLevel,
)
from .environment_service import EnvironmentSnapshotService
from .errors import (
    ConflictError,
    ContractViolation,
    CorruptObject,
    ElmosCacheError,
    IdempotencyConflict,
    IdempotencyOutcomeUnknown,
    NotFound,
    PermissionDenied,
    ProvenanceInvalid,
    RemoteUnavailable,
    Unsupported,
)
from .gc import GarbageCollector
from .manifests import ActionResultManifest, ExecutionMetrics
from .parity_api import ParityApiService, ParityRepository, ServiceResult
from .parity_composition import CompositionLayer
from .parity_composition_wiring import (
    ActionCacheLayerProbe,
    CompositionRunner,
    LayerProbeFn,
    ParityCompositionOutcomeSink,
    ServingCompositionWiring,
)
from .parity_evidence import CasParityEvidenceVerifier, ParityEvidenceTrustVerifier
from .parity_runtime import SERVING_LAYERS, ServingAuthorizer
from .prompt_cache import PromptCacheController
from .publish import TreePublisher
from .staging import Workspace

SCHEMA_VERSION = "1.2.0"
API_VERSION = "v1"
MAX_PAGE_SIZE = 500
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024
AUTHENTICATED_CONTEXT_ENVIRON_KEY = "elmos.authenticated_context"
COMPOSITION_REQUEST_ID_HEADER = "X-Elmos-Request-Id"
COMPOSITION_OUTCOME_HEADER = "X-Elmos-Cache-Outcome-Persisted"
_HTTP_TENANT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
# The composition's request_id vocabulary is the same bounded identifier.
_COMPOSITION_REQUEST_ID = _HTTP_TENANT_IDENTIFIER


@dataclass(frozen=True)
class AuthenticatedHttpContext:
    """Identity injected by trusted WSGI middleware, never parsed from headers."""

    tenant_id: str
    principal_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not _HTTP_TENANT_IDENTIFIER.fullmatch(
            self.tenant_id
        ):
            raise ContractViolation("authenticated tenant_id is invalid")
        require_digest(self.principal_digest)


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    body: dict[str, Any] | bytes | None = None
    headers: Mapping[str, str] = ()  # type: ignore[assignment]
    query: Mapping[str, str] = ()  # type: ignore[assignment]
    authenticated_principal_digest: str | None = None

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
IDEMPOTENCY_SEMANTIC_HEADERS = (
    "accept",
    "content-encoding",
    "content-type",
    "if-match",
    "if-none-match",
    "prefer",
)
# Mutating routes whose tenancy lives in the request body rather than in the
# path. ``_authorize_resource_preflight`` resolves project ownership for each
# of them *before* ``handle`` takes the durable idempotency claim, so that:
#
# * a refusal writes no ``idempotency_records`` row and therefore cannot burn
#   the caller's key -- or anyone else's, since keys are tenant-scoped;
# * a foreign project and an absent project produce one identical refusal, so
#   the response code cannot be used to enumerate the global project namespace;
# * an already-used key and a fresh key answer identically to a caller who is
#   not authorized for the project, so the refusal cannot be used to enumerate
#   which idempotency keys exist in the tenant;
# * no route in this set can bring a ``projects`` row into existence as a side
#   effect. Project creation is a deliberate claim, made only by ``create_run``
#   (``POST /runs``), which answers ``CONFLICT`` on a name it cannot have.
BODY_PROJECT_SCOPED_HANDLERS = frozenset(
    {
        "append_context_ledger_event",
        "compile_prompt_prefix",
        "decide_cache_affinity",
        "prepare_provider_prompt",
        "record_provider_usage",
        "start_cache_parity_run",
    }
)


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
        parity_repository: ParityRepository | None = None,
        affinity_registry: AttestedAffinityRegistry | None = None,
        affinity_authorizer: AffinityAuthorizationResolver | None = None,
        environment_service: EnvironmentSnapshotService | None = None,
        serving_authorizer: ServingAuthorizer | None = None,
        parity_evidence_trust_verifier: ParityEvidenceTrustVerifier | None = None,
        prompt_cache_controller: PromptCacheController | None = None,
        serving_composition: ServingCompositionWiring | None = None,
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
        # Serving authority is trusted runtime composition, never a request or
        # repository-config assertion. Absence is an explicit deny-all state.
        self.serving_authorizer = serving_authorizer
        # Provider profiles, kill switches and circuit-breaker state are the
        # same kind of trusted composition: there is no safe default to build
        # here, so absence stays absence and the provider routes fail closed.
        self.prompt_cache_controller = prompt_cache_controller
        # The signed five-layer composition is the same kind of trusted
        # composition again. Absence stays absence: without it every route
        # behaves exactly as it did before the composition existed, and the
        # composed path is built only when the boundary, the rollback latch and
        # the outcome repository are all present.
        self.serving_composition = serving_composition
        resolved_parity_repository = parity_repository
        try:
            from .parity_store import ParityMetadataRepository
        except ImportError:
            # A source-only partial install must fail closed at the parity
            # endpoints instead of falling back to process memory.
            pass
        else:
            if resolved_parity_repository is None:
                resolved_parity_repository = ParityMetadataRepository(
                    store, project_scope_claim=False
                )
            elif isinstance(resolved_parity_repository, ParityMetadataRepository):
                # Serving a request must never claim a globally unique project
                # name. Ownership is already decided in the preflight, but the
                # plane refuses the capability outright rather than depending
                # on how it happened to be composed.
                resolved_parity_repository = (
                    resolved_parity_repository.without_project_claim()
                )
        self.parity_repository = resolved_parity_repository
        resolved_environment_service = environment_service or EnvironmentSnapshotService(
            store,
            cas,
            clock=clock,
        )
        self.parity_api = ParityApiService(
            tenant_id=tenant_id,
            store=store,
            repository=resolved_parity_repository,
            clock=clock,
            evidence_verifier=CasParityEvidenceVerifier(
                cas,
                ownership=store,
                trust_verifier=parity_evidence_trust_verifier,
                clock=clock,
            ),
            affinity_registry=affinity_registry,
            affinity_authorizer=affinity_authorizer,
            environment_service=resolved_environment_service,
            prompt_cache_controller=prompt_cache_controller,
        )
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
        self.route("POST", "/cache/prompt-prefixes/compile", self.compile_prompt_prefix)
        self.route(
            "POST", "/cache/provider-prompts/prepare", self.prepare_provider_prompt
        )
        self.route("POST", "/cache/provider-prompts/usage", self.record_provider_usage)
        self.route(
            "POST",
            "/cache/context-ledgers/{streamId}/events",
            self.append_context_ledger_event,
        )
        self.route(
            "GET",
            "/cache/environments/{snapshotKey}",
            self.lookup_environment_snapshot,
        )
        self.route("POST", "/cache/affinity/decide", self.decide_cache_affinity)
        self.route("GET", "/cache/explain/{requestId}", self.explain_cache_outcome)
        self.route("POST", "/cache/parity/runs", self.start_cache_parity_run)
        self.route(
            "GET", "/cache/parity/reports/{reportId}", self.get_cache_parity_report
        )
        self.route("GET", "/status", self.status)

    def handle(self, request: Request) -> Response:
        """Dispatch with a durable claim before any mutating handler runs."""
        matched: tuple[Handler, dict[str, str]] | None = None
        for method, pattern, handler in self._routes:
            if method == request.method.upper():
                match = pattern.match(request.path)
                if match is not None:
                    matched = (handler, match.groupdict())
                    break
        if matched is None:
            return _error(404, "NOT_FOUND", f"no route for {request.method} {request.path}")

        handler, params = matched
        try:
            # Resource authorization precedes the durable idempotency claim.
            # A denied cross-tenant mutation must leave no metadata row or CAS
            # side effect merely because it supplied an Idempotency-Key.
            self._authorize_resource_preflight(handler, request, params)
        except ElmosCacheError as exc:
            return _error(exc.http_status, exc.code, exc.message, exc.details)
        idempotency_key = request.header("Idempotency-Key")
        claim: IdempotencyClaim | None = None
        request_fingerprint: dict[str, Any] | None = None
        if request.method.upper() in MUTATING_METHODS:
            if not idempotency_key:
                return _error(
                    400,
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "mutating operations require an Idempotency-Key header",
                )
            try:
                request_fingerprint = _request_payload(request)
                with self.store.transaction():
                    claim = self.store.claim_idempotent(
                        self.tenant_id,
                        idempotency_key,
                        self._idempotency_operation(request),
                        request_fingerprint,
                    )
            except (IdempotencyConflict, IdempotencyOutcomeUnknown) as exc:
                return _error(exc.http_status, exc.code, exc.message, exc.details)
            if claim.replayed:
                try:
                    return _response_from_idempotency(claim.response).with_headers(
                        **{"Idempotent-Replay": "true"}
                    )
                except ElmosCacheError as exc:
                    return _error(exc.http_status, exc.code, exc.message, exc.details)

        try:
            response = handler(request, params)
        except ElmosCacheError as exc:
            self.store.rollback()
            response = _error(exc.http_status, exc.code, exc.message, exc.details)
        except Exception as exc:  # noqa: BLE001 - never leak a traceback
            self.store.rollback()
            return _error(500, "INTERNAL", type(exc).__name__)

        response = response.with_headers(**{"X-Elmos-Api-Version": API_VERSION})
        if claim is None or idempotency_key is None or request_fingerprint is None:
            return response
        if response.status >= 500:
            self.store.rollback()
            return response
        try:
            self._idempotency_before_complete(request, response)
            assert claim.owner_token is not None
            with self.store.transaction():
                completed = self.store.complete_idempotent(
                    self.tenant_id,
                    idempotency_key,
                    self._idempotency_operation(request),
                    request_fingerprint,
                    claim.owner_token,
                    claim.fence,
                    _idempotency_response(response),
                )
            return _response_from_idempotency(completed)
        except ElmosCacheError as exc:
            self.store.rollback()
            return _error(exc.http_status, exc.code, exc.message, exc.details)
        except Exception as exc:  # noqa: BLE001 - completion failure makes outcome ambiguous
            self.store.rollback()
            return _error(
                500,
                "OUTCOME_UNKNOWN",
                "operation completed but its idempotency response was not durably recorded",
                {"failure": type(exc).__name__, "state": "PENDING"},
            )

    def _idempotency_operation(self, request: Request) -> str:
        return f"{request.method.upper()} {request.path}"

    def _idempotency_before_complete(self, request: Request, response: Response) -> None:
        """Fault-injection seam for a crash after the handler side effect."""

    def _owned_run(self, run_id: str) -> Any:
        return self.store.get_run_for_tenant(self.tenant_id, run_id)

    def _owned_staged_file(self, run_id: str, staged_file_id: str) -> Any:
        self._owned_run(run_id)
        return self.store.get_staged_file_for_tenant(
            self.tenant_id,
            run_id,
            staged_file_id,
        )

    def _owned_project(self, project_id: str) -> None:
        """Fail closed on any project this tenant does not own.

        A project owned by somebody else and a project that was never created
        must be indistinguishable, otherwise the error code alone enumerates
        another tenant's projects. ``create_run`` deliberately answers
        ``CONFLICT`` instead because it is claiming an identifier rather than
        reading one.
        """

        owner = self.store.query_one(
            "SELECT tenant_id FROM projects WHERE project_id=?",
            (project_id,),
        )
        if owner is None or str(owner[0]) != self.tenant_id:
            raise NotFound("project does not exist", project_id=project_id)

    def _owned_usable_artifact(self, digest: str) -> Any:
        normalized = require_digest(digest)
        registration = self.store.get_artifact(self.tenant_id, normalized)
        if (
            registration is None
            or registration.tenant_id != self.tenant_id
            or registration.digest != normalized
            or registration.storage_state
            not in (ArtifactStorageState.LOCAL, ArtifactStorageState.REMOTE)
            or registration.validation_level is ValidationLevel.QUARANTINED
            or self.cas.is_quarantined(normalized)
        ):
            raise NotFound("blob does not exist")
        return registration

    def _authorize_resource_preflight(
        self,
        handler: Handler,
        request: Request,
        params: dict[str, str],
    ) -> None:
        """Read-only tenant/resource checks for every globally keyed route."""

        run_id = params.get("runId")
        if run_id is not None:
            self._owned_run(run_id)
        staged_file_id = params.get("stagedFileId")
        if run_id is not None and staged_file_id is not None:
            self._owned_staged_file(run_id, staged_file_id)
        if handler.__name__ == "apply_gc_plan":
            self.store.get_gc_plan_for_tenant(self.tenant_id, params["planId"])
        if handler.__name__ == "create_run":
            payload = request.body if isinstance(request.body, dict) else {}
            run_id = payload.get("run_id")
            if isinstance(run_id, str):
                owner = self.store.query_one(
                    "SELECT tenant_id FROM runs WHERE run_id=?",
                    (run_id,),
                )
                if owner is not None and str(owner[0]) != self.tenant_id:
                    raise ConflictError("run identifier is unavailable")
            project_id = payload.get("project_id")
            if isinstance(project_id, str):
                owner = self.store.query_one(
                    "SELECT tenant_id FROM projects WHERE project_id=?",
                    (project_id,),
                )
                if owner is not None and str(owner[0]) != self.tenant_id:
                    raise ConflictError("project identifier is unavailable")
        if handler.__name__ in BODY_PROJECT_SCOPED_HANDLERS:
            payload = request.body if isinstance(request.body, dict) else {}
            project_id = payload.get("project_id")
            if not isinstance(project_id, str) or not project_id:
                raise ContractViolation(
                    "project-scoped cache operations require project_id"
                )
            self._owned_project(project_id)
        if handler.__name__ == "seal_staged_file":
            payload = request.body if isinstance(request.body, dict) else {}
            content = payload.get("content_digest")
            if payload.get("blob") is None and isinstance(content, str):
                self._owned_usable_artifact(require_digest(content))
        if handler.__name__ == "commit_action":
            payload = request.body if isinstance(request.body, dict) else {}
            outputs = payload.get("output_artifacts")
            if isinstance(outputs, list | tuple):
                for digest in outputs:
                    if isinstance(digest, str):
                        self._owned_usable_artifact(require_digest(digest))

    # -- action cache -----------------------------------------------------
    def lookup_action(self, request: Request, params: dict[str, str]) -> Response:
        action_key = _normalize_digest(params["actionKey"])
        minimum = ValidationLevel(request.param("minimumValidation", "TEST_VERIFIED") or "TEST_VERIFIED")
        namespace = TrustNamespace(
            request.param("trustNamespace", str(self.trust_namespace)) or "branch"
        )
        mode = CacheMode(request.param("mode", "read-write") or "read-write")
        probe = ActionCacheLayerProbe(
            self.action_cache,
            tenant_id=self.tenant_id,
            action_key=action_key,
            trust_namespace=namespace,
            minimum_validation=minimum,
            mode=mode,
        )
        runner = self._composition_runner(
            request,
            work={
                "operation": "lookup_action",
                "action_key": action_key,
                "trust_namespace": str(namespace),
                "minimum_validation": str(minimum),
                "mode": str(mode),
            },
            probes={CompositionLayer.ACTION: probe},
        )
        if runner is None:
            return self._action_lookup_response(action_key, probe.lookup(), reused=None)
        # Only a verified, boundary-authorised, restored exact Action result may
        # answer "you do not have to execute this". Every other composition
        # outcome — a miss, a denied grant, a failed restore, an expired cache
        # deadline — reports a miss, so the composed skip set is a strict subset
        # of the unwired one.
        outcome = runner.run(_action_lookup_reports_a_miss)
        response = self._action_lookup_response(
            action_key,
            probe.lookup(),
            reused=outcome.result.exact_action_reused,
        )
        return response.with_headers(
            **{
                COMPOSITION_OUTCOME_HEADER: (
                    "true" if outcome.result.outcome_persisted else "false"
                )
            }
        )

    def _action_lookup_response(
        self,
        action_key: str,
        result: LookupResult,
        *,
        reused: bool | None,
    ) -> Response:
        # Serving is the conjunction, enforced here rather than inferred from
        # ``reused``. The 200 body is built entirely from ``result``, so a
        # composition reporting an exact reuse the Action Cache did not produce
        # would otherwise answer "you do not have to execute this" with
        # ``result: null`` attached. Requiring ``result.hit`` on both branches
        # is what actually makes the composed 200-set a subset of the unwired
        # one: ``reused`` may only ever subtract from it, never add.
        served = result.hit and (reused is None or reused)
        if not served:
            detail = dict(result.detail)
            if reused is False and result.hit:
                detail["composition"] = "COMPOSITION_REFUSED_EXACT_ACTION_REUSE"
            elif reused is True and not result.hit:
                detail["composition"] = "COMPOSITION_CLAIMED_UNBACKED_EXACT_ACTION_REUSE"
            return Response(
                404,
                {
                    "hit": False,
                    "miss_reasons": [str(reason) for reason in result.reasons],
                    "detail": detail,
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
        registration = self._owned_usable_artifact(digest)
        info = self.cas.info(digest)
        if info.size != registration.size_bytes:
            raise CorruptObject("registered blob size does not match CAS bytes")
        return Response(200, {}).with_headers(
            **{"Content-Length": str(info.size), "X-Elmos-Digest": digest}
        )

    def get_blob(self, request: Request, params: dict[str, str]) -> Response:
        digest = _normalize_digest(params["digest"])
        registration = self._owned_usable_artifact(digest)
        data = self.cas.get_bytes(digest, verify=True)
        if len(data) != registration.size_bytes:
            raise CorruptObject("registered blob size does not match CAS bytes")
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
        run = self._owned_run(params["runId"])
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
        run = self._owned_run(run_id)
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
        self._owned_run(run_id)
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
        record = self._owned_staged_file(params["runId"], params["stagedFileId"])
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
        record = self._owned_staged_file(params["runId"], params["stagedFileId"])
        payload = request.json()
        content = payload.get("content_digest")
        blob = payload.get("blob")
        if blob is None and content is None:
            return _error(400, "SCHEMA_INVALID", "seal requires content_digest or blob")
        if isinstance(blob, str):
            data = bytes.fromhex(blob)
        else:
            content_digest = require_digest(str(content))
            self._owned_usable_artifact(content_digest)
            data = self.cas.get_bytes(content_digest, verify=True)
        with self.store.transaction():
            sealed = workspace.write_and_seal(
                record, data, int(payload["lease_epoch"]), expected_digest=content
            )
        return Response(200, _staged_dict(sealed))

    def promote_staged_file(self, request: Request, params: dict[str, str]) -> Response:
        workspace = self._workspace(params["runId"])
        record = self._owned_staged_file(params["runId"], params["stagedFileId"])
        with self.store.transaction():
            promoted = workspace.promote(record)
        return Response(200, _staged_dict(promoted))

    def list_staged_files(self, request: Request, params: dict[str, str]) -> Response:
        self._owned_run(params["runId"])
        records = self.store.list_staged_files(params["runId"])
        return _paginate(request, [_staged_dict(record) for record in records], "staged_file_id")

    # -- checkpoints ------------------------------------------------------
    def commit_checkpoint(self, request: Request, params: dict[str, str]) -> Response:
        self._owned_run(params["runId"])
        service = self.checkpoints.get(params["runId"])
        if service is None:
            raise NotFound("no checkpoint service for this run", run_id=params["runId"])
        return _error(501, "UNSUPPORTED", "checkpoint commit requires an authenticated worker lease")

    def list_checkpoints(self, request: Request, params: dict[str, str]) -> Response:
        self._owned_run(params["runId"])
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
        self._owned_run(run_id)
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

    # -- cache parity supplement ----------------------------------------
    @staticmethod
    def _parity_response(result: ServiceResult) -> Response:
        return Response(result.status, result.body)

    def _authorize_parity_serving(self, layer: str, project_id: str) -> None:
        authorizer = self.serving_authorizer
        if authorizer is None:
            raise PermissionDenied(
                "cache parity serving is not authorized",
                layer=layer,
                state="NOT_WIRED",
            )
        authorizer.authorize_serving(layer, self.tenant_id, project_id)

    # -- five-layer cache-parity composition -----------------------------
    def _composition_request_id(self, request: Request) -> str:
        """A bounded, content-free correlation id for the explain endpoint."""

        for header in (COMPOSITION_REQUEST_ID_HEADER, "Idempotency-Key"):
            value = request.header(header)
            if value and _COMPOSITION_REQUEST_ID.fullmatch(value):
                return value
        return "req-" + digest_of(
            {
                "method": request.method.upper(),
                "path": request.path,
                "query": dict(request.query),
                "principal_digest": request.authenticated_principal_digest,
                "observed_at": self.clock.now(),
            }
        ).removeprefix("sha256:")

    def _composition_runner(
        self,
        request: Request,
        *,
        work: Mapping[str, Any],
        probes: Mapping[CompositionLayer, LayerProbeFn],
    ) -> CompositionRunner | None:
        """Build one composed request scope, or ``None`` when not wired.

        Every collaborator is required. A partially wired plane is not a
        half-composed plane: it is an unwired one, and behaves exactly as it did
        before this row existed.
        """

        wiring = self.serving_composition
        latch = self.serving_authorizer
        repository = self.parity_repository
        if wiring is None or latch is None or repository is None:
            return None
        principal_digest = request.authenticated_principal_digest
        if not principal_digest:
            # The composition binds a principal. Serving an anonymous request
            # through it would bind it to somebody else's scope, so refuse.
            raise PermissionDenied(
                "cache parity composition requires an authenticated principal",
                state="NO_AUTHENTICATED_PRINCIPAL",
            )
        # The project scope is the signed receipt's, never the request's: a
        # request cannot nominate the scope it is authorized against.
        project_id = wiring.serving_boundary.project_id
        return CompositionRunner(
            wiring,
            tenant_id=self.tenant_id,
            project_id=project_id,
            principal_digest=principal_digest,
            request_id=self._composition_request_id(request),
            work_digest=digest_of(dict(work)),
            outcome_sink=ParityCompositionOutcomeSink(
                repository,
                tenant_id=self.tenant_id,
                project_id=project_id,
                now=self.clock.now,
            ),
            rollback_latch=latch,
            probes=probes,
        )

    def _serving_call(
        self,
        request: Request,
        layer: str,
        project_id: str,
        operation: Callable[[], ServiceResult],
    ) -> Response:
        self._authorize_parity_serving(layer, project_id)
        runner = self._composition_runner(
            request,
            work={
                "operation": "serving_call",
                "layer": layer,
                "project_id": project_id,
                "path": request.path,
            },
            # No serving route carries an action key, so this call site has no
            # Action probe to offer. That is NOT the same as the Action layer
            # being out of scope: ``CompositionRunner`` merges
            # ``wiring.layer_probes`` *underneath* these per-call probes, so a
            # deployment that registers an ACTION probe there does put the
            # Action layer in scope on serving routes too. What actually keeps a
            # serving route from skipping its operation is the explicit
            # ``exact_action_reused`` refusal in ``_composed_serving_call``,
            # which latches ``SERVING_PATH_SKIPPED_EXECUTION`` and raises. That
            # guard is the load-bearing part, not this empty mapping.
            probes={},
        )
        if runner is None:
            return self._direct_serving_call(operation)
        return self._composed_serving_call(runner, operation)

    def _direct_serving_call(
        self,
        operation: Callable[[], ServiceResult],
    ) -> Response:
        try:
            result = operation()
            if result.status >= 500:
                assert self.serving_authorizer is not None
                self.serving_authorizer.latch_rollback("SERVING_PATH_PERSISTENCE_FAILED")
            return self._parity_response(result)
        except (CorruptObject, ProvenanceInvalid):
            assert self.serving_authorizer is not None
            self.serving_authorizer.latch_rollback("SERVING_PATH_INTEGRITY_FAILED")
            raise
        except RemoteUnavailable:
            assert self.serving_authorizer is not None
            self.serving_authorizer.latch_rollback("SERVING_PATH_RUNTIME_FAILED")
            raise
        except ElmosCacheError:
            raise
        except Exception:
            # A backend/runtime failure after authorization cannot leave the
            # control plane claiming that serving is healthy. The latch is
            # process-local safety state; it is not production evidence.
            assert self.serving_authorizer is not None
            self.serving_authorizer.latch_rollback("SERVING_PATH_RUNTIME_FAILED")
            raise

    def _composed_serving_call(
        self,
        runner: CompositionRunner,
        operation: Callable[[], ServiceResult],
    ) -> Response:
        """Run the serving operation inside one signed five-layer scope.

        The three refusal paths that escape the composition as exceptions — a
        fallback executor that crashes, one that returns an unknown type and one
        that skips unrestored work — all leave here as typed engine errors, so
        the route maps them to a code instead of leaking an internal traceback.
        """

        latch = self.serving_authorizer
        assert latch is not None
        try:
            outcome = runner.run(operation)
        except (CorruptObject, ProvenanceInvalid):
            latch.latch_rollback("SERVING_PATH_INTEGRITY_FAILED")
            raise
        except RemoteUnavailable:
            latch.latch_rollback("SERVING_PATH_RUNTIME_FAILED")
            raise
        except ElmosCacheError:
            # Includes the composition's own ContractViolation refusals, which
            # have already latched their own reason code.
            raise
        except Exception:
            latch.latch_rollback("SERVING_PATH_RUNTIME_FAILED")
            raise
        composed = outcome.result
        if composed.exact_action_reused:
            # Unreachable by construction: no Action probe is in scope on a
            # serving route. Kept as an enforced invariant rather than a comment,
            # because the cost of it becoming reachable is served-without-execution.
            latch.latch_rollback("SERVING_PATH_SKIPPED_EXECUTION")
            raise ContractViolation(
                "cache parity serving may not skip its operation",
                request_id=composed.request_id,
            )
        result = outcome.fallback_value
        if not isinstance(result, ServiceResult):
            latch.latch_rollback("SERVING_PATH_RESULT_CONTRACT_INVALID")
            raise ContractViolation("cache parity serving produced an unknown result")
        if result.status >= 500:
            latch.latch_rollback("SERVING_PATH_PERSISTENCE_FAILED")
        return self._parity_response(result).with_headers(
            **{
                # A composed call whose outcome graph did not persist has no
                # audit trail; the composition already latched, and the caller
                # must not read the 200 as a complete record.
                COMPOSITION_OUTCOME_HEADER: (
                    "true" if composed.outcome_persisted else "false"
                )
            }
        )

    def compile_prompt_prefix(self, request: Request, params: dict[str, str]) -> Response:
        return self._parity_response(self.parity_api.compile_prompt_prefix(request.json()))

    def prepare_provider_prompt(self, request: Request, params: dict[str, str]) -> Response:
        return self._parity_response(
            _content_free_provider_prompt(
                self.parity_api.prepare_provider_prompt(request.json())
            )
        )

    def record_provider_usage(self, request: Request, params: dict[str, str]) -> Response:
        return self._parity_response(
            self.parity_api.record_provider_usage(request.json())
        )

    def append_context_ledger_event(
        self, request: Request, params: dict[str, str]
    ) -> Response:
        return self._parity_response(
            self.parity_api.append_context_event(
                params["streamId"],
                request.json(),
                request.header("Idempotency-Key") or "",
            )
        )

    def lookup_environment_snapshot(
        self, request: Request, params: dict[str, str]
    ) -> Response:
        project_id = request.param("projectId", "") or ""
        return self._serving_call(
            request,
            "environment_snapshot",
            project_id,
            lambda: self.parity_api.lookup_environment_snapshot(
                params["snapshotKey"], dict(request.query)
            ),
        )

    def decide_cache_affinity(self, request: Request, params: dict[str, str]) -> Response:
        payload = request.json()
        project_id = payload.get("project_id")
        return self._serving_call(
            request,
            "affinity",
            project_id if isinstance(project_id, str) else "",
            lambda: self.parity_api.decide_affinity(
                payload,
                principal_digest=request.authenticated_principal_digest or "",
            ),
        )

    def explain_cache_outcome(self, request: Request, params: dict[str, str]) -> Response:
        return self._parity_response(
            self.parity_api.explain_cache_outcome(
                params["requestId"], dict(request.query)
            )
        )

    def start_cache_parity_run(self, request: Request, params: dict[str, str]) -> Response:
        return self._parity_response(self.parity_api.start_parity_run(request.json()))

    def get_cache_parity_report(
        self, request: Request, params: dict[str, str]
    ) -> Response:
        return self._parity_response(
            self.parity_api.get_parity_report(params["reportId"], dict(request.query))
        )

    # -- status -----------------------------------------------------------
    def status(self, request: Request, params: dict[str, str]) -> Response:
        if self.serving_authorizer is None:
            parity_serving: dict[str, Any] = {
                "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
                "external_provider_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "serving": {layer: False for layer in SERVING_LAYERS},
                "wiring": {
                    "control_plane_authorizer": "NOT_WIRED",
                    "layers": {layer: "NOT_WIRED" for layer in SERVING_LAYERS},
                },
            }
        else:
            parity_serving = self.serving_authorizer.report() or {
                "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
                "external_provider_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "serving": {layer: False for layer in SERVING_LAYERS},
                "wiring": {"control_plane_authorizer": "WIRED", "plane": "DISABLED"},
            }
        return Response(
            200,
            {
                "api_version": API_VERSION,
                "schema_version": SCHEMA_VERSION,
                "tenant_id": self.tenant_id,
                "cas": self._tenant_cas_accounting(),
                "action_cache": self.action_cache.statistics(self.tenant_id),
                "runs": len(self.store.list_runs(self.tenant_id)),
                "cache_parity": parity_serving,
            },
        )

    def _tenant_cas_accounting(self) -> dict[str, int]:
        """Return logical/physical counters only for tenant-owned digests."""

        registrations = [
            artifact
            for artifact in self.store.list_artifacts(self.tenant_id)
            if artifact.storage_state is not ArtifactStorageState.DELETED
        ]
        present = [artifact for artifact in registrations if self.cas.contains(artifact.digest)]
        stored_bytes = 0
        for artifact in present:
            try:
                stored_bytes += self.cas.info(artifact.digest).stored_size
            except NotFound:
                continue
        return {
            "object_count": len(present),
            "stored_bytes": stored_bytes,
            "logical_bytes": sum(artifact.size_bytes for artifact in present),
            "quarantined_count": sum(
                1
                for artifact in registrations
                if artifact.storage_state is ArtifactStorageState.QUARANTINED
                or artifact.validation_level is ValidationLevel.QUARANTINED
                or self.cas.is_quarantined(artifact.digest)
            ),
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _action_lookup_reports_a_miss() -> None:
    """The control plane's fallback for an action lookup.

    ``GET /cache/actions/{actionKey}`` never runs a stage itself: when no exact
    result may be reused it answers 404, and the caller executes. Making that
    the composition's fallback keeps "did not reuse" and "must execute" the same
    branch instead of two branches that can drift apart.
    """


def _request_payload(request: Request) -> dict[str, Any]:
    """Semantic request fingerprint without retaining request payload bytes."""
    if isinstance(request.body, bytes):
        body = {
            "kind": "BYTES",
            "digest": sha256_bytes(request.body),
            "size_bytes": len(request.body),
        }
    elif isinstance(request.body, dict):
        body = {
            "kind": "JSON",
            "digest": digest_of(request.body),
        }
    else:
        body = {"kind": "NONE", "digest": digest_of(None)}
    semantic_headers = {
        name: (request.header(name) or "").strip()
        for name in IDEMPOTENCY_SEMANTIC_HEADERS
    }
    principal_digest = request.authenticated_principal_digest
    if principal_digest is not None:
        principal_digest = require_digest(principal_digest)
    return {
        "method": request.method.upper(),
        "path": request.path,
        "authenticated_principal_digest": principal_digest,
        "body": body,
        "query": dict(sorted(dict(request.query).items())),
        "semantic_headers": semantic_headers,
    }


def _content_free_provider_prompt(result: ServiceResult) -> ServiceResult:
    """Exchange the transient provider payload for its digest.

    :meth:`CacheControlPlane.handle` persists the response it returns, byte
    for byte, as the durable idempotency record and replays it later out of a
    store whose access rules are not the prompt's.  The assembled provider
    payload is the only field of this operation that carries raw tenant
    prompt bytes, so the control plane never puts it on the wire in the first
    place: response and durable record stay identical, which is what makes a
    replay a replay.  A caller that must actually issue the model request
    holds the segments it just submitted and uses
    :meth:`ParityApiService.prepare_provider_prompt` in process.
    """

    body = dict(result.body)
    provider_request = body.get("provider_request")
    if not isinstance(provider_request, Mapping):
        return result
    projected: dict[str, Any] = {
        key: value for key, value in provider_request.items() if key != "payload"
    }
    projected["payload_digest"] = digest_of(provider_request.get("payload"))
    projected["payload_retained"] = False
    body["provider_request"] = projected
    return ServiceResult(result.status, body)


def _idempotency_response(response: Response) -> dict[str, Any]:
    if isinstance(response.body, bytes):
        body: dict[str, Any] = {
            "kind": "BYTES",
            "base64": base64.b64encode(response.body).decode("ascii"),
        }
    else:
        body = {"kind": "JSON", "value": response.body}
    return {
        "schema_version": "1.0.0",
        "status": response.status,
        "headers": dict(sorted((response.headers or {}).items())),
        "body": body,
    }


def _response_from_idempotency(value: Any) -> Response:
    if not isinstance(value, dict):
        raise ContractViolation("stored idempotency response is not an object")
    # Backward-compatible replay for complete records written before the
    # crash-safe response envelope existed.
    if value.get("schema_version") != "1.0.0":
        body = value.get("body", {})
        if body == {"binary": True}:
            raise IdempotencyOutcomeUnknown(
                "legacy binary response cannot be reconstructed safely",
                state="OUTCOME_UNKNOWN",
            )
        return Response(int(value.get("status", 200)), body, {})
    headers = value.get("headers")
    body = value.get("body")
    if not isinstance(headers, dict) or not isinstance(body, dict):
        raise ContractViolation("stored idempotency response envelope is invalid")
    kind = body.get("kind")
    if kind == "JSON":
        payload: dict[str, Any] | bytes = body.get("value", {})
        if not isinstance(payload, dict):
            raise ContractViolation("stored JSON idempotency response is invalid")
    elif kind == "BYTES":
        encoded = body.get("base64")
        if not isinstance(encoded, str):
            raise ContractViolation("stored binary idempotency response is invalid")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ContractViolation("stored binary idempotency response is invalid") from exc
    else:
        raise ContractViolation("stored idempotency response kind is invalid")
    return Response(
        int(value.get("status", 200)),
        payload,
        {str(key): str(item) for key, item in headers.items()},
    )


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
    """Expose the control plane behind a trusted authenticated middleware.

    ``Authorization`` and tenant headers are deliberately ignored. The
    deployment boundary must authenticate the peer and inject an
    :class:`AuthenticatedHttpContext` under
    :data:`AUTHENTICATED_CONTEXT_ENVIRON_KEY`.
    """

    def application(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        from urllib.parse import parse_qsl

        def reject(response: Response) -> Iterable[bytes]:
            payload = json.dumps(response.body, sort_keys=True).encode("utf-8")
            start_response(
                f"{response.status} ",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(payload))),
                ],
            )
            return [payload]

        authenticated = environ.get(AUTHENTICATED_CONTEXT_ENVIRON_KEY)
        if not isinstance(authenticated, AuthenticatedHttpContext):
            return reject(
                _error(
                    401,
                    "AUTHENTICATION_REQUIRED",
                    "trusted authenticated WSGI context is required",
                )
            )
        if authenticated.tenant_id != plane.tenant_id:
            return reject(
                _error(
                    403,
                    "PERMISSION_DENIED",
                    "authenticated tenant is not authorized for this control plane",
                )
            )

        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            length = -1
        if length < 0:
            response = _error(400, "CONTENT_LENGTH_INVALID", "Content-Length must be non-negative")
            payload = json.dumps(response.body, sort_keys=True).encode("utf-8")
            start_response(
                f"{response.status} ",
                [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))],
            )
            return [payload]
        if length > MAX_REQUEST_BODY_BYTES:
            response = _error(
                413,
                "REQUEST_TOO_LARGE",
                "request body exceeds the configured byte limit",
                {"maximum_bytes": MAX_REQUEST_BODY_BYTES},
            )
            payload = json.dumps(response.body, sort_keys=True).encode("utf-8")
            start_response(
                f"{response.status} ",
                [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))],
            )
            return [payload]
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
            authenticated_principal_digest=authenticated.principal_digest,
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
