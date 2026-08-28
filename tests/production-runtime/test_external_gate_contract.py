from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/production-runtime"))

from external_gate_contract import (  # noqa: E402
    ContractError,
    EXPECTED_PACKAGE_SHA256,
    load_object,
    preflight,
    validate_authorization,
    validate_plan,
    validate_verifier_receipt,
)


class ExternalGateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = load_object(ROOT / "docs/production-runtime/EXTERNAL-GATE-PLAN.json")

    def test_checked_in_plan_is_digest_bound_and_non_certifying(self) -> None:
        validate_plan(self.plan, ROOT)
        self.assertEqual(EXPECTED_PACKAGE_SHA256, self.plan["package"]["archive_sha256"])
        self.assertEqual("NOT_CERTIFIED", self.plan["production_certification"])
        self.assertTrue(all(item["status"] == "NOT_RUN" for item in self.plan["operations"].values()))

    def test_preflight_surfaces_bindings_without_contacting_external_systems(self) -> None:
        blockers = preflight(self.plan, ROOT, environ={})
        self.assertIn("_execution", blockers)
        self.assertIn("provider_runtime", blockers)
        self.assertIn("backup_pitr", blockers)
        self.assertIn("production_deployment", blockers)

    def test_plan_cannot_predeclare_external_success(self) -> None:
        invalid = copy.deepcopy(self.plan)
        invalid["operations"]["chaos"]["status"] = "PASS"
        with self.assertRaises(ContractError):
            validate_plan(invalid, ROOT)

    def test_authorization_is_expiring_scoped_and_not_self_verified(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["execution"] = {
            "environment": "staging-approved",
            "region": "cn-east-1",
            "change_id": "CHG-123",
        }
        authorization = {
            "schema_version": 1,
            "authorized": True,
            "actor": "release-operator",
            "environment": "staging-approved",
            "change_id": "CHG-123",
            "approval_id": "APR-123",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "operations": ["target_cluster_load"],
            "allow_destructive_operations": False,
        }
        validate_authorization(authorization, plan, {"target_cluster_load"})
        invalid = dict(authorization, actor="INDEPENDENT_VERIFIER")
        with self.assertRaises(ContractError):
            validate_authorization(invalid, plan, {"target_cluster_load"})

    def test_independent_receipt_is_digest_and_actor_bound(self) -> None:
        operation = self.plan["operations"]["independent_verification"]
        receipt = {
            "verification_id": "verify-123",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "signature": "external-signature",
            "status": "PASS",
            "report_sha256": "a" * 64,
            "producer_actor": operation["producer_actor"],
            "verifier_actor": operation["verifier_actor"],
        }
        self.assertEqual(receipt, validate_verifier_receipt(receipt, operation, "a" * 64))
        with self.assertRaises(ContractError):
            validate_verifier_receipt(dict(receipt, report_sha256="b" * 64), operation, "a" * 64)


if __name__ == "__main__":
    unittest.main()
