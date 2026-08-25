"""Fail-closed contract for one raw local-qualification result.

This module validates the exact result envelope emitted by the fifty bounded
runtime handlers.  It does not execute a handler, infer missing evidence, or
raise any certification state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hmac
from types import MappingProxyType
from typing import Any, Final

from .canonical import CanonicalizationError, canonical_digest, validate_digest
from .runtime import HandlerBinding, SKILL_REGISTRY


class QualificationContractError(ValueError):
    """Raised when a raw qualification result violates the pinned contract."""


@dataclass(frozen=True, slots=True)
class ExpectedRequestScope:
    request_id: str
    tenant_id: str
    project_id: str
    revision: str

    def __post_init__(self) -> None:
        for field_name in ("request_id", "tenant_id", "project_id", "revision"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
            if len(value.encode("utf-8")) > 256:
                raise ValueError(f"{field_name} exceeds 256 UTF-8 bytes")
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ValueError(f"{field_name} contains a control character")


RAW_RESULT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "skill",
        "handler_id",
        "capability_state",
        "request_id",
        "tenant_id",
        "project_id",
        "revision",
        "state",
        "code",
        "outputs",
        "unavailable",
        "warnings",
        "external_effects_performed",
        "external_evidence",
        "certification",
        "result_digest",
    }
)


_OUTPUT_KEYS = {
    "elmos-insight-orchestrator": (
        "automatic_effects",
        "execution_order",
        "requested_skills",
    ),
    "elmos-product-scope": (
        "candidate_capabilities",
        "requirement_count",
        "scope_digest",
        "unconfirmed_requirement_ids",
    ),
    "elmos-reference-architecture": (
        "boundaries",
        "components",
        "deployment_verified",
    ),
    "elmos-repository-ingestion": (
        "code_executed",
        "manifest",
        "manifest_digest",
        "revision",
    ),
    "elmos-project-fingerprinting": (
        "build_markers",
        "fingerprint_digest",
        "languages",
    ),
    "elmos-multilanguage-parsing": (
        "imports",
        "parsed_file_count",
        "symbols",
        "unsupported_paths",
    ),
    "elmos-symbol-code-graph": ("edges", "graph_digest", "nodes"),
    "elmos-project-intelligence-graph": (
        "claims",
        "edges",
        "graph_digest",
        "nodes",
    ),
    "elmos-evidence-provenance": ("bindings", "unbound_claim_count"),
    "elmos-online-code-reader": ("files", "truncated"),
    "elmos-semantic-navigation": (
        "confidence",
        "definitions",
        "references",
        "symbol",
    ),
    "elmos-code-explanation": (
        "evidence_refs",
        "facts",
        "narrative_model_used",
    ),
    "elmos-onboarding-learning-path": ("steps",),
    "elmos-architecture-discovery": ("components", "runtime_verified"),
    "elmos-business-capability-map": (
        "capabilities",
        "human_confirmation_required",
    ),
    "elmos-flow-discovery": ("flows", "unknown_runtime_branches"),
    "elmos-data-architecture-lineage": ("assets", "runtime_lineage_verified"),
    "elmos-api-event-topology": ("endpoints", "events", "runtime_activity"),
    "elmos-runtime-trace-fusion": ("collector_executed", "observations"),
    "elmos-diagram-spec-engine": ("diagram_spec", "digest"),
    "elmos-diagram-rendering": ("content", "digest", "media_type"),
    "elmos-diagram-editor": (
        "diagram_spec",
        "locked_node_ids",
        "rejected_operations",
    ),
    "elmos-architecture-documentation": ("content", "digest", "media_type"),
    "elmos-presentation-generation": ("digest", "pptx_generated", "slides"),
    "elmos-project-report-bundle": (
        "artifacts",
        "bundle_digest",
        "content_addressed",
    ),
    "elmos-project-search-qa": ("answer", "confidence", "matches", "query"),
    "elmos-impact-analysis": ("bounded", "changed", "impacted"),
    "elmos-architecture-rules": ("findings", "rule_count"),
    "elmos-architecture-drift": (
        "coverage",
        "missing_declared",
        "undeclared_discovered",
    ),
    "elmos-risk-technical-debt": ("hotspots", "model_version"),
    "elmos-security-threat-model": (
        "graph_edge_count",
        "secrets_disclosed",
        "threats",
    ),
    "elmos-incremental-analysis-cache": (
        "cache_key",
        "hit",
        "input_digest",
        "stage",
    ),
    "elmos-artifact-versioning-human-lock": (
        "artifact_id",
        "content_digest",
        "human_locked",
        "version",
    ),
    "elmos-git-pr-automation": (
        "changed_paths",
        "draft",
        "git_mutated",
        "push_performed",
        "title",
    ),
    "elmos-collaboration-governance": (
        "allowed",
        "audit_digest",
        "missing_roles",
        "tenant_match",
    ),
    "elmos-integrations-mcp": (
        "connector_called",
        "connector_id",
        "forbidden_scopes",
        "scopes",
    ),
    "elmos-large-repository-scaling": (
        "distributed_execution",
        "shards",
        "total_files",
    ),
    "elmos-observability-slo": (
        "met",
        "production_slo_claimed",
        "sample_count",
        "success_rate",
        "target",
    ),
    "elmos-testing-evaluation": (
        "external_evidence",
        "failed",
        "local_pass",
        "required_count",
    ),
    "elmos-conversion-integration": (
        "conversion_executed",
        "invalid_mappings",
        "mapping_count",
    ),
    "elmos-runtime-cost-estimator": (
        "currency_cost",
        "human_review_effort_seconds",
        "model_version",
        "system_wall_clock_eta_p50_seconds",
        "system_wall_clock_eta_p90_seconds",
    ),
    "elmos-deployment-private-cloud": (
        "deployment_performed",
        "missing_controls",
        "topology",
    ),
    "elmos-release-certification": (
        "certified",
        "decision",
        "failing_gates",
        "release_authorized",
    ),
    "elmos-commercial-packaging": (
        "allowed_features",
        "billing_performed",
        "denied_features",
        "edition",
        "usage_record_digest",
    ),
    "elmos-debug-adapter-gateway": (
        "adapter_started",
        "forbidden",
        "negotiated",
        "unsupported",
    ),
    "elmos-debug-sandbox-orchestration": ("policy", "sandbox_started"),
    "elmos-online-debug-workbench": ("event_count", "threads", "ui_rendered"),
    "elmos-debug-learning-copilot": ("mission", "model_used", "side_effects"),
    "elmos-debug-record-replay": ("bundle", "digest"),
    "elmos-distributed-debug-correlation": (
        "causal_gaps",
        "distributed_pause_performed",
        "timelines",
    ),
}

OUTPUT_KEYS_BY_SKILL: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    _OUTPUT_KEYS
)


_AUTHORITY_FALSE_PATHS: Final[Mapping[str, tuple[tuple[str, ...], ...]]] = (
    MappingProxyType(
        {
            "elmos-insight-orchestrator": (("automatic_effects",),),
            "elmos-reference-architecture": (("deployment_verified",),),
            "elmos-repository-ingestion": (("code_executed",),),
            "elmos-code-explanation": (("narrative_model_used",),),
            "elmos-architecture-discovery": (("runtime_verified",),),
            "elmos-data-architecture-lineage": (("runtime_lineage_verified",),),
            "elmos-runtime-trace-fusion": (("collector_executed",),),
            "elmos-presentation-generation": (("pptx_generated",),),
            "elmos-security-threat-model": (("secrets_disclosed",),),
            "elmos-git-pr-automation": (("git_mutated",), ("push_performed",)),
            "elmos-integrations-mcp": (("connector_called",),),
            "elmos-large-repository-scaling": (("distributed_execution",),),
            "elmos-observability-slo": (("production_slo_claimed",),),
            "elmos-conversion-integration": (("conversion_executed",),),
            "elmos-deployment-private-cloud": (("deployment_performed",),),
            "elmos-release-certification": (
                ("certified",),
                ("release_authorized",),
            ),
            "elmos-commercial-packaging": (("billing_performed",),),
            "elmos-debug-adapter-gateway": (("adapter_started",),),
            "elmos-debug-sandbox-orchestration": (("sandbox_started",),),
            "elmos-online-debug-workbench": (("ui_rendered",),),
            "elmos-debug-learning-copilot": (("model_used",), ("side_effects",)),
            "elmos-debug-record-replay": (("bundle", "native_reverse_debug"),),
            "elmos-distributed-debug-correlation": (("distributed_pause_performed",),),
        }
    )
)


_EXPECTED_STATE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "LOCAL": "LOCAL_EXECUTED",
        "PARTIAL": "PARTIAL_LOCAL_EXECUTED",
        "PLAN": "PLANNING_ONLY",
    }
)


_AUTHORITY_NAME_MARKERS: Final[tuple[str, ...]] = (
    "authoriz",
    "approv",
    "certif",
    "external_effect",
    "side_effect",
    "secret_disclos",
    "secrets_disclos",
    "deployment_verified",
    "deployment_performed",
    "runtime_verified",
    "runtime_lineage_verified",
    "native_reverse_debug",
    "git_mutated",
    "push_performed",
    "connector_called",
    "distributed_execution",
    "distributed_pause_performed",
    "adapter_started",
    "sandbox_started",
    "ui_rendered",
    "model_used",
    "code_executed",
    "collector_executed",
    "billing_performed",
    "conversion_executed",
    "production_slo_claimed",
    "pptx_generated",
    "automatic_effects",
)


def _registered_binding(binding: HandlerBinding) -> HandlerBinding:
    if not isinstance(binding, HandlerBinding):
        raise QualificationContractError("binding must be a HandlerBinding")
    registered = SKILL_REGISTRY.get(binding.skill)
    if registered is None or registered != binding:
        raise QualificationContractError(
            "binding does not match the exact runtime registry"
        )
    return registered


def _literal_false(value: Any, *, path: str) -> None:
    if type(value) is not bool or value is not False:
        raise QualificationContractError(f"{path} must be the literal boolean false")


def _nested_value(outputs: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = outputs
    traversed: list[str] = ["outputs"]
    for component in path:
        if type(value) is not dict or component not in value:
            raise QualificationContractError(
                f"{'.'.join(traversed + [component])} is missing"
            )
        value = value[component]
        traversed.append(component)
    return value


def _authority_paths(value: Any, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                raise QualificationContractError("output mappings require string keys")
            item_path = (*path, key)
            lowered = key.lower()
            if any(marker in lowered for marker in _AUTHORITY_NAME_MARKERS):
                found.add(item_path)
            found.update(_authority_paths(item, item_path))
    elif type(value) is list:
        for index, item in enumerate(value):
            found.update(_authority_paths(item, (*path, f"[{index}]")))
    return found


def _validate_string_list(value: Any, *, field_name: str) -> list[str]:
    if type(value) is not list:
        raise QualificationContractError(f"{field_name} must be a list")
    if any(not isinstance(item, str) or not item for item in value):
        raise QualificationContractError(
            f"{field_name} must contain only non-empty strings"
        )
    if len(value) != len(set(value)):
        raise QualificationContractError(f"{field_name} cannot contain duplicates")
    return value


def validate_qualification_result(
    binding: HandlerBinding,
    result: dict[str, Any],
    expected_scope: ExpectedRequestScope,
) -> None:
    """Validate one raw result against the exact local qualification contract.

    Success means only that this local result is structurally and
    cryptographically consistent with the pinned handler contract.  It does not
    establish external evidence, production behavior, or certification.
    """

    binding = _registered_binding(binding)
    if not isinstance(expected_scope, ExpectedRequestScope):
        raise QualificationContractError(
            "expected_scope must be an ExpectedRequestScope"
        )
    if type(result) is not dict:
        raise QualificationContractError("raw qualification result must be a dict")
    observed_keys = frozenset(result)
    if observed_keys != RAW_RESULT_KEYS:
        missing = sorted(RAW_RESULT_KEYS - observed_keys)
        extra = sorted(observed_keys - RAW_RESULT_KEYS)
        raise QualificationContractError(
            f"raw result key set mismatch; missing={missing}, extra={extra}"
        )

    exact_values = {
        "schema_version": "elmos.project-intelligence.result.v1",
        "skill": binding.skill,
        "handler_id": binding.handler_id,
        "capability_state": binding.capability_state,
        "state": _EXPECTED_STATE.get(binding.capability_state),
        "code": binding.expected_success_code,
        "request_id": expected_scope.request_id,
        "tenant_id": expected_scope.tenant_id,
        "project_id": expected_scope.project_id,
        "revision": expected_scope.revision,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    if exact_values["state"] is None:
        raise QualificationContractError(
            f"unsupported capability state: {binding.capability_state}"
        )
    for field_name, expected in exact_values.items():
        if result[field_name] != expected or type(result[field_name]) is not type(
            expected
        ):
            raise QualificationContractError(
                f"{field_name} does not match the exact qualification contract"
            )

    _literal_false(
        result["external_effects_performed"],
        path="external_effects_performed",
    )
    warnings = _validate_string_list(result["warnings"], field_name="warnings")
    unavailable = _validate_string_list(result["unavailable"], field_name="unavailable")
    if binding.capability_state in {"PARTIAL", "PLAN"} and not unavailable:
        raise QualificationContractError(
            "PARTIAL and PLAN results require non-empty unavailable capabilities"
        )
    if binding.capability_state == "LOCAL" and unavailable:
        raise QualificationContractError("LOCAL results require empty unavailable")
    # Access the value so static analyzers and future changes cannot silently
    # remove validation of the warnings field.
    _ = warnings

    outputs = result["outputs"]
    if type(outputs) is not dict or not outputs:
        raise QualificationContractError("outputs must be a non-empty map")
    expected_output_keys = OUTPUT_KEYS_BY_SKILL.get(binding.skill)
    if expected_output_keys is None:
        raise QualificationContractError("Skill has no pinned output-key contract")
    if tuple(sorted(outputs)) != expected_output_keys:
        raise QualificationContractError(
            f"output-key tuple mismatch for {binding.skill}"
        )

    expected_authority_paths = set(_AUTHORITY_FALSE_PATHS.get(binding.skill, ()))
    observed_authority_paths = _authority_paths(outputs)
    if observed_authority_paths != expected_authority_paths:
        unexpected = sorted(
            ".".join(path)
            for path in observed_authority_paths - expected_authority_paths
        )
        missing = sorted(
            ".".join(path)
            for path in expected_authority_paths - observed_authority_paths
        )
        raise QualificationContractError(
            f"authority-field paths mismatch; missing={missing}, unexpected={unexpected}"
        )
    for path in expected_authority_paths:
        _literal_false(
            _nested_value(outputs, path),
            path="outputs." + ".".join(path),
        )

    if binding.skill == "elmos-testing-evaluation":
        if outputs["external_evidence"] != "NOT_RUN":
            raise QualificationContractError(
                "outputs.external_evidence must remain NOT_RUN"
            )
    if binding.skill == "elmos-api-event-topology":
        if outputs["runtime_activity"] != "NOT_RUN":
            raise QualificationContractError(
                "outputs.runtime_activity must remain NOT_RUN"
            )

    supplied_digest = result["result_digest"]
    if type(supplied_digest) is not str:
        raise QualificationContractError("result_digest must be a string")
    try:
        normalized_digest = validate_digest(supplied_digest)
        digest_payload = {
            key: value for key, value in result.items() if key != "result_digest"
        }
        expected_digest = canonical_digest(digest_payload)
    except (CanonicalizationError, ValueError, TypeError) as exc:
        raise QualificationContractError(
            "result is not canonical-digest compatible"
        ) from exc
    if supplied_digest != normalized_digest:
        raise QualificationContractError(
            "result_digest must use canonical lowercase sha256 form"
        )
    if not hmac.compare_digest(normalized_digest, expected_digest):
        raise QualificationContractError("result_digest does not bind the raw result")


__all__ = [
    "ExpectedRequestScope",
    "OUTPUT_KEYS_BY_SKILL",
    "QualificationContractError",
    "RAW_RESULT_KEYS",
    "validate_qualification_result",
]
