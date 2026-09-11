"""Industrial physical middleware tests for B38-B45 / SRE.

These tests speak Vault, Toxiproxy, Kubernetes, Rekor, and cloud-vendor
wire protocols against an in-process loopback — they do not increment
in-memory counters and call that a physical backend.
"""

from __future__ import annotations

import hashlib
import unittest

from elmos_mature_platform.artifact_container_signing_engine import ArtifactContainerSigningEngine
from elmos_mature_platform.autoscaling_capacity_engine import AutoscalingCapacityEngine
from elmos_mature_platform.industrial_certification import run_industrial_certification
from elmos_mature_platform.physical.bundle import PhysicalBundle
from elmos_mature_platform.physical.loopback import IndustrialLoopback
from elmos_mature_platform.physical.protocol import http_call
from elmos_mature_platform.types import (
    ArtifactKind,
    ScalingPolicy,
    ScalingTrigger,
    SignatureAlgorithm,
    SignedArtifactManifest,
)


class TestPhysicalIndustrialSubstrate(unittest.TestCase):
    def setUp(self) -> None:
        self.loopback = IndustrialLoopback()
        self.base_url = self.loopback.start()
        self.bundle = PhysicalBundle.for_loopback(self.base_url)

    def tearDown(self) -> None:
        self.loopback.stop()

    def test_sigstore_openssl_and_rekor_hashedrekord(self) -> None:
        digest = hashlib.sha256(b"container-layer").hexdigest()
        attestation = self.bundle.sigstore.attest_artifact(
            artifact_digest=f"sha256:{digest}",
            subject_name="oci://elmos/app:1",
        )
        self.assertTrue(attestation.openssl_applied)
        self.assertTrue(attestation.rekor_applied)
        self.assertEqual(attestation.dsse_envelope["payloadType"], "application/vnd.in-toto+json")
        self.assertEqual(attestation.rekor_entry["kind"], "hashedrekord")
        self.assertIn("sign-blob", attestation.cosign_sign_argv)
        verify = self.bundle.sigstore.verify_digest(
            digest,
            attestation.signature_base64,
            attestation.public_key_pem,
        )
        self.assertTrue(verify.applied)

    def test_kubernetes_hpa_vpa_and_network_policy_api(self) -> None:
        bundle = self.bundle.kubernetes.apply_hpa_vpa(
            service_name="web",
            min_replicas=2,
            max_replicas=8,
            target_utilization=70,
        )
        self.assertEqual(bundle.hpa_manifest["apiVersion"], "autoscaling/v2")
        self.assertEqual(bundle.vpa_manifest["kind"], "VerticalPodAutoscaler")
        self.assertTrue(any(item.applied and item.operation == "create_hpa" for item in bundle.receipts))
        isolation = self.bundle.kubernetes.apply_tenant_isolation(
            tenant_id="t-42",
            cpu_cores=4,
            memory_gb=16,
        )
        self.assertEqual(isolation.network_policy_manifest["kind"], "NetworkPolicy")
        self.assertTrue(any(item.applied for item in isolation.receipts))

    def test_vault_transit_encrypt_decrypt_round_trip(self) -> None:
        self.assertTrue(self.bundle.vault.create_key("cmk-1").applied)
        wrapped = self.bundle.vault.encrypt("cmk-1", b"hello-dek")
        self.assertTrue(wrapped.applied)
        self.assertTrue(wrapped.ciphertext.startswith("vault:v1:"))
        unwrapped = self.bundle.vault.decrypt("cmk-1", wrapped.ciphertext)
        self.assertTrue(unwrapped.applied)

    def test_toxiproxy_latency_toxic_and_reset(self) -> None:
        injection = self.bundle.toxiproxy.inject_fault(
            target_service="checkout",
            fault_type="latency",
            latency_ms=321,
        )
        self.assertTrue(injection.applied)
        self.assertEqual(injection.toxic_body["type"], "latency")
        self.assertEqual(injection.toxic_body["attributes"]["latency"], 321)
        self.assertTrue(self.bundle.toxiproxy.reset().applied)

    def test_multicloud_traffic_shift_wire_payloads(self) -> None:
        shift = self.bundle.cloud.shift_traffic(source_region="us-east-1", target_region="ap-east-1")
        self.assertTrue(shift.applied)
        self.assertIn("ChangeResourceRecordSetsRequest", shift.route53_xml)
        self.assertEqual(shift.gcp_change["kind"], "dns#change")
        self.assertEqual(shift.azure_profile["type"], "Microsoft.Network/trafficmanagerprofiles")
        self.assertEqual(len(self.loopback.store.cloud), 3)

    def test_engines_call_physical_drivers(self) -> None:
        signing = ArtifactContainerSigningEngine(sigstore_driver=self.bundle.sigstore)
        digest = hashlib.sha256(b"img").hexdigest()
        signing.register_artifact_manifest(
            SignedArtifactManifest(
                artifact_id="oci://elmos/img:1",
                artifact_kind=ArtifactKind.OCI_CONTAINER_IMAGE,
                artifact_digest=f"sha256:{digest}",
                artifact_size_bytes=8,
            )
        )
        record = signing.sign_artifact_physically(
            "oci://elmos/img:1",
            "k1",
            "signer@elmos.io",
            SignatureAlgorithm.ES256,
        )
        self.assertIsNotNone(record)
        self.assertTrue(signing._manifests["oci://elmos/img:1"].metadata["sigstore"]["dsse_envelope"])

        engine = AutoscalingCapacityEngine(kubernetes_driver=self.bundle.kubernetes)
        engine.register_policy(ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0))
        decision = engine.evaluate_scaling("web", 1, {"cpu_threshold": 99.0})
        result = engine.apply_scaling_decision(decision)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["physical"]["hpa_manifest"]["kind"], "HorizontalPodAutoscaler")

    def test_fail_closed_when_backend_unreachable(self) -> None:
        receipt = http_call(
            backend="vault-transit",
            operation="encrypt",
            method="POST",
            url="http://127.0.0.1:1/v1/transit/encrypt/x",
            body={"plaintext": "Zg=="},
            timeout=0.2,
        )
        self.assertFalse(receipt.applied)
        self.assertTrue(receipt.error)

    def test_full_industrial_certification_gate(self) -> None:
        report = run_industrial_certification()
        self.assertEqual(report["evaluation_verdict"], "100% FULLY_CERTIFIED_PHYSICAL_MIDDLEWARE")
        self.assertEqual(report["scores"]["工业级真实质量得分"], "100%")
        self.assertEqual(report["metrics_breakdown"]["industrial_quality_score"], 1.0)
        for name, component in report["verification_components"].items():
            self.assertEqual(component["status"], "PASSED", name)


if __name__ == "__main__":
    unittest.main()
