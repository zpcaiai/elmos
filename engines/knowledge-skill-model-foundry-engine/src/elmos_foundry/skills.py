"""Exact Foundry catalog, meta router, and fail-closed Skill runtime.

Runtime authority comes only from the repository-owned compiled catalog and
the explicit 41-pack handler allowlist. Source-package instructions are never
loaded as instructions or executed by this module.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence, cast
import zipfile

from .adapters import AdapterRegistry, InvocationPermit
from .domain import (
    CertificationStatus,
    EvidenceState,
    ExecutionResult,
    LifecycleState,
    SkillContract,
    TenantScope,
)
from .handlers import (
    CERTIFICATION_STATUS,
    EXTERNAL_EVIDENCE_STATUS,
    LOCAL_EVIDENCE_STATUS,
    MAXIMUM_LOCAL_DECISION,
    PACK_HANDLER_REGISTRY,
    digest_json,
)
from .kernel import ExecutionKernel
from .local_semantics import (
    LOCAL_SEMANTIC_SKILLS,
    CatalogView,
    build_local_adapter_registry,
)
from .store import FoundryStore


ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_CATALOG_PATH = (
    ROOT / "engines/knowledge-skill-model-foundry-engine/catalog/compiled-catalog.json"
)
PACKAGED_CATALOG_PATH = Path(__file__).resolve().parent / "catalog/compiled-catalog.json"
DEFAULT_CATALOG_PATH = (
    PACKAGED_CATALOG_PATH if PACKAGED_CATALOG_PATH.is_file() else REPOSITORY_CATALOG_PATH
)
SOURCE_ARCHIVE_PATH = ROOT / "skills/subskills/elmos-knowledge-skill-model-foundry-v3.0.0.zip"
SOURCE_ARCHIVE_PREFIX = "elmos-knowledge-skill-model-foundry-v3.0.0/"
CATALOG_SCHEMA_VERSION = "elmos.knowledge-skill-model-foundry.compiled-catalog.v2"
EXPECTED_COMPILED_CATALOG_SHA256 = (
    "74004fd557b95b58eb293c2c46518582f6d699eb6f2aea97c32e86ce9f45a2b9"
)
EXPECTED_PACKAGE = {
    "id": "elmos-knowledge-skill-model-foundry-v3.0.0",
    "name": "elmos-knowledge-skill-model-foundry",
    "version": "3.0.0",
    "archive_sha256": "e29673a598756deff422e8dd7f36b2826e9c1aaff6df22db2c0699b0857ee0e4",
    "archive_bytes": 16_668_810,
}
EXPECTED_CATALOG_PATH = "registry/skill-catalog.yaml"
EXPECTED_PIPELINES = frozenset(
    {
        "ai-agent-rag-golden-route",
        "capability-gap-to-skill",
        "cross-language-golden-route",
        "customer-delivery-lifecycle",
        "customer-private-adapter",
        "data-platform-golden-route",
        "database-zero-downtime-golden-route",
        "experience-to-dataset",
        "frontend-miniapp-golden-route",
        "knowledge-to-skill",
        "project-generation-golden-route",
        "repository-task-intake-to-certify",
        "spring-modernization-golden-route",
        "train-certify-deploy",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,255}$")

_ROOT_KEYS = {"schema_version", "package", "authority", "discovery", "atomic_skills", "meta_skills", "pipelines"}
_PACKAGE_KEYS = {"id", "name", "version", "archive_sha256", "archive_bytes"}
_AUTHORITY_KEYS = {"catalog_path", "catalog_sha256", "auxiliary_json_status"}
_DISCOVERY_KEYS = {"startup", "candidate_limit", "activation_limit"}
_ATOMIC_KEYS = {
    "name", "pack", "version", "priority", "risk_class", "maturity", "owner",
    "description", "kernel", "exposure", "source_path", "source_sha256",
    "source_bindings", "dependencies", "dependency_semantics", "inputs",
    "input_contracts", "outputs", "output_contracts", "preconditions", "workflow",
    "allowed_tools", "tool_contract", "required_gates", "evidence_contract",
    "rollback_contract", "execution_contract", "compatibility_contract",
    "maturity_contract", "learning_contract", "telemetry_contract", "support_contract",
    "business_lines", "capability_tags", "triggers", "negative_triggers", "invariants",
    "failure_modes", "contract_generation", "policy_contract", "conformance_contract",
    "activation_contract", "handler_id", "semantic_handler_binding", "capability_state",
    "external_evidence_status", "certification_status",
}
_META_KEYS = {"name", "pack", "source_path", "source_sha256", "candidates"}
_PIPELINE_KEYS = {"name", "kind", "source_path", "source_sha256", "execution_mode"}
_SOURCE_BINDING_KEYS = {
    "skill_markdown", "skill_contract", "execution_policy", "conformance",
    "eval_contract", "eval_cases",
}
_UNBOUND = "UNBOUND"
_BOOTSTRAP_SKILLS = frozenset(
    {
        "typed-skill-contract", "evidence-contract", "policy-contract",
        "skill-transaction-and-rollback", "tenant-policy-aware-retrieval",
    }
)
_BASIC_PRECONDITIONS = (
    "tenant.authorized == true",
    "task.contract != null",
    "release.versionPinned == true",
)
_ENHANCED_PRECONDITIONS = _BASIC_PRECONDITIONS + (
    "baseline.snapshotAvailable == true",
    "evidence.serviceAvailable == true",
)
_BASIC_POLICY = {
    "default": "deny",
    "allow_when": (
        "tenant-authorized",
        "version-compatible",
        "required-evidence-service-available",
    ),
    "approval_when": (
        "production-write",
        "data-export",
        "training-global",
        "security-policy-change",
    ),
    "deny_when": (
        "revoked-skill",
        "unsigned-dependency",
        "quarantined-data",
        "cross-tenant-access",
    ),
}
_ENHANCED_POLICY = {
    "default": "deny",
    "allow_when": (
        "tenant-authorized",
        "version-compatible",
        "baseline-and-rollback-available",
        "required-evidence-service-available",
        "tool-authority-owned-by-environment",
    ),
    "approval_when": (
        "production-write",
        "irreversible-data-change",
        "data-export",
        "training-or-adapter-update",
        "security-policy-change",
    ),
    "deny_when": (
        "revoked-skill",
        "unsigned-dependency",
        "quarantined-data",
        "cross-tenant-access",
        "missing-version-pin",
        "hard-gate-bypass-requested",
    ),
}
_CONFORMANCE_CHECKS = (
    "schema-valid",
    "frontmatter-valid",
    "id-unique-and-length-valid",
    "owner-and-business-line-assigned",
    "dependencies-resolvable-and-acyclic",
    "tools-default-deny",
    "eight-positive-eight-negative-four-ambiguous-four-adversarial-evals",
    "evidence-gates-nonempty",
    "rollback-required",
    "learning-policy-explicit",
    "telemetry-wall-clock-and-cost-enabled",
    "unsupported-version-never-presented-as-supported",
    "no-placeholder-or-empty-required-artifact",
)
_BASIC_FAILURE_MODES = (
    "unsupported-version-or-environment",
    "insufficient-semantic-coverage",
    "deterministic-verification-failure",
    "authorization-or-data-rights-failure",
    "rollback-target-unavailable",
)
_ENHANCED_FAILURE_MODES = (
    "unsupported-source-or-target-version",
    "insufficient-semantic-or-contract-coverage",
    "deterministic-verification-failure",
    "security-privacy-or-license-policy-failure",
    "performance-or-capacity-regression",
    "rollback-or-recovery-evidence-missing",
)


class CatalogValidationError(RuntimeError):
    """The checked-in compiled catalog is missing, malformed, or inconsistent."""


def _exact_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogValidationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise CatalogValidationError(
            f"{label} keys mismatch; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CatalogValidationError(f"{label} must be a non-empty canonical string")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise CatalogValidationError(f"{label} contains a control character")
    return value


def _slug(value: Any, label: str) -> str:
    text = _string(value, label)
    if _SLUG_RE.fullmatch(text) is None:
        raise CatalogValidationError(f"{label} must be a lowercase hyphenated identifier")
    return text


def _digest(value: Any, label: str) -> str:
    text = _string(value, label)
    if not _SHA256_RE.fullmatch(text):
        raise CatalogValidationError(f"{label} must be a lowercase SHA-256")
    return text


def _relative_path(value: Any, label: str) -> str:
    text = _string(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise CatalogValidationError(f"{label} must be a safe relative POSIX path")
    return text


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CatalogValidationError(f"{label} must be an array")
    result = tuple(_string(item, f"{label}[]") for item in value)
    if len(set(result)) != len(result):
        raise CatalogValidationError(f"{label} must not contain duplicates")
    return result


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _freeze_record(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _deep_freeze(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - caller contract
        raise TypeError("record must remain a mapping")
    return frozen


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise CatalogValidationError(f"{label} must be boolean")
    return value


def _unbound_or_boolean(value: Any, label: str) -> bool | str:
    if value == _UNBOUND:
        return _UNBOUND
    return _boolean(value, label)


def _unbound_or_nonnegative_int(value: Any, label: str) -> int | str:
    if value == _UNBOUND:
        return _UNBOUND
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CatalogValidationError(f"{label} must be UNBOUND or a non-negative integer")
    return value


def _typed_io_contracts(
    value: Any,
    *,
    label: str,
    flag_name: str,
    expected_names: Sequence[str],
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise CatalogValidationError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    names: list[str] = []
    for index, raw in enumerate(value):
        row_label = f"{label}[{index}]"
        row = _exact_keys(raw, {"name", flag_name, "schema_binding"}, row_label)
        name = _string(row["name"], f"{row_label}.name")
        if row[flag_name] is not True or row["schema_binding"] != _UNBOUND:
            raise CatalogValidationError(f"{row_label} must preserve true flag and UNBOUND schema")
        names.append(name)
        rows.append(_freeze_record(dict(row)))
    if tuple(names) != tuple(expected_names) or len(set(names)) != len(names):
        raise CatalogValidationError(f"{label} does not match declared names")
    return tuple(rows)


def _closed_contract(
    value: Any,
    expected_keys: set[str],
    label: str,
) -> Mapping[str, Any]:
    return _exact_keys(value, expected_keys, label)


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    path: Path
    content_sha256: str
    source_authority_status: str
    runtime_archive_reverified: bool
    package: Mapping[str, Any]
    authority: Mapping[str, Any]
    discovery: Mapping[str, Any]
    atomic_skills: Mapping[str, Mapping[str, Any]]
    meta_skills: Mapping[str, Mapping[str, Any]]
    pipelines: Mapping[str, Mapping[str, Any]]


def _validate_source_bindings(
    value: Any,
    *,
    label: str,
    pack: str,
    name: str,
    source_digests: dict[str, str],
) -> Mapping[str, Any]:
    bindings = _exact_keys(value, _SOURCE_BINDING_KEYS, label)
    base = f"skills/atomic/{pack}/{name}"
    expected_paths = {
        "skill_markdown": f"{base}/SKILL.md",
        "skill_contract": f"{base}/skill.yaml",
        "execution_policy": f"{base}/policies/execution.yaml",
        "conformance": f"{base}/tests/conformance.yaml",
        "eval_contract": f"{base}/evals/contract.yaml",
        "eval_cases": f"{base}/evals/cases.yaml",
    }
    compiled: dict[str, Mapping[str, str]] = {}
    for role, expected_path in expected_paths.items():
        item_label = f"{label}.{role}"
        item = _exact_keys(bindings[role], {"path", "sha256"}, item_label)
        path = _relative_path(item["path"], f"{item_label}.path")
        digest = _digest(item["sha256"], f"{item_label}.sha256")
        if path != expected_path:
            raise CatalogValidationError(f"{name}: {role} source path is not exact")
        if path in source_digests:
            raise CatalogValidationError(f"duplicate source authority path: {path}")
        source_digests[path] = digest
        compiled[role] = MappingProxyType({"path": path, "sha256": digest})
    return MappingProxyType(compiled)


def _validate_atomic_contract_row(
    row: Mapping[str, Any],
    *,
    label: str,
    name: str,
    pack: str,
    source_digests: dict[str, str],
) -> Mapping[str, Any]:
    generation = _string(row["contract_generation"], f"{label}.contract_generation")
    if generation not in {"BASIC", "ENHANCED"}:
        raise CatalogValidationError(f"{name}: unsupported contract generation")
    enhanced = generation == "ENHANCED"
    inputs = _string_tuple(row["inputs"], f"{label}.inputs")
    outputs = _string_tuple(row["outputs"], f"{label}.outputs")
    input_contracts = _typed_io_contracts(
        row["input_contracts"],
        label=f"{label}.input_contracts",
        flag_name="required",
        expected_names=inputs,
    )
    output_contracts = _typed_io_contracts(
        row["output_contracts"],
        label=f"{label}.output_contracts",
        flag_name="content_addressed",
        expected_names=outputs,
    )
    preconditions = _string_tuple(row["preconditions"], f"{label}.preconditions")
    if preconditions != (_ENHANCED_PRECONDITIONS if enhanced else _BASIC_PRECONDITIONS):
        raise CatalogValidationError(f"{name}: precondition profile drift")
    workflow = _string_tuple(row["workflow"], f"{label}.workflow")
    if len(workflow) != 7:
        raise CatalogValidationError(f"{name}: workflow must contain exactly seven steps")

    allowed_tools = _string_tuple(row["allowed_tools"], f"{label}.allowed_tools")
    tools = _closed_contract(
        row["tool_contract"],
        {
            "allowed", "default_deny", "environment_owned_authority",
            "parameter_validation_required", "parameter_schemas",
        },
        f"{label}.tool_contract",
    )
    if _string_tuple(tools["allowed"], f"{label}.tool_contract.allowed") != allowed_tools:
        raise CatalogValidationError(f"{name}: tool allowlist projection drift")
    if tools["default_deny"] is not True or tools["parameter_schemas"] != _UNBOUND:
        raise CatalogValidationError(f"{name}: tool fail-closed boundary drift")
    expected_enhanced_value: bool | str = True if enhanced else _UNBOUND
    if (
        tools["environment_owned_authority"] != expected_enhanced_value
        or tools["parameter_validation_required"] != expected_enhanced_value
    ):
        raise CatalogValidationError(f"{name}: tool generation profile drift")

    required_gates = _string_tuple(row["required_gates"], f"{label}.required_gates")
    evidence = _closed_contract(
        row["evidence_contract"],
        {
            "required_gates", "minimum_level", "independent_replay_required",
            "source_binding_required",
        },
        f"{label}.evidence_contract",
    )
    if _string_tuple(evidence["required_gates"], f"{label}.evidence_contract.required_gates") != required_gates:
        raise CatalogValidationError(f"{name}: evidence gate projection drift")
    minimum_level = _string(evidence["minimum_level"], f"{label}.evidence_contract.minimum_level")
    if minimum_level not in {"E1", "E2", "E3"}:
        raise CatalogValidationError(f"{name}: evidence level is unsupported")
    expected_replay: bool | str = minimum_level == "E3" if enhanced else _UNBOUND
    expected_source_binding: bool | str = True if enhanced else _UNBOUND
    if (
        evidence["independent_replay_required"] != expected_replay
        or evidence["source_binding_required"] != expected_source_binding
    ):
        raise CatalogValidationError(f"{name}: evidence generation profile drift")

    rollback = _closed_contract(
        row["rollback_contract"],
        {"required", "strategy", "rehearsal_required"},
        f"{label}.rollback_contract",
    )
    if rollback["required"] is not True:
        raise CatalogValidationError(f"{name}: rollback must be required")
    expected_strategy = (
        "restore-versioned-checkpoint-and-compensate-side-effects"
        if enhanced
        else "restore-checkpoint-and-compensate-side-effects"
    )
    risk_class = _string(row["risk_class"], f"{label}.risk_class")
    expected_rehearsal: bool | str = risk_class == "critical" if enhanced else _UNBOUND
    if rollback["strategy"] != expected_strategy or rollback["rehearsal_required"] != expected_rehearsal:
        raise CatalogValidationError(f"{name}: rollback profile drift")

    execution = _closed_contract(
        row["execution_contract"],
        {
            "class", "idempotency_required", "checkpoint_required",
            "independent_verification_required", "production_write_approval_required",
            "max_unverified_side_effects",
        },
        f"{label}.execution_contract",
    )
    if (
        execution["class"] != "durable-replayable"
        or execution["idempotency_required"] is not True
        or execution["checkpoint_required"] is not True
        or execution["independent_verification_required"] is not True
        or execution["production_write_approval_required"] is not True
        or execution["max_unverified_side_effects"] != (0 if enhanced else _UNBOUND)
    ):
        raise CatalogValidationError(f"{name}: execution profile drift")

    compatibility = _closed_contract(
        row["compatibility_contract"],
        {"package_version", "runtime", "version_pinned", "matrix_required", "exact_runtime_tuple"},
        f"{label}.compatibility_contract",
    )
    if dict(compatibility) != {
        "package_version": "3.0.0",
        "runtime": "Elmos Proof-Driven Agentic Harness v3+",
        "version_pinned": True,
        "matrix_required": True,
        "exact_runtime_tuple": _UNBOUND,
    }:
        raise CatalogValidationError(f"{name}: compatibility profile drift")
    maturity = _closed_contract(
        row["maturity_contract"],
        {"status", "runtime_implementation", "certification_target"},
        f"{label}.maturity_contract",
    )
    if dict(maturity) != {
        "status": "specification-ready",
        "runtime_implementation": "required",
        "certification_target": minimum_level,
    }:
        raise CatalogValidationError(f"{name}: maturity profile drift")

    policy = _closed_contract(
        row["policy_contract"],
        {"default", "allow_when", "approval_when", "deny_when"},
        f"{label}.policy_contract",
    )
    normalized_policy: dict[str, str | tuple[str, ...]] = {
        "default": _string(policy["default"], f"{label}.policy_contract.default")
    }
    for field in ("allow_when", "approval_when", "deny_when"):
        normalized_policy[field] = _string_tuple(
            policy[field], f"{label}.policy_contract.{field}"
        )
    if normalized_policy != (_ENHANCED_POLICY if enhanced else _BASIC_POLICY):
        raise CatalogValidationError(f"{name}: policy generation profile drift")

    conformance = _closed_contract(
        row["conformance_contract"],
        {"package_version", "required_checks", "runtime_status"},
        f"{label}.conformance_contract",
    )
    if (
        conformance["package_version"] != "3.0.0"
        or conformance["runtime_status"] != "not-implemented-by-this-specification-package"
        or _string_tuple(
            conformance["required_checks"],
            f"{label}.conformance_contract.required_checks",
        )
        != _CONFORMANCE_CHECKS
    ):
        raise CatalogValidationError(f"{name}: conformance boundary drift")

    activation = _closed_contract(
        row["activation_contract"],
        {
            "positive_required", "negative_required", "ambiguous_required",
            "adversarial_required", "split", "outcome", "process", "efficiency",
            "security", "learning", "corpus_embedded",
        },
        f"{label}.activation_contract",
    )
    if (
        activation["positive_required"] != 8
        or activation["negative_required"] != 8
        or activation["ambiguous_required"] != 4
        or activation["adversarial_required"] != 4
        or activation["split"] != "repo-org-time-disjoint"
        or activation["corpus_embedded"] is not False
    ):
        raise CatalogValidationError(f"{name}: activation boundary drift")
    outcomes = activation["outcome"]
    if not isinstance(outcomes, list):
        raise CatalogValidationError(f"{label}.activation_contract.outcome must be an array")
    outcome_gates: list[str] = []
    for index, raw_outcome in enumerate(outcomes):
        outcome = _exact_keys(
            raw_outcome, {"gate", "type"}, f"{label}.activation_contract.outcome[{index}]"
        )
        outcome_gates.append(_string(outcome["gate"], f"{label}.activation_contract.outcome[{index}].gate"))
        if outcome["type"] != "deterministic-first":
            raise CatalogValidationError(f"{name}: activation outcome type drift")
    if tuple(outcome_gates) != required_gates:
        raise CatalogValidationError(f"{name}: activation/evidence gate mismatch")
    expected_activation_profiles = {
        "process": (
            (
                "authorized-tools-only",
                "environment-owned-authority",
                "checkpoint-created",
                "source-target-lineage",
                "independent-verification",
                "rollback-on-hard-failure",
            )
            if enhanced
            else (
                "authorized-tools-only",
                "checkpoint-created",
                "independent-verification",
                "rollback-on-hard-failure",
            )
        ),
        "efficiency": (
            (
                "wall_clock_ms",
                "queue_ms",
                "input_tokens",
                "output_tokens",
                "tool_calls",
                "build_minutes",
                "cost",
            )
            if enhanced
            else ("wall_clock_ms", "input_tokens", "output_tokens", "tool_calls", "cost")
        ),
        "security": (
            (
                "tenant-isolation",
                "prompt-injection",
                "secret-leakage",
                "artifact-integrity",
                "supply-chain",
            )
            if enhanced
            else (
                "tenant-isolation",
                "prompt-injection",
                "secret-leakage",
                "artifact-integrity",
            )
        ),
        "learning": (
            "training-rights",
            "dataset-tier",
            "eval-leakage",
            "human-acceptance",
        ),
    }
    for field, expected_profile in expected_activation_profiles.items():
        if (
            _string_tuple(activation[field], f"{label}.activation_contract.{field}")
            != expected_profile
        ):
            raise CatalogValidationError(f"{name}: activation {field} profile drift")

    source_bindings = _validate_source_bindings(
        row["source_bindings"],
        label=f"{label}.source_bindings",
        pack=pack,
        name=name,
        source_digests=source_digests,
    )
    source_path = _relative_path(row["source_path"], f"{label}.source_path")
    source_sha256 = _digest(row["source_sha256"], f"{label}.source_sha256")
    if (
        source_path != source_bindings["skill_markdown"]["path"]
        or source_sha256 != source_bindings["skill_markdown"]["sha256"]
    ):
        raise CatalogValidationError(f"{name}: primary source projection drift")

    dependencies = _string_tuple(row["dependencies"], f"{label}.dependencies")
    dependency_semantics = _string(row["dependency_semantics"], f"{label}.dependency_semantics")
    if dependency_semantics != ("bootstrap-dag" if name in _BOOTSTRAP_SKILLS else _UNBOUND):
        raise CatalogValidationError(f"{name}: dependency semantics drift")

    semantic_handler = _string(
        row["semantic_handler_binding"], f"{label}.semantic_handler_binding"
    )
    capability_state = _string(row["capability_state"], f"{label}.capability_state")
    if capability_state == "PREPARE_ONLY":
        if semantic_handler != _UNBOUND:
            raise CatalogValidationError(f"{name}: prepare-only Skill cannot bind semantic handler")
    elif capability_state == "LOCAL":
        if semantic_handler != f"local.{name}":
            raise CatalogValidationError(f"{name}: LOCAL semantic handler binding is not exact")
    else:
        raise CatalogValidationError(f"{name}: unsupported capability state")

    simple_string_fields = (
        "owner", "description", "kernel", "exposure", "maturity",
    )
    normalized: dict[str, Any] = {
        field: _string(row[field], f"{label}.{field}") for field in simple_string_fields
    }
    if normalized["exposure"] != "atomic-registry-only" or normalized["maturity"] != "specification-ready":
        raise CatalogValidationError(f"{name}: exposure or maturity overclaim")
    tuple_fields = (
        "business_lines", "capability_tags", "triggers", "negative_triggers",
        "invariants", "failure_modes",
    )
    normalized.update(
        {field: _string_tuple(row[field], f"{label}.{field}") for field in tuple_fields}
    )
    invariant_tail = (
        (
            "tenant-boundary-preserved",
            "source-and-target-traceable",
            "no-hidden-test-weakening",
            "no-evidence-fabrication",
            "machine-wall-clock-recorded",
        )
        if enhanced
        else (
            "tenant-boundary-preserved",
            "no-evidence-fabrication",
            "hard-gates-not-weakened",
        )
    )
    if normalized["invariants"] != required_gates + invariant_tail:
        raise CatalogValidationError(f"{name}: gate/invariant alignment drift")
    if normalized["failure_modes"] != (
        _ENHANCED_FAILURE_MODES if enhanced else _BASIC_FAILURE_MODES
    ):
        raise CatalogValidationError(f"{name}: failure-mode generation profile drift")
    learning = _closed_contract(
        row["learning_contract"],
        {
            "captureTrajectory",
            "globalTrainingEligible",
            "tenantAdapterEligible",
            *(("humanAcceptanceRequired", "minimumDatasetTier") if enhanced else ()),
        },
        f"{label}.learning_contract",
    )
    expected_learning: dict[str, Any] = {
        "captureTrajectory": True,
        "globalTrainingEligible": False,
        "tenantAdapterEligible": "explicit-opt-in",
    }
    if enhanced:
        expected_learning.update(
            {
                "humanAcceptanceRequired": risk_class == "critical",
                "minimumDatasetTier": "Gold",
            }
        )
    if dict(learning) != expected_learning:
        raise CatalogValidationError(f"{name}: learning generation profile drift")
    telemetry = _closed_contract(
        row["telemetry_contract"],
        {
            "emitTrace",
            "emitCost",
            "emitWallClock",
            *(("emitEvidenceLineage", "emitProgress", "sensitiveContentDefault") if enhanced else ()),
        },
        f"{label}.telemetry_contract",
    )
    expected_telemetry: dict[str, Any] = {
        "emitTrace": True,
        "emitCost": True,
        "emitWallClock": True,
    }
    if enhanced:
        expected_telemetry.update(
            {
                "emitEvidenceLineage": True,
                "emitProgress": True,
                "sensitiveContentDefault": "redacted",
            }
        )
    if dict(telemetry) != expected_telemetry:
        raise CatalogValidationError(f"{name}: telemetry generation profile drift")
    support = _closed_contract(
        row["support_contract"],
        {"supportTier", "deprecationPolicyRequired"},
        f"{label}.support_contract",
    )
    if (
        support["supportTier"] not in {"standard", "LTS-candidate"}
        or support["deprecationPolicyRequired"] is not True
    ):
        raise CatalogValidationError(f"{name}: support profile drift")
    normalized.update(
        {
            "name": name,
            "pack": pack,
            "version": "3.0.0",
            "priority": _string(row["priority"], f"{label}.priority"),
            "risk_class": risk_class,
            "source_path": source_path,
            "source_sha256": source_sha256,
            "source_bindings": source_bindings,
            "dependencies": dependencies,
            "dependency_semantics": dependency_semantics,
            "inputs": inputs,
            "input_contracts": input_contracts,
            "outputs": outputs,
            "output_contracts": output_contracts,
            "preconditions": preconditions,
            "workflow": workflow,
            "allowed_tools": allowed_tools,
            "tool_contract": _deep_freeze(dict(tools)),
            "required_gates": required_gates,
            "evidence_contract": _deep_freeze(dict(evidence)),
            "rollback_contract": _deep_freeze(dict(rollback)),
            "execution_contract": _deep_freeze(dict(execution)),
            "compatibility_contract": _deep_freeze(dict(compatibility)),
            "maturity_contract": _deep_freeze(dict(maturity)),
            "learning_contract": _deep_freeze(dict(learning)),
            "telemetry_contract": _deep_freeze(dict(telemetry)),
            "support_contract": _deep_freeze(dict(support)),
            "contract_generation": generation,
            "policy_contract": _deep_freeze(dict(policy)),
            "conformance_contract": _deep_freeze(dict(conformance)),
            "activation_contract": _deep_freeze(dict(activation)),
            "handler_id": _string(row["handler_id"], f"{label}.handler_id"),
            "semantic_handler_binding": semantic_handler,
            "capability_state": capability_state,
            "external_evidence_status": _string(
                row["external_evidence_status"], f"{label}.external_evidence_status"
            ),
            "certification_status": _string(
                row["certification_status"], f"{label}.certification_status"
            ),
        }
    )
    return _freeze_record(normalized)


def load_compiled_catalog(path: Path = DEFAULT_CATALOG_PATH) -> CatalogSnapshot:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise CatalogValidationError(f"compiled catalog unavailable: {path}: {exc}") from exc
    observed_catalog_digest = hashlib.sha256(raw_bytes).hexdigest()
    if observed_catalog_digest != EXPECTED_COMPILED_CATALOG_SHA256:
        raise CatalogValidationError(
            "compiled catalog SHA-256 does not match the hard-pinned runtime identity"
        )
    try:
        raw = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(f"compiled catalog is invalid JSON: {exc}") from exc
    root = _exact_keys(raw, _ROOT_KEYS, "catalog")
    if root["schema_version"] != CATALOG_SCHEMA_VERSION:
        raise CatalogValidationError("compiled catalog schema_version is unsupported")
    package = _exact_keys(root["package"], _PACKAGE_KEYS, "package")
    if dict(package) != EXPECTED_PACKAGE:
        raise CatalogValidationError("compiled catalog package identity is not pinned v3")
    authority = _exact_keys(root["authority"], _AUTHORITY_KEYS, "authority")
    if authority["catalog_path"] != EXPECTED_CATALOG_PATH:
        raise CatalogValidationError("catalog authority path is not exact")
    catalog_authority_digest = _digest(authority["catalog_sha256"], "authority.catalog_sha256")
    if authority["auxiliary_json_status"] != "STALE_NON_AUTHORITATIVE":
        raise CatalogValidationError("auxiliary JSON must remain stale and non-authoritative")
    discovery = _exact_keys(root["discovery"], _DISCOVERY_KEYS, "discovery")
    if dict(discovery) != {"startup": "meta-only", "candidate_limit": 16, "activation_limit": 8}:
        raise CatalogValidationError("compiled catalog discovery limits are not exact")

    atomic_rows = root["atomic_skills"]
    meta_rows = root["meta_skills"]
    pipeline_rows = root["pipelines"]
    if not isinstance(atomic_rows, list) or len(atomic_rows) != 1_310:
        raise CatalogValidationError("compiled catalog must contain exactly 1,310 atomic Skills")
    if not isinstance(meta_rows, list) or len(meta_rows) != 41:
        raise CatalogValidationError("compiled catalog must contain exactly 41 meta Skills")
    if not isinstance(pipeline_rows, list) or len(pipeline_rows) != 14:
        raise CatalogValidationError("compiled catalog must contain exactly 14 pipelines")

    atomic: dict[str, Mapping[str, Any]] = {}
    packs: set[str] = set()
    source_digests: dict[str, str] = {EXPECTED_CATALOG_PATH: catalog_authority_digest}
    for index, row_value in enumerate(atomic_rows):
        label = f"atomic_skills[{index}]"
        row = _exact_keys(row_value, _ATOMIC_KEYS, label)
        name = _slug(row["name"], f"{label}.name")
        if name in atomic:
            raise CatalogValidationError(f"duplicate atomic Skill: {name}")
        pack = _slug(row["pack"], f"{label}.pack")
        compiled_row = _validate_atomic_contract_row(
            row,
            label=label,
            name=name,
            pack=pack,
            source_digests=source_digests,
        )
        handler_id = str(compiled_row["handler_id"])
        if handler_id != f"pack.{pack.replace('-', '_')}" or handler_id not in PACK_HANDLER_REGISTRY:
            raise CatalogValidationError(f"{name}: handler binding is not allowlisted and exact")
        if row["version"] != "3.0.0":
            raise CatalogValidationError(f"{name}: version is not exact")
        if row["external_evidence_status"] != EXTERNAL_EVIDENCE_STATUS:
            raise CatalogValidationError(f"{name}: external evidence cannot claim execution")
        if row["certification_status"] != CERTIFICATION_STATUS:
            raise CatalogValidationError(f"{name}: certification status must fail closed")
        atomic[name] = compiled_row
        packs.add(pack)
    generation_counts = Counter(str(row["contract_generation"]) for row in atomic.values())
    if generation_counts != Counter({"BASIC": 458, "ENHANCED": 852}):
        raise CatalogValidationError("compiled contract generation distribution is not exact")
    bootstrap_names = {
        name for name, row in atomic.items() if row["dependency_semantics"] == "bootstrap-dag"
    }
    if bootstrap_names != _BOOTSTRAP_SKILLS:
        raise CatalogValidationError("bootstrap dependency semantics set is not exact")
    local_names = {
        name for name, row in atomic.items() if row["capability_state"] == "LOCAL"
    }
    if local_names != LOCAL_SEMANTIC_SKILLS:
        raise CatalogValidationError(
            "compiled LOCAL capability set does not match the exact local semantic registry"
        )
    if len(packs) != 41:
        raise CatalogValidationError("atomic Skills must cover exactly 41 packs")
    if {handler.pack for handler in PACK_HANDLER_REGISTRY.values()} != packs:
        raise CatalogValidationError("catalog packs do not match the 41-pack handler allowlist")
    atomic_names = set(atomic)
    for name, row in atomic.items():
        missing_dependencies = sorted(set(row["dependencies"]) - atomic_names)
        if missing_dependencies:
            raise CatalogValidationError(f"{name}: unresolved dependencies: {missing_dependencies}")
    _check_dag(atomic)

    meta: dict[str, Mapping[str, Any]] = {}
    meta_packs: set[str] = set()
    for index, row_value in enumerate(meta_rows):
        label = f"meta_skills[{index}]"
        row = _exact_keys(row_value, _META_KEYS, label)
        name = _slug(row["name"], f"{label}.name")
        pack = _slug(row["pack"], f"{label}.pack")
        if name in meta or pack in meta_packs:
            raise CatalogValidationError("meta Skills and pack ownership must be unique")
        if name != f"elmos-{pack}" or pack not in packs:
            raise CatalogValidationError(f"{name}: meta Skill identity is not exact")
        candidates = _string_tuple(row["candidates"], f"{label}.candidates")
        if candidates != tuple(sorted(candidates)):
            raise CatalogValidationError(f"{name}: candidates must be canonically sorted")
        expected_candidates = {atomic_name for atomic_name, atomic_row in atomic.items() if atomic_row["pack"] == pack}
        if set(candidates) != expected_candidates:
            raise CatalogValidationError(f"{name}: candidate ownership is incomplete or foreign")
        source_path = _relative_path(row["source_path"], f"{label}.source_path")
        if source_path != f"skills/meta/{pack}/SKILL.md":
            raise CatalogValidationError(f"{name}: meta source path is not exact")
        source_sha256 = _digest(row["source_sha256"], f"{label}.source_sha256")
        if source_path in source_digests:
            raise CatalogValidationError(f"duplicate source authority path: {source_path}")
        source_digests[source_path] = source_sha256
        meta[name] = _freeze_record(
            {"name": name, "pack": pack, "source_path": source_path, "source_sha256": source_sha256, "candidates": candidates}
        )
        meta_packs.add(pack)
    if meta_packs != packs:
        raise CatalogValidationError("meta Skills must own all and only the 41 packs")

    pipelines: dict[str, Mapping[str, Any]] = {}
    pipeline_kinds: Counter[str] = Counter()
    for index, row_value in enumerate(pipeline_rows):
        label = f"pipelines[{index}]"
        row = _exact_keys(row_value, _PIPELINE_KEYS, label)
        name = _slug(row["name"], f"{label}.name")
        if name in pipelines:
            raise CatalogValidationError(f"duplicate pipeline: {name}")
        kind = _string(row["kind"], f"{label}.kind")
        if kind not in {"Pipeline", "DurablePipeline"}:
            raise CatalogValidationError(f"{name}: unsupported pipeline kind")
        if row["execution_mode"] != "PREPARE_ONLY":
            raise CatalogValidationError(f"{name}: pipeline cannot claim runtime execution")
        source_path = _relative_path(row["source_path"], f"{label}.source_path")
        if source_path != f"pipelines/{name}.yaml":
            raise CatalogValidationError(f"{name}: pipeline source path is not exact")
        source_sha256 = _digest(row["source_sha256"], f"{label}.source_sha256")
        if source_path in source_digests:
            raise CatalogValidationError(f"duplicate source authority path: {source_path}")
        source_digests[source_path] = source_sha256
        pipelines[name] = _freeze_record(
            {"name": name, "kind": kind, "source_path": source_path, "source_sha256": source_sha256, "execution_mode": "PREPARE_ONLY"}
        )
        pipeline_kinds[kind] += 1
    if set(pipelines) != EXPECTED_PIPELINES:
        raise CatalogValidationError("pipeline registry is not the exact 14-pipeline set")
    if pipeline_kinds != Counter({"DurablePipeline": 10, "Pipeline": 4}):
        raise CatalogValidationError("pipeline kind distribution is not source exact")

    packaged_runtime = path.resolve() == PACKAGED_CATALOG_PATH.resolve()
    if packaged_runtime:
        source_authority_status = "BUILD_TIME_DIGEST_BOUND_SOURCE_AUTHORITY"
        runtime_archive_reverified = False
    else:
        _verify_archive_sources(source_digests)
        source_authority_status = "RUNTIME_ARCHIVE_REVERIFIED"
        runtime_archive_reverified = True
    return CatalogSnapshot(
        path=path.resolve(),
        content_sha256=observed_catalog_digest,
        source_authority_status=source_authority_status,
        runtime_archive_reverified=runtime_archive_reverified,
        package=MappingProxyType(dict(package)),
        authority=MappingProxyType(dict(authority)),
        discovery=MappingProxyType(dict(discovery)),
        atomic_skills=MappingProxyType(atomic),
        meta_skills=MappingProxyType(meta),
        pipelines=MappingProxyType(pipelines),
    )


def _verify_archive_sources(source_digests: Mapping[str, str]) -> None:
    """Bind every compiled authority row back to bytes in the pinned ZIP."""
    try:
        if SOURCE_ARCHIVE_PATH.is_symlink():
            raise CatalogValidationError("pinned source archive must not be a symlink")
        archive_bytes = SOURCE_ARCHIVE_PATH.read_bytes()
    except OSError as exc:
        raise CatalogValidationError(f"pinned source archive unavailable: {exc}") from exc
    if len(archive_bytes) != EXPECTED_PACKAGE["archive_bytes"]:
        raise CatalogValidationError("pinned source archive byte size drift")
    if hashlib.sha256(archive_bytes).hexdigest() != EXPECTED_PACKAGE["archive_sha256"]:
        raise CatalogValidationError("pinned source archive SHA-256 drift")
    try:
        with zipfile.ZipFile(SOURCE_ARCHIVE_PATH) as archive:
            members: dict[str, list[zipfile.ZipInfo]] = {}
            for info in archive.infolist():
                members.setdefault(info.filename, []).append(info)
            for relative_path, expected_digest in source_digests.items():
                member_name = SOURCE_ARCHIVE_PREFIX + relative_path
                matches = members.get(member_name, [])
                if len(matches) != 1 or matches[0].is_dir():
                    raise CatalogValidationError(f"archive source member is absent, duplicate, or non-file: {relative_path}")
                hasher = hashlib.sha256()
                with archive.open(matches[0], "r") as source:
                    while chunk := source.read(1024 * 1024):
                        hasher.update(chunk)
                if hasher.hexdigest() != expected_digest:
                    raise CatalogValidationError(f"compiled source digest does not match archive: {relative_path}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise CatalogValidationError(f"pinned source archive cannot be verified: {exc}") from exc


def _check_dag(atomic: Mapping[str, Mapping[str, Any]]) -> None:
    indegree = {name: 0 for name in atomic}
    outgoing: dict[str, list[str]] = {name: [] for name in atomic}
    for name, row in atomic.items():
        for dependency in row["dependencies"]:
            indegree[name] += 1
            outgoing[dependency].append(name)
    queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for successor in sorted(outgoing[current]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if visited != len(atomic):
        cycle = sorted(name for name, degree in indegree.items() if degree)
        raise CatalogValidationError(f"atomic Skill dependency cycle: {cycle[:16]}")


class SkillCatalog:
    """Validated exact catalog plus prepare-only and adapter execution paths."""

    def __init__(self, kernel: ExecutionKernel | None = None, *, catalog_path: Path | None = None, adapter_registry: AdapterRegistry | None = None, store: FoundryStore | None = None) -> None:
        self.kernel = kernel or ExecutionKernel()
        self.snapshot = load_compiled_catalog(catalog_path or DEFAULT_CATALOG_PATH)
        self.store = store
        self.adapters = (
            adapter_registry
            if adapter_registry is not None
            else build_local_adapter_registry(cast(CatalogView, self.snapshot), store=store)
        )
        if adapter_registry is None:
            for name in sorted(LOCAL_SEMANTIC_SKILLS):
                binding = self.adapters.binding_for(name)
                if (
                    binding is None
                    or binding.adapter_id
                    != self.snapshot.atomic_skills[name]["semantic_handler_binding"]
                ):
                    raise CatalogValidationError(
                        f"{name}: local adapter registry/catalog binding mismatch"
                    )
        self._records = self.snapshot.atomic_skills
        self._meta_skills = self.snapshot.meta_skills
        self._pipelines = self.snapshot.pipelines
        self._skills: dict[str, SkillContract] = {}
        self._aliases: dict[str, str] = {}
        self._skill_bindings: dict[str, str] = {}
        for name, record in self._records.items():
            self._skills[name] = SkillContract(
                skill_name=name,
                pack=str(record["pack"]),
                owner=str(record["owner"]),
                risk_class=str(record["risk_class"]),
                status=LifecycleState.PLANNED,
                version=str(record["version"]),
                content_hash=str(record["source_sha256"]),
                preconditions=tuple(str(value) for value in record["preconditions"]),
                postconditions=tuple(str(value) for value in record["required_gates"]),
                inputs_schema={
                    "contracts": tuple(dict(value) for value in record["input_contracts"]),
                    "binding": _UNBOUND,
                },
                outputs_schema={
                    "contracts": tuple(dict(value) for value in record["output_contracts"]),
                    "binding": _UNBOUND,
                },
                rollback_policy=dict(record["rollback_contract"]),
            )
            installed_name = name if name.startswith("elmos-") else f"elmos-{name}"
            for alias in {name, installed_name}:
                owner = self._aliases.get(alias)
                if owner is not None and owner != name:
                    raise CatalogValidationError(f"ambiguous Skill alias: {alias}")
                self._aliases[alias] = name
            self._skill_bindings[name] = str(record["handler_id"])
        if len(self._skill_bindings) != 1_310:
            raise CatalogValidationError("every atomic Skill must have one exact binding")

    @property
    def total_atomic_skills(self) -> int:
        return len(self._skills)

    @property
    def total_meta_skills(self) -> int:
        return len(self._meta_skills)

    @property
    def total_pipelines(self) -> int:
        return len(self._pipelines)

    @property
    def skill_bindings(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self._skill_bindings))

    @property
    def pipeline_records(self) -> Mapping[str, Mapping[str, Any]]:
        return self._pipelines

    def _canonical_skill_name(self, skill_name: str) -> str | None:
        if not isinstance(skill_name, str) or not skill_name:
            return None
        return self._aliases.get(skill_name)

    def get_skill(self, skill_name: str) -> SkillContract | None:
        canonical = self._canonical_skill_name(skill_name)
        return self._skills.get(canonical) if canonical else None

    def get_skill_record(self, skill_name: str) -> Mapping[str, Any] | None:
        canonical = self._canonical_skill_name(skill_name)
        return self._records.get(canonical) if canonical else None

    def route_meta_skill_plan(
        self,
        meta_skill_name: str,
        query: str = "",
        *,
        filters: Mapping[str, Any] | None = None,
        candidate_limit: int | None = None,
        activation_limit: int | None = None,
    ) -> Mapping[str, Any]:
        if not isinstance(meta_skill_name, str):
            raise TypeError("meta_skill_name must be a string")
        meta_name = meta_skill_name if meta_skill_name.startswith("elmos-") else f"elmos-{meta_skill_name}"
        meta = self._meta_skills.get(meta_name)
        if meta is None:
            return MappingProxyType({"status": "UNKNOWN_META_SKILL", "meta_skill": meta_skill_name, "candidates": (), "activated": ()})
        configured_candidates = int(self.snapshot.discovery["candidate_limit"])
        configured_activation = int(self.snapshot.discovery["activation_limit"])
        candidate_bound = _bounded_limit(candidate_limit, configured_candidates, "candidate_limit")
        activation_bound = min(_bounded_limit(activation_limit, configured_activation, "activation_limit"), candidate_bound)
        records = [self._records[name] for name in meta["candidates"]]
        records = self._apply_filters(records, filters or {})
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        tokens = tuple(token for token in re.split(r"[^a-z0-9]+", query.lower()) if token)
        if tokens:
            records = [record for record in records if all(token in str(record["name"]).lower() for token in tokens)]
        candidates = tuple(str(record["name"]) for record in records[:candidate_bound])
        activated = candidates[:activation_bound]
        return MappingProxyType(
            {
                "status": "ROUTED",
                "meta_skill": meta_name,
                "pack": meta["pack"],
                "candidate_limit": candidate_bound,
                "activation_limit": activation_bound,
                "candidates": candidates,
                "activated": activated,
                "candidate_count": len(candidates),
                "activation_count": len(activated),
            }
        )

    def route_meta_skill(self, meta_skill_name: str, query: str = "", *, filters: Mapping[str, Any] | None = None, candidate_limit: int | None = None, activation_limit: int | None = None) -> Sequence[str]:
        return tuple(self.route_meta_skill_plan(meta_skill_name, query, filters=filters, candidate_limit=candidate_limit, activation_limit=activation_limit)["activated"])

    @staticmethod
    def _apply_filters(records: Sequence[Mapping[str, Any]], filters: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        if not isinstance(filters, Mapping):
            raise TypeError("filters must be an object")
        exact_fields = {"pack", "version", "priority", "risk_class", "maturity", "capability_state", "external_evidence_status", "certification_status", "handler_id"}
        collection_fields = {"dependency": "dependencies", "allowed_tool": "allowed_tools", "required_gate": "required_gates"}
        filtered = list(records)
        for key, expected in filters.items():
            if key in exact_fields:
                accepted = _accepted_filter_values(expected, key)
                filtered = [record for record in filtered if record[key] in accepted]
            elif key in collection_fields:
                accepted = _accepted_filter_values(expected, key)
                field = collection_fields[key]
                filtered = [record for record in filtered if accepted.issubset(set(record[field]))]
            elif key == "name_prefix":
                prefix = _string(expected, "filters.name_prefix")
                filtered = [record for record in filtered if str(record["name"]).startswith(prefix)]
            else:
                raise ValueError(f"unsupported filter fails closed: {key}")
        return filtered

    def execute_skill(
        self,
        skill_name: str,
        inputs: Mapping[str, Any],
        tenant_scope: TenantScope | None = None,
        *,
        adapter_id: str | None = None,
        invocation_id: str | None = None,
        permit: InvocationPermit | None = None,
    ) -> ExecutionResult:
        if not isinstance(inputs, Mapping):
            raise TypeError("Skill inputs must be an object")
        scope = tenant_scope or self.kernel.current_tenant
        operation = inputs.get("operation", "prepare")
        if not isinstance(operation, str) or not operation:
            self.kernel.require_context(scope, "foundry.skill.prepare")
            return _result(operation="invalid-operation", status="BLOCKED", outputs={"outcome": "INVALID_OPERATION", "execution_status": "NOT_RUN", "reason": "operation must be a non-empty string", "certification_status": CERTIFICATION_STATUS}, error="invalid operation")
        required_capability = "foundry.skill.prepare" if operation == "prepare" else "foundry.adapter.execute"
        self.kernel.require_context(scope, required_capability)
        canonical = self._canonical_skill_name(skill_name)
        if canonical is None:
            requested_shape = {"requested_type": type(skill_name).__name__, "requested_length": len(skill_name) if isinstance(skill_name, str) else 0}
            return _result(operation="unknown-skill", status="UNKNOWN_SKILL", outputs={"outcome": "UNKNOWN_SKILL", "requested_skill_digest": digest_json(requested_shape), "execution_status": "NOT_RUN", "external_evidence_status": EXTERNAL_EVIDENCE_STATUS, "certification_status": CERTIFICATION_STATUS}, error="unknown Skill has no runtime authority")
        record = self._records[canonical]
        if operation == "prepare":
            handler = PACK_HANDLER_REGISTRY[self._skill_bindings[canonical]]
            try:
                prepared = handler.prepare(skill=record, payload=inputs, tenant_scope=scope, catalog_digest=self.snapshot.content_sha256)
            except (TypeError, ValueError) as exc:
                return _result(operation=canonical, status="BLOCKED", outputs={"skill": canonical, "outcome": "BLOCKED", "execution_status": "NOT_RUN", "certification_status": CERTIFICATION_STATUS}, error=str(exc))
            outputs = dict(prepared.outputs)
            outputs["outcome"] = prepared.status
            return _result(operation=canonical, status=prepared.status, outputs=outputs, error=prepared.error)
        if not invocation_id:
            return _result(operation=canonical, status="NOT_RUN", outputs={"skill": canonical, "outcome": "NOT_RUN", "execution_status": "NOT_RUN", "reason": "non-prepare operations require an invocation_id", "external_evidence_status": EXTERNAL_EVIDENCE_STATUS, "certification_status": CERTIFICATION_STATUS}, error="missing invocation_id")
        if invocation_id != scope.invocation_id:
            return _result(operation=canonical, status="NOT_RUN", outputs={"skill": canonical, "outcome": "INVOCATION_SCOPE_MISMATCH", "execution_status": "NOT_RUN", "external_evidence_status": EXTERNAL_EVIDENCE_STATUS, "certification_status": CERTIFICATION_STATUS}, error="invocation_id does not match the host-minted context")
        adapter_result = self.adapters.invoke(
            skill_name=canonical,
            payload=inputs,
            tenant_scope=scope,
            invocation_id=invocation_id,
            adapter_id=adapter_id,
            permit=permit,
            risk_class=str(record["risk_class"]),
            required_inputs=tuple(str(item) for item in record["inputs"]),
            required_outputs=tuple(str(item) for item in record["outputs"]),
            allowed_tools=tuple(str(item) for item in record["allowed_tools"]),
            required_gates=tuple(str(item) for item in record["required_gates"]),
            store=self.store,
        )
        outputs = dict(adapter_result.outputs)
        outputs.update(
            {
                "local_maximum_decision": (
                    MAXIMUM_LOCAL_DECISION
                    if adapter_result.status == "SUCCEEDED"
                    else "NOT_READY"
                ),
                "external_evidence_status": adapter_result.external_evidence_status,
                "certification_status": adapter_result.certification_status,
                "outcome": adapter_result.status,
            }
        )
        return _result(operation=canonical, status=adapter_result.status, outputs=outputs, error=adapter_result.error, external_effects_performed=adapter_result.external_effects_performed)

    def describe(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "status": "LOCAL_RUNTIME_BOUND",
                "package": dict(self.snapshot.package),
                "catalog_sha256": self.snapshot.content_sha256,
                "source_authority": MappingProxyType(
                    {
                        "status": self.snapshot.source_authority_status,
                        "runtime_archive_reverified": self.snapshot.runtime_archive_reverified,
                        "archive_sha256": self.snapshot.package["archive_sha256"],
                        "compiled_catalog_sha256": self.snapshot.content_sha256,
                    }
                ),
                "atomic_skills": self.total_atomic_skills,
                "meta_skills": self.total_meta_skills,
                "packs": len(PACK_HANDLER_REGISTRY),
                "pipelines": self.total_pipelines,
                "bindings": len(self._skill_bindings),
                "adapters": self.adapters.describe(),
                "implementation_status": "MIXED_LOCAL_AND_PREPARE_ONLY",
                "capability_states": MappingProxyType(
                    {"LOCAL": len(LOCAL_SEMANTIC_SKILLS), "PREPARE_ONLY": 1_284}
                ),
                "local_evidence_status": "NOT_RUN",
                "local_evidence_ceiling": LOCAL_EVIDENCE_STATUS,
                "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
                "certification_status": CERTIFICATION_STATUS,
            }
        )


def _bounded_limit(requested: int | None, configured: int, label: str) -> int:
    value = configured if requested is None else requested
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    if value > configured:
        raise ValueError(f"{label} cannot exceed configured maximum {configured}")
    return value


def _accepted_filter_values(value: Any, label: str) -> set[str]:
    values: Iterable[Any]
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = value
    else:
        raise ValueError(f"filter {label} must be a string or string collection")
    accepted = {_string(item, f"filters.{label}") for item in values}
    if not accepted:
        raise ValueError(f"filter {label} must not be empty")
    return accepted


def _result(*, operation: str, status: str, outputs: Mapping[str, Any], error: str | None = None, external_effects_performed: bool = False) -> ExecutionResult:
    body = dict(outputs)
    digest = digest_json({"operation": operation, "status": status, "outputs": body, "error": error})
    coarse_status = "SUCCESS" if status in {LOCAL_EVIDENCE_STATUS, "SUCCEEDED"} else "FAILED" if status == "FAILED" else "BLOCKED"
    return ExecutionResult(
        operation=operation,
        status=coarse_status,
        outputs=body,
        evidence_digest=f"sha256:{digest}",
        duration_ms=0.0,
        error=error,
        evidence_state=EvidenceState.COLLECTED_SELF_ATTESTED if coarse_status == "SUCCESS" else EvidenceState.NOT_RUN,
        external_evidence_status=str(body.get("external_evidence_status", EXTERNAL_EVIDENCE_STATUS)),
        certification_status=CertificationStatus.NOT_CERTIFIED,
        external_effects_performed=external_effects_performed,
    )


_DEFAULT_CATALOG: SkillCatalog | None = None


def get_foundry_catalog() -> dict[str, Any]:
    """Return truthful local inventory; an unavailable catalog invents no counts."""
    global _DEFAULT_CATALOG
    try:
        if _DEFAULT_CATALOG is None:
            _DEFAULT_CATALOG = SkillCatalog()
        described = dict(_DEFAULT_CATALOG.describe())
        described["total_skills"] = _DEFAULT_CATALOG.total_atomic_skills + _DEFAULT_CATALOG.total_meta_skills
        described["pack_list"] = tuple(sorted(handler.pack for handler in PACK_HANDLER_REGISTRY.values()))
        return described
    except CatalogValidationError as exc:
        return {
            "status": "CATALOG_UNAVAILABLE",
            "total_skills": 0,
            "atomic_skills": 0,
            "meta_skills": 0,
            "packs": 0,
            "pipelines": 0,
            "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
            "certification_status": CERTIFICATION_STATUS,
            "error": str(exc),
        }


__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "CatalogSnapshot",
    "CatalogValidationError",
    "DEFAULT_CATALOG_PATH",
    "EXPECTED_COMPILED_CATALOG_SHA256",
    "EXPECTED_PIPELINES",
    "PACKAGED_CATALOG_PATH",
    "REPOSITORY_CATALOG_PATH",
    "SOURCE_ARCHIVE_PATH",
    "SkillCatalog",
    "get_foundry_catalog",
    "load_compiled_catalog",
]
