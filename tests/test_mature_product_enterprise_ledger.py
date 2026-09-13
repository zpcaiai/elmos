"""Tests for Batches 38-45 Mature Product Enterprise Ledger."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.mature_product_enterprise_ledger import (
    MatureBatchDomain,
    MatureItemStatus,
    MatureProductDispositionSummary,
    MatureProductEnterpriseLedger,
    MatureProductItem,
)


class TestMatureProductEnterpriseLedger(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = MatureProductEnterpriseLedger()

    def test_empty_scan(self) -> None:
        summary = self.ledger.scan_and_classify([])
        self.assertEqual(summary.total_items, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertFalse(summary.is_fully_dispositioned)

    def test_all_automated(self) -> None:
        items = [
            MatureProductItem(
                item_id="MATURE-001",
                domain=MatureBatchDomain.B38_DEPLOYMENT_EDITIONS,
                name="sovereign_vpc_topology",
                status=MatureItemStatus.AUTOMATED_CONFORMANCE_VERIFIED,
                target_resource="infra/vpc-edition.tf",
            ),
            MatureProductItem(
                item_id="MATURE-002",
                domain=MatureBatchDomain.B39_GLOBAL_SRE_OPS,
                name="api_latency_slo_target",
                status=MatureItemStatus.SLO_PROVED,
                target_resource="monitoring/slo-api.json",
            ),
            MatureProductItem(
                item_id="MATURE-003",
                domain=MatureBatchDomain.B40_SUPPLY_CHAIN_SECURITY,
                name="container_cosign_signature",
                status=MatureItemStatus.SIGNATURE_VERIFIED,
                target_resource="docker/release-image.tar",
            ),
        ]
        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 3)
        self.assertEqual(summary.automated_verified_count, 3)
        self.assertEqual(summary.governance_handoff_count, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

    def test_mixed_dual_track_100_percent_disposition(self) -> None:
        items = [
            MatureProductItem(
                item_id="MATURE-101",
                domain=MatureBatchDomain.B38_DEPLOYMENT_EDITIONS,
                name="airgap_signed_tarball",
                status=MatureItemStatus.AIRGAP_BUNDLE_DEFECT,
                target_resource="dist/offline-bundle-v2.1.tar.gz",
                priority="P0",
            ),
            MatureProductItem(
                item_id="MATURE-102",
                domain=MatureBatchDomain.B39_GLOBAL_SRE_OPS,
                name="multi_region_pitr_restore",
                status=MatureItemStatus.SRE_FAILOVER_GAP,
                target_resource="db/cluster-ap-southeast.json",
                priority="P0",
            ),
            MatureProductItem(
                item_id="MATURE-103",
                domain=MatureBatchDomain.B40_SUPPLY_CHAIN_SECURITY,
                name="openssl_cve_mitigation",
                status=MatureItemStatus.CVE_SECURITY_REMEDIATION,
                target_resource="cve/CVE-2026-1122.json",
                priority="P0",
            ),
            MatureProductItem(
                item_id="MATURE-104",
                domain=MatureBatchDomain.B41_KNOWLEDGE_PREDICTION,
                name="tenant_data_differential_privacy",
                status=MatureItemStatus.KNOWLEDGE_LEAKAGE_RISK,
                target_resource="models/rag-tenant-weights",
                priority="P1",
            ),
            MatureProductItem(
                item_id="MATURE-105",
                domain=MatureBatchDomain.B42_GOVERNED_AGENT_FACTORY,
                name="agent_worker_killswitch",
                status=MatureItemStatus.AGENT_KILLSWITCH_UNVERIFIED,
                target_resource="agent/supervisor-worker-pool",
                priority="P0",
            ),
            MatureProductItem(
                item_id="MATURE-106",
                domain=MatureBatchDomain.B43_PRODUCT_LIFECYCLE_LTS,
                name="event_schema_v2_breakage",
                status=MatureItemStatus.BREAKING_SCHEMA_BLOCKED,
                target_resource="schemas/events/payment.json",
                priority="P1",
            ),
            MatureProductItem(
                item_id="MATURE-107",
                domain=MatureBatchDomain.B44_FINOPS_ECONOMICS,
                name="heavy_gpu_pilot_contract",
                status=MatureItemStatus.MARGIN_DEFICIT_ESCALATION,
                target_resource="billing/contracts/tenant-99.json",
                priority="P1",
            ),
            MatureProductItem(
                item_id="MATURE-108",
                domain=MatureBatchDomain.B45_MATURE_PRODUCT_CERTIFICATION,
                name="overall_l5_maturity_review",
                status=MatureItemStatus.MATURE_CERTIFIED,
                target_resource="certification/enterprise-l5.json",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 8)
        self.assertEqual(summary.automated_verified_count, 1)
        self.assertEqual(summary.governance_handoff_count, 7)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

        self.assertIn("offline update bundle", items[0].remediation_runbook)
        self.assertIn("evacuation drill", items[1].remediation_runbook)
        self.assertIn("CISO", items[2].remediation_runbook)

    def test_dossier_generation_and_write(self) -> None:
        items = [
            MatureProductItem(
                item_id="MATURE-201",
                domain=MatureBatchDomain.B44_FINOPS_ECONOMICS,
                name="metering_ledger_sync",
                status=MatureItemStatus.FINOPS_RECONCILED,
                target_resource="billing/ledger.json",
            ),
            MatureProductItem(
                item_id="MATURE-202",
                domain=MatureBatchDomain.B45_MATURE_PRODUCT_CERTIFICATION,
                name="external_audit_risk_residual",
                status=MatureItemStatus.CRITICAL_RESIDUAL_RISK,
                target_resource="audit/board-findings.json",
                priority="P0",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        json_data = self.ledger.generate_enterprise_json(summary)
        self.assertEqual(json_data["total_items"], 2)
        self.assertEqual(json_data["automated_verified_count"], 1)
        self.assertEqual(json_data["governance_handoff_count"], 1)
        self.assertEqual(json_data["disposition_coverage_ratio"], 1.0)
        self.assertTrue(json_data["is_fully_dispositioned"])

        md_text = self.ledger.generate_markdown_dossier(summary)
        self.assertIn("Batches 38-45 Mature Commercial Platform Product Disposition Dossier", md_text)
        self.assertIn("100% Accounted", md_text)
        self.assertIn("`MATURE-202`", md_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = self.ledger.write_handoff_dossier(summary, Path(tmpdir))
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

            saved_json = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_json["total_items"], 2)


if __name__ == "__main__":
    unittest.main()
