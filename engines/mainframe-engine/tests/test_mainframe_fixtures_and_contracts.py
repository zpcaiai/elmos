import json
import unittest
from pathlib import Path

# Add src to sys.path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from elmos_mainframe_bridge import parse_comp3_field, format_comp3_field


class TestMainframeFixturesAndContracts(unittest.TestCase):
    """Tests validating mainframe engine policies, contract fixtures, and copybook models."""

    def setUp(self):
        self.fixtures_dir = ROOT / "test-fixtures"
        self.policies_dir = ROOT / "policies"

    def test_copybook_layout_fixture(self):
        fixture_path = self.fixtures_dir / "copybook-layout.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))

        self.assertEqual(data["itemId"], "PAY-AMOUNT")
        self.assertEqual(data["name"], "PAY-AMOUNT")
        self.assertEqual(data["pic"], "S9(11)V99")
        self.assertEqual(data["usage"], "COMP-3")
        self.assertEqual(data["offset"], 16)
        self.assertEqual(data["length"], 7)
        self.assertEqual(data["ccsid"], "IBM-1047")

    def test_copybook_field_comp3_encoding_and_decoding(self):
        """Simulate reading and writing a record according to copybook-layout.json."""
        # 16 bytes header + 7 bytes PAY-AMOUNT COMP-3 + 9 bytes trailing
        record_len = 32
        record = bytearray(b"\x00" * record_len)

        # Write amount "98765432101.23" (13 digits: 11 int + 2 frac)
        amount_str = "98765432101.23"
        comp3_bytes = format_comp3_field(amount_str, scale=2, length=7)
        self.assertEqual(len(comp3_bytes), 7)

        # Place at offset 16
        record[16:23] = comp3_bytes

        # Parse back using copybook specs
        extracted = parse_comp3_field(bytes(record), offset=16, length=7, scale=2)
        self.assertEqual(extracted, amount_str)

    def test_jcl_flow_fixture(self):
        fixture_path = self.fixtures_dir / "jcl-flow.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))

        self.assertEqual(data["stepId"], "POSTPAY")
        self.assertEqual(data["jobId"], "DAILYPAY")
        self.assertEqual(data["executionTarget"], "PAYMENT1")
        self.assertTrue(data["restartable"])
        self.assertIn("CONSUMES:PAY.GDG(-1)", data["datasetEdges"])
        self.assertEqual(data["returnCodePolicy"]["businessFailure"], [12])

    def test_cobol_semantic_fixture(self):
        fixture_path = self.fixtures_dir / "cobol-semantic.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))

        self.assertEqual(data["programId"], "PAYMENT1")
        self.assertIn("MAIN", data["sections"])
        self.assertIn("POST-PAYMENT", data["sections"])
        self.assertTrue(len(data["calls"]) > 0)
        self.assertEqual(data["calls"][0]["kind"], "DYNAMIC_CALL_VARIABLE")
        self.assertEqual(data["calls"][0]["target"], "PAYMENT-HANDLER")

    def test_cics_contract_fixture(self):
        fixture_path = self.fixtures_dir / "cics-contract.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_ims_contract_fixture(self):
        fixture_path = self.fixtures_dir / "ims-contract.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_mainframe_estate_fixture(self):
        fixture_path = self.fixtures_dir / "mainframe-estate.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_mainframe_business_rule_fixture(self):
        fixture_path = self.fixtures_dir / "mainframe-business-rule.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_mainframe_semantic_equivalence_fixture(self):
        fixture_path = self.fixtures_dir / "mainframe-semantic-equivalence.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_batch19_acceptance_scenarios_fixture(self):
        fixture_path = self.fixtures_dir / "batch19-acceptance-scenarios.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertTrue(isinstance(data, list) or "scenarios" in data)

    def test_fixture_matrix(self):
        fixture_path = self.fixtures_dir / "fixture-matrix.json"
        self.assertTrue(fixture_path.exists())
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, (dict, list))

    def test_mainframe_adapters_policy(self):
        policy_path = self.policies_dir / "mainframe-adapters-v1.json"
        self.assertTrue(policy_path.exists())
        policy = json.loads(policy_path.read_text(encoding="utf-8"))

        self.assertEqual(policy["schemaVersion"], "1.0")
        self.assertEqual(policy["defaultStatus"], "NOT_CONFIGURED")
        self.assertEqual(policy["network"], "ALLOWLIST_REQUIRED")
        self.assertEqual(policy["discoveryDefault"], "READ_ONLY")

        # Security: defaultDeny must include production writing / arbitrary execution
        default_deny = set(policy["defaultDeny"])
        self.assertIn("SUBMIT_ARBITRARY_JCL", default_deny)
        self.assertIn("WRITE_PRODUCTION_DATASET", default_deny)
        self.assertIn("WRITE_PRODUCTION_LOADLIB", default_deny)
        self.assertIn("ALTER_CICS_RESOURCE", default_deny)
        self.assertIn("ALTER_IMS_RESOURCE", default_deny)
        self.assertIn("ALTER_DB2", default_deny)
        self.assertIn("MODIFY_SCHEDULER", default_deny)

        # Adapters supported
        adapters = set(policy["adapters"])
        self.assertIn("ZOSMF_REST", adapters)
        self.assertIn("CICS", adapters)
        self.assertIn("IMS", adapters)
        self.assertIn("DB2_ZOS", adapters)
        self.assertIn("SCHEDULER", adapters)

    def test_modernization_targets_policy(self):
        policy_path = self.policies_dir / "modernization-targets-v1.json"
        self.assertTrue(policy_path.exists())
        policy = json.loads(policy_path.read_text(encoding="utf-8"))

        self.assertEqual(policy["schemaVersion"], "1.0")
        self.assertIsNone(policy["defaultTarget"])

        targets = set(policy["targets"])
        self.assertIn("KEEP_AND_OPTIMIZE", targets)
        self.assertIn("API_ENABLE", targets)
        self.assertIn("MODULARIZE_COBOL", targets)
        self.assertIn("HYBRID_EXTRACT", targets)
        self.assertIn("COBOL_TO_JAVA", targets)
        self.assertIn("REPLATFORM_RUNTIME", targets)
        self.assertIn("DATA_ONLY_MODERNIZATION", targets)
        self.assertIn("PACKAGE_REPLACEMENT", targets)
        self.assertIn("RETIRE", targets)

        rules = policy["rules"]
        self.assertTrue(rules["noDefaultCobolToJava"])
        self.assertTrue(rules["onlineAndBatchSeparate"])
        self.assertTrue(rules["testReadinessRequired"])
        self.assertTrue(rules["uniqueDataAuthorityRequired"])
        self.assertTrue(rules["blockedIsValidOutcome"])


if __name__ == "__main__":
    unittest.main()
