"""Tests for Autonomic Cluster Delivery, Packaging Verification, and Self-Healing Pipeline."""

from __future__ import annotations

from elmos_project_synthesis.autonomic_healing_pipeline import (
    AutonomicHealingPipeline,
    ContainerPackagingVerifier,
    SelfHealingReceipt,
)
from elmos_project_synthesis.k8s_deployment_controller import (
    K8sDeploymentController,
    generate_enterprise_k8s_manifests,
)


def test_container_packaging_verifier_detects_root_and_single_stage():
    insecure_dockerfile = """
    FROM python:3.12-slim
    WORKDIR /app
    COPY . .
    CMD ["python", "main.py"]
    """
    res = ContainerPackagingVerifier.verify_dockerfile(insecure_dockerfile)
    assert not res.valid
    assert not res.has_non_root_user
    assert any("CRITICAL_RUN_AS_ROOT" in f for f in res.findings)

    secure_dockerfile = """
    FROM python:3.12-slim AS builder
    WORKDIR /build
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt

    FROM python:3.12-slim
    WORKDIR /app
    COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
    COPY . .
    USER 10001
    HEALTHCHECK --interval=30s CMD curl -f http://localhost:8080/health/live || exit 1
    ENTRYPOINT ["python", "main.py"]
    """
    res2 = ContainerPackagingVerifier.verify_dockerfile(secure_dockerfile)
    assert res2.valid
    assert res2.has_multistage
    assert res2.has_non_root_user
    assert res2.has_healthcheck


def test_autonomic_delivery_healthy_rollout_promotes_revision():
    pipeline = AutonomicHealingPipeline(app_name="order-api", namespace="prod", port=8080)
    v1_manifest = generate_enterprise_k8s_manifests("order-api", namespace="prod", port=8080)
    pipeline.register_revision("v1-stable", v1_manifest, is_stable=True)

    v2_manifest = generate_enterprise_k8s_manifests("order-api", namespace="prod", port=8080)
    status, receipt, probes = pipeline.deploy_and_supervise("v2-candidate", v2_manifest)

    assert status == "SUCCESS"
    assert receipt is None
    assert all(p.passed for p in probes)
    assert pipeline.stable_revision == "v2-candidate"


def test_autonomic_delivery_degraded_probe_triggers_automatic_rollback_and_receipt():
    pipeline = AutonomicHealingPipeline(app_name="payment-svc", namespace="prod", port=8080)
    v1_manifest = generate_enterprise_k8s_manifests("payment-svc", namespace="prod", port=8080)
    pipeline.register_revision("v1-stable", v1_manifest, is_stable=True)

    v2_manifest = generate_enterprise_k8s_manifests("payment-svc", namespace="prod", port=8080)

    # Simulate readiness probe returning HTTP 503 (database connection pool exhausted)
    mock_failing_probes = [
        ("startup", "/health/live", 200),
        ("liveness", "/health/live", 200),
        ("readiness", "/health/ready", 503),
        ("metrics", "/metrics", 200),
    ]

    status, receipt, probes = pipeline.deploy_and_supervise(
        "v2-bad", v2_manifest, mock_probe_responses=mock_failing_probes
    )

    # Verify self-healing triggered
    assert status == "REVERTED"
    assert receipt is not None
    assert isinstance(receipt, SelfHealingReceipt)

    # Verify receipt metadata
    assert receipt.app_name == "payment-svc"
    assert receipt.failed_revision == "v2-bad"
    assert receipt.reverted_to_revision == "v1-stable"
    assert receipt.recovery_status == "RECOVERED"
    assert receipt.remedy_action == "AUTOMATIC_ROLLBACK"
    assert "readiness failed with HTTP 503" in receipt.failure_reason
    assert receipt.receipt_sha256.startswith("sha256:")

    # Verify current revision reverted to v1-stable
    assert pipeline.current_revision == "v1-stable"


def test_localk8s_deployer_integration_with_autonomic_healing():
    deployer = K8sDeploymentController()

    # 1. Healthy deployment
    status, receipt, probes = deployer.run_autonomic_deployment_with_healing("auth-svc")
    assert status == "SUCCESS"
    assert receipt is None

    # 2. Degraded deployment triggers healing
    status_fail, receipt_fail, _ = deployer.run_autonomic_deployment_with_healing(
        "auth-svc",
        mock_probe_responses=[
            ("startup", "/health/live", 500),
            ("liveness", "/health/live", 500),
            ("readiness", "/health/ready", 500),
            ("metrics", "/metrics", 500),
        ],
    )
    assert status_fail == "REVERTED"
    assert receipt_fail is not None
    assert receipt_fail.recovery_status == "RECOVERED"
