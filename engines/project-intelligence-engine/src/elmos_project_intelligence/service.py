"""Durable execution service joining strict handlers, SQLite, and local CAS."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import ContentAddressedArtifactStore
from .canonical import canonical_json_bytes
from .contracts import (
    ArtifactInput,
    CreateRunRequest,
    EvidenceInput,
    EvidenceState,
    IdempotencyDisposition,
    RunStatus,
)
from .runtime import SKILL_REGISTRY, RuntimeRequest, SkillRuntimeError, dispatch_skill
from .store import ProjectIntelligenceStore


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
        if decision.disposition is IdempotencyDisposition.REPLAYED and run.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
        }:
            if not isinstance(run.response, Mapping):
                raise RuntimeError("terminal idempotent run has no response")
            return {**dict(run.response), "idempotency": "REPLAYED"}

        if run.status is RunStatus.PENDING:
            self.store.set_run_status(
                request.tenant_id,
                request.project_id,
                request.request_id,
                RunStatus.RUNNING,
            )

        result = dispatch_skill(skill, request_value)
        result_bytes = canonical_json_bytes(result)
        content_digest = self.artifacts.put(result_bytes)
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
            RunStatus.FAILED if result["state"] == "BLOCKED" else RunStatus.SUCCEEDED
        )
        stored = self.store.set_run_status(
            request.tenant_id,
            request.project_id,
            request.request_id,
            terminal,
            response=result,
        )
        return {
            **result,
            "idempotency": decision.disposition.value,
            "run_status": stored.status.value,
            "artifact_digest": content_digest,
            "evidence_state": EvidenceState.COLLECTED.value,
            "independent_verifier": False,
        }


__all__ = ["ProjectIntelligenceService"]
