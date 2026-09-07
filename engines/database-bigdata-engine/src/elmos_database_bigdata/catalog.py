"""Exact 46-Skill and 554-task bounded runtime catalog."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from .canonical import MAX_JSON_BYTES, CanonicalError, strict_json_loads


class CatalogError(ValueError):
    """Raised when the repository manifest and runtime catalog differ."""


BLOCKER_DEFINITIONS: Final[Mapping[str, str]] = {
    "B1": "authoritative input, data, SLO, owner, or authorization is missing",
    "B2": "official capability, license, price, or exact-version evidence is missing",
    "B3": "a real connector, provider, SaaS, or protocol adapter is missing",
    "B4": "exact engine, runtime, build, startup, and behavior execution is missing",
    "B5": "cloud, IAM, network, secret, Kubernetes, or IaC apply authorization is missing",
    "B6": "representative performance, chaos, recovery, restore, or failover evidence is missing",
    "B7": "production, shadow, cutover, repair, or other write authorization is missing",
    "B8": "independent holdout, representative workload, or independent verifier is missing",
    "B9": "business owner, privacy, compliance, or domain approval is missing",
}


@dataclass(frozen=True, slots=True)
class SkillContract:
    ordinal: int
    name: str
    group: str
    task_prefix: str
    task_count: int
    local_primitives: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(
            f"{self.task_prefix}-{index:03d}" for index in range(1, self.task_count + 1)
        )

    @property
    def handler_id(self) -> str:
        return "handle_" + self.name.replace("-", "_")


# Rows are ordered exactly like the pinned source Skill inventory.
_ROWS: Final[
    tuple[tuple[str, str, str, int, tuple[str, ...], tuple[str, ...]], ...]
] = (
    (
        "elmos-batch-processing-generator",
        "bigdata-core",
        "BATCH",
        12,
        ("batch_ir", "batch_dag", "incremental_plan", "provider_neutral_project_plan"),
        ("B3", "B4", "B6", "B8"),
    ),
    (
        "elmos-bigdata-api-dashboard",
        "bigdata-core",
        "SERVE",
        12,
        ("serving_contract", "api_spec", "bi_model", "dashboard_spec"),
        ("B3", "B4", "B6", "B8"),
    ),
    (
        "elmos-bigdata-auto-repair",
        "bigdata-core",
        "REPAIR",
        12,
        ("incident_graph", "root_cause_ranking", "repair_plan", "approval_gate"),
        ("B4", "B6", "B7", "B8"),
    ),
    (
        "elmos-bigdata-cost-autotuning",
        "bigdata-core",
        "OPT",
        12,
        ("optimization_candidates", "guardrails", "rollback_thresholds"),
        ("B2", "B4", "B6", "B7", "B8"),
    ),
    (
        "elmos-bigdata-evidence-certification",
        "bigdata-core",
        "CERT",
        12,
        ("evidence_integrity_plan", "readiness_scorecard", "fail_closed_gate_plan"),
        ("B4", "B6", "B7", "B8", "B9"),
    ),
    (
        "elmos-bigdata-infra-deployment",
        "bigdata-core",
        "INFRA",
        12,
        (
            "environment_matrix",
            "provider_neutral_iac_plan",
            "policy_plan",
            "local_profile",
        ),
        ("B3", "B4", "B5", "B6"),
    ),
    (
        "elmos-bigdata-pattern-selector",
        "bigdata-core",
        "PATTERN",
        12,
        ("pattern_rules", "architecture_decision", "reconsideration_rules"),
        ("B2", "B6"),
    ),
    (
        "elmos-bigdata-performance-chaos",
        "bigdata-core",
        "CHAOS",
        12,
        ("workload_scenarios", "fault_scenarios", "capacity_envelope_spec"),
        ("B4", "B5", "B6", "B8"),
    ),
    (
        "elmos-bigdata-project-classifier",
        "bigdata-core",
        "CLASS",
        12,
        ("project_classifier", "scenario_map", "capability_needs"),
        ("B1",),
    ),
    (
        "elmos-bigdata-project-orchestrator",
        "orchestration",
        "MASTER",
        14,
        (
            "trusted_snapshot_plan",
            "durable_dag",
            "tenant_quota",
            "checkpoint_plan",
            "artifact_graph",
            "cost_eta",
            "evidence_handoff",
        ),
        tuple(BLOCKER_DEFINITIONS),
    ),
    (
        "elmos-bigdata-security-governance",
        "bigdata-core",
        "GOV",
        12,
        (
            "classification_policy",
            "retention_policy",
            "governance_workflow",
            "access_review_plan",
        ),
        ("B3", "B4", "B5", "B8", "B9"),
    ),
    (
        "elmos-bigdata-test-validation",
        "bigdata-core",
        "TEST",
        12,
        ("traceable_test_matrix", "fixture_plan", "differential_plan", "defect_ledger"),
        ("B3", "B4", "B6", "B8"),
    ),
    (
        "elmos-cdc-event-backbone",
        "bigdata-core",
        "CDC",
        12,
        ("event_contract", "topic_plan", "snapshot_stream_boundary", "replay_policy"),
        ("B3", "B4", "B6"),
    ),
    (
        "elmos-data-architecture-adr",
        "database-intelligence",
        "ADR",
        12,
        ("immutable_adr", "decision_ledger", "baseline_digest"),
        ("B2", "B6", "B9"),
    ),
    (
        "elmos-data-modeling-semantic-layer",
        "bigdata-core",
        "MODEL",
        12,
        ("semantic_model", "metrics_catalog", "scd_temporal_model"),
        ("B4", "B8", "B9"),
    ),
    (
        "elmos-data-quality-observability",
        "bigdata-core",
        "DQOBS",
        12,
        ("data_contracts", "quality_rules", "data_slos", "alert_plan"),
        ("B4", "B8", "B9"),
    ),
    (
        "elmos-data-requirement-intake",
        "database-intelligence",
        "REQ",
        12,
        ("contract_io", "requirements_snapshot", "gap_ledger"),
        ("B1",),
    ),
    (
        "elmos-database-benchmark-harness",
        "database-intelligence",
        "BENCH",
        12,
        ("workload_pack", "benchmark_plan", "result_ingestion_plan"),
        ("B4", "B6", "B8"),
    ),
    (
        "elmos-database-capability-registry",
        "database-intelligence",
        "REG",
        12,
        ("catalog_snapshot", "evidence_expiry", "adapter_state"),
        ("B2", "B3"),
    ),
    (
        "elmos-database-constraint-filter",
        "database-intelligence",
        "FILTER",
        12,
        ("closed_constraint_solver", "minimum_conflict_set", "rejection_proof"),
        ("B2",),
    ),
    (
        "elmos-database-cost-capacity-planner",
        "database-intelligence",
        "COST",
        12,
        ("decimal_capacity_model", "parametric_tco", "scenario_envelope"),
        ("B2", "B6"),
    ),
    (
        "elmos-database-ha-dr",
        "database-intelligence",
        "HADR",
        12,
        ("ha_topology", "backup_policy", "restore_runbook", "dr_plan"),
        ("B4", "B6", "B8"),
    ),
    (
        "elmos-database-mcda-ranker",
        "database-intelligence",
        "RANK",
        12,
        ("mcda", "pareto_frontier", "interval_propagation", "seeded_sensitivity"),
        ("B2", "B6"),
    ),
    (
        "elmos-database-migration-modernization",
        "database-intelligence",
        "MIG",
        12,
        (
            "migration_dag",
            "watermark_plan",
            "reconciliation_plan",
            "cutover_rollback_plan",
        ),
        ("B3", "B4", "B6", "B7", "B8", "B9"),
    ),
    (
        "elmos-database-schema-physical-design",
        "database-intelligence",
        "SCHEMA",
        12,
        ("logical_model", "typed_target_profile", "ddl_plan", "index_partition_plan"),
        ("B2", "B4", "B8"),
    ),
    (
        "elmos-database-security-multitenancy",
        "database-intelligence",
        "DBSEC",
        12,
        ("isolation_model", "access_matrix", "security_test_plan"),
        ("B3", "B4", "B5", "B8", "B9"),
    ),
    (
        "elmos-feature-store-ml-pipeline",
        "bigdata-core",
        "FEAST",
        12,
        (
            "feature_contract",
            "point_in_time_join_plan",
            "materialization_plan",
            "parity_tests",
        ),
        ("B3", "B4", "B6", "B8", "B9"),
    ),
    (
        "elmos-federated-query-data-fabric",
        "bigdata-core",
        "FED",
        12,
        ("federation_topology", "connector_catalog", "pushdown_policy"),
        ("B3", "B4", "B6", "B8"),
    ),
    (
        "elmos-ingestion-connector-planner",
        "bigdata-core",
        "INGEST",
        12,
        ("source_mode_plan", "connector_matrix", "source_contracts"),
        ("B2", "B3", "B4"),
    ),
    (
        "elmos-lakehouse-generator",
        "bigdata-core",
        "LAKE",
        12,
        (
            "table_layout",
            "catalog_plan",
            "maintenance_dag",
            "provider_neutral_project_plan",
        ),
        ("B3", "B4", "B5", "B6"),
    ),
    (
        "elmos-metadata-catalog-lineage",
        "bigdata-core",
        "META",
        12,
        ("stable_asset_ids", "lineage_policy", "ownership_map", "catalog_seed"),
        ("B3", "B4", "B8", "B9"),
    ),
    (
        "elmos-orchestration-backfill-replay",
        "bigdata-core",
        "ORCH",
        12,
        (
            "workflow_dag",
            "checkpoint_store_plan",
            "backfill_plan",
            "replay_lock",
            "idempotency_policy",
        ),
        ("B3", "B4", "B6"),
    ),
    (
        "elmos-polyglot-persistence-planner",
        "database-intelligence",
        "POLY",
        12,
        (
            "role_portfolio",
            "authority_map",
            "synchronization_contract",
            "complexity_penalty",
        ),
        ("B3", "B4"),
    ),
    (
        "elmos-stream-processing-generator",
        "bigdata-core",
        "STREAM",
        12,
        (
            "stream_ir",
            "state_watermark_plan",
            "checkpoint_policy",
            "provider_neutral_project_plan",
        ),
        ("B3", "B4", "B6", "B8"),
    ),
    (
        "elmos-template-cdc-migration-modernization",
        "bigdata-templates",
        "TPLMIG",
        12,
        ("template_plan_cdc_migration",),
        ("B3", "B4", "B6", "B7", "B8", "B9"),
    ),
    (
        "elmos-template-data-governance-platform",
        "bigdata-templates",
        "TPLGOV",
        12,
        ("template_plan_governance_platform",),
        ("B3", "B4", "B8", "B9"),
    ),
    (
        "elmos-template-fraud-risk",
        "bigdata-templates",
        "TPLRISK",
        12,
        ("template_plan_fraud_risk",),
        ("B3", "B4", "B6", "B7", "B8", "B9"),
    ),
    (
        "elmos-template-iot-timeseries",
        "bigdata-templates",
        "TPLIOT",
        12,
        ("template_plan_iot_timeseries",),
        ("B3", "B4", "B6", "B7", "B8", "B9"),
    ),
    (
        "elmos-template-log-observability",
        "bigdata-templates",
        "TPLOBS",
        12,
        ("template_plan_log_observability",),
        ("B3", "B4", "B6", "B8", "B9"),
    ),
    (
        "elmos-template-offline-warehouse",
        "bigdata-templates",
        "TPLDW",
        12,
        ("template_plan_offline_warehouse",),
        ("B3", "B4", "B6", "B8", "B9"),
    ),
    (
        "elmos-template-realtime-analytics",
        "bigdata-templates",
        "TPLRT",
        12,
        ("template_plan_realtime_analytics",),
        ("B3", "B4", "B6", "B8"),
    ),
    (
        "elmos-template-realtime-user-profile",
        "bigdata-templates",
        "TPL360",
        12,
        ("template_plan_customer_360",),
        ("B3", "B4", "B6", "B8", "B9"),
    ),
    (
        "elmos-template-recommendation-system",
        "bigdata-templates",
        "TPLREC",
        12,
        ("template_plan_recommendation",),
        ("B3", "B4", "B6", "B8", "B9"),
    ),
    (
        "elmos-template-vector-knowledge-analytics",
        "bigdata-templates",
        "TPLVEC",
        12,
        ("template_plan_vector_knowledge",),
        ("B2", "B3", "B4", "B6", "B8", "B9"),
    ),
    (
        "elmos-warehouse-olap-serving",
        "bigdata-core",
        "OLAP",
        12,
        ("olap_model", "materialization_plan", "query_slo", "serving_plan"),
        ("B3", "B4", "B6", "B8"),
    ),
    (
        "elmos-workload-profiler",
        "database-intelligence",
        "PROF",
        12,
        ("static_file_profile", "query_log_profile", "confidence_model"),
        ("B1", "B4"),
    ),
)


SKILL_CONTRACTS: Final[tuple[SkillContract, ...]] = tuple(
    SkillContract(index, *row) for index, row in enumerate(_ROWS)
)
SKILL_CONTRACT_BY_NAME: Final[Mapping[str, SkillContract]] = {
    contract.name: contract for contract in SKILL_CONTRACTS
}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_installed_manifest(root: Path | None = None) -> dict[str, Any]:
    path = (
        root or repository_root()
    ) / "docs/database-bigdata-skills/installed-manifest.json"
    try:
        content = path.read_bytes()
        if len(content) > MAX_JSON_BYTES:
            raise CatalogError("installed database/Big Data manifest is too large")
        value = strict_json_loads(
            content.decode("utf-8", errors="strict"), label="installed manifest"
        )
    except (OSError, UnicodeError, CanonicalError) as exc:
        raise CatalogError(
            f"cannot load the installed database/Big Data manifest: {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CatalogError("installed database/Big Data manifest must be an object")
    return value


def _confined_regular_file(root: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise CatalogError(f"{label} path must be a non-empty string")
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or str(pure) != relative
        or ".." in pure.parts
        or "\\" in relative
    ):
        raise CatalogError(f"{label} path is not normalized and confined: {relative}")
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CatalogError(f"{label} path escapes or is missing: {relative}") from exc
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise CatalogError(f"{label} path contains a symlink: {relative}")
    if not resolved.is_file():
        raise CatalogError(f"{label} is not a regular file: {relative}")
    return resolved


def _source_tree_digest(records: list[Mapping[str, Any]], prefix: str) -> str:
    value = hashlib.sha256()
    marker = prefix.rstrip("/") + "/"
    for item in records:
        path = str(item["path"])
        if not path.startswith(marker):
            raise CatalogError(
                "source inventory path differs from canonical source root"
            )
        value.update(path.removeprefix(marker).encode("utf-8"))
        value.update(b"\0")
        value.update(str(item["sha256"]).encode("ascii"))
        value.update(b"\0")
        value.update(str(item["bytes"]).encode("ascii"))
        value.update(b"\0")
        value.update(str(item["mode"]).encode("ascii"))
        value.update(b"\0")
    return "sha256:" + value.hexdigest()


def _validate_source_provenance(root: Path, manifest: Mapping[str, Any]) -> None:
    archive = _confined_regular_file(
        root, manifest.get("source_archive_path"), "source archive"
    )
    archive_content = archive.read_bytes()
    archive_digest = "sha256:" + hashlib.sha256(archive_content).hexdigest()
    if manifest.get("source_archive_bytes") != len(archive_content):
        raise CatalogError("source archive byte count drifted")
    if manifest.get("source_archive_sha256") != archive_digest:
        raise CatalogError("source archive digest drifted")

    source_root_value = manifest.get("canonical_source_path")
    if not isinstance(source_root_value, str) or not source_root_value:
        raise CatalogError("canonical source root is invalid")
    source_root_pure = PurePosixPath(source_root_value)
    if (
        source_root_pure.is_absolute()
        or str(source_root_pure) != source_root_value
        or ".." in source_root_pure.parts
        or "\\" in source_root_value
    ):
        raise CatalogError("canonical source root is not normalized and confined")
    source_root = root / source_root_value
    try:
        resolved_source_root = source_root.resolve(strict=True)
        resolved_source_root.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CatalogError("canonical source root escapes or is missing") from exc
    if source_root.is_symlink() or not resolved_source_root.is_dir():
        raise CatalogError("canonical source root is not a regular directory")

    records = manifest.get("source_files")
    if not isinstance(records, list) or not records:
        raise CatalogError("source inventory is missing")
    if manifest.get("canonical_source_file_count") != len(records):
        raise CatalogError("source inventory count drifted")
    actual_paths: list[str] = []
    for path in resolved_source_root.rglob("*"):
        if path.is_symlink():
            raise CatalogError(f"canonical source contains a symlink: {path}")
        if path.is_file() and "__pycache__" not in path.parts:
            actual_paths.append(path.relative_to(root).as_posix())
    declared_paths = [item.get("path") for item in records if isinstance(item, Mapping)]
    if (
        len(declared_paths) != len(records)
        or not all(isinstance(path, str) for path in declared_paths)
        or declared_paths != sorted(declared_paths)
        or sorted(actual_paths) != declared_paths
    ):
        raise CatalogError("canonical source inventory drifted")
    for item in records:
        if set(item) != {"path", "bytes", "mode", "sha256"}:
            raise CatalogError("source inventory record fields are not exact")
        path = _confined_regular_file(root, item["path"], "canonical source file")
        content = path.read_bytes()
        mode = f"{path.stat().st_mode & 0o777:04o}"
        actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if (
            item["bytes"] != len(content)
            or item["mode"] != mode
            or item["sha256"] != actual_digest
        ):
            raise CatalogError(f"canonical source bytes drifted: {item['path']}")
    if manifest.get("canonical_source_tree_sha256") != _source_tree_digest(
        records, source_root_value
    ):
        raise CatalogError("canonical source tree digest drifted")
    source_manifest = _confined_regular_file(
        root, f"{source_root_value}/MANIFEST.json", "canonical source manifest"
    )
    source_manifest_digest = (
        "sha256:" + hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    )
    if manifest.get("canonical_manifest_sha256") != source_manifest_digest:
        raise CatalogError("canonical source manifest digest drifted")


def validate_catalog(
    root: Path | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Mapping[str, Any]]:
    if len(SKILL_CONTRACTS) != 46 or len(SKILL_CONTRACT_BY_NAME) != 46:
        raise CatalogError("runtime catalog must contain 46 unique Skills")
    if [item.ordinal for item in SKILL_CONTRACTS] != list(range(46)):
        raise CatalogError("runtime ordinals must be the exact 0..45 sequence")
    if Counter(item.group for item in SKILL_CONTRACTS) != {
        "bigdata-core": 22,
        "bigdata-templates": 10,
        "database-intelligence": 13,
        "orchestration": 1,
    }:
        raise CatalogError("runtime Skill group counts changed")
    task_ids = [task_id for item in SKILL_CONTRACTS for task_id in item.task_ids]
    if len(task_ids) != 554 or len(set(task_ids)) != 554:
        raise CatalogError("runtime catalog must contain 554 unique stable task IDs")
    if any(
        code not in BLOCKER_DEFINITIONS
        for item in SKILL_CONTRACTS
        for code in item.blockers
    ):
        raise CatalogError("runtime catalog contains an unknown blocker code")

    resolved_root = (root or repository_root()).resolve(strict=True)
    if manifest is None:
        manifest = load_installed_manifest(resolved_root)
    elif not isinstance(manifest, Mapping):
        raise CatalogError("installed database/Big Data manifest must be an object")
    _validate_source_provenance(resolved_root, manifest)
    required_statuses = {
        "technology_catalog_state": "CATALOG_ONLY",
        "repository_bounded_handler_state": "BOUND_PLAN_SKELETON_ONLY",
        "skill_implementation_state": "DECLARED",
        "repository_handler_runtime_evidence": "NOT_RUN",
        "reference_tool_state": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "source_license_status": "ABSENT",
        "source_signature_status": "ABSENT",
        "source_sbom_status": "ABSENT",
        "source_provenance_attestation_status": "ABSENT",
    }
    for field, expected in required_statuses.items():
        if manifest.get(field) != expected:
            raise CatalogError(f"installed manifest status drifted: {field}")
    records = manifest.get("skills")
    if not isinstance(records, list) or len(records) != 46:
        raise CatalogError("installed manifest must contain 46 Skill records")
    by_name = {item.get("name"): item for item in records if isinstance(item, dict)}
    if list(by_name) != [item.name for item in SKILL_CONTRACTS]:
        raise CatalogError(
            "installed manifest Skill order or identity differs from runtime catalog"
        )
    for contract in SKILL_CONTRACTS:
        record = by_name[contract.name]
        if record.get("source_group") != contract.group:
            raise CatalogError(f"installed group differs for {contract.name}")
        source_path_value = record.get("source_path")
        if not isinstance(source_path_value, str) or not source_path_value:
            raise CatalogError(f"installed source path is invalid for {contract.name}")
        source_path = resolved_root / source_path_value
        try:
            resolved_source = source_path.resolve(strict=True)
            resolved_source.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise CatalogError(
                f"installed source path escapes for {contract.name}"
            ) from exc
        if not resolved_source.is_file() or source_path.is_symlink():
            raise CatalogError(
                f"installed source path is not a regular file for {contract.name}"
            )
        source_digest = (
            "sha256:" + hashlib.sha256(resolved_source.read_bytes()).hexdigest()
        )
        if record.get("source_sha256") != source_digest:
            raise CatalogError(f"installed source digest differs for {contract.name}")
        if record.get("source_task_ids") != list(contract.task_ids):
            raise CatalogError(f"installed task IDs differ for {contract.name}")
        outputs = record.get("source_outputs")
        if (
            not isinstance(outputs, list)
            or not outputs
            or not all(isinstance(item, str) and item for item in outputs)
        ):
            raise CatalogError(f"installed outputs are invalid for {contract.name}")
        if record.get("repository_handler_id") != contract.handler_id:
            raise CatalogError(
                f"installed handler identity differs for {contract.name}"
            )
        skill_statuses = {
            "installation_state": "INSTALLED",
            "skill_implementation_state": "DECLARED",
            "repository_runtime_binding": "BOUNDED_PLAN_SKELETON",
            "repository_handler_runtime_evidence": "NOT_RUN",
            "whole_skill_implementation_effect": "NONE",
            "reference_tool_state": "NOT_APPLICABLE_TO_WHOLE_SKILL",
            "provider_runtime_evidence": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
        }
        for field, expected in skill_statuses.items():
            if record.get(field) != expected:
                raise CatalogError(
                    f"installed Skill status drifted for {contract.name}: {field}"
                )
    return by_name


__all__ = [
    "BLOCKER_DEFINITIONS",
    "SKILL_CONTRACTS",
    "SKILL_CONTRACT_BY_NAME",
    "CatalogError",
    "SkillContract",
    "load_installed_manifest",
    "repository_root",
    "validate_catalog",
]
