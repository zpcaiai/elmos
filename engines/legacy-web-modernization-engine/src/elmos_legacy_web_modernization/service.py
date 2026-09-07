"""Durable service façade for single Skills and resumable local runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .contracts import RuntimeRequest
from .persistence import PersistenceError, StateStore
from .runtime import CATALOG, dispatch


class ModernizationService:
    def __init__(self, state_dir: str | Path) -> None:
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        self.store = StateStore(state_dir / "control-plane.sqlite3", state_dir / "artifacts")

    def execute(self, request_value: Mapping[str, Any]) -> dict[str, Any]:
        request = RuntimeRequest.from_dict(request_value)
        cached = self.store.lookup_idempotency(request)
        if cached is not None:
            cached = dict(cached)
            cached["idempotency"] = "REPLAYED"
            return cached
        lease_id, fencing_token = self.store.acquire_lease(request)
        self.store.record_run(request, state="RUNNING", phase=request.skill_id)
        self.store.append_event(request, "skill.started", {"skillId": request.skill_id, "requestId": request.request_id})
        try:
            result = dispatch(request_value)
            if result.get("state") == "BLOCKED":
                self.store.record_run(request, state="BLOCKED", phase=request.skill_id)
                self.store.append_event(request, "skill.failed", {"skillId": request.skill_id, "code": result.get("code")})
            else:
                for artifact in result.get("artifacts", []):
                    envelope = _artifact_from_result(artifact)
                    self.store.publish_artifact(request, envelope)
                    if envelope.artifact_type == "change-set":
                        self.store.save_change_set(request, envelope.payload, fencing_token=fencing_token)
                self.store.checkpoint(request, state="committed", cursor={"skillId": request.skill_id, "inputDigest": result.get("inputDigest")}, lease_id=lease_id, fencing_token=fencing_token)
                self.store.record_run(request, state="COMPLETED", phase=request.skill_id)
                self.store.append_event(request, "skill.completed", {"skillId": request.skill_id, "artifactCount": len(result.get("artifacts", []))})
            response = dict(result)
            response["idempotency"] = "CREATED"
            self.store.store_idempotency(request, response)
            return response
        finally:
            self.store.release_lease(request, lease_id=lease_id, fencing_token=fencing_token)

    def run_readonly(self, request_value: Mapping[str, Any]) -> dict[str, Any]:
        """Run the pinned DAG with one immutable source root.

        This is intentionally a local qualification/analysis run.  It never
        invokes Maven/Gradle, starts an application, calls a provider, commits
        Git, writes production data or upgrades external evidence.
        """

        request = RuntimeRequest.from_dict(request_value)
        if not isinstance(request.inputs.get("repository_root"), str):
            raise PersistenceError("repository_root is required for a DAG run")
        results: list[dict[str, Any]] = []
        for ordinal, skill_id in enumerate(CATALOG.topological_order):
            child = dict(request_value)
            child["request_id"] = f"{request.request_id}-{ordinal:02d}"
            child["skill_id"] = skill_id
            child["idempotency_key"] = f"{request.idempotency_key}-{ordinal:02d}"
            results.append(self.execute(child))
        succeeded = sum(item.get("state") != "BLOCKED" for item in results)
        return {"jobId": request.job_id, "state": "COMPLETED_WITH_BOUNDARIES", "skills": len(results), "succeeded": succeeded, "blocked": len(results) - succeeded, "externalEvidence": "NOT_RUN", "certification": "NOT_CERTIFIED", "results": results}


def _artifact_from_result(value: Mapping[str, Any]):
    from .contracts import ArtifactEnvelope

    return ArtifactEnvelope(
        artifact_id=str(value.get("artifactId", "")),
        artifact_type=str(value["type"]),
        payload=value.get("payload", {}),
        producer_skill=str(value["producerSkill"]),
        producer_version=str(value.get("producerVersion", "1.0.0")),
        schema_version=str(value.get("schemaVersion", "1.0.0")),
        input_hashes=tuple(value.get("inputHashes", ())),
        policy_snapshot_hash=str(value.get("policySnapshotHash", "sha256:" + "0" * 64)),
        environment_id=str(value.get("environmentId", "local-scan")),
        evidence_refs=tuple(value.get("evidenceRefs", ())),
        confidence=float(value.get("confidence", 0.0)),
        created_at=str(value.get("createdAt")),
    )
