from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any

from .canonical import canonical_json, digest_value, validate_identifier
from .contracts import ProofRunState, Scope, TrustedIdentity
from .artifact_store import ContentAddressedArtifactStore
from .executor import LocalBoundedExecutor
from .execution import ExecutionPermitSigner, ResourceLimits, ToolchainRegistration
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
    execution_root: Path | None = None
    execution_limits: ResourceLimits = field(default_factory=ResourceLimits)
    execution_permit_signer: ExecutionPermitSigner | None = None
    toolchains: tuple[ToolchainRegistration, ...] = ()
    telemetry_exporter: TelemetryExporter | None = None

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
        if not isinstance(self.toolchains, tuple) or any(
            not isinstance(item, ToolchainRegistration) for item in self.toolchains
        ):
            raise ValueError("toolchains must be a tuple of ToolchainRegistration")


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
        self.store = store or StateStore()
        self.artifact_store = (
            ContentAddressedArtifactStore(self.config.artifact_root)
            if self.config.artifact_root is not None
            else None
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
        self.production_executor = ProductionSkillExecutor(
            store=self.store,
            artifact_store=self.artifact_store,
            permit_signer=self.config.execution_permit_signer,
            toolchains=self.config.toolchains,
            limits=self.config.execution_limits,
            execution_root=self.config.execution_root,
            observability=self.observability,
        )

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
        scope = self._scope(payload.get("scope"), identity)
        subject = validate_identifier(
            subject_id or payload.get("subjectId"), "subjectId"
        )
        key = validate_identifier(
            idempotency_key or payload.get("idempotencyKey"), "idempotencyKey"
        )
        storage_key = digest_value(
            {"scope": scope.to_dict(), "idempotencyKey": key}
        )
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
        replay = self.store.get_idempotent(
            scope.tenant_id, storage_key, request_digest
        )
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
        scope = self._scope(payload.get("scope"), identity)
        try:
            concurrency = int(
                payload.get("accountConcurrency", self.config.account_concurrency)
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeRequestError("accountConcurrency must be an integer") from exc
        if concurrency > self.config.account_concurrency:
            raise RuntimeAuthorizationError(
                "requested account concurrency exceeds the runtime policy"
            )
        run = self.store.submit_run(
            scope,
            validate_identifier(payload.get("runId"), "runId"),
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

    def get_run(self, payload: dict[str, Any], identity: TrustedIdentity) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeRequestError("run lookup payload must be an object")
        run = self.store.get_run(
            self._scope(payload.get("scope"), identity),
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
        scope = self._scope(payload.get("scope"), identity)
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
            worker_id = validate_identifier(payload.get("workerId"), "workerId")
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
        storage_key = digest_value(
            {"scope": scope.to_dict(), "idempotencyKey": key}
        )
        replay = self.store.get_idempotent(
            scope.tenant_id, storage_key, request_digest
        )
        if replay is not None:
            return replay
        response = self._run_document(self.store.control_run(scope, run_id, action))
        self.store.put_idempotent(
            scope.tenant_id, storage_key, request_digest, response
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
            self._scope(payload.get("scope"), identity),
            validate_identifier(payload.get("runId"), "runId"),
            validate_identifier(payload.get("workerId"), "workerId"),
            token,
            evaluation,
            assumption_hash=assumption_hash,
            tcb_hash=tcb_hash,
        )
        return self._run_document(run)

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
            "certification": "NOT_CERTIFIED",
        }
        if run.get("bound_json"):
            result["bound"] = json.loads(run["bound_json"])
        if run.get("options_json"):
            result["options"] = json.loads(run["options_json"])
        if run.get("result_json"):
            result["result"] = json.loads(run["result_json"])
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


__all__ = [
    "FormalAssuranceRuntime",
    "RuntimeAuthorizationError",
    "RuntimeConfig",
    "RuntimeRequestError",
]
