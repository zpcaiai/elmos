"""Fail-closed contract for one raw local-qualification result.

This module validates the exact result envelope emitted by the fifty bounded
runtime handlers.  It does not execute a handler, infer missing evidence, or
raise any certification state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hmac
import math
import re
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
        "artifact_bytes_verified",
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
        "caller_reported_key_match",
        "implementation_version",
        "input_digest",
        "schema_version",
        "stage",
    ),
    "elmos-artifact-versioning-human-lock": (
        "artifact_id",
        "authoritative_lock_verified",
        "caller_reported_human_locked",
        "content_digest",
        "proposed_version",
        "version_persisted",
    ),
    "elmos-git-pr-automation": (
        "changed_paths",
        "draft",
        "git_mutated",
        "push_performed",
        "title",
    ),
    "elmos-collaboration-governance": (
        "audit_digest",
        "enforcement_authorized",
        "simulated_missing_roles",
        "simulated_tenant_match",
    ),
    "elmos-integrations-mcp": (
        "connector_called",
        "connector_id",
        "enforcement_authorized",
        "forbidden_scopes",
        "scopes",
    ),
    "elmos-large-repository-scaling": (
        "distributed_execution",
        "oversized_paths",
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
        "as_of",
        "assumptions",
        "estimate_id",
        "human_review_effort",
        "pipeline",
        "project_revision_id",
        "stages",
        "system_wall_clock_eta",
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
        "billing_performed",
        "caller_reported_allowed_features",
        "caller_reported_denied_features",
        "caller_reported_entitled_features",
        "edition",
        "enforcement_authorized",
        "usage_record_digest",
    ),
    "elmos-debug-adapter-gateway": (
        "adapter_started",
        "enforcement_authorized",
        "forbidden",
        "negotiated",
        "unsupported",
    ),
    "elmos-debug-sandbox-orchestration": (
        "debug_session",
        "sandbox_started",
    ),
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
            "elmos-artifact-versioning-human-lock": (
                ("authoritative_lock_verified",),
                ("version_persisted",),
            ),
            "elmos-git-pr-automation": (("git_mutated",), ("push_performed",)),
            "elmos-collaboration-governance": (("enforcement_authorized",),),
            "elmos-integrations-mcp": (
                ("connector_called",),
                ("enforcement_authorized",),
            ),
            "elmos-large-repository-scaling": (("distributed_execution",),),
            "elmos-observability-slo": (("production_slo_claimed",),),
            "elmos-conversion-integration": (("conversion_executed",),),
            "elmos-deployment-private-cloud": (("deployment_performed",),),
            "elmos-release-certification": (
                ("certified",),
                ("release_authorized",),
            ),
            "elmos-commercial-packaging": (
                ("billing_performed",),
                ("enforcement_authorized",),
            ),
            "elmos-debug-adapter-gateway": (
                ("adapter_started",),
                ("enforcement_authorized",),
            ),
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

_CACHE_KEY_SCHEMA_VERSION = "elmos.project-intelligence.analysis-cache-key.v1"
_CACHE_IMPLEMENTATION_VERSION = "elmos-project-intelligence-engine/1.1.0"
_RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


_AUTHORITY_NAME_MARKERS: Final[tuple[str, ...]] = (
    "authoriz",
    "authoritative_lock",
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
    "version_persisted",
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


def _literal_true(value: Any, *, path: str) -> None:
    if type(value) is not bool or value is not True:
        raise QualificationContractError(f"{path} must be the literal boolean true")


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


def _canonical_digest_field(value: Any, *, field_name: str) -> str:
    if type(value) is not str:
        raise QualificationContractError(f"{field_name} must be a string")
    try:
        normalized = validate_digest(value)
    except (TypeError, ValueError) as exc:
        raise QualificationContractError(
            f"{field_name} must be a canonical sha256 digest"
        ) from exc
    if value != normalized:
        raise QualificationContractError(
            f"{field_name} must use canonical lowercase sha256 form"
        )
    return value


def _validate_diagram_output(
    outputs: dict[str, Any], expected_scope: ExpectedRequestScope
) -> None:
    spec = outputs["diagram_spec"]
    if type(spec) is not dict:
        raise QualificationContractError("outputs.diagram_spec must be an object")
    required = {
        "schema_version",
        "diagram_id",
        "type",
        "project_id",
        "revision_id",
        "nodes",
        "edges",
    }
    if not required.issubset(spec):
        raise QualificationContractError(
            "outputs.diagram_spec is missing source-schema required fields"
        )
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise QualificationContractError(
            "outputs.diagram_spec.schema_version must be integer 1"
        )
    _canonical_digest_field(
        spec["diagram_id"], field_name="outputs.diagram_spec.diagram_id"
    )
    if not isinstance(spec["type"], str) or not spec["type"]:
        raise QualificationContractError(
            "outputs.diagram_spec.type must be a non-empty string"
        )
    if spec["project_id"] != expected_scope.project_id:
        raise QualificationContractError(
            "outputs.diagram_spec.project_id must match the expected scope"
        )
    if spec["revision_id"] != expected_scope.revision:
        raise QualificationContractError(
            "outputs.diagram_spec.revision_id must match the expected scope"
        )
    if type(spec["nodes"]) is not list or type(spec["edges"]) is not list:
        raise QualificationContractError(
            "outputs.diagram_spec nodes and edges must be lists"
        )
    node_ids: set[str] = set()
    for node in spec["nodes"]:
        if type(node) is not dict or not {"id", "kind", "label"}.issubset(node):
            raise QualificationContractError(
                "outputs.diagram_spec contains an invalid node"
            )
        for field_name in ("id", "kind", "label"):
            if not isinstance(node[field_name], str) or not node[field_name]:
                raise QualificationContractError(
                    "outputs.diagram_spec node identifiers and labels must be non-empty"
                )
        if node["id"] in node_ids:
            raise QualificationContractError(
                "outputs.diagram_spec contains duplicate node IDs"
            )
        node_ids.add(node["id"])
        if "evidence_refs" in node:
            _validate_string_list(
                node["evidence_refs"],
                field_name="outputs.diagram_spec.node.evidence_refs",
            )
        if "confidence" in node:
            confidence = _nonnegative_number(
                node["confidence"],
                field_name="outputs.diagram_spec.node.confidence",
            )
            if confidence > 1:
                raise QualificationContractError(
                    "outputs.diagram_spec node confidence cannot exceed 1"
                )
    edge_ids: set[str] = set()
    for edge in spec["edges"]:
        if (
            type(edge) is not dict
            or not {"id", "source", "target", "kind"}.issubset(edge)
            or "from" in edge
            or "to" in edge
        ):
            raise QualificationContractError(
                "outputs.diagram_spec edges must use the source-schema contract"
            )
        for field_name in ("id", "source", "target", "kind"):
            if not isinstance(edge[field_name], str) or not edge[field_name]:
                raise QualificationContractError(
                    "outputs.diagram_spec edge fields must be non-empty strings"
                )
        if edge["id"] in edge_ids:
            raise QualificationContractError(
                "outputs.diagram_spec contains duplicate edge IDs"
            )
        edge_ids.add(edge["id"])
        if edge["source"] not in node_ids or edge["target"] not in node_ids:
            raise QualificationContractError(
                "outputs.diagram_spec contains a dangling edge endpoint"
            )
        if "evidence_refs" in edge:
            _validate_string_list(
                edge["evidence_refs"],
                field_name="outputs.diagram_spec.edge.evidence_refs",
            )
        if "confidence" in edge:
            confidence = _nonnegative_number(
                edge["confidence"],
                field_name="outputs.diagram_spec.edge.confidence",
            )
            if confidence > 1:
                raise QualificationContractError(
                    "outputs.diagram_spec edge confidence cannot exceed 1"
                )
    _canonical_digest_field(outputs["digest"], field_name="outputs.digest")
    if outputs["digest"] != canonical_digest(spec):
        raise QualificationContractError(
            "outputs.digest does not bind outputs.diagram_spec"
        )


def _validate_cache_output(
    outputs: dict[str, Any], expected_scope: ExpectedRequestScope
) -> None:
    if outputs["schema_version"] != _CACHE_KEY_SCHEMA_VERSION:
        raise QualificationContractError("cache schema version drifted")
    if outputs["implementation_version"] != _CACHE_IMPLEMENTATION_VERSION:
        raise QualificationContractError("cache implementation version drifted")
    if not isinstance(outputs["stage"], str) or not outputs["stage"]:
        raise QualificationContractError("outputs.stage must be a non-empty string")
    input_digest = _canonical_digest_field(
        outputs["input_digest"], field_name="outputs.input_digest"
    )
    cache_key = _canonical_digest_field(
        outputs["cache_key"], field_name="outputs.cache_key"
    )
    if type(outputs["caller_reported_key_match"]) is not bool:
        raise QualificationContractError(
            "outputs.caller_reported_key_match must be a boolean"
        )
    expected_key = canonical_digest(
        {
            "schema_version": _CACHE_KEY_SCHEMA_VERSION,
            "implementation_version": _CACHE_IMPLEMENTATION_VERSION,
            "tenant_id": expected_scope.tenant_id,
            "project_id": expected_scope.project_id,
            "revision": expected_scope.revision,
            "stage": outputs["stage"],
            "input_digest": input_digest,
        }
    )
    if not hmac.compare_digest(cache_key, expected_key):
        raise QualificationContractError(
            "outputs.cache_key is not bound to the exact trusted request scope"
        )


def _validate_bundle_output(outputs: dict[str, Any]) -> None:
    _literal_true(
        outputs["artifact_bytes_verified"],
        path="outputs.artifact_bytes_verified",
    )
    _literal_true(outputs["content_addressed"], path="outputs.content_addressed")
    artifacts = outputs["artifacts"]
    if type(artifacts) is not list:
        raise QualificationContractError("outputs.artifacts must be a list")
    artifact_ids: list[str] = []
    for artifact in artifacts:
        if type(artifact) is not dict or set(artifact) != {
            "artifact_id",
            "digest",
            "media_type",
            "byte_count",
            "content_encoding",
        }:
            raise QualificationContractError(
                "outputs.artifacts entry does not match the verified byte contract"
            )
        for field_name in ("artifact_id", "media_type"):
            if not isinstance(artifact[field_name], str) or not artifact[field_name]:
                raise QualificationContractError(
                    f"artifact {field_name} must be a non-empty string"
                )
        artifact_ids.append(artifact["artifact_id"])
        _canonical_digest_field(
            artifact["digest"], field_name="outputs.artifacts.digest"
        )
        if type(artifact["byte_count"]) is not int or artifact["byte_count"] < 0:
            raise QualificationContractError(
                "artifact byte_count must be a non-negative integer"
            )
        if artifact["content_encoding"] not in {"utf-8", "base64"}:
            raise QualificationContractError(
                "artifact content_encoding must be utf-8 or base64"
            )
    if artifact_ids != sorted(artifact_ids) or len(artifact_ids) != len(
        set(artifact_ids)
    ):
        raise QualificationContractError(
            "outputs.artifacts must have unique sorted artifact IDs"
        )
    bundle_digest = _canonical_digest_field(
        outputs["bundle_digest"], field_name="outputs.bundle_digest"
    )
    if bundle_digest != canonical_digest(artifacts):
        raise QualificationContractError(
            "outputs.bundle_digest does not bind the verified artifact index"
        )


def _nonnegative_number(value: Any, *, field_name: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualificationContractError(f"{field_name} must be a number")
    if not math.isfinite(value) or value < 0:
        raise QualificationContractError(
            f"{field_name} must be a finite non-negative number"
        )
    return value


def _validate_estimate_output(
    outputs: dict[str, Any], expected_scope: ExpectedRequestScope
) -> None:
    _canonical_digest_field(outputs["estimate_id"], field_name="outputs.estimate_id")
    as_of = outputs["as_of"]
    if not isinstance(as_of, str) or not _RFC3339_DATE_TIME.fullmatch(as_of):
        raise QualificationContractError("outputs.as_of must be an RFC 3339 date-time")
    try:
        parsed = datetime.fromisoformat(
            as_of[:-1] + "+00:00" if as_of.endswith("Z") else as_of
        )
    except ValueError as exc:
        raise QualificationContractError(
            "outputs.as_of must be a valid RFC 3339 date-time"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QualificationContractError("outputs.as_of must include a UTC offset")
    if outputs["project_revision_id"] != expected_scope.revision:
        raise QualificationContractError(
            "outputs.project_revision_id must match the expected revision"
        )
    pipeline = _validate_string_list(outputs["pipeline"], field_name="outputs.pipeline")
    assumptions = _validate_string_list(
        outputs["assumptions"], field_name="outputs.assumptions"
    )
    if not assumptions:
        raise QualificationContractError("outputs.assumptions cannot be empty")
    eta = outputs["system_wall_clock_eta"]
    if type(eta) is not dict or set(eta) != {
        "p50_seconds",
        "p90_seconds",
        "confidence",
    }:
        raise QualificationContractError(
            "outputs.system_wall_clock_eta does not match estimate.schema.json"
        )
    eta_p50 = _nonnegative_number(
        eta["p50_seconds"], field_name="outputs.system_wall_clock_eta.p50_seconds"
    )
    eta_p90 = _nonnegative_number(
        eta["p90_seconds"], field_name="outputs.system_wall_clock_eta.p90_seconds"
    )
    confidence = _nonnegative_number(
        eta["confidence"], field_name="outputs.system_wall_clock_eta.confidence"
    )
    if eta_p90 < eta_p50 or confidence > 1:
        raise QualificationContractError(
            "outputs.system_wall_clock_eta has an invalid interval or confidence"
        )
    stages = outputs["stages"]
    if type(stages) is not list or not stages:
        raise QualificationContractError("outputs.stages must be a non-empty list")
    stage_names: list[str] = []
    for stage in stages:
        if type(stage) is not dict or set(stage) != {
            "name",
            "p50_seconds",
            "p90_seconds",
            "queue_seconds",
        }:
            raise QualificationContractError(
                "outputs.stages entries do not match estimate.schema.json"
            )
        if not isinstance(stage["name"], str) or not stage["name"]:
            raise QualificationContractError("stage names must be non-empty strings")
        stage_names.append(stage["name"])
        stage_p50 = _nonnegative_number(
            stage["p50_seconds"], field_name="stage.p50_seconds"
        )
        stage_p90 = _nonnegative_number(
            stage["p90_seconds"], field_name="stage.p90_seconds"
        )
        _nonnegative_number(stage["queue_seconds"], field_name="stage.queue_seconds")
        if stage_p90 < stage_p50:
            raise QualificationContractError("stage P90 cannot be less than P50")
    if pipeline != stage_names:
        raise QualificationContractError(
            "outputs.pipeline must match the ordered estimate stages"
        )
    review = outputs["human_review_effort"]
    if type(review) is not dict or set(review) != {"p50_hours", "p90_hours"}:
        raise QualificationContractError(
            "outputs.human_review_effort does not match estimate.schema.json"
        )
    review_p50 = _nonnegative_number(
        review["p50_hours"], field_name="outputs.human_review_effort.p50_hours"
    )
    review_p90 = _nonnegative_number(
        review["p90_hours"], field_name="outputs.human_review_effort.p90_hours"
    )
    if review_p90 < review_p50:
        raise QualificationContractError("human review P90 cannot be less than P50")


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

    if binding.skill == "elmos-diagram-spec-engine":
        _validate_diagram_output(outputs, expected_scope)
    elif binding.skill == "elmos-project-report-bundle":
        _validate_bundle_output(outputs)
    elif binding.skill == "elmos-incremental-analysis-cache":
        _validate_cache_output(outputs, expected_scope)
    elif binding.skill == "elmos-runtime-cost-estimator":
        _validate_estimate_output(outputs, expected_scope)

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
    if binding.skill == "elmos-evidence-provenance":
        bindings = outputs["bindings"]
        if type(bindings) is not list:
            raise QualificationContractError("outputs.bindings must be a list")
        for item in bindings:
            if type(item) is not dict or set(item) != {
                "claim_id",
                "confidence",
                "evidence_refs",
                "verification_state",
            }:
                raise QualificationContractError(
                    "evidence binding does not match the exact unverified contract"
                )
            if item["verification_state"] != "NOT_RUN" or item["confidence"] not in {
                "REFERENCED_UNVERIFIED",
                "UNKNOWN",
            }:
                raise QualificationContractError(
                    "evidence binding cannot claim verified or confirmed evidence"
                )
            if type(item["evidence_refs"]) is not list:
                raise QualificationContractError(
                    "evidence binding references must be a list"
                )
            expected_confidence = (
                "REFERENCED_UNVERIFIED" if item["evidence_refs"] else "UNKNOWN"
            )
            if item["confidence"] != expected_confidence:
                raise QualificationContractError(
                    "evidence binding confidence does not match its references"
                )
    if binding.skill == "elmos-release-certification":
        if outputs["decision"] != "EXTERNAL_GATE_REQUIRED":
            raise QualificationContractError(
                "local release fixture must require the external gate"
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
