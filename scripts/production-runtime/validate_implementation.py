#!/usr/bin/env python3
"""Static fail-closed checks for the repository-owned runtime implementation."""

from __future__ import annotations

import argparse
import json
import re
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
    "ProductionProviderPayloadPort.java",
    "ProductionProviderArtifactPort.java",
    "JdbcProductionProviderPayloadStore.java",
    "HttpProductionModelProviderAdapter.java",
    "ProductionModelProviderRegistry.java",
    "ProductionModelCallRecoveryService.java",
    "OwnerOnlyProviderCredentialFile.java",
    "S3ProductionProviderArtifactStore.java",
    "HttpProductionBillingClient.java",
    "HttpProductionToolCallClient.java",
    "HttpProductionWorkerGateway.java",
    "HttpTransactionalOutboxTransport.java",
    "JdbcProductionObjectStorageMetadata.java",
    "ProductionRuntimeSchedulingService.java",
}

REQUIRED_CONTROL_PLANE = {
    "ProductionRuntimeControlPlaneApplication.java",
    "ProductionRuntimeControlPlaneConfiguration.java",
    "ProductionRuntimeTopUpAuthenticator.java",
    "ProductionRuntimeControlPlaneMetrics.java",
    "ProductionRuntimeMigrationConfiguration.java",
    "ProductionRuntimeBillingController.java",
    "ProductionRuntimeInternalController.java",
    "ProductionRuntimeProviderConfiguration.java",
}

REQUIRED_WORKER = {
    "ProductionRuntimeWorkerApplication.java",
    "ProductionWorkerAttemptService.java",
    "ProductionWorkerController.java",
    "ProductionWorkerDurableJournal.java",
    "ProductionWorkerRegistrationLoop.java",
    "ProductionWorkerRouteCatalog.java",
    "ProductionWorkerMetrics.java",
}

MIGRATION_VERSION = re.compile(r"^V([0-9]+(?:_[0-9]+)*)__.+\.sql$")


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
        migration = (
            root
            / "modules/production-runtime/src/main/resources/db/production-runtime/V1__production_repository_execution_os.sql"
        ).read_text(encoding="utf-8")
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
        role_script = (root / "deploy/production/postgres/production_runtime_roles.sql").read_text(encoding="utf-8")
        for role in ("elmos_scheduler_rw", "elmos_billing_rw", "elmos_runtime_worker_limited", "elmos_projector_limited", "elmos_readonly_analytics", "elmos_recovery_verifier_limited"):
            if f"CREATE ROLE {role}" not in role_script or role not in role_script:
                fail(f"role boundary missing: {role}")
        if "ai_usage.tool_calls" not in role_script or "ai_usage.tool_call_receipts" not in role_script:
            fail("Billing role is missing the distinct ToolCall authority")
        chart = root / "deploy/helm/elmos-runtime"
        for path in (
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
        ):
            if not path.is_file():
                fail(f"deployment asset missing: {path}")
        for path in (
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
            root / "docs/production-runtime/EXTERNAL-GATE-PLAN.json",
            root / "docs/production-runtime/TELEMETRY-CONTRACT.json",
            root / "docs/production-runtime/OPERATIONS.md",
            root / "tests/production-runtime/helm-production-values.yaml",
        ):
            if not path.is_file():
                fail(f"production gate asset missing: {path}")
        harness = (root / "scripts/production-runtime/run_local_harness.py").read_text(encoding="utf-8")
        if "tests/production-runtime/helm-production-values.yaml" not in harness:
            fail("local harness must render the strict production Helm fixture")
        worker_template = (chart / "templates/worker-statefulset.yaml").read_text(encoding="utf-8")
        values_text = (chart / "values.yaml").read_text(encoding="utf-8")
        if ".Values.containerSecurityContext" not in worker_template \
                or "readOnlyRootFilesystem: true" not in values_text:
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
        if "ELMOS_PRODUCTION_RUNTIME_TOPUP_TOKEN_FILE" not in deployments \
                or ".Values.credentials.topupTokenKey" not in deployments:
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
        if not isinstance(scenarios, dict) or len(scenarios) != 20 or scenario_status.get("decision") != "NOT_CERTIFIED":
            fail("scenario status must preserve all 20 scenarios and remain non-certified")
        if any(value.get("status") == "LOCAL_TEST_PASS" and not value.get("test") for value in scenarios.values()):
            fail("a local scenario result is missing its executable test binding")
        for name in ("ChaosMatrix", "RedisLoss", "PITRRestore"):
            value = scenarios.get(name)
            if not isinstance(value, dict) or value.get("status") != "LOCAL_HARNESS_PASS" or not value.get("test"):
                fail(f"local harness scenario is not qualified: {name}")
        deployment_plan = json.loads((root / "docs/production-runtime/EXTERNAL-GATE-PLAN.json").read_text(encoding="utf-8"))
        supply_chain = deployment_plan["operations"]["production_deployment"].get("supply_chain")
        if not isinstance(supply_chain, dict) \
                or supply_chain.get("signature_verification") != "cosign-key-v1" \
                or supply_chain.get("sbom_predicate_type") != "https://cyclonedx.org/bom" \
                or supply_chain.get("provenance_predicate_type") != "https://slsa.dev/provenance/v1":
            fail("external deployment plan is missing signed image/SBOM/provenance verification")
        external_gate = (root / "scripts/production-runtime/run_external_gate.py").read_text(encoding="utf-8")
        for phrase in ("monitoring_crd_command(binding)", "verify_image_supply_chain", "supply_chain_commands"):
            if phrase not in external_gate:
                fail(f"external deployment gate is missing required pre-mutation control: {phrase}")
        worker_crash = scenarios.get("WorkerCrashCheckpointResume")
        if not isinstance(worker_crash, dict) or worker_crash.get("status") != "LOCAL_TEST_PASS" \
                or worker_crash.get("test") != "ProductionWorkerRestartRecoveryTest":
            fail("worker restart scenario is not bound to the durable-journal recovery test")
        source_identity = json.loads((root / "docs/production-runtime/SOURCE-IDENTITY.json").read_text(encoding="utf-8"))
        external = source_identity.get("external_evidence")
        if not isinstance(external, dict) or external.get("production_certification") != "NOT_CERTIFIED":
            fail("source identity must retain NOT_CERTIFIED production boundary")
        for name in ("provider_runtime", "target_cluster_load", "chaos", "worker_process_kill", "redis_loss", "backup_pitr", "independent_verification", "production_deployment"):
            if external.get(name) != "NOT_RUN":
                fail(f"external evidence must remain NOT_RUN until independently executed: {name}")
    except (OSError, ValueError) as exc:
        print(f"production-runtime implementation validation: FAIL: {exc}", file=sys.stderr)
        return 1
    print("production-runtime implementation validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
