#!/usr/bin/env python3
"""Regenerate implementation-only bindings for the 144 MTF source tasks.

This tool deliberately cannot promote execution or evidence.  It updates only
repository implementation state and content-addressed file bindings while
preserving the immutable source package, V100-V102 NOT_APPLIED boundary, four
unresolved dependencies, external NOT_RUN state, and NOT_CERTIFIED production
state.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "skills/elmos-multitenant-task-finops-skills-v1.0.0/docs/task-catalog.json"
RESULTS = ROOT / "docs/multitenant-task-finops-skills/repository-task-results.json"

IMPLEMENTED = {
    "ELMOS-MTF-001-T01", "ELMOS-MTF-001-T03", "ELMOS-MTF-001-T04",
    "ELMOS-MTF-001-T08", "ELMOS-MTF-001-T10", "ELMOS-MTF-001-T12",
    "ELMOS-MTF-002-T01", "ELMOS-MTF-002-T02", "ELMOS-MTF-002-T03",
    "ELMOS-MTF-002-T04", "ELMOS-MTF-002-T05", "ELMOS-MTF-002-T06",
    "ELMOS-MTF-002-T07", "ELMOS-MTF-002-T11",
    "ELMOS-MTF-003-T01", "ELMOS-MTF-003-T02", "ELMOS-MTF-003-T03",
    "ELMOS-MTF-003-T04", "ELMOS-MTF-003-T05", "ELMOS-MTF-003-T06",
    "ELMOS-MTF-003-T07", "ELMOS-MTF-003-T09", "ELMOS-MTF-003-T11",
    "ELMOS-MTF-004-T01", "ELMOS-MTF-004-T02", "ELMOS-MTF-004-T07",
    "ELMOS-MTF-005-T01", "ELMOS-MTF-005-T02", "ELMOS-MTF-005-T05",
    "ELMOS-MTF-005-T06", "ELMOS-MTF-005-T08",
    "ELMOS-MTF-006-T01", "ELMOS-MTF-006-T02", "ELMOS-MTF-006-T03",
    "ELMOS-MTF-006-T04", "ELMOS-MTF-006-T05", "ELMOS-MTF-006-T11",
    "ELMOS-MTF-007-T02", "ELMOS-MTF-007-T03", "ELMOS-MTF-007-T04",
    "ELMOS-MTF-007-T05", "ELMOS-MTF-007-T06", "ELMOS-MTF-007-T10",
    "ELMOS-MTF-008-T02", "ELMOS-MTF-008-T05", "ELMOS-MTF-008-T06",
    "ELMOS-MTF-009-T01", "ELMOS-MTF-009-T02", "ELMOS-MTF-009-T07",
    "ELMOS-MTF-009-T08", "ELMOS-MTF-009-T09",
    "ELMOS-MTF-010-T01", "ELMOS-MTF-010-T02", "ELMOS-MTF-010-T03",
    "ELMOS-MTF-010-T04", "ELMOS-MTF-010-T05", "ELMOS-MTF-010-T06",
    "ELMOS-MTF-010-T08", "ELMOS-MTF-010-T09",
    "ELMOS-MTF-011-T01", "ELMOS-MTF-011-T02", "ELMOS-MTF-011-T10",
    "ELMOS-MTF-011-T11",
}

PARTIAL = {
    "ELMOS-MTF-001-T02", "ELMOS-MTF-001-T05", "ELMOS-MTF-001-T06",
    "ELMOS-MTF-001-T07", "ELMOS-MTF-001-T09", "ELMOS-MTF-001-T11",
    "ELMOS-MTF-002-T08", "ELMOS-MTF-002-T09", "ELMOS-MTF-002-T10",
    "ELMOS-MTF-002-T12",
    "ELMOS-MTF-003-T08", "ELMOS-MTF-003-T10", "ELMOS-MTF-003-T12",
    "ELMOS-MTF-004-T04", "ELMOS-MTF-004-T05", "ELMOS-MTF-004-T06",
    "ELMOS-MTF-004-T08", "ELMOS-MTF-004-T09", "ELMOS-MTF-004-T11",
    "ELMOS-MTF-005-T03", "ELMOS-MTF-005-T04", "ELMOS-MTF-005-T07",
    "ELMOS-MTF-005-T09", "ELMOS-MTF-005-T11",
    "ELMOS-MTF-006-T06", "ELMOS-MTF-006-T07", "ELMOS-MTF-006-T08",
    "ELMOS-MTF-006-T09", "ELMOS-MTF-006-T10", "ELMOS-MTF-006-T12",
    "ELMOS-MTF-007-T01", "ELMOS-MTF-007-T07", "ELMOS-MTF-007-T08",
    "ELMOS-MTF-007-T09", "ELMOS-MTF-007-T11",
    "ELMOS-MTF-008-T01", "ELMOS-MTF-008-T03", "ELMOS-MTF-008-T04",
    "ELMOS-MTF-008-T07", "ELMOS-MTF-008-T08", "ELMOS-MTF-008-T09",
    "ELMOS-MTF-008-T10", "ELMOS-MTF-008-T11", "ELMOS-MTF-008-T12",
    "ELMOS-MTF-009-T03", "ELMOS-MTF-009-T04", "ELMOS-MTF-009-T05",
    "ELMOS-MTF-009-T06", "ELMOS-MTF-009-T10", "ELMOS-MTF-009-T11",
    "ELMOS-MTF-009-T12",
    "ELMOS-MTF-010-T07", "ELMOS-MTF-010-T10", "ELMOS-MTF-010-T11",
    "ELMOS-MTF-010-T12",
    "ELMOS-MTF-011-T03", "ELMOS-MTF-011-T04", "ELMOS-MTF-011-T05",
    "ELMOS-MTF-011-T07", "ELMOS-MTF-011-T08", "ELMOS-MTF-011-T09",
    "ELMOS-MTF-011-T12",
    "ELMOS-MTF-012-T01", "ELMOS-MTF-012-T02", "ELMOS-MTF-012-T03",
    "ELMOS-MTF-012-T08", "ELMOS-MTF-012-T09", "ELMOS-MTF-012-T10",
    "ELMOS-MTF-012-T12",
}

EXPECTED_IMPLEMENTATION_COUNTS = {
    "IMPLEMENTED": 63,
    "NOT_STARTED": 12,
    "PARTIAL": 69,
}

FILES_BY_SKILL = {
    "ELMOS-MTF-001": [
        "database-packs/postgresql-17-5-multitenant-task-finops/pack.json",
        "docs/multitenant-task-finops-runtime/IMPLEMENTATION_CONTRACT.md",
        "docs/multitenant-task-finops-runtime/LOCAL_QUALIFICATION.md",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77_1__task_finops_recovery_lifecycle_and_settlement.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsFeatureRollout.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsOperationsPort.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsFeatureRolloutTest.java",
        "tooling/update_multitenant_task_finops_bindings.py",
        "tooling/validate_multitenant_task_finops_runtime.py",
    ],
    "ELMOS-MTF-002": [
        "apps/control-plane/src/main/java/io/elmos/controlplane/ControlPlanePrincipal.java",
        "apps/control-plane/src/main/java/io/elmos/controlplane/OidcTenantMembershipFilter.java",
        "apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsOperationsController.java",
        "apps/control-plane/src/test/java/io/elmos/controlplane/TaskFinopsOperationsControllerTest.java",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/main/resources/db/migration/V77_1__task_finops_recovery_lifecycle_and_settlement.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsOperationsPort.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TenantLifecyclePolicy.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TenantLifecyclePolicyTest.java",
    ],
    "ELMOS-MTF-003": [
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcExecutionJobStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/MultitenantTaskFinopsRuntimeIntegrationTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/ExecutionJobPort.java",
    ],
    "ELMOS-MTF-004": [
        "apps/control-plane/src/main/java/io/elmos/controlplane/ExecutionJobController.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPolicy.java",
    ],
    "ELMOS-MTF-005": [
        "apps/runner-agent/src/main/java/io/elmos/runner/HeartbeatPump.java",
        "apps/runner-agent/src/main/java/io/elmos/runner/JobExecutor.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/workflow/src/main/java/io/elmos/workflow/ExecutionJobPort.java",
    ],
    "ELMOS-MTF-006": [
        "apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsController.java",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsStore.java",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/main/resources/db/migration/V77_2__task_finops_analytics_rebuild_and_exports.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsAnalytics.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsAnalyticsService.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsServiceTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPolicy.java",
    ],
    "ELMOS-MTF-007": [
        "apps/runner-agent/src/main/java/io/elmos/runner/JobExecutor.java",
        "apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsOperationsController.java",
        "apps/control-plane/src/test/java/io/elmos/controlplane/TaskFinopsOperationsControllerTest.java",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/main/resources/db/migration/V77_1__task_finops_recovery_lifecycle_and_settlement.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/MultitenantTaskFinopsRuntimeIntegrationTest.java",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/CheckpointForkPolicy.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsOperationsPort.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPort.java",
        "modules/workflow/src/test/java/io/elmos/workflow/CheckpointForkPolicyTest.java",
    ],
    "ELMOS-MTF-008": [
        "modules/persistence/src/main/resources/db/migration/V58__artifact_object_storage_and_retention.sql",
        "modules/persistence/src/main/resources/db/migration/V61__artifact_physical_retention_gc.sql",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/main/resources/db/migration/V77_1__task_finops_recovery_lifecycle_and_settlement.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsOperationsPort.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPort.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TenantLifecyclePolicy.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TenantLifecyclePolicyTest.java",
    ],
    "ELMOS-MTF-009": [
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsFinancialSemanticsContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPolicy.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPort.java",
    ],
    "ELMOS-MTF-010": [
        "docs/multitenant-task-finops-runtime/METRIC_CATALOG.md",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/main/resources/db/migration/V77_1__task_finops_recovery_lifecycle_and_settlement.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsFinancialSemanticsContractTest.java",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/PaymentSettlementReconciler.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPolicy.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsOperationsPort.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPort.java",
        "modules/workflow/src/test/java/io/elmos/workflow/PaymentSettlementReconcilerTest.java",
    ],
    "ELMOS-MTF-011": [
        "apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsController.java",
        "apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsOperationsController.java",
        "apps/control-plane/src/test/java/io/elmos/controlplane/TaskFinopsOperationsControllerTest.java",
        "docs/multitenant-task-finops-runtime/METRIC_CATALOG.md",
        "modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java",
        "modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql",
        "modules/persistence/src/main/resources/db/migration/V77_2__task_finops_analytics_rebuild_and_exports.sql",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsAnalytics.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsAnalyticsService.java",
        "modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsOperationsPort.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsExportTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsServiceTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsTest.java",
    ],
    "ELMOS-MTF-012": [
        "database-packs/postgresql-17-5-multitenant-task-finops/certification/gate-result.json",
        "docs/multitenant-task-finops-runtime/LOCAL_QUALIFICATION.md",
        "modules/persistence/src/test/java/io/elmos/persistence/MultitenantTaskFinopsRuntimeIntegrationTest.java",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsFinancialSemanticsContractTest.java",
        "modules/persistence/src/test/java/io/elmos/persistence/TaskFinopsOperationsMigrationContractTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/CheckpointForkPolicyTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/PaymentSettlementReconcilerTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsExportTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsServiceTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsAnalyticsTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TaskFinopsFeatureRolloutTest.java",
        "modules/workflow/src/test/java/io/elmos/workflow/TenantLifecyclePolicyTest.java",
        "tests/multitenant-task-finops/test_runtime_validation.py",
        "tooling/validate_multitenant_task_finops_runtime.py",
    ],
}

PARTIAL_BLOCKERS = {
    "ELMOS-MTF-001": "EXTERNAL_DEPENDENCIES_AND_PRODUCTION_VERTICAL_SLICE_NOT_QUALIFIED",
    "ELMOS-MTF-002": "EXTERNAL_OIDC_BYPASSRLS_AND_LIFECYCLE_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-003": "HIGH_CONTENTION_MULTI_REPLICA_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-004": "TEMPORAL_OTEL_AUTOSCALING_AND_LOAD_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-005": "TEMPORAL_RUNTIME_REPLAY_AND_LONG_HISTORY_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-006": "EVENT_BUS_SSE_OBJECT_LOG_AND_DELIVERY_CHAOS_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-007": "PROVIDER_WORKSPACE_CRASH_INJECTION_AND_RECOVERY_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-008": "OBJECT_EXPORT_DELETION_RETENTION_AND_SECRET_NEGATIVE_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-009": "PROVIDER_METERING_INVOICE_AND_BUDGET_RUNTIME_EVIDENCE_NOT_RUN",
    "ELMOS-MTF-010": "PAYMENT_SETTLEMENT_TAX_AND_MANUAL_APPROVAL_DEPENDENCIES_UNRESOLVED",
    "ELMOS-MTF-011": "AGGREGATE_EXPORT_DASHBOARD_AND_REBUILD_RUNTIME_INCOMPLETE",
    "ELMOS-MTF-012": "PRODUCT_QUALIFICATION_CAMPAIGN_EVIDENCE_NOT_RUN",
}

PARTIAL_TASK_BLOCKERS = {
    "ELMOS-MTF-008-T10": "OBJECT_PROVIDER_EXPORT_DELETE_NOT_RUN",
    "ELMOS-MTF-010-T11": "PAYMENT_PROVIDER_ADAPTER_AND_SETTLEMENT_EVIDENCE_NOT_RUN",
}

NOT_STARTED_BLOCKERS = {
    "ELMOS-MTF-001": "REPOSITORY_IMPLEMENTATION_NOT_BOUND",
    "ELMOS-MTF-002": "TENANT_LIFECYCLE_IMPLEMENTATION_NOT_BOUND",
    "ELMOS-MTF-003": "REPRESENTATIVE_RACE_CAMPAIGN_NOT_IMPLEMENTED",
    "ELMOS-MTF-004": "EXTERNAL_SCHEDULER_OBSERVABILITY_OR_BENCHMARK_RUNTIME_NOT_IMPLEMENTED",
    "ELMOS-MTF-005": "TEMPORAL_DEPENDENCY_UNRESOLVED",
    "ELMOS-MTF-006": "EVENT_REBUILD_OR_EXTERNAL_DELIVERY_RUNTIME_NOT_IMPLEMENTED",
    "ELMOS-MTF-007": "RECOVERY_FORK_OR_CRASH_CAMPAIGN_RUNTIME_NOT_IMPLEMENTED",
    "ELMOS-MTF-008": "TENANT_EXPORT_DELETION_OR_OBJECT_RUNTIME_NOT_IMPLEMENTED",
    "ELMOS-MTF-009": "EXTERNAL_PROVIDER_METERING_OR_INVOICE_RUNTIME_NOT_IMPLEMENTED",
    "ELMOS-MTF-010": "PAYMENT_SETTLEMENT_RUNTIME_NOT_IMPLEMENTED",
    "ELMOS-MTF-011": "ANALYTICS_AGGREGATE_EXPORT_OR_REBUILD_RUNTIME_NOT_IMPLEMENTED",
    "ELMOS-MTF-012": "EXTERNAL_PRODUCT_QUALIFICATION_RUNTIME_NOT_IMPLEMENTED",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def binding(relative: str) -> dict[str, object]:
    path = ROOT / relative
    payload = path.read_bytes()
    return {
        "path": relative,
        "byte_size": len(payload),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
    }


def render() -> dict:
    catalog = load(CATALOG)
    document = load(RESULTS)
    tasks = catalog.get("tasks", [])
    task_ids = {task["task_id"] for task in tasks}
    if IMPLEMENTED & PARTIAL:
        raise ValueError("implementation state sets overlap")
    if not (IMPLEMENTED | PARTIAL).issubset(task_ids):
        raise ValueError("implementation state set contains an unknown task")
    if document.get("source_reference_application_status") != "NOT_APPLIED":
        raise ValueError("V100-V102 safety boundary drifted")
    if document.get("source_external_dependency_status") != "DECLARED_UNRESOLVED":
        raise ValueError("external dependency safety boundary drifted")
    if document.get("external_evidence_status") != "NOT_RUN":
        raise ValueError("external evidence safety boundary drifted")
    if document.get("production_certification") != "NOT_CERTIFIED":
        raise ValueError("production certification safety boundary drifted")

    source_results = document.get("tasks", [])
    if [item.get("task_id") for item in source_results] != [
        item.get("task_id") for item in tasks
    ]:
        raise ValueError("repository task results do not match source order")
    for item in source_results:
        if (
            item.get("execution_state") != "NOT_RUN"
            or item.get("evidence_state") != "NONE"
            or item.get("result_receipts") != []
        ):
            raise ValueError("task execution/evidence boundary must remain all NOT_RUN/NONE")

    counts: collections.Counter[str] = collections.Counter()
    rendered = []
    for source, current in zip(tasks, source_results, strict=True):
        task_id = source["task_id"]
        skill_id = source["skill_id"]
        item = dict(current)
        if task_id in IMPLEMENTED:
            state = "IMPLEMENTED"
            paths = FILES_BY_SKILL[skill_id]
            blockers: list[str] = []
        elif task_id in PARTIAL:
            state = "PARTIAL"
            paths = FILES_BY_SKILL[skill_id]
            blockers = [
                PARTIAL_TASK_BLOCKERS.get(task_id, PARTIAL_BLOCKERS[skill_id])
            ]
        else:
            state = "NOT_STARTED"
            paths = []
            blockers = [NOT_STARTED_BLOCKERS[skill_id]]
        item["implementation_state"] = state
        item["execution_state"] = "NOT_RUN"
        item["evidence_state"] = "NONE"
        item["implementation_bindings"] = [
            binding(path) for path in sorted(set(paths))
        ]
        item["result_receipts"] = []
        item["blockers"] = blockers
        counts[state] += 1
        rendered.append(item)
    if dict(sorted(counts.items())) != EXPECTED_IMPLEMENTATION_COUNTS:
        raise ValueError(
            "implementation state count drift: "
            f"expected {EXPECTED_IMPLEMENTATION_COUNTS}, got {dict(sorted(counts.items()))}"
        )
    document["tasks"] = rendered
    document["summary"] = {
        "total": len(rendered),
        "implementation": dict(sorted(counts.items())),
        "execution": {"NOT_RUN": len(rendered)},
        "evidence": {"NONE": len(rendered)},
    }
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = render()
    current = load(RESULTS)
    if args.check:
        if current != expected:
            print("ERROR: repository task implementation bindings are stale")
            return 1
        print("OK: repository task implementation bindings are current")
        return 0
    RESULTS.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print(
        "UPDATED: repository task implementation bindings; "
        "execution=NOT_RUN:144 evidence=NONE:144"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
