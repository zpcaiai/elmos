from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any

from .canonical import canonical_json, digest_value, validate_identifier
from .contracts import ProofRunState, Scope, TrustedIdentity
from .artifact_store import (
    ArtifactEnvelopeCipher,
    ArtifactStore,
    ContentAddressedArtifactStore,
)
from .bundles import EvidenceBundleService, EvidenceBundleSigner
from .executor import LocalBoundedExecutor
from .execution import ExecutionPermitSigner, ResourceLimits, ToolchainRegistration
from .events import EventPublisher, OutboxDispatcher
from .gate_evidence import GateEvidenceVerifier
from .governance import GovernanceAuthorizationError, GovernanceService
from .handlers import HandlerContext
from .observability import FormalObservabilityService, TelemetryExporter
from .production import ProductionSkillExecutor
from .registry import SkillRegistry
from .store import StateStore


class RuntimeAuthorizationError(PermissionError):
    pass


class RuntimeRequestError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    account_concurrency: int = 3
    max_request_bytes: int = 2 * 1024 * 1024
    artifact_root: Path | None = None
    artifact_envelope_cipher: ArtifactEnvelopeCipher | None = field(
        default=None, repr=False
    )
    artifact_store_adapter: ArtifactStore | None = None
    execution_root: Path | None = None
    execution_limits: ResourceLimits = field(default_factory=ResourceLimits)
    execution_permit_signer: ExecutionPermitSigner | None = None
    toolchains: tuple[ToolchainRegistration, ...] = ()
    telemetry_exporter: TelemetryExporter | None = None
    bundle_signer: EvidenceBundleSigner | None = None
    gate_evidence_verifier: GateEvidenceVerifier | None = None
    event_publisher: EventPublisher | None = None
    outbox_max_attempts: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.account_concurrency, int) or isinstance(
            self.account_concurrency, bool
        ):
            raise ValueError("account_concurrency must be an integer")
        if not 1 <= self.account_concurrency <= 3:
            raise ValueError("account_concurrency must be between 1 and 3")
        if not isinstance(self.max_request_bytes, int) or isinstance(
            self.max_request_bytes, bool
        ):
            raise ValueError("max_request_bytes must be an integer")
        if self.max_request_bytes < 1 or self.max_request_bytes > 16 * 1024 * 1024:
            raise ValueError("max_request_bytes is outside the allowed bound")
        if not isinstance(self.execution_limits, ResourceLimits):
            raise ValueError("execution_limits must be ResourceLimits")
        if self.artifact_root is not None and self.artifact_store_adapter is not None:
            raise ValueError(
                "artifact_root and artifact_store_adapter are mutually exclusive"
            )
        if self.artifact_root is not None and self.artifact_envelope_cipher is None:
            raise ValueError(
                "artifact_envelope_cipher is required when artifact_root is configured"
            )
        if self.artifact_root is None and self.artifact_envelope_cipher is not None:
            raise ValueError(
                "artifact_envelope_cipher may only be used with artifact_root"
            )
        if self.artifact_store_adapter is not None and any(
            not callable(getattr(self.artifact_store_adapter, method, None))
            for method in ("put", "get", "metadata", "verify_reference", "delete")
        ):
            raise ValueError(
                "artifact_store_adapter does not implement the CAS contract"
            )
        if not isinstance(self.toolchains, tuple) or any(
            not isinstance(item, ToolchainRegistration) for item in self.toolchains
        ):
            raise ValueError("toolchains must be a tuple of ToolchainRegistration")
        if self.event_publisher is not None and not callable(
            getattr(self.event_publisher, "publish", None)
        ):
            raise ValueError("event_publisher must implement publish")
        if self.gate_evidence_verifier is not None and not callable(
            getattr(self.gate_evidence_verifier, "verify", None)
        ):
            raise ValueError("gate_evidence_verifier must implement verify")
        if (
            not isinstance(self.outbox_max_attempts, int)
            or isinstance(self.outbox_max_attempts, bool)
            or not 1 <= self.outbox_max_attempts <= 100
        ):
            raise ValueError("outbox_max_attempts must be between 1 and 100")


