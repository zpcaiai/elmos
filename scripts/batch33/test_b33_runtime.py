"""Test suite verifying all 20 Batch 33 skills through B33SkillRuntime."""

from __future__ import annotations

import pytest
from b33_skill_runtime import B33SkillRuntime


@pytest.fixture
def runtime() -> B33SkillRuntime:
    return B33SkillRuntime()


def test_all_20_skills_registered(runtime: B33SkillRuntime) -> None:
    assert len(runtime.SKILLS) == 20


def test_provider_neutral_iac_ir(runtime: B33SkillRuntime) -> None:
    build_res = runtime.dispatch("b33-provider-neutral-iac-ir", "build_ir", {
        "pack_key": "cloud-iac-test",
        "resources": [
            {"id": "res1", "type": "storage_bucket", "name": "data-bucket"},
            {"id": "res2", "type": "compute_instance", "name": "worker", "depends_on": ["res1"]},
        ],
    })
    assert build_res["valid"] is True
    assert "ir" in build_res
    ir = build_res["ir"]
    assert len(ir["resources"]) == 2

    val_res = runtime.dispatch("b33-provider-neutral-iac-ir", "validate_ir", {"ir": ir})
    assert val_res["valid"] is True
    assert val_res["resource_count"] == 2


def test_runtime_architecture_contract(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-runtime-architecture-contract", "validate", {
        "components": [{"id": "api"}, {"id": "db"}],
        "connections": [{"from": "api", "to": "db"}],
    })
    assert res["valid"] is True
    assert "contract" in res


def test_cloud_iac_devops_factory(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-cloud-iac-devops-factory", "plan", {
        "source_cloud": "aws",
        "target_cloud": "gcp",
    })
    assert res["ready_for_execution"] is True
    assert len(res["pipeline_stages"]) == 5


def test_cloud_service_capability_map(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-cloud-service-capability-map", "map_service", {
        "source_service": "aws_sqs",
    })
    assert res["exact_parity"] is True
    assert res["mapping"]["target_gcp"] == "google_pubsub_topic"


def test_cloud_native_iac_migration(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-cloud-native-iac-migration", "migrate_iac", {
        "source_type": "cloudformation",
        "target_type": "terraform",
    })
    assert res["migrated_resources"] == 2
    assert "google_storage_bucket" in res["generated_hcl"]


def test_terraform_module_migration(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-terraform-module-migration", "migrate_module", {
        "source_tf_version": "0.14",
    })
    assert res["opentofu_compatible"] is True
    assert res["target_version"] == "1.8.x"


def test_kubernetes_manifest_migration(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-kubernetes-manifest-migration", "migrate_manifests", {
        "manifests": ["app.yaml", "ing.yaml"],
    })
    assert res["manifests_processed"] == 2
    assert res["security_context_hardened"] is True


def test_helm_chart_migration(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-helm-chart-migration", "migrate_chart", {
        "chart_name": "checkout-service",
    })
    assert res["helm_target_version"] == "v3"
    assert res["tiller_dependency_removed"] is True


def test_container_build_migration(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-container-build-migration", "migrate_dockerfile", {})
    assert res["multi_stage_optimized"] is True
    assert res["sbom_generation_enabled"] is True


def test_cicd_pipeline_migration(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-cicd-pipeline-migration", "migrate_pipeline", {
        "source_ci": "gitlab-ci",
        "target_ci": "github-actions",
    })
    assert len(res["jobs_migrated"]) == 4
    assert res["secrets_mapping_completed"] is True


def test_api_gateway_ingress_traffic(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-api-gateway-ingress-traffic", "configure_ingress", {
        "routes": [{"path": "/api", "backend": "srv"}],
    })
    assert res["tls_cert_manager_configured"] is True
    assert res["migrated_routes_count"] == 1


def test_identity_network_dns_mesh(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-identity-network-dns-mesh", "configure_mesh", {
        "mesh_type": "istio",
    })
    assert res["mtls_strict_mode"] is True
    assert res["network_policies_generated"] is True


def test_secret_config_environment(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-secret-config-environment", "migrate_secrets", {
        "secrets": ["KEY1", "KEY2"],
    })
    assert res["secrets_migrated"] == 2
    assert res["in_memory_rotation_supported"] is True


def test_observability_alert_dashboard(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-observability-alert-dashboard", "generate_telemetry", {
        "metrics": ["request_count"],
    })
    assert res["telemetry_protocol"] == "OpenTelemetry-v1"
    assert res["slo_alerts_configured"] is True


def test_serverless_event_runtime(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-serverless-event-runtime", "migrate_functions", {
        "functions": ["f1", "f2"],
    })
    assert res["functions_migrated"] == 2
    assert res["event_trigger"] == "cloudevents-pubsub"


def test_managed_service_mapping(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-managed-service-mapping", "map_database", {
        "database": "aws_aurora_postgresql",
    })
    assert res["target_db"] == "google_cloud_sql_postgresql"
    assert res["high_availability"] is True


def test_cloud_cost_capacity_optimizer(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-cloud-cost-capacity-optimizer", "optimize_spend", {
        "monthly_spend_usd": 10000.0,
    })
    assert res["projected_spend_usd"] == 7150.0
    assert len(res["recommendations"]) == 3


def test_cloud_security_guardrails(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-cloud-security-guardrails", "evaluate_policies", {
        "policies": ["p1", "p2"],
    })
    assert res["cis_benchmark_compliance"] == "100%"
    assert len(res["violations"]) == 0


def test_infrastructure_drift_validator(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-infrastructure-drift-validator", "validate_drift", {
        "actual": {"vpc": "vpc-1"},
        "declared": {"vpc": "vpc-1"},
    })
    assert res["state_in_sync"] is True
    assert res["drift_detected"] is False


def test_cloud_certification_gate(runtime: B33SkillRuntime) -> None:
    res = runtime.dispatch("b33-cloud-certification-gate", "evaluate_gate", {
        "iac_ir_valid": True,
        "security_pass": True,
        "drift_pass": True,
        "plan_pass": True,
    })
    assert res["gate_decision"] == "PASS"
    assert res["certified_for_local_execution"] is True
