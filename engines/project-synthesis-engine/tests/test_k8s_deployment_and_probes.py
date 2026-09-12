"""Tests for Kubernetes Manifest Generation, Restricted PSS, and 3-Tier Probing."""

from __future__ import annotations

import http.server
import threading

import yaml

from elmos_project_synthesis.k8s_deployment_controller import (
    K8sDeploymentController,
    LocalK8sDetector,
    generate_enterprise_k8s_manifests,
)


def test_enterprise_k8s_manifest_generation_and_pss_compliance():
    manifest_yaml = generate_enterprise_k8s_manifests(
        app_name="order-service",
        namespace="enterprise-prod",
        port=8080,
        replicas=3,
        image_name="registry.enterprise.org/order-service:1.0.0",
    )

    documents = list(yaml.safe_load_all(manifest_yaml))
    assert len(documents) >= 5

    kinds = {doc["kind"] for doc in documents if doc}
    assert "Namespace" in kinds
    assert "ServiceAccount" in kinds
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "NetworkPolicy" in kinds

    # Verify Namespace PodSecurity label
    ns_doc = next(d for d in documents if d.get("kind") == "Namespace")
    assert ns_doc["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"

    # Verify Deployment security context
    deploy_doc = next(d for d in documents if d.get("kind") == "Deployment")
    pod_spec = deploy_doc["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert "ALL" in container["securityContext"]["capabilities"]["drop"]

    # Verify 3-tier health probes in Deployment
    assert container["startupProbe"]["httpGet"]["path"] == "/health/live"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"


def test_k8s_manifest_dry_run_validation():
    manifest_yaml = generate_enterprise_k8s_manifests(
        app_name="payment-service",
        namespace="default",
    )
    # Keep this unit test independent of whether the hosted image happens to
    # preinstall kubectl or configure a cluster. Real-cluster behavior is
    # exercised only by the separately authorized acceptance path.
    controller = K8sDeploymentController(kubectl_bin="/elmos/test/missing-kubectl")
    valid, msg = controller.dry_run_validate(manifest_yaml)

    assert valid is True
    assert len(msg) > 0


class _MockHealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health/live":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "UP"}')
        elif self.path == "/health/ready":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ready": true, "components": {"database": "UP"}}')
        elif self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"http_requests_total 42\n")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet during tests


def test_k8s_3_tier_probe_pipeline_execution():
    server = http.server.HTTPServer(("127.0.0.1", 0), _MockHealthHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        controller = K8sDeploymentController()
        probes = controller.probe_service_http(base_url=f"http://127.0.0.1:{port}", app_name="mock-service")

        assert len(probes) == 4
        # Probe types: startup, liveness, readiness, metrics
        probe_map = {p.probe_type: p for p in probes}
        assert probe_map["startup"].passed is True
        assert probe_map["liveness"].passed is True
        assert probe_map["readiness"].passed is True
        assert probe_map["metrics"].passed is True

        assert probe_map["liveness"].status_code == 200
        assert probe_map["readiness"].status_code == 200
    finally:
        server.shutdown()
        server.server_close()


def test_local_cluster_detector():
    is_available, context = LocalK8sDetector.detect_cluster()
    assert isinstance(is_available, bool)
    assert isinstance(context, str)
