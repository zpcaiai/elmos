"""Durable execution service joining strict handlers, SQLite, and local CAS."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import ContentAddressedArtifactStore
from .canonical import canonical_digest, canonical_json_bytes
from .contracts import (
    ArtifactInput,
    CreateRunRequest,
    EvidenceInput,
    EvidenceState,
    IdempotencyDisposition,
    RunRecord,
    RunStatus,
)
from .runtime import SKILL_REGISTRY, RuntimeRequest, SkillRuntimeError, dispatch_skill
from .store import ProjectIntelligenceStore


class FailureFinalizationError(RuntimeError):
    """Raised when a created run cannot be durably terminalized after retries."""


_SAFE_ERROR_TYPE = re.compile(r"[^A-Za-z0-9_.-]+")


class ProjectIntelligenceService:
    """Execute one allowlisted Skill and persist its exact local evidence.

    The service writes only to its caller-owned SQLite database and private
    artifact root. It cannot execute repository content or perform SCM,
    connector, deployment, debug-adapter, provider, or certification effects.
    """

    def __init__(
        self,
        store: ProjectIntelligenceStore,
        artifacts: ContentAddressedArtifactStore,
    ) -> None:
        if not isinstance(store, ProjectIntelligenceStore):
            raise TypeError("store must be ProjectIntelligenceStore")
        if not isinstance(artifacts, ContentAddressedArtifactStore):
            raise TypeError("artifacts must be ContentAddressedArtifactStore")
        self.store = store
        self.artifacts = artifacts

    def execute(
        self,
        skill: str,
        request_value: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not isinstance(skill, str) or skill not in SKILL_REGISTRY:
            raise SkillRuntimeError(f"unknown Project Intelligence Skill: {skill}")
        request = RuntimeRequest.parse(request_value)
        self.store.register_project(
            request.tenant_id,
            request.project_id,
            metadata={"local_project_intelligence": True},
        )
        decision = self.store.create_run(
            CreateRunRequest(
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                run_id=request.request_id,
                operation=skill,
                idempotency_key=idempotency_key,
                request=dict(request_value),
            )
        )
        run = decision.run
        if decision.disposition is IdempotencyDisposition.REPLAYED:
            if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED}:
                if not isinstance(run.response, Mapping):
                    raise RuntimeError("terminal idempotent run has no response")
                return {
                    **dict(run.response),
                    "idempotency": "REPLAYED",
                    "run_status": run.status.value,
                }
            return self._in_progress_response(skill=skill, request=request, run=run)

        if run.status is RunStatus.PENDING:
            phase = "run-transition"
        else:
            phase = "handler-dispatch"
        try:
            if run.status is RunStatus.PENDING:
                self.store.set_run_status(
                    request.tenant_id,
                    request.project_id,
                    request.request_id,
                    RunStatus.RUNNING,
                )

            phase = "handler-dispatch"
            result = dispatch_skill(skill, request_value)
            phase = "result-canonicalization"
            result_bytes = canonical_json_bytes(result)
            phase = "artifact-write"
            content_digest = self.artifacts.put(result_bytes)
            phase = "artifact-record"
            artifact = self.store.put_artifact(
                request.tenant_id,
                request.project_id,
                request.request_id,
                ArtifactInput(
                    artifact_id="handler-result",
                    kind="project-intelligence-result",
                    content_digest=content_digest,
                    byte_count=len(result_bytes),
                    media_type="application/json",
                    metadata={
                        "skill": skill,
                        "handler_id": result["handler_id"],
                        "state": result["state"],
                    },
                ),
            )
            phase = "evidence-record"
            self.store.put_evidence(
                request.tenant_id,
                request.project_id,
                request.request_id,
                EvidenceInput(
                    evidence_id="local-handler-output",
                    kind="local-self-attested-handler-execution",
                    subject_digest=str(result.get("result_digest", content_digest)),
                    state=EvidenceState.COLLECTED,
                    details={
                        "external_evidence": "NOT_RUN",
                        "independent_verifier": False,
                        "certification": "NOT_CERTIFIED",
                    },
                    artifact_id=artifact.artifact_id,
                ),
            )
            phase = "checkpoint-record"
            self.store.append_checkpoint(
                request.tenant_id,
                request.project_id,
                request.request_id,
                {
                    "skill": skill,
                    "handler_id": result["handler_id"],
                    "state": result["state"],
                    "result_digest": result.get("result_digest"),
                    "artifact_digest": content_digest,
                },
                expected_previous_sequence=0,
            )
            terminal = (
                RunStatus.FAILED
                if result["state"] == "BLOCKED"
                else RunStatus.SUCCEEDED
            )
            phase = "terminal-status"
            stored = self.store.set_run_status(
                request.tenant_id,
                request.project_id,
                request.request_id,
                terminal,
                response=result,
            )
        except Exception as exc:
            self._finalize_failure(
                skill=skill,
                request=request,
                phase=phase,
                error=exc,
            )
            raise
        return {
            **result,
            "idempotency": decision.disposition.value,
            "run_status": stored.status.value,
            "artifact_digest": content_digest,
            "evidence_state": EvidenceState.COLLECTED.value,
            "independent_verifier": False,
        }

    @staticmethod
    def _safe_error_type(error: Exception) -> str:
        value = _SAFE_ERROR_TYPE.sub("_", type(error).__name__).strip("._-")
        return (value or "Exception")[:64]

    @staticmethod
    def _in_progress_response(
        *, skill: str, request: RuntimeRequest, run: RunRecord
    ) -> dict[str, Any]:
        binding = SKILL_REGISTRY[skill]
        response: dict[str, Any] = {
            "schema_version": "elmos.project-intelligence.service-in-progress.v1",
            "skill": skill,
            "handler_id": binding.handler_id,
            "capability_state": binding.capability_state,
            "request_id": request.request_id,
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "revision": request.revision,
            "state": "IN_PROGRESS",
            "code": "IDEMPOTENT_RUN_IN_PROGRESS",
            "outputs": {},
            "unavailable": ["active-run-completion"],
            "warnings": [],
            "external_effects_performed": False,
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "idempotency": "REPLAYED",
            "run_status": run.status.value,
        }
        response["result_digest"] = canonical_digest(response)
        return response

    @staticmethod
    def _failure_id(
        *, skill: str, request: RuntimeRequest, phase: str, error_type: str
    ) -> str:
        return canonical_digest(
            {
                "schema_version": "elmos.project-intelligence.failure-id.v1",
                "skill": skill,
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "run_id": request.request_id,
                "phase": phase,
                "error_type": error_type,
            }
        )

    def _ensure_failure_checkpoint(
        self,
        *,
        skill: str,
        request: RuntimeRequest,
        phase: str,
        error_type: str,
        failure_id: str,
    ) -> bool:
        checkpoint_state = {
            "kind": "service-failure",
            "failure_id": failure_id,
            "skill": skill,
            "phase": phase,
            "error_type": error_type,
            "error_message_disclosed": False,
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for _ in range(2):
            try:
                existing = self.store.list_checkpoints(
                    request.tenant_id,
                    request.project_id,
                    request.request_id,
                )
            except Exception:
                existing = ()
            if any(
                isinstance(checkpoint.state, Mapping)
                and checkpoint.state.get("failure_id") == failure_id
                for checkpoint in existing
            ):
                return True
            try:
                self.store.append_checkpoint(
                    request.tenant_id,
                    request.project_id,
                    request.request_id,
                    checkpoint_state,
                )
                return True
            except Exception:
                continue
        return False

    def _finalize_failure(
        self,
        *,
        skill: str,
        request: RuntimeRequest,
        phase: str,
        error: Exception,
    ) -> None:
        error_type = self._safe_error_type(error)
        failure_id = self._failure_id(
            skill=skill,
            request=request,
            phase=phase,
            error_type=error_type,
        )
        checkpoint_recorded = self._ensure_failure_checkpoint(
            skill=skill,
            request=request,
            phase=phase,
            error_type=error_type,
            failure_id=failure_id,
        )
        response = {
            "schema_version": "elmos.project-intelligence.service-failure.v1",
            "skill": skill,
            "handler_id": SKILL_REGISTRY[skill].handler_id,
            "capability_state": SKILL_REGISTRY[skill].capability_state,
            "request_id": request.request_id,
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "revision": request.revision,
            "state": "BLOCKED",
            "code": "SERVICE_EXECUTION_FAILED",
            "outputs": {},
            "unavailable": ["local-execution-incomplete"],
            "warnings": [],
            "error": {
                "phase": phase,
                "type": error_type,
                "fingerprint": failure_id,
                "message_disclosed": False,
            },
            "failure_checkpoint_recorded": checkpoint_recorded,
            "external_effects_performed": False,
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "run_status": RunStatus.FAILED.value,
        }
        for _ in range(3):
            try:
                current = self.store.get_run(
                    request.tenant_id,
                    request.project_id,
                    request.request_id,
                )
                if current.status is RunStatus.FAILED:
                    return
                if current.status is RunStatus.SUCCEEDED:
                    break
                self.store.set_run_status(
                    request.tenant_id,
                    request.project_id,
                    request.request_id,
                    RunStatus.FAILED,
                    response=response,
                )
                return
            except Exception:
                continue
        raise FailureFinalizationError(
            f"durable failure finalization failed: {failure_id}"
        ) from None


__all__ = ["FailureFinalizationError", "ProjectIntelligenceService"]
