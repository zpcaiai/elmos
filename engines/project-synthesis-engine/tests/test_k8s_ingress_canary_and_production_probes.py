"""Tests for Enterprise K8s Ingress Canary, Istio VirtualService, and Hardened 3-Tier Health Probes."""

from __future__ import annotations

from elmos_project_synthesis.k8s_deployment_controller import (
    K8sDeploymentController,
    generate_enterprise_k8s_manifests,
    generate_istio_canary_manifests,
)


def test_enterprise_k8s_manifests_probe_and_canary():
    manifests = generate_enterprise_k8s_manifests(
        app_name="enterprise-order-svc",
        namespace="prod-enterprise",
        image="registry.internal/enterprise/order-svc:v1.2.0",
        port=8000,
        replicas=3,
    )

    # 1. Probe configurations
    assert "startupProbe:" in manifests
    assert "failureThreshold: 12" in manifests
    assert "periodSeconds: 5" in manifests

    assert "livenessProbe:" in manifests
    assert "periodSeconds: 10" in manifests
    assert "timeoutSeconds: 3" in manifests

    assert "readinessProbe:" in manifests
    assert "periodSeconds: 5" in manifests
    assert "timeoutSeconds: 3" in manifests

    # 2. Hardened Pod Security
    assert "readOnlyRootFilesystem: true" in manifests
    assert "allowPrivilegeEscalation: false" in manifests
    assert "drop:" in manifests
    assert "- ALL" in manifests

    # 3. Nginx Canary Ingress
    assert "enterprise-order-svc-ingress-canary" in manifests
    assert 'nginx.ingress.kubernetes.io/canary: "true"' in manifests
    assert 'nginx.ingress.kubernetes.io/canary-by-header: "X-Canary"' in manifests
    assert 'nginx.ingress.kubernetes.io/canary-weight: "20"' in manifests
    assert 'nginx.ingress.kubernetes.io/canary-by-cookie: "canary_user"' in manifests

    # 4. Dry run validation
    controller = K8sDeploymentController()
    valid, msg = controller.dry_run_validate(manifests)
    assert valid is True


def test_istio_virtualservice_and_destinationrule():
    istio_manifests = generate_istio_canary_manifests(
        app_name="order-service",
        namespace="istio-mesh",
        host="orders.corp.internal",
        v1_weight=80,
        v2_weight=20,
    )

    # VirtualService
    assert "kind: VirtualService" in istio_manifests
    assert "orders.corp.internal" in istio_manifests
    assert "x-canary:" in istio_manifests
    assert "exact: always" in istio_manifests
    assert "weight: 80" in istio_manifests
    assert "weight: 20" in istio_manifests

    # DestinationRule
    assert "kind: DestinationRule" in istio_manifests
    assert "consecutive5xxErrors: 3" in istio_manifests
    assert "baseEjectionTime: 30s" in istio_manifests
    assert "name: v1" in istio_manifests
    assert "name: v2" in istio_manifests
