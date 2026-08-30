#!/usr/bin/env python3
"""Static fail-closed checks for the repository-owned runtime implementation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_JAVA = {
    "HttpProductionBillingClient.java",
    "HttpProductionModelProviderAdapter.java",
    "HttpProductionToolCallClient.java",
    "HttpProductionWorkerGateway.java",
    "HttpTransactionalOutboxTransport.java",
    "JdbcProductionBillingService.java",
    "JdbcProductionObjectStorageMetadata.java",
    "JdbcProductionProviderPayloadStore.java",
    "JdbcProductionRepositoryArtifactService.java",
    "JdbcProductionRuntimeStore.java",
    "JdbcProductionToolCallService.java",
    "OwnerOnlyProviderCredentialFile.java",
    "ProductionBillingPort.java",
    "ProductionModelCallExecutor.java",
    "ProductionModelCallRecoveryService.java",
    "ProductionModelProviderPort.java",
    "ProductionModelProviderRegistry.java",
    "ProductionProviderArtifactPort.java",
    "ProductionProviderPayloadPort.java",
    "ProductionRepositoryArtifactPort.java",
    "ProductionRuntimeConfiguration.java",
    "ProductionRuntimeCoordinator.java",
    "ProductionRuntimeException.java",
    "ProductionRuntimeModels.java",
    "ProductionRuntimeRecoveryService.java",
    "ProductionRuntimeScheduler.java",
    "ProductionRuntimeSchedulingService.java",
    "ProductionRuntimeSettlementReconciler.java",
    "ProductionRuntimeStore.java",
    "ProductionToolCallPort.java",
    "ProductionWorkloadPackCatalog.java",
    "S3ProductionProviderArtifactStore.java",
    "TransactionalOutboxPublisher.java",
}

REQUIRED_CONTROL_PLANE = {
    "ProductionRuntimeBillingController.java",
    "ProductionRuntimeBillingGateController.java",
    "ProductionRuntimeControlPlaneApplication.java",
    "ProductionRuntimeControlPlaneConfiguration.java",
    "ProductionRuntimeControlPlaneMetrics.java",
    "ProductionRuntimeGateAuthenticator.java",
    "ProductionRuntimeGateFixture.java",
    "ProductionRuntimeInternalAuthenticator.java",
    "ProductionRuntimeInternalController.java",
    "ProductionRuntimeMigrationConfiguration.java",
    "ProductionRuntimeProviderConfiguration.java",
    "ProductionRuntimeSchedulerGateController.java",
    "ProductionRuntimeTopUpAuthenticator.java",
}

REQUIRED_WORKER = {
    "ProductionRuntimeWorkerApplication.java",
    "ProductionWorkerAttemptService.java",
    "ProductionWorkerConfiguration.java",
    "ProductionWorkerController.java",
    "ProductionWorkerDurableJournal.java",
    "ProductionWorkerMetrics.java",
    "ProductionWorkerRegistrationLoop.java",
    "ProductionWorkerRouteCatalog.java",
}

SCENARIO_BINDINGS = {
    "BillingReconciliation": ("LOCAL_TEST_PASS", "billingReconciliationViewMatchesWalletAndReservationTruth"),
    "ChaosMatrix": ("LOCAL_HARNESS_PASS", "chaosMatrixKeepsUnknownNonSuccessAndReleasesRejectedWork"),
    "ConcurrentReserve": ("LOCAL_TEST_PASS", "concurrentReservationsNeverDriveWalletNegative"),
    "CreditExhaustionResume": ("LOCAL_TEST_PASS", "creditExhaustionResumesAfterVerifiedTopUp"),
    "DuplicateProviderCallReplay": ("LOCAL_TEST_PASS", "modelCallReplayIsStableAndProviderUncertaintyBlocksBlindRetry"),
    "DuplicateUsage": ("LOCAL_TEST_PASS", "duplicateProviderUsageCannotSettleAnotherModelCall"),
    "IdempotencyConflict": ("LOCAL_TEST_PASS", "topUpIdempotencyConflictCannotChangeMoney"),
    "JournalBalance": ("LOCAL_TEST_PASS", "journalEntriesRemainBalancedForTopUpAndUsage"),
    "LeaseExpiry": ("LOCAL_TEST_PASS", "leaseExpiryRemovesLeaseAndMakesWorkRetryable"),
    "PITRRestore": ("LOCAL_HARNESS_PASS", "scripts/production-runtime/run_pitr_drill.py"),
    "ProjectorReplay": ("LOCAL_TEST_PASS", "projectorReplayRebuildsTheSameAuthoritativeCounts"),
    "RLSIsolation": ("LOCAL_TEST_PASS", "rlsRoleCannotReadAnotherTenant"),
    "RedisLoss": ("LOCAL_HARNESS_PASS", "redisLossDoesNotDeleteDurableDispatchOrMoneyState"),
    "SchedulerRestartAtDispatching": ("LOCAL_TEST_PASS", "dispatchingUnknownOutcomeConvergesThroughDurableRecovery"),
    "SchedulerRestartAtReserved": ("LOCAL_TEST_PASS", "reservedStateCanBeReplayedAfterSchedulerRestart"),
    "SchedulerRestartAtReserving": ("LOCAL_TEST_PASS", "reservingStateCanBeReplayedAfterSchedulerRestart"),
    "StaleFence": ("LOCAL_TEST_PASS", "staleFenceCannotCommitTerminalResult"),
    "StreamingUsageReconciliation": ("LOCAL_TEST_PASS", "streamingUsageReconciliationIsMonotonicAndFinal"),
    "TopUpReplay": ("LOCAL_TEST_PASS", "topUpReplayIsExactlyOnceAcrossMoneyJournalAndOutbox"),
    "WorkerCrashCheckpointResume": ("LOCAL_TEST_PASS", "ProductionWorkerRestartRecoveryTest"),
}

EXTERNAL_EVIDENCE = {
    "provider_runtime",
    "target_cluster_load",
    "chaos",
    "worker_process_kill",
    "redis_loss",
    "backup_pitr",
    "independent_verification",
    "production_deployment",
}

EXTERNAL_REQUIRED = {
    "provider-runtime",
    "target-cluster-load",
    "redis-flush-recovery",
    "worker-process-kill",
    "backup-pitr-restore",
    "chaos-matrix",
    "independent-verification",
    "production-deployment",
}

MIGRATION_VERSION = re.compile(r"^V([0-9]+(?:_[0-9]+)*)__.+\.sql$")
JUNIT_TEST = re.compile(r"^\s*@Test\s*$", re.MULTILINE)


def fail(message: str) -> None:
    raise ValueError(message)


def require_files(paths: tuple[Path, ...], label: str) -> None:
    for path in paths:
        if not path.is_file():
            fail(f"{label} missing: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        source = root / "modules/production-runtime/src/main/java/io/elmos/productionruntime"
        missing = REQUIRED_JAVA - {path.name for path in source.glob("*.java")}
        if missing:
            fail(f"missing repository-owned handlers: {sorted(missing)}")

        for path, required, label in (
            (
                root / "apps/production-runtime-control-plane/src/main/java/io/elmos/controlplane",
                REQUIRED_CONTROL_PLANE,
                "control-plane",
            ),
            (
                root / "apps/production-runtime-worker/src/main/java/io/elmos/productionworker",
                REQUIRED_WORKER,
                "worker",
            ),
        ):
            app_missing = required - {item.name for item in path.glob("*.java")}
            if app_missing:
                fail(f"missing dedicated {label} handlers: {sorted(app_missing)}")

        migration_dir = root / "modules/persistence/src/main/resources/db/migration"
        versions: dict[tuple[int, ...], list[str]] = {}
        for path in migration_dir.glob("V*.sql"):
            match = MIGRATION_VERSION.fullmatch(path.name)
            if not match:
                fail(f"invalid Flyway migration filename: {path.name}")
            version = tuple(int(part) for part in match.group(1).split("_"))
            versions.setdefault(version, []).append(path.name)
        duplicate_versions = {
            ".".join(str(part) for part in version): sorted(names)
            for version, names in versions.items()
            if len(names) > 1
        }
        if duplicate_versions:
            fail(f"duplicate Flyway migration versions: {duplicate_versions}")

        migration_path = migration_dir / "V77__production_repository_execution_os.sql"
        migration = migration_path.read_text(encoding="utf-8")
        for phrase in (
            "CREATE SCHEMA IF NOT EXISTS billing",
            "CREATE TABLE runtime.dispatch_intents",
            "CREATE TABLE ai_usage.model_calls",
            "CREATE TABLE ai_usage.tool_calls",
            "CREATE TABLE ai_usage.model_call_request_payloads",
            "CREATE TABLE ai_usage.tool_call_receipts",
            "CREATE TABLE billing.credit_reservations",
            "CREATE TABLE billing.usage_meter_events",
            "CREATE TABLE billing.token_usage_events",
            "CREATE TABLE runtime.settlement_requests",
            "CREATE TABLE billing.ledger_entries",
            "CREATE TABLE billing.billing_journals",
            "CREATE TABLE billing.billing_journal_lines",
            "CREATE TABLE observability.outbox_events",
            "CREATE TABLE observability.pitr_markers",
            "CREATE TABLE artifact.content_objects",
            "CREATE OR REPLACE FUNCTION runtime.allocate_fence",
            "CREATE OR REPLACE FUNCTION runtime.select_fair_ready_work_items",
            "SECURITY DEFINER",
            "ENABLE ROW LEVEL SECURITY",
            "APPEND_ONLY_MUTATION_FORBIDDEN",
            "MODEL_CALL_RECEIPT_DIVERGENCE",
            "TOOL_CALL_RECEIPT_DIVERGENCE",
            "REVOKE ALL ON FUNCTION",
        ):
            if phrase not in migration:
                fail(f"migration is missing required production boundary: {phrase}")
        stage_migration = migration_dir / "V78__production_workload_stage_lifecycle.sql"
        stage_sql = stage_migration.read_text(encoding="utf-8")
        for phrase in (
            "CREATE OR REPLACE FUNCTION orchestration.advance_job_stages",
            "STAGE_TENANT_CONTEXT_REQUIRED",
            "status = 'SUCCEEDED'",
            "status = 'FAILED'",
        ):
            if phrase not in stage_sql:
                fail(f"workload stage lifecycle is missing required boundary: {phrase}")
        if "js.status IN ('READY', 'RUNNING')" not in migration:
            fail("fair scheduler can bypass a blocked workload stage")

        role_script = (root / "deploy/production/postgres/production_runtime_roles.sql").read_text(encoding="utf-8")
        for role in (
            "elmos_scheduler_rw",
            "elmos_billing_rw",
            "elmos_runtime_worker_limited",
            "elmos_projector_limited",
            "elmos_readonly_analytics",
            "elmos_recovery_verifier_limited",
        ):
            if f"CREATE ROLE {role}" not in role_script:
                fail(f"role boundary missing: {role}")
        if "ai_usage.tool_calls" not in role_script or "ai_usage.tool_call_receipts" not in role_script:
            fail("billing role is missing the distinct ToolCall authority")

        chart = root / "deploy/helm/elmos-runtime"
        require_files(
            (
                chart / "Chart.yaml",
                chart / "values.yaml",
                chart / "values.schema.json",
                chart / "templates/_helpers.tpl",
                chart / "templates/network-policy.yaml",
                chart / "templates/runtime-deployments.yaml",
                chart / "templates/worker-statefulset.yaml",
                chart / "templates/migration-job.yaml",
                chart / "templates/service-accounts.yaml",
                chart / "templates/services.yaml",
                chart / "templates/pod-disruption-budgets.yaml",
                chart / "templates/horizontal-pod-autoscalers.yaml",
                chart / "templates/monitoring.yaml",
            ),
            "deployment asset",
        )
        require_files(
            (
                root / "scripts/production-runtime/run_local_harness.py",
                root / "scripts/production-runtime/run_pitr_drill.py",
                root / "scripts/production-runtime/verify_local_harness.py",
                root / "scripts/production-runtime/external_gate_contract.py",
                root / "scripts/production-runtime/validate_external_gate.py",
                root / "scripts/production-runtime/run_external_gate.py",
                root / "scripts/production-runtime/external_provider_adapter.py",
                root / "scripts/production-runtime/hosted_pitr_adapter.py",
                root / "scripts/production-runtime/independent_verifier.py",
                root / "scripts/production-runtime/independent_verifier_service.py",
                root / "scripts/production-runtime/external_verifier_crypto.py",
                root / "scripts/production-runtime/prepare_pitr_marker.sql",
                root / "scripts/production-runtime/verify_pitr_restore.sql",
                root / "scripts/production-runtime/external-load-smoke.js",
                root / "docs/production-runtime/EXTERNAL-GATE.md",
                root / "docs/production-runtime/EXTERNAL-GATE-PLAN.json",
                root / "docs/production-runtime/TELEMETRY-CONTRACT.json",
                root / "docs/production-runtime/OPERATIONS.md",
                root / "tests/production-runtime/helm-production-values.yaml",
            ),
            "production gate asset",
        )

        harness = (root / "scripts/production-runtime/run_local_harness.py").read_text(encoding="utf-8")
        if "tests/production-runtime/helm-production-values.yaml" not in harness:
            fail("local harness must render the strict production Helm fixture")
        worker_template = (chart / "templates/worker-statefulset.yaml").read_text(encoding="utf-8")
        values_text = (chart / "values.yaml").read_text(encoding="utf-8")
        if ".Values.containerSecurityContext" not in worker_template or "readOnlyRootFilesystem: true" not in values_text:
            fail("worker chart is not read-only")
        if "clusterIP: None" not in (chart / "templates/services.yaml").read_text(encoding="utf-8"):
            fail("worker chart lost individual addressability")
        monitoring = (chart / "templates/monitoring.yaml").read_text(encoding="utf-8")
        for phrase in ("kind: PodMonitor", "kind: PrometheusRule", "actuator/prometheus", "ElmosRuntimeLoopFailures"):
            if phrase not in monitoring:
                fail(f"monitoring asset is missing required boundary: {phrase}")
        migration_job = (chart / "templates/migration-job.yaml").read_text(encoding="utf-8")
        if "ELMOS_PRODUCTION_RUNTIME_WORKLOAD_TOKEN_FILE" in migration_job:
            fail("migration-only process must not mount a runtime workload credential")

        control_plane = (
            root
            / "apps/production-runtime-control-plane/src/main/java/io/elmos/controlplane/ProductionRuntimeControlPlaneConfiguration.java"
        ).read_text(encoding="utf-8")
        if "'${component:scheduler}' != 'migration'" not in control_plane:
            fail("migration-only process does not exclude control-plane runtime loops")
        billing_controller = (
            root
            / "apps/production-runtime-control-plane/src/main/java/io/elmos/controlplane/ProductionRuntimeBillingController.java"
        ).read_text(encoding="utf-8")
        if "topUpAuthenticator.require(authorization)" not in billing_controller:
            fail("top-up mutation does not require its dedicated payment authority")
        chart_schema = json.loads((chart / "values.schema.json").read_text(encoding="utf-8"))
        credential_fields = chart_schema["properties"]["credentials"]["required"]
        if "topupTokenKey" not in credential_fields:
            fail("chart schema is missing the dedicated top-up credential")
        deployments = (chart / "templates/runtime-deployments.yaml").read_text(encoding="utf-8")
        if "ELMOS_PRODUCTION_RUNTIME_TOPUP_TOKEN_FILE" not in deployments or ".Values.credentials.topupTokenKey" not in deployments:
            fail("billing deployment is missing the dedicated top-up credential mount")

        telemetry = json.loads((root / "docs/production-runtime/TELEMETRY-CONTRACT.json").read_text(encoding="utf-8"))
        if telemetry.get("collection", {}).get("endpoint") != "/actuator/prometheus":
            fail("telemetry contract is missing the Prometheus endpoint")
        if "tenant_id" not in telemetry.get("labels_policy", {}).get("deny", []):
            fail("telemetry contract does not deny tenant identity labels")

        billing_source = (source / "JdbcProductionBillingService.java").read_text(encoding="utf-8")
        tool_source = (source / "JdbcProductionToolCallService.java").read_text(encoding="utf-8")
        worker_source = (
            root
            / "apps/production-runtime-worker/src/main/java/io/elmos/productionworker/ProductionWorkerAttemptService.java"
        ).read_text(encoding="utf-8")
        for label, text, phrases in (
            ("ModelCall", billing_source, ("claimProviderDispatch", "PROVIDER_SEND_CLAIMED")),
            ("ToolCall", tool_source, ("claimProviderDispatch", "PROVIDER_SEND_CLAIMED", "markProviderFailed")),
            ("Worker", worker_source, ("COMPLETION_OUTCOME_UNKNOWN", "MAX_ENGINE_RESPONSE_BYTES")),
        ):
            for phrase in phrases:
                if phrase not in text:
                    fail(f"{label} implementation is missing crash-safe boundary: {phrase}")

        scenario_status = json.loads((root / "docs/production-runtime/SCENARIO-STATUS.json").read_text(encoding="utf-8"))
        scenarios = scenario_status.get("scenarios")
        if not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIO_BINDINGS):
            fail("scenario status must preserve the exact 20-scenario inventory")
        if scenario_status.get("decision") != "NOT_CERTIFIED":
            fail("local scenario status cannot certify production")
        for name, (status, test) in SCENARIO_BINDINGS.items():
            if scenarios.get(name) != {"status": status, "test": test}:
                fail(f"scenario binding is incomplete or broadened: {name}")
        if set(scenario_status.get("external_required", [])) != EXTERNAL_REQUIRED:
            fail("scenario status is missing an exact external-gate requirement")

        test_roots = (
            root / "modules/production-runtime/src/test",
            root / "apps/production-runtime-control-plane/src/test",
            root / "apps/production-runtime-worker/src/test",
        )
        test_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for test_root in test_roots
            for path in test_root.rglob("*.java")
        )
        for _, test in SCENARIO_BINDINGS.values():
            if test.endswith(".py"):
                if not (root / test).is_file():
                    fail(f"scenario script binding does not exist: {test}")
            elif test not in test_sources:
                fail(f"scenario test binding does not exist: {test}")

        deployment_plan = json.loads((root / "docs/production-runtime/EXTERNAL-GATE-PLAN.json").read_text(encoding="utf-8"))
        supply_chain = deployment_plan["operations"]["production_deployment"].get("supply_chain")
        if (
            not isinstance(supply_chain, dict)
            or supply_chain.get("signature_verification") != "cosign-key-v1"
            or supply_chain.get("sbom_predicate_type") != "https://cyclonedx.org/bom"
            or supply_chain.get("provenance_predicate_type") != "https://slsa.dev/provenance/v1"
        ):
            fail("external deployment plan is missing signed image/SBOM/provenance verification")
        external_gate = (root / "scripts/production-runtime/run_external_gate.py").read_text(encoding="utf-8")
        for phrase in ("monitoring_crd_command(binding)", "verify_image_supply_chain", "supply_chain_commands"):
            if phrase not in external_gate:
                fail(f"external deployment gate is missing required pre-mutation control: {phrase}")

        source_identity = json.loads((root / "docs/production-runtime/SOURCE-IDENTITY.json").read_text(encoding="utf-8"))
        if source_identity.get("database_migration") != str(stage_migration.relative_to(root)):
            fail("source identity is not bound to the active production stage lifecycle migration")
        actual_test_count = sum(len(JUNIT_TEST.findall(path.read_text(encoding="utf-8"))) for test_root in test_roots for path in test_root.rglob("*.java"))
        if source_identity.get("local_engineering_evidence", {}).get("tests") != actual_test_count:
            fail("source identity test count does not match the executable JUnit inventory")
        external = source_identity.get("external_evidence")
        expected_keys = EXTERNAL_EVIDENCE | {"production_certification"}
        if not isinstance(external, dict) or set(external) != expected_keys:
            fail("source identity external evidence inventory is incomplete or broadened")
        for name in EXTERNAL_EVIDENCE:
            if external.get(name) != "NOT_RUN":
                fail(f"external evidence must remain NOT_RUN until independently executed: {name}")
        if external.get("production_certification") != "NOT_CERTIFIED":
            fail("source identity must retain NOT_CERTIFIED production boundary")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"production-runtime implementation validation: FAIL: {exc}", file=sys.stderr)
        return 1
    print("production-runtime implementation validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
