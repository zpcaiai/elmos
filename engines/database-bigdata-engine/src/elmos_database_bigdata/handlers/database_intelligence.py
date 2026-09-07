"""Unique bounded handlers for the thirteen database-intelligence Skills."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..catalog import SKILL_CONTRACT_BY_NAME
from ..contracts import RuntimeRequest
from .common import compile_bounded_plan


def _plan(
    name: str,
    request: RuntimeRequest,
    record: Mapping[str, Any],
    focus: tuple[str, ...],
) -> dict[str, Any]:
    return compile_bounded_plan(
        SKILL_CONTRACT_BY_NAME[name], request, record, focus=focus
    )


def handle_elmos_data_architecture_adr(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-data-architecture-adr",
        request,
        record,
        ("decision-ledger", "alternatives", "rollback-conditions"),
    )


def handle_elmos_data_requirement_intake(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-data-requirement-intake",
        request,
        record,
        ("requirements-ir", "unknown-preservation", "authorization-scope"),
    )


def handle_elmos_database_benchmark_harness(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-benchmark-harness",
        request,
        record,
        ("corpus-separation", "measurement-protocol", "real-engine-gate"),
    )


def handle_elmos_database_capability_registry(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-capability-registry",
        request,
        record,
        ("catalog-only", "exact-version-evidence", "expiry"),
    )


def handle_elmos_database_constraint_filter(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-constraint-filter",
        request,
        record,
        ("hard-constraints", "minimum-conflict-set", "rejection-proof"),
    )


def handle_elmos_database_cost_capacity_planner(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-cost-capacity-planner",
        request,
        record,
        ("decimal-model", "range-scenarios", "pricing-evidence"),
    )


def handle_elmos_database_ha_dr(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-ha-dr",
        request,
        record,
        ("rpo-rto", "restore-runbook", "failover-evidence"),
    )


def handle_elmos_database_mcda_ranker(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-mcda-ranker",
        request,
        record,
        ("mcda", "pareto", "seeded-sensitivity"),
    )


def handle_elmos_database_migration_modernization(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-migration-modernization",
        request,
        record,
        ("typed-db-ir", "reconciliation", "cutover-rollback"),
    )


def handle_elmos_database_schema_physical_design(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-schema-physical-design",
        request,
        record,
        ("logical-model", "typed-target-profile", "physical-design"),
    )


def handle_elmos_database_security_multitenancy(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-database-security-multitenancy",
        request,
        record,
        ("tenant-isolation", "least-privilege", "negative-security-tests"),
    )


def handle_elmos_polyglot_persistence_planner(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-polyglot-persistence-planner",
        request,
        record,
        ("system-of-record", "synchronization-contract", "complexity-penalty"),
    )


def handle_elmos_workload_profiler(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-workload-profiler",
        request,
        record,
        ("static-profile", "runtime-profile-gap", "confidence"),
    )


__all__ = [name for name in globals() if name.startswith("handle_elmos_")]
