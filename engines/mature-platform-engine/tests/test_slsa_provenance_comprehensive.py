import unittest
import uuid
import hashlib
import hmac
from datetime import datetime, timezone
from elmos_mature_platform.types import (
    InTotoStatement,
    ProvenanceAttestationStatus,
    SlsaLevel,
)
from elmos_mature_platform.slsa_provenance_engine import SlsaProvenanceEngine


class TestSlsaProvenanceEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SlsaProvenanceEngine()

    def test_generate_statement_assigns_id(self):
        stmt = InTotoStatement(statement_id="", subject_name="test-artifact", subject_sha256="abc")
        stmt_id = self.engine.generate_statement(stmt)
        self.assertTrue(stmt_id)
        self.assertEqual(stmt.status, ProvenanceAttestationStatus.GENERATED)
        self.assertTrue(stmt.created_at)

    def test_generate_statement_keeps_id(self):
        stmt_id = "test-id"
        stmt = InTotoStatement(statement_id=stmt_id, subject_name="test", subject_sha256="abc")
        res_id = self.engine.generate_statement(stmt)
        self.assertEqual(res_id, stmt_id)

    def test_sign_statement_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.sign_statement("invalid-id", "key1", "secret")

    def test_sign_statement_valid(self):
        stmt = InTotoStatement(statement_id="", subject_name="artifact", subject_sha256="sha", builder_id="builder")
        stmt_id = self.engine.generate_statement(stmt)
        signed_stmt = self.engine.sign_statement(stmt_id, "key-1", "my-secret")
        self.assertEqual(signed_stmt.status, ProvenanceAttestationStatus.SIGNED)
        self.assertEqual(signed_stmt.signer_key_id, "key-1")
        self.assertTrue(signed_stmt.signature)

        msg = b"artifactshabuildermy-secret"
        expected_sig = hmac.new(b"my-secret", msg, hashlib.sha256).hexdigest()
        self.assertEqual(signed_stmt.signature, expected_sig)

    def test_verify_provenance_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.verify_provenance("invalid", "sha", SlsaLevel.LEVEL_1)

    def test_verify_provenance_tamper_detected(self):
        stmt = InTotoStatement(statement_id="", subject_name="artifact", subject_sha256="expected-sha")
        stmt_id = self.engine.generate_statement(stmt)
        res = self.engine.verify_provenance(stmt_id, "different-sha", SlsaLevel.LEVEL_1)
        self.assertFalse(res.passed)
        self.assertTrue(res.tamper_detected)
        self.assertIn("Digest mismatch", res.violations)

    def test_verify_provenance_not_signed(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha")
        stmt_id = self.engine.generate_statement(stmt)
        res = self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_1)
        self.assertFalse(res.passed)
        self.assertFalse(res.tamper_detected)
        self.assertTrue(any("Statement not signed" in v for v in res.violations))

    def test_verify_provenance_missing_signature(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha")
        stmt_id = self.engine.generate_statement(stmt)
        stmt.status = ProvenanceAttestationStatus.SIGNED # Force status
        res = self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_1)
        self.assertFalse(res.passed)
        self.assertTrue(any("Missing signature" in v for v in res.violations))

    def test_verify_provenance_level_mismatch(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha", slsa_level=SlsaLevel.LEVEL_1)
        stmt_id = self.engine.generate_statement(stmt)
        self.engine.sign_statement(stmt_id, "key1", "secret")
        res = self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_2)
        self.assertFalse(res.passed)
        self.assertTrue(any("does not meet target" in v for v in res.violations))

    def test_verify_provenance_success(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha", slsa_level=SlsaLevel.LEVEL_3)
        stmt_id = self.engine.generate_statement(stmt)
        self.engine.sign_statement(stmt_id, "key1", "secret")
        res = self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_2)
        self.assertTrue(res.passed)
        self.assertFalse(res.tamper_detected)
        self.assertEqual(len(res.violations), 0)
        self.assertEqual(stmt.status, ProvenanceAttestationStatus.VERIFIED)

    def test_detect_tamper_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.detect_tamper("bad-id", "sha")

    def test_detect_tamper_true(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha")
        stmt_id = self.engine.generate_statement(stmt)
        self.assertTrue(self.engine.detect_tamper(stmt_id, "wrong-sha"))

    def test_detect_tamper_false(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha")
        stmt_id = self.engine.generate_statement(stmt)
        self.assertFalse(self.engine.detect_tamper(stmt_id, "sha"))

    def test_register_trusted_builder(self):
        self.engine.register_trusted_builder("b1", SlsaLevel.LEVEL_3)
        self.assertIn("b1", self.engine._trusted_builders)
        self.assertEqual(self.engine._trusted_builders["b1"], SlsaLevel.LEVEL_3)

    def test_evaluate_builder_policy_unregistered(self):
        res = self.engine.evaluate_builder_policy("b1", SlsaLevel.LEVEL_1)
        self.assertFalse(res["compliant"])
        self.assertEqual(res["reason"], "Builder not registered")

    def test_evaluate_builder_policy_insufficient_level(self):
        self.engine.register_trusted_builder("b1", SlsaLevel.LEVEL_1)
        res = self.engine.evaluate_builder_policy("b1", SlsaLevel.LEVEL_3)
        self.assertFalse(res["compliant"])
        self.assertIn("lower than required", res["reason"])

    def test_evaluate_builder_policy_sufficient_level(self):
        self.engine.register_trusted_builder("b1", SlsaLevel.LEVEL_3)
        res = self.engine.evaluate_builder_policy("b1", SlsaLevel.LEVEL_3)
        self.assertTrue(res["compliant"])
        self.assertEqual(res["reason"], "Builder supports required level")

    def test_evaluate_builder_policy_higher_level(self):
        self.engine.register_trusted_builder("b1", SlsaLevel.LEVEL_4)
        res = self.engine.evaluate_builder_policy("b1", SlsaLevel.LEVEL_2)
        self.assertTrue(res["compliant"])

    def test_get_artifact_provenance_chain_empty(self):
        chain = self.engine.get_artifact_provenance_chain("unknown")
        self.assertEqual(len(chain), 0)

    def test_get_artifact_provenance_chain_multiple(self):
        stmt1 = InTotoStatement(statement_id="", subject_name="art1", subject_sha256="s1")
        stmt2 = InTotoStatement(statement_id="", subject_name="art1", subject_sha256="s2")
        stmt3 = InTotoStatement(statement_id="", subject_name="art2", subject_sha256="s3")
        self.engine.generate_statement(stmt1)
        self.engine.generate_statement(stmt2)
        self.engine.generate_statement(stmt3)
        chain = self.engine.get_artifact_provenance_chain("art1")
        self.assertEqual(len(chain), 2)

    def test_get_compliance_report_empty(self):
        report = self.engine.get_compliance_report()
        self.assertEqual(report["tamper_count"], 0)
        self.assertEqual(report["trusted_builders_count"], 0)
        self.assertEqual(sum(report["statements_by_level"].values()), 0)
        self.assertEqual(sum(report["statements_by_status"].values()), 0)

    def test_get_compliance_report_with_data(self):
        stmt1 = InTotoStatement(statement_id="", subject_name="art1", subject_sha256="s1", slsa_level=SlsaLevel.LEVEL_1)
        stmt2 = InTotoStatement(statement_id="", subject_name="art2", subject_sha256="s2", slsa_level=SlsaLevel.LEVEL_4)
        self.engine.generate_statement(stmt1)
        stmt2_id = self.engine.generate_statement(stmt2)
        self.engine.sign_statement(stmt2_id, "key1", "secret")
        
        stmt3 = InTotoStatement(statement_id="", subject_name="art3", subject_sha256="s3")
        stmt3_id = self.engine.generate_statement(stmt3)
        self.engine._statements[stmt3_id].status = ProvenanceAttestationStatus.TAMPERED

        self.engine.register_trusted_builder("b1", SlsaLevel.LEVEL_3)
        self.engine.register_trusted_builder("b2", SlsaLevel.LEVEL_4)

        report = self.engine.get_compliance_report()
        self.assertEqual(report["tamper_count"], 1)
        self.assertEqual(report["trusted_builders_count"], 2)
        self.assertEqual(report["statements_by_level"][SlsaLevel.LEVEL_1.value], 2) # art1 and art3 default to L1
        self.assertEqual(report["statements_by_level"][SlsaLevel.LEVEL_4.value], 1)
        
        self.assertEqual(report["statements_by_status"][ProvenanceAttestationStatus.GENERATED.value], 1)
        self.assertEqual(report["statements_by_status"][ProvenanceAttestationStatus.SIGNED.value], 1)
        self.assertEqual(report["statements_by_status"][ProvenanceAttestationStatus.TAMPERED.value], 1)

    # Adding a few more tests to meet the 28-35 requirement

    def test_sign_statement_changes_status_to_signed(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha")
        stmt_id = self.engine.generate_statement(stmt)
        self.engine.sign_statement(stmt_id, "key", "sec")
        self.assertEqual(self.engine._statements[stmt_id].status, ProvenanceAttestationStatus.SIGNED)

    def test_verify_provenance_verified_status(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha", slsa_level=SlsaLevel.LEVEL_2)
        stmt_id = self.engine.generate_statement(stmt)
        self.engine.sign_statement(stmt_id, "key", "sec")
        self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_2)
        self.assertEqual(self.engine._statements[stmt_id].status, ProvenanceAttestationStatus.VERIFIED)
        
    def test_verify_provenance_already_verified_status(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha", slsa_level=SlsaLevel.LEVEL_2)
        stmt_id = self.engine.generate_statement(stmt)
        self.engine.sign_statement(stmt_id, "key", "sec")
        self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_2)
        # Verify again
        res = self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_2)
        self.assertTrue(res.passed)

    def test_verify_provenance_generates_id_and_time(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha", slsa_level=SlsaLevel.LEVEL_2)
        stmt_id = self.engine.generate_statement(stmt)
        self.engine.sign_statement(stmt_id, "key", "sec")
        res = self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_2)
        self.assertTrue(res.verification_id)
        self.assertTrue(res.verified_at)

    def test_verify_provenance_achieved_level_is_set(self):
        stmt = InTotoStatement(statement_id="", subject_name="art", subject_sha256="sha", slsa_level=SlsaLevel.LEVEL_4)
        stmt_id = self.engine.generate_statement(stmt)
        self.engine.sign_statement(stmt_id, "key", "sec")
        res = self.engine.verify_provenance(stmt_id, "sha", SlsaLevel.LEVEL_2)
        self.assertEqual(res.achieved_slsa_level, SlsaLevel.LEVEL_4)

    def test_evaluate_builder_policy_exact_match(self):
        self.engine.register_trusted_builder("b1", SlsaLevel.LEVEL_0)
        res = self.engine.evaluate_builder_policy("b1", SlsaLevel.LEVEL_0)
        self.assertTrue(res["compliant"])

if __name__ == "__main__":
    unittest.main()
