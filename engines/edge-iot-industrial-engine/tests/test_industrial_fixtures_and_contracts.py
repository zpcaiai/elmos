"""Comprehensive test suite for Edge IoT & Industrial engine fixtures, policies, and contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestIndustrialFixturesAndContracts(unittest.TestCase):
    """Validates Batch 24 industrial safety boundaries, contracts, and fixture matrices."""

    def setUp(self) -> None:
        self.fixtures_dir = ROOT / "test-fixtures"
        self.policies_dir = ROOT / "policies"
        self.val_profiles_dir = ROOT / "validation-profiles"

    def test_adapters_policy(self) -> None:
        policy_file = self.policies_dir / "adapters-v1.json"
        self.assertTrue(policy_file.exists())
        policy = json.loads(policy_file.read_text(encoding="utf-8"))

        self.assertEqual(policy["schemaVersion"], "1.0")
        self.assertEqual(policy["tokenPolicy"], "SHORT_LIVED_SCOPED")
        self.assertEqual(policy["discoveryDefault"], "READ_ONLY")

        adapters = policy["adapters"]
        expected_adapters = [
            "OPCUA", "MQTT", "SPARKPLUG", "MODBUS", "INDUSTRIAL_PROTOCOLS",
            "ECLIPSE_DITTO", "KUBEEDGE", "HISTORIAN", "OTA", "EDGE_AI", "VENDOR_PLC"
        ]
        self.assertEqual(len(adapters), 11)
        for ea in expected_adapters:
            self.assertIn(ea, adapters)
            self.assertEqual(adapters[ea], "NOT_CONFIGURED")

    def test_safety_boundary_policy(self) -> None:
        policy_file = self.policies_dir / "safety-boundary-v1.json"
        self.assertTrue(policy_file.exists())
        policy = json.loads(policy_file.read_text(encoding="utf-8"))

        self.assertEqual(policy["schemaVersion"], "1.0")
        self.assertEqual(policy["batch"], 24)
        self.assertFalse(policy["controlPlaneExecution"])
        self.assertEqual(policy["productionMutationDefault"], "DENY")
        self.assertFalse(policy["humanDecisionAutoGrant"])
        self.assertFalse(policy["workerMayModifyGate"])
        self.assertFalse(policy["notRunCanPass"])
        self.assertEqual(policy["riskAcceptanceAuthority"], "HUMAN_ONLY")

    def test_hard_gates_validation_profile(self) -> None:
        profile_file = self.val_profiles_dir / "hard-gates-v1.json"
        self.assertTrue(profile_file.exists())
        profile = json.loads(profile_file.read_text(encoding="utf-8"))

        self.assertEqual(profile["schemaVersion"], "1.0")
        self.assertEqual(profile["batch"], 24)
        self.assertEqual(profile["outcomeOnMissingEvidence"], "BLOCKED")
        self.assertEqual(profile["outcomeOnStaleEvidence"], "BLOCKED")
        self.assertTrue(profile["independentEvidenceRequired"])
        self.assertEqual(profile["productionDecisionAuthority"], "INDEPENDENT_CONTROL_PLANE_AND_HUMAN")

    def test_batch24_acceptance_scenarios_all_fail_closed(self) -> None:
        scenarios_file = self.fixtures_dir / "batch24-acceptance-scenarios.json"
        self.assertTrue(scenarios_file.exists())
        scenarios = json.loads(scenarios_file.read_text(encoding="utf-8"))

        self.assertEqual(len(scenarios), 36)
        for s in scenarios:
            self.assertIn("scenarioId", s)
            self.assertIn("title", s)
            self.assertIn("requirements", s)
            self.assertEqual(s["safeOutcome"], "FAIL_CLOSED")
            self.assertFalse(s["externalExecutionExpected"])
            self.assertFalse(s["autoApprovalAllowed"])

    def test_industrial_tag_contract_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "industrial-tag-contract-fixture.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        expected_keys = [
            "tagId", "assetId", "sourceEndpointId", "address",
            "dataType", "qualityProfile", "writePolicy"
        ]
        for k in expected_keys:
            self.assertIn(k, data)

    def test_digital_twin_state_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "digital-twin-state-fixture.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("twinId", data)
        self.assertIn("featureId", data)
        self.assertIn("stateType", data)
        self.assertEqual(data["stateType"], "REPORTED")
        self.assertIn("value", data)
        self.assertIn("quality", data)
        self.assertIn("sourceTimestamp", data)
        self.assertIn("version", data)

    def test_device_command_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "device-command-fixture.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("commandId", data)
        self.assertIn("targetDeviceId", data)
        self.assertIn("commandType", data)
        self.assertIn("parameters", data)
        self.assertIn("deadline", data)
        self.assertIn("approvalPolicy", data)
        self.assertIn("status", data)

    def test_industrial_cutover_decision_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "industrial-cutover-decision-fixture.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("cutoverScopeId", data)
        self.assertIn("decision", data)
        self.assertEqual(data["decision"], "READY")
        self.assertIn("safetyStatus", data)
        self.assertIn("shadowStatus", data)
        self.assertIn("rollbackStatus", data)
        self.assertIn("evidenceRefs", data)

    def test_ota_release_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "ota-release-fixture.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("releaseId", data)
        self.assertIn("artifactDigest", data)
        self.assertIn("targetModels", data)
        self.assertIn("releaseCounter", data)
        self.assertIn("signatureRefs", data)
        self.assertIn("rollbackPolicy", data)

    def test_fixture_matrix(self) -> None:
        matrix_file = self.fixtures_dir / "fixture-matrix.json"
        self.assertTrue(matrix_file.exists())
        matrix = json.loads(matrix_file.read_text(encoding="utf-8"))

        self.assertEqual(matrix["batch"], 24)
        self.assertIn("entries", matrix)
        self.assertTrue(len(matrix["entries"]) > 0)


if __name__ == "__main__":
    unittest.main()