class FormalAssuranceRuntime:
    """The only dispatch authority for the 60 exact Formal Assurance Skills."""

    def __init__(
        self,
        *,
        registry: SkillRegistry | None = None,
        store: StateStore | None = None,
        config: RuntimeConfig | None = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self._owns_store = store is None
        self._closed = False
        self.store = store if store is not None else StateStore()
        self.artifact_store = self.config.artifact_store_adapter
        if self.artifact_store is None and self.config.artifact_root is not None:
            assert self.config.artifact_envelope_cipher is not None
            self.artifact_store = ContentAddressedArtifactStore(
                self.config.artifact_root,
                envelope_cipher=self.config.artifact_envelope_cipher,
            )
        if registry is None:
            repository_root = Path(__file__).resolve().parents[4]
            metadata = (
                repository_root / "docs/formal-assurance-kernel/skill-registry.json"
            )
            registry = SkillRegistry(metadata if metadata.is_file() else None)
        self.registry = registry
        self.local_executor = LocalBoundedExecutor(self.store, self.artifact_store)
        self.observability = FormalObservabilityService(
            self.store, self.config.telemetry_exporter
        )
        self.governance = GovernanceService(self.store)
        self.evidence_bundles = EvidenceBundleService(
            self.store, self.artifact_store, self.config.bundle_signer
        )
        self.outbox_dispatcher = (
            OutboxDispatcher(
                self.store,
                self.config.event_publisher,
                max_attempts=self.config.outbox_max_attempts,
            )
            if self.config.event_publisher is not None
            else None
        )
        self.production_executor = ProductionSkillExecutor(
            store=self.store,
            artifact_store=self.artifact_store,
            permit_signer=self.config.execution_permit_signer,
            toolchains=self.config.toolchains,
            limits=self.config.execution_limits,
            execution_root=self.config.execution_root,
            observability=self.observability,
        )

    def close(self) -> None:
        """Release resources created by this runtime without closing injections."""
        if self._closed:
            return
        if self._owns_store:
            self.store.close()
        self._closed = True

    def __enter__(self) -> FormalAssuranceRuntime:
        if self._closed:
            raise RuntimeError("formal assurance runtime is closed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_skills(self) -> list[dict[str, Any]]:
        return self.registry.list()

    def dispatch(
        self,
        skill_id: str,
        payload: dict[str, Any],
        identity: TrustedIdentity,
        *,
        subject_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("request payload must be an object")
        binding = self.registry.get(skill_id)
        scope = self._authorized_scope(
            payload.get("scope"), identity, action="dispatch-skill"
        )
        subject = validate_identifier(
            subject_id or payload.get("subjectId"), "subjectId"
        )
        key = validate_identifier(
            idempotency_key or payload.get("idempotencyKey"), "idempotencyKey"
        )
        storage_key = digest_value({"scope": scope.to_dict(), "idempotencyKey": key})
        request_payload = dict(payload)
        request_payload.pop("scope", None)
        request_payload.pop("subjectId", None)
        request_payload.pop("idempotencyKey", None)
        if len(canonical_json(request_payload)) > self.config.max_request_bytes:
            raise RuntimeRequestError("request payload exceeds local bound")
        request_document = {
            "skillId": skill_id,
            "scope": scope.to_dict(),
            "subjectId": subject,
            "payload": request_payload,
        }
        request_digest = digest_value(request_document)
        replay = self.store.get_idempotent(scope.tenant_id, storage_key, request_digest)
        if replay is not None:
            return replay
        context = HandlerContext(
            skill_id=skill_id,
            handler_id=binding.handler_id,
            capability_state=binding.capability_state,
            scope=scope,
            subject_id=subject,
            identity=identity,
            payload=request_payload,
            store=self.store,
            artifact_store=self.artifact_store,
            production=self.production_executor,
            gate_evidence_verifier=self.config.gate_evidence_verifier,
        )
        started_ns = time.monotonic_ns()
        outcome = self.registry.handler(skill_id)(context)
        duration_micros = max(0, (time.monotonic_ns() - started_ns) // 1000)
        trace_id = request_payload.get("traceId")
        if not isinstance(trace_id, str) or not trace_id:
            trace_id = "trace-" + request_digest.removeprefix("sha256:")[:32]
        validate_identifier(trace_id, "traceId")
        self.observability.record_invocation(
            scope,
            skill_id=skill_id,
            proof_status=outcome.proof_status.value,
            duration_micros=duration_micros,
            trace_id=trace_id,
        )
        response = outcome.to_dict()
        response["requestDigest"] = request_digest
        response["scope"] = scope.to_dict()
        return self.store.complete_idempotent_invocation(
            scope, storage_key, skill_id, subject, request_digest, response
        )

    def submit_run(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("run payload must be an object")
        self._require_exact_body(
            payload,
            {
                "scope",
                "runId",
                "id",
                "tenant",
                "obligationId",
                "accountConcurrency",
                "engine",
                "engineVersion",
                "mode",
                "formulaHash",
                "bound",
                "options",
                "traceId",
                "state",
                "fencingToken",
            },
        )
        scope = self._authorized_scope(
            payload.get("scope"), identity, action="submit-proof-run"
        )
        run_id = validate_identifier(
            payload.get("runId", payload.get("id")), "runId"
        )
        if payload.get("id") is not None and payload["id"] != run_id:
            raise RuntimeRequestError("id and runId aliases disagree")
        tenant = payload.get("tenant")
        if tenant is not None:
            if not isinstance(tenant, dict) or set(tenant) - {
                "tenantId",
                "accountId",
                "projectId",
            }:
                raise RuntimeRequestError("tenant binding is invalid")
            expected_tenant = {
                "tenantId": scope.tenant_id,
                "accountId": scope.account_id,
                "projectId": scope.project_id,
            }
            if any(
                tenant.get(key) != value
                for key, value in expected_tenant.items()
                if key in tenant or value is not None
            ):
                raise RuntimeAuthorizationError(
                    "run tenant binding does not match trusted scope"
                )
        if payload.get("state", "QUEUED") != "QUEUED":
            raise RuntimeRequestError("new proof runs must begin in QUEUED state")
        fencing_token = payload.get("fencingToken", 1)
        if (
            not isinstance(fencing_token, int)
            or isinstance(fencing_token, bool)
            or fencing_token != 1
        ):
            raise RuntimeRequestError(
                "new proof runs must begin with fencingToken 1"
            )
        concurrency = payload.get(
            "accountConcurrency", self.config.account_concurrency
        )
        if not isinstance(concurrency, int) or isinstance(concurrency, bool):
            raise RuntimeRequestError("accountConcurrency must be an integer")
        if concurrency > self.config.account_concurrency:
            raise RuntimeAuthorizationError(
                "requested account concurrency exceeds the runtime policy"
            )
        run = self.store.submit_run(
            scope,
            run_id,
            validate_identifier(payload.get("obligationId"), "obligationId"),
            concurrency,
            engine=str(payload.get("engine", "local")),
            engine_version=str(payload.get("engineVersion", "1.0.0")),
            mode=str(payload.get("mode", "BOUNDED")),
            formula_hash=payload.get("formulaHash"),
            bound=payload.get("bound"),
            options=payload.get("options"),
            trace_id=payload.get("traceId"),
        )
        return self._run_document(run)

    def get_run(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("run lookup payload must be an object")
        self._require_exact_body(payload, {"scope", "runId"})
        run = self.store.get_run(
            self._authorized_scope(
                payload.get("scope"), identity, action="read-proof-run"
            ),
            validate_identifier(payload.get("runId"), "runId"),
        )
        return self._run_document(run)

    def control_run(
        self,
        payload: dict[str, Any],
        identity: TrustedIdentity,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("run action payload must be an object")
        self._require_exact_body(
            payload,
            {
                "scope",
                "runId",
                "action",
                "workerId",
                "token",
                "idempotencyKey",
            },
        )
        scope = self._authorized_scope(
            payload.get("scope"), identity, action="control-proof-run"
        )
        run_id = validate_identifier(payload.get("runId"), "runId")
        action = str(payload.get("action", ""))
        transitions = {
            "PAUSE": ProofRunState.PAUSED,
            "RESUME": ProofRunState.RUNNING,
            "CANCEL": ProofRunState.CANCEL_REQUESTED,
        }
        if action not in transitions:
            raise RuntimeRequestError("action must be PAUSE, RESUME or CANCEL")
        if payload.get("workerId") is not None or payload.get("token") is not None:
            if payload.get("workerId") is None or payload.get("token") is None:
                raise RuntimeRequestError(
                    "workerId and token must be supplied together"
                )
            worker_id = validate_identifier(payload.get("workerId"), "workerId")
            if worker_id != identity.actor_id and not set(identity.roles) & {
                "formal-assurance-executor",
                "formal-assurance-admin",
                "admin",
            }:
                raise RuntimeAuthorizationError(
                    "control worker must match the authenticated actor"
                )
            raw_token = payload.get("token")
            if isinstance(raw_token, bool) or not isinstance(raw_token, (int, str)):
                raise RuntimeRequestError("token must be an integer")
            try:
                token = int(raw_token)
            except ValueError as exc:
                raise RuntimeRequestError("token must be an integer") from exc
            run = self.store.authorized_transition(
                scope, run_id, worker_id, token, transitions[action]
            )
            return self._run_document(run)
        if not set(identity.roles) & {
            "formal-assurance-control",
            "formal-assurance-admin",
            "admin",
        }:
            raise RuntimeAuthorizationError(
                "proof run control requires an explicit control role"
            )
        key = validate_identifier(payload.get("idempotencyKey"), "idempotencyKey")
        request_digest = digest_value(
            {"scope": scope.to_dict(), "runId": run_id, "action": action}
        )
        storage_key = digest_value({"scope": scope.to_dict(), "idempotencyKey": key})
        replay = self.store.get_idempotent(scope.tenant_id, storage_key, request_digest)
        if replay is not None:
            return replay
        response = self._run_document(self.store.control_run(scope, run_id, action))
        self.store.put_idempotent(
            scope.tenant_id, storage_key, request_digest, response
        )
        return response

    def checkpoint_run(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("checkpoint payload must be an object")
        self._require_exact_body(
            payload,
            {
                "scope",
                "runId",
                "workerId",
                "token",
                "checkpoint",
                "progress",
                "idempotencyKey",
            },
        )
        scope = self._authorized_scope(
            payload.get("scope"), identity, action="checkpoint-proof-run"
        )
        run_id = validate_identifier(payload.get("runId"), "runId")
        worker_id = validate_identifier(payload.get("workerId"), "workerId")
        if worker_id != identity.actor_id and not set(identity.roles) & {
            "formal-assurance-executor",
            "formal-assurance-admin",
            "admin",
        }:
            raise RuntimeAuthorizationError(
                "checkpoint worker must match the authenticated actor"
            )
        raw_token = payload.get("token")
        if isinstance(raw_token, bool) or not isinstance(raw_token, (int, str)):
            raise RuntimeRequestError("token must be an integer")
        try:
            token = int(raw_token)
        except ValueError as exc:
            raise RuntimeRequestError("token must be an integer") from exc
        checkpoint = payload.get("checkpoint")
        progress = payload.get("progress")
        if not isinstance(checkpoint, dict) or not isinstance(progress, dict):
            raise RuntimeRequestError("checkpoint and progress must be objects")
        key = validate_identifier(payload.get("idempotencyKey"), "idempotencyKey")
        request_document = {
            "scope": scope.to_dict(),
            "runId": run_id,
            "workerId": worker_id,
            "token": token,
            "checkpoint": checkpoint,
            "progress": progress,
        }
        request_digest = digest_value(request_document)
        storage_key = digest_value({"scope": scope.to_dict(), "idempotencyKey": key})
        response = self._run_document(
            self.store.checkpoint_run(
                scope,
                run_id,
                worker_id,
                token,
                checkpoint,
                progress,
                operation_key=storage_key,
                request_digest=request_digest,
            )
        )
        return response

    def retry_run(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("retry payload must be an object")
        self._require_exact_body(
            payload,
            {
                "scope",
                "runId",
                "retryRunId",
                "maximumAttempts",
                "idempotencyKey",
            },
        )
        if not set(identity.roles) & {
            "formal-assurance-control",
            "formal-assurance-admin",
            "admin",
        }:
            raise RuntimeAuthorizationError(
                "proof run retry requires an explicit control role"
            )
        scope = self._authorized_scope(
            payload.get("scope"), identity, action="retry-proof-run"
        )
        run_id = validate_identifier(payload.get("runId"), "runId")
        retry_run_id = validate_identifier(payload.get("retryRunId"), "retryRunId")
        key = validate_identifier(payload.get("idempotencyKey"), "idempotencyKey")
        maximum_attempts = payload.get("maximumAttempts")
        if maximum_attempts is not None and (
            not isinstance(maximum_attempts, int)
            or isinstance(maximum_attempts, bool)
        ):
            raise RuntimeRequestError("maximumAttempts must be an integer")
        request_document = {
            "scope": scope.to_dict(),
            "runId": run_id,
            "retryRunId": retry_run_id,
            "maximumAttempts": maximum_attempts,
        }
        request_digest = digest_value(request_document)
        storage_key = digest_value({"scope": scope.to_dict(), "idempotencyKey": key})
        response = self._run_document(
            self.store.retry_run(
                scope,
                run_id,
                retry_run_id,
                account_concurrency=self.config.account_concurrency,
                maximum_attempts=maximum_attempts,
                operation_key=storage_key,
                request_digest=request_digest,
            )
        )
        return response

    def execute_local_run(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("local execution payload must be an object")
        raw_token = payload.get("token")
        if isinstance(raw_token, bool) or not isinstance(raw_token, (int, str)):
            raise RuntimeRequestError("token must be an integer")
        try:
            token = int(raw_token)
        except ValueError as exc:
            raise RuntimeRequestError("token must be an integer") from exc
        evaluation = payload.get("evaluation")
        if not isinstance(evaluation, dict):
            raise RuntimeRequestError("evaluation must be an object")
        assumption_hash = payload.get("assumptionHash")
        tcb_hash = payload.get("tcbHash")
        if not isinstance(assumption_hash, str) or not isinstance(tcb_hash, str):
            raise RuntimeRequestError("assumptionHash and tcbHash are required")
        run = self.local_executor.execute(
            self._authorized_scope(
                payload.get("scope"), identity, action="execute-local-proof-run"
            ),
            validate_identifier(payload.get("runId"), "runId"),
            validate_identifier(payload.get("workerId"), "workerId"),
            token,
            evaluation,
            assumption_hash=assumption_hash,
            tcb_hash=tcb_hash,
        )
        return self._run_document(run)

    def register_assumption(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        return self._governed_mutation(
            payload,
            identity,
            "register-assumption",
            lambda scope, body: self.governance.register_assumption(
                scope, identity, body
            ),
        )

    def register_trusted_component(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        return self._governed_mutation(
            payload,
            identity,
            "register-trusted-component",
            lambda scope, body: self.governance.register_trusted_component(
                scope, identity, body
            ),
        )

    def propose_waiver(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        return self._governed_mutation(
            payload,
            identity,
            "propose-waiver",
            lambda scope, body: self.governance.propose_waiver(scope, identity, body),
        )

    def approve_waiver(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        def mutation(scope: Scope, body: dict[str, Any]) -> dict[str, Any]:
            self._require_exact_body(body, {"waiverId", "approvalRole"})
            return self.governance.approve_waiver(
                scope,
                identity,
                validate_identifier(body.get("waiverId"), "waiverId"),
                str(body.get("approvalRole", "")),
            )

        return self._governed_mutation(payload, identity, "approve-waiver", mutation)

    def revoke_waiver(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        def mutation(scope: Scope, body: dict[str, Any]) -> dict[str, Any]:
            self._require_exact_body(body, {"waiverId", "reason"})
            return self.governance.revoke_waiver(
                scope,
                identity,
                validate_identifier(body.get("waiverId"), "waiverId"),
                str(body.get("reason", "")),
            )

        return self._governed_mutation(payload, identity, "revoke-waiver", mutation)

    def report_drift(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        return self._governed_mutation(
            payload,
            identity,
            "report-proof-drift",
            lambda scope, body: self.governance.report_drift(scope, identity, body),
        )

    def build_evidence_bundle(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        def mutation(scope: Scope, body: dict[str, Any]) -> dict[str, Any]:
            self._require_exact_body(body, {"subjectId", "redactionPolicy", "sign"})
            return self.evidence_bundles.build(
                scope,
                identity,
                subject_id=validate_identifier(body.get("subjectId"), "subjectId"),
                redaction_policy=str(body.get("redactionPolicy", "")),
                sign=body.get("sign", True),
            )

        return self._governed_mutation(
            payload, identity, "build-evidence-bundle", mutation
        )

    def verify_evidence_bundle(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        def mutation(scope: Scope, body: dict[str, Any]) -> dict[str, Any]:
            self._require_exact_body(body, {"bundleId"})
            return self.evidence_bundles.verify(
                scope,
                bundle_id=validate_identifier(body.get("bundleId"), "bundleId"),
            )

        return self._governed_mutation(
            payload, identity, "verify-evidence-bundle", mutation
        )

    def dispatch_outbox(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        """Deliver one bounded outbox batch through an operator-supplied adapter."""
        if not isinstance(payload, dict):
            raise RuntimeRequestError("outbox dispatch payload must be an object")
        scope = self._authorized_scope(
            payload.get("scope"), identity, action="dispatch-event-outbox"
        )
        if not set(identity.roles) & {
            "formal-assurance-event-publisher",
            "formal-assurance-admin",
            "admin",
        }:
            error = RuntimeAuthorizationError(
                "outbox dispatch requires an explicit event-publisher role"
            )
            self.store.record_security_audit(
                identity,
                action="dispatch-event-outbox",
                decision="DENY",
                reason=str(error),
                request_metadata={"scopeDigest": digest_value(scope.to_dict())},
            )
            setattr(error, "audit_recorded", True)
            raise error
        if self.outbox_dispatcher is None:
            raise RuntimeRequestError("event publisher is not configured")
        unknown = set(payload) - {"scope", "limit"}
        if unknown:
            raise RuntimeRequestError(
                "outbox dispatch contains unknown fields: " + ", ".join(sorted(unknown))
            )
        limit = payload.get("limit", 100)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise RuntimeRequestError("outbox dispatch limit must be an integer")
        result = self.outbox_dispatcher.dispatch(scope, limit=limit).to_dict()
        self.store.record_security_audit(
            identity,
            action="dispatch-event-outbox",
            decision="ALLOW",
            reason="bounded outbox batch dispatched",
            request_metadata={
                "scopeDigest": digest_value(scope.to_dict()),
                "resultDigest": digest_value(result),
            },
        )
        return {
            **result,
            "deliveryEvidenceStatus": "LOCAL_EXECUTED_SELF_ATTESTED",
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
        }

    def _governed_mutation(
        self,
        payload: dict[str, Any],
        identity: TrustedIdentity,
        action: str,
        callback: Any,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("governance payload must be an object")
        scope = self._authorized_scope(payload.get("scope"), identity, action=action)
        key = validate_identifier(payload.get("idempotencyKey"), "idempotencyKey")
        body = dict(payload)
        body.pop("scope", None)
        body.pop("idempotencyKey", None)
        if len(canonical_json(body)) > self.config.max_request_bytes:
            raise RuntimeRequestError("governance payload exceeds local bound")
        request_digest = digest_value(
            {"action": action, "scope": scope.to_dict(), "body": body}
        )
        storage_key = digest_value(
            {
                "action": action,
                "scope": scope.to_dict(),
                "idempotencyKey": key,
            }
        )
        replay = self.store.get_idempotent(scope.tenant_id, storage_key, request_digest)
        if replay is not None:
            return replay
        try:
            response = callback(scope, body)
        except GovernanceAuthorizationError as exc:
            self.store.record_security_audit(
                identity,
                action=action,
                decision="DENY",
                reason=str(exc),
                request_metadata={
                    "action": action,
                    "requestDigest": request_digest,
                },
            )
            setattr(exc, "audit_recorded", True)
            raise
        if not isinstance(response, dict):
            raise RuntimeRequestError(
                "governance mutation returned an invalid response"
            )
        self.store.record_security_audit(
            identity,
            action=action,
            decision="ALLOW",
            reason="authorized governance mutation committed",
            request_metadata={"action": action, "requestDigest": request_digest},
        )
        self.store.put_idempotent(
            scope.tenant_id, storage_key, request_digest, response
        )
        return response

    @staticmethod
    def _require_exact_body(body: dict[str, Any], allowed: set[str]) -> None:
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise RuntimeRequestError(
                "request contains unknown fields: " + ", ".join(unknown)
            )

    @staticmethod
    def _run_document(run: dict[str, Any]) -> dict[str, Any]:
        """Serialize the local persistence row to the package API contract."""
        result = {
            "id": run["run_id"],
            "tenant": {
                "tenantId": run["tenant_id"],
                "accountId": run["account_id"],
                "projectId": run.get("project_id"),
            },
            "obligationId": run["obligation_id"],
            "engine": run["engine"],
            "engineVersion": run["engine_version"],
            "mode": run["mode"],
            "state": run["state"],
            "ownerId": run.get("owner_id"),
            "fencingToken": run["fencing_token"],
            "startedAt": run.get("started_at") or run["created_at"],
            "completedAt": run.get("completed_at"),
            "wallClockMs": run.get("wall_clock_ms"),
            "traceId": run.get("trace_id"),
            "retryOf": run.get("retry_parent_run_id"),
            "retryRootRunId": run.get("retry_root_run_id"),
            "retryAttempt": run.get("retry_attempt")
            if run.get("retry_root_run_id") is not None
            else None,
            "retryMaximumAttempts": run.get("retry_maximum_attempts"),
            "certification": "NOT_CERTIFIED",
        }
        if run.get("bound_json"):
            result["bound"] = json.loads(run["bound_json"])
        if run.get("options_json"):
            result["options"] = json.loads(run["options_json"])
        if run.get("result_json"):
            result["result"] = json.loads(run["result_json"])
        if run.get("checkpoint_json"):
            result["checkpoint"] = json.loads(run["checkpoint_json"])
        if "localEvidence" in run:
            result["localEvidence"] = run["localEvidence"]
        return {key: value for key, value in result.items() if value is not None}

    def _scope(self, value: Any, identity: TrustedIdentity) -> Scope:
        if not isinstance(value, dict):
            raise RuntimeRequestError("scope is required and must be an object")
        tenant_id = value.get("tenantId")
        if tenant_id != identity.tenant_id:
            raise RuntimeAuthorizationError(
                "request tenant does not match trusted identity"
            )
        project_id = value.get("projectId")
        if identity.project_id is not None and project_id != identity.project_id:
            raise RuntimeAuthorizationError(
                "request project does not match trusted identity"
            )
        try:
            return Scope(
                tenant_id=tenant_id,
                account_id=value["accountId"],
                project_id=project_id,
                source_artifact_digest=value["sourceArtifactDigest"],
                target_artifact_digest=value["targetArtifactDigest"],
                environment_digest=value["environmentDigest"],
                workload_key=value["workloadKey"],
                data_classification=value.get("dataClassification", "confidential"),
            )
        except (KeyError, ValueError) as exc:
            raise RuntimeRequestError(str(exc)) from exc

    def _authorized_scope(
        self,
        value: Any,
        identity: TrustedIdentity,
        *,
        action: str,
    ) -> Scope:
        """Resolve trusted scope and durably audit identity-boundary denials."""
        try:
            return self._scope(value, identity)
        except RuntimeAuthorizationError as exc:
            self.store.record_security_audit(
                identity,
                action=action,
                decision="DENY",
                reason=str(exc),
                request_metadata={
                    "action": action,
                    "claimedTenantDigest": digest_value(
                        str(value.get("tenantId"))
                        if isinstance(value, dict)
                        else type(value).__name__
                    ),
                },
            )
            setattr(exc, "audit_recorded", True)
            raise


__all__ = [
    "FormalAssuranceRuntime",
    "RuntimeAuthorizationError",
    "RuntimeConfig",
    "RuntimeRequestError",
]
