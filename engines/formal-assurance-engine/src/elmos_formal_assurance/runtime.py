from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import digest_value, validate_identifier
from .contracts import Scope, TrustedIdentity
from .artifact_store import ContentAddressedArtifactStore
from .handlers import HandlerContext
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
        request_payload = dict(payload)
        request_payload.pop("scope", None)
        request_payload.pop("subjectId", None)
        request_payload.pop("idempotencyKey", None)
        request_document = {
            "skillId": skill_id,
            "scope": scope.to_dict(),
            "subjectId": subject,
            "payload": request_payload,
        }
        request_digest = digest_value(request_document)
        replay = self.store.get_idempotent(scope.tenant_id, key, request_digest)
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
        )
        outcome = self.registry.handler(skill_id)(context)
        response = outcome.to_dict()
        response["requestDigest"] = request_digest
        response["scope"] = scope.to_dict()
        return self.store.complete_idempotent_invocation(
            scope, key, skill_id, subject, request_digest, response
        )

    def submit_run(
        self, payload: dict[str, Any], identity: TrustedIdentity
    ) -> dict[str, Any]:
        scope = self._scope(payload.get("scope"), identity)
        return self.store.submit_run(
            scope,
            validate_identifier(payload.get("runId"), "runId"),
            validate_identifier(payload.get("obligationId"), "obligationId"),
            int(payload.get("accountConcurrency", self.config.account_concurrency)),
        )

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
