"""Unit tests for CloudIaCHandoffLedger in batch33."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "batch33"))

from cloud_iac_handoff_ledger import CloudIaCHandoffLedger, CloudResourceFinding


class TestCloudIaCHandoffLedger(unittest.TestCase):
    def test_cloud_iac_handoff_ledger_100_percent_coverage(self) -> None:
        findings = [
            CloudResourceFinding(
                resource_id="k8s-deployment-payment",
                resource_type="apps/v1.Deployment",
                source_file="deploy/k8s/payment.yaml",
                line_number=1,
                is_automated_converted=True,
                excerpt="apiVersion: apps/v1\nkind: Deployment...",
            ),
            CloudResourceFinding(
                resource_id="aws-cloudhsm-cluster",
                resource_type="AWS::CloudHSMv2::Cluster",
                source_file="deploy/cloudformation/security.yaml",
                line_number=54,
                is_automated_converted=False,
                hazard_code="PROPRIETARY_CLOUD_RESOURCE",
                hazard_reason="Hardware HSM cluster requires managed target HSM bridge",
                excerpt="Type: AWS::CloudHSMv2::Cluster...",
            ),
            CloudResourceFinding(
                resource_id="privileged-daemonset",
                resource_type="apps/v1.DaemonSet",
                source_file="deploy/k8s/monitoring.yaml",
                line_number=22,
                is_automated_converted=False,
                hazard_code="PRIVILEGED_SECURITY_POLICY",
                hazard_reason="securityContext.privileged: true violates enterprise security gate",
                excerpt="privileged: true\nhostNetwork: true",
            ),
        ]

        ledger = CloudIaCHandoffLedger.from_resources(findings)

        self.assertEqual(ledger.total_resources, 3)
        self.assertEqual(len(ledger.automated_converted), 1)
        self.assertEqual(len(ledger.handoff_items), 2)
        self.assertEqual(ledger.disposition_coverage, 1.0)
        self.assertTrue(ledger.is_100_percent_covered())

        data = ledger.to_dict()
        self.assertEqual(data["schema_version"], "1.0.0")
        self.assertEqual(data["summary"]["coverage_rate"], 1.0)

        dossier = ledger.generate_markdown_dossier()
        self.assertIn("100% Accounted", dossier)
        self.assertIn("PROPRIETARY_CLOUD_RESOURCE", dossier)
        self.assertIn("PRIVILEGED_SECURITY_POLICY", dossier)


if __name__ == "__main__":
    unittest.main()
