#!/usr/bin/env python3
"""Static fail-closed checks for the repository-owned runtime implementation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_JAVA = {
    "ProductionRuntimeModels.java",
    "ProductionRuntimeStore.java",
    "JdbcProductionRuntimeStore.java",
    "ProductionBillingPort.java",
    "JdbcProductionBillingService.java",
    "ProductionToolCallPort.java",
    "JdbcProductionToolCallService.java",
    "ProductionRepositoryArtifactPort.java",
    "JdbcProductionRepositoryArtifactService.java",
    "ProductionRuntimeCoordinator.java",
    "ProductionRuntimeRecoveryService.java",
    "ProductionRuntimeSettlementReconciler.java",
    "TransactionalOutboxPublisher.java",
    "ProductionModelProviderPort.java",
    "ProductionModelCallExecutor.java",
}


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        source = root / "modules/production-runtime/src/main/java/io/elmos/productionruntime"
        actual = {path.name for path in source.glob("*.java")}
        missing = REQUIRED_JAVA - actual
        if missing:
            fail(f"missing repository-owned handlers: {sorted(missing)}")
        migration = (root / "modules/persistence/src/main/resources/db/migration/V77__production_repository_execution_os.sql").read_text(encoding="utf-8")
        for phrase in (
            "CREATE SCHEMA IF NOT EXISTS billing",
            "CREATE TABLE runtime.dispatch_intents",
            "CREATE TABLE ai_usage.model_calls",
            "CREATE TABLE ai_usage.tool_calls",
            "CREATE TABLE billing.credit_reservations",
            "CREATE TABLE billing.usage_meter_events",
            "CREATE TABLE billing.token_usage_events",
            "CREATE TABLE runtime.settlement_requests",
            "CREATE TABLE billing.ledger_entries",
            "CREATE TABLE observability.outbox_events",
            "CREATE OR REPLACE FUNCTION runtime.allocate_fence",
            "CREATE OR REPLACE FUNCTION runtime.select_fair_ready_work_items",
            "SECURITY DEFINER",
            "ENABLE ROW LEVEL SECURITY",
            "APPEND_ONLY_MUTATION_FORBIDDEN",
            "REVOKE ALL ON FUNCTION",
        ):
            if phrase not in migration:
                fail(f"migration is missing required production boundary: {phrase}")
        role_script = (root / "deploy/production/postgres/production_runtime_roles.sql").read_text(encoding="utf-8")
        for role in ("elmos_scheduler_rw", "elmos_billing_rw", "elmos_runtime_worker_limited", "elmos_projector_limited", "elmos_readonly_analytics"):
            if f"CREATE ROLE {role}" not in role_script or role not in role_script:
                fail(f"role boundary missing: {role}")
        chart = root / "deploy/helm/elmos-runtime"
        for path in (chart / "Chart.yaml", chart / "values.yaml", chart / "templates/network-policy.yaml", chart / "templates/worker-statefulset.yaml"):
            if not path.is_file():
                fail(f"deployment asset missing: {path}")
        for path in (root / "scripts/production-runtime/run_local_harness.py", root / "scripts/production-runtime/run_pitr_drill.py", root / "scripts/production-runtime/verify_local_harness.py"):
            if not path.is_file():
                fail(f"local qualification harness asset missing: {path}")
        if "readOnlyRootFilesystem: true" not in (chart / "templates/worker-statefulset.yaml").read_text(encoding="utf-8"):
            fail("worker chart is not read-only")
        if "clusterIP: None" not in (chart / "templates/worker-statefulset.yaml").read_text(encoding="utf-8"):
            fail("worker chart lost individual addressability")
        scenario_status = json.loads((root / "docs/production-runtime/SCENARIO-STATUS.json").read_text(encoding="utf-8"))
        scenarios = scenario_status.get("scenarios")
        if not isinstance(scenarios, dict) or len(scenarios) != 20 or scenario_status.get("decision") != "NOT_CERTIFIED":
            fail("scenario status must preserve all 20 scenarios and remain non-certified")
        if any(value.get("status") == "LOCAL_TEST_PASS" and not value.get("test") for value in scenarios.values()):
            fail("a local scenario result is missing its executable test binding")
        for name in ("ChaosMatrix", "RedisLoss", "PITRRestore", "WorkerCrashCheckpointResume"):
            value = scenarios.get(name)
            if not isinstance(value, dict) or value.get("status") != "LOCAL_HARNESS_PASS" or not value.get("test"):
                fail(f"local harness scenario is not qualified: {name}")
    except (OSError, ValueError) as exc:
        print(f"production-runtime implementation validation: FAIL: {exc}", file=sys.stderr)
        return 1
    print("production-runtime implementation validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
