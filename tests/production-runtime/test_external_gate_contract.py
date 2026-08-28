from __future__ import annotations

import copy
import hashlib
import shutil
import subprocess
import sys
import tempfile
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
from external_verifier_crypto import sign_receipt  # noqa: E402
from run_external_gate import helm_candidate_value_arguments, monitoring_crd_command, supply_chain_commands  # noqa: E402


class ExternalGateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = load_object(ROOT / "docs/production-runtime/EXTERNAL-GATE-PLAN.json")

    def test_checked_in_plan_is_digest_bound_and_non_certifying(self) -> None:
        validate_plan(self.plan, ROOT)
        self.assertEqual(EXPECTED_PACKAGE_SHA256, self.plan["package"]["archive_sha256"])
        self.assertEqual("NOT_CERTIFIED", self.plan["production_certification"])
        self.assertTrue(all(item["status"] == "NOT_RUN" for item in self.plan["operations"].values()))
        self.assertEqual(
            "https://cyclonedx.org/bom",
            self.plan["operations"]["production_deployment"]["supply_chain"]["sbom_predicate_type"],
        )

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

    def test_candidate_render_and_upgrade_share_exact_resource_identity(self) -> None:
        binding = copy.deepcopy(self.plan["operations"]["production_deployment"])
        binding["resource_prefix"] = "runtime-candidate"
        binding["image_digests"] = {
            "controlPlane": "registry.example/elmos/control-plane@sha256:" + "a" * 64,
            "worker": "registry.example/elmos/worker@sha256:" + "b" * 64,
        }
        arguments = helm_candidate_value_arguments(binding, "/secure/runtime-values.yaml")
        self.assertIn("fullnameOverride=runtime-candidate", arguments)
        self.assertIn("validation.enforceProductionValues=true", arguments)
        self.assertIn("gate.enabled=true", arguments)

    def test_supply_chain_contract_verifies_each_digest_signature_sbom_and_provenance(self) -> None:
        binding = copy.deepcopy(self.plan["operations"]["production_deployment"])
        binding["image_digests"] = {
            "controlPlane": "registry.example/elmos/control-plane@sha256:" + "a" * 64,
            "worker": "registry.example/elmos/worker@sha256:" + "b" * 64,
        }
        commands = supply_chain_commands(binding, "/secure/cosign.pub")
        self.assertEqual(6, len(commands))
        for _, command in commands:
            self.assertEqual("cosign", command[0])
            self.assertIn("/secure/cosign.pub", command)
            self.assertTrue(any(value.endswith("@sha256:" + "a" * 64) or value.endswith("@sha256:" + "b" * 64) for value in command))
        self.assertIn("https://cyclonedx.org/bom", commands[1][1])
        self.assertIn("https://slsa.dev/provenance/v1", commands[2][1])

    def test_deployment_requires_prometheus_operator_crds_before_mutation(self) -> None:
        binding = copy.deepcopy(self.plan["operations"]["production_deployment"])
        self.assertEqual(
            [
                "kubectl", "--context", binding["context"], "get", "crd",
                "podmonitors.monitoring.coreos.com",
                "prometheusrules.monitoring.coreos.com", "-o", "name",
            ],
            monitoring_crd_command(binding),
        )
        self.assertIn("supply_chain", binding)

    def test_resource_prefix_reserves_space_for_component_suffixes(self) -> None:
        invalid = copy.deepcopy(self.plan)
        prefix = "a" * 54
        invalid["operations"]["production_deployment"]["resource_prefix"] = prefix
        invalid["operations"]["chaos"]["cases"][0]["resource"] = (
            f"deployment/{prefix}-scheduler"
        )
        invalid["operations"]["chaos"]["cases"][0]["recovery_resource"] = (
            f"deployment/{prefix}-scheduler"
        )
        invalid["operations"]["worker_process_kill"]["recovery_resource"] = (
            f"statefulset/{prefix}-worker"
        )
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
        if shutil.which("openssl") is None:
            self.skipTest("openssl is required for detached verifier signature test")
        with tempfile.TemporaryDirectory() as temporary:
            private_key = Path(temporary) / "private.pem"
            public_key = Path(temporary) / "public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)],
                check=True, capture_output=True,
            )
            private_key.chmod(0o600)
            subprocess.run(
                ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
                check=True, capture_output=True,
            )
            operation = copy.deepcopy(self.plan["operations"]["independent_verification"])
            operation["public_key_sha256"] = hashlib.sha256(public_key.read_bytes()).hexdigest()
            receipt = {
                "schema_version": 1,
                "verification_id": "verify-123",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "status": "PASS",
                "report_sha256": "a" * 64,
                "producer_actor": operation["producer_actor"],
                "verifier_actor": operation["verifier_actor"],
                "signing_key_sha256": operation["public_key_sha256"],
            }
            receipt["signature"] = sign_receipt(receipt, private_key)
            env = {operation["public_key_env"]: str(public_key)}
            self.assertEqual(
                receipt,
                validate_verifier_receipt(receipt, operation, "a" * 64, env),
            )
            with self.assertRaises(ContractError):
                validate_verifier_receipt(
                    dict(receipt, report_sha256="b" * 64), operation, "b" * 64, env
                )
            with self.assertRaises(ContractError):
                validate_verifier_receipt(
                    dict(receipt, signature="ZmFrZQ=="), operation, "a" * 64, env
                )


if __name__ == "__main__":
    unittest.main()
