"""Audited prepare-only handlers for the 41 Foundry capability packs."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import canonical_digest, canonical_value
from .domain import TenantScope


LOCAL_EVIDENCE_STATUS = "LOCAL_EXECUTED_SELF_ATTESTED"
EXTERNAL_EVIDENCE_STATUS = "NOT_RUN"
CERTIFICATION_STATUS = "NOT_CERTIFIED"
MAXIMUM_LOCAL_DECISION = "READY_FOR_EXTERNAL_GATE"


def canonical_json(value: Any, *, _depth: int = 0) -> Any:
    if _depth != 0:
        raise ValueError("callers cannot override canonical traversal depth")
    return canonical_value(value)


def digest_json(value: Any) -> str:
    return canonical_digest(value).removeprefix("sha256:")


@dataclass(frozen=True, slots=True)
class HandlerResult:
    status: str
    outputs: Mapping[str, Any]
    content_digest: str
    error: str | None = None

    def __post_init__(self) -> None:
        normalized = canonical_value(self.outputs)
        if not isinstance(normalized, dict):
            raise TypeError("handler outputs must be an object")
        object.__setattr__(self, "outputs", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class PackHandler:
    handler_id: str
    pack: str

    def prepare(
        self,
        *,
        skill: Mapping[str, Any],
        payload: Mapping[str, Any],
        tenant_scope: TenantScope,
        catalog_digest: str,
    ) -> HandlerResult:
        if skill.get("pack") != self.pack:
            raise ValueError("Skill pack does not match the exact handler binding")
        if skill.get("handler_id") != self.handler_id:
            raise ValueError("Skill handler_id does not match the allowlisted handler")
        normalized_payload = canonical_json(payload)
        if not isinstance(normalized_payload, dict):
            raise TypeError("Skill payload must be an object")
        input_digest = digest_json(normalized_payload)
        declared_inputs = tuple(skill.get("inputs", ()))
        provided_keys = tuple(sorted(normalized_payload))
        missing_inputs = tuple(
            item
            for item in declared_inputs
            if isinstance(item, str)
            and (
                item not in normalized_payload
                or normalized_payload[item] is None
                or normalized_payload[item] == ""
                or normalized_payload[item] == []
                or normalized_payload[item] == {}
            )
        )
        complete = not missing_inputs
        plan = {
            "skill": skill["name"],
            "pack": self.pack,
            "handler_id": self.handler_id,
            "capability_state": skill["capability_state"],
            "tenant_scope": {
                "tenant_id": tenant_scope.tenant_id,
                "project_id": tenant_scope.project_id,
                "actor_id": tenant_scope.actor_id,
                "environment_id": tenant_scope.environment_id,
                "workspace_digest": tenant_scope.workspace_digest,
                "revision_set_id": tenant_scope.revision_set_id,
                "invocation_id": tenant_scope.invocation_id,
                "lease_id": tenant_scope.lease_id,
                "context_digest": tenant_scope.binding_digest,
            },
            "source": {
                "path": skill["source_path"],
                "sha256": skill["source_sha256"],
            },
            "catalog_digest": catalog_digest,
            "input_digest": input_digest,
            "provided_input_keys": provided_keys,
            "declared_inputs": declared_inputs,
            "missing_declared_inputs": missing_inputs,
            "declared_outputs": tuple(skill.get("outputs", ())),
            "dependencies": tuple(skill.get("dependencies", ())),
            "allowed_tools": tuple(skill.get("allowed_tools", ())),
            "required_gates": tuple(skill.get("required_gates", ())),
            "preparation_status": "PREPARED" if complete else "BLOCKED_INCOMPLETE_INPUT",
            "local_validation_status": (
                "PASSED_SELF_ATTESTED" if complete else "FAILED_SELF_ATTESTED"
            ),
            "semantic_execution_status": "NOT_RUN",
            "local_evidence_status": LOCAL_EVIDENCE_STATUS if complete else "NOT_RUN",
            "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
            "certification_status": CERTIFICATION_STATUS,
            "maximum_local_decision": MAXIMUM_LOCAL_DECISION if complete else "NOT_READY",
        }
        plan_digest = digest_json(plan)
        outputs = dict(plan)
        outputs["plan_digest"] = plan_digest
        return HandlerResult(
            status=LOCAL_EVIDENCE_STATUS if complete else "BLOCKED",
            outputs=outputs,
            content_digest=plan_digest,
            error=None
            if complete
            else "required declared Skill inputs are missing; semantic execution did not run",
        )


def _handler(pack: str) -> PackHandler:
    return PackHandler(f"pack.{pack.replace('-', '_')}", pack)


_PACK_HANDLERS: tuple[PackHandler, ...] = tuple(
    _handler(pack)
    for pack in (
        "00-foundation-contracts",
        "01-knowledge-ingestion-governance",
        "02-repository-semantic-intelligence",
        "03-retrieval-context-engineering",
        "04-memory-experience-flywheel",
        "05-skill-foundry-runtime",
        "06-dataset-foundry",
        "07-private-model-foundry",
        "08-agentic-training-rl",
        "09-evaluation-proof-certification",
        "10-serving-routing-inference",
        "11-security-privacy-compliance",
        "12-observability-lineage-finops",
        "13-commercial-multitenant-platform",
        "14-human-governance-operations",
        "15-domain-engineering-packs",
        "16-self-evolution-release-engineering",
        "17-repository-execution-os",
        "18-java-spring-enterprise-modernization",
        "19-cross-language-semantic-conversion",
        "20-sql-database-modernization",
        "21-project-generation-product-engineering",
        "22-frontend-mobile-miniapp-modernization",
        "23-repository-refactoring-technical-debt",
        "24-api-event-integration-modernization",
        "25-data-engineering-lakehouse-analytics",
        "26-cloud-native-devops-platform-engineering",
        "27-test-quality-assurance-factory",
        "28-security-compliance-supply-chain",
        "29-performance-reliability-cost-engineering",
        "30-architecture-documentation-ide",
        "31-ai-agent-rag-ml-engineering",
        "32-legacy-mainframe-enterprise-modernization",
        "33-industrial-iot-edge-robotics",
        "34-language-runtime-adapters",
        "35-database-engine-adapters",
        "36-framework-runtime-adapters",
        "37-cloud-platform-adapters",
        "38-golden-route-customer-delivery",
        "39-product-commercialization-marketplace",
        "40-regulated-industry-assurance",
    )
)

PACK_HANDLER_REGISTRY: Mapping[str, PackHandler] = MappingProxyType(
    {handler.handler_id: handler for handler in _PACK_HANDLERS}
)
if len(PACK_HANDLER_REGISTRY) != 41:
    raise RuntimeError("the exact 41-pack handler allowlist is incomplete")


__all__ = [
    "CERTIFICATION_STATUS",
    "EXTERNAL_EVIDENCE_STATUS",
    "HandlerResult",
    "LOCAL_EVIDENCE_STATUS",
    "MAXIMUM_LOCAL_DECISION",
    "PACK_HANDLER_REGISTRY",
    "PackHandler",
    "canonical_json",
    "digest_json",
]
