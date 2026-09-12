import unittest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from elmos_mature_platform.types import (
    BuildRequest, BuildAttestation, BuildPolicy, BuildIsolationLevel,
    BuildVerdict, SlsaLevel
)
from elmos_mature_platform.isolated_trusted_builder_engine import IsolatedTrustedBuilderEngine


class TestIsolatedTrustedBuilderEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IsolatedTrustedBuilderEngine()
        
    def test_submit_build_returns_id(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        res = self.engine.submit_build(req)
        self.assertEqual(res, "b1")
        
    def test_submit_build_initial_state(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        att = self.engine.get_build("b1")
        self.assertEqual(att.verdict, BuildVerdict.FAILED)
        self.assertNotEqual(att.started_at, "")

    def test_complete_build_success(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED, network_allowed=True)
        self.engine.submit_build(req)
        att = self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        self.assertEqual(att.verdict, BuildVerdict.PASSED)
        self.assertEqual(att.slsa_level, SlsaLevel.LEVEL_1)
        
    def test_complete_build_unknown_id(self):
        with self.assertRaises(ValueError):
            self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
            
    def test_complete_build_timeout(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED, timeout_seconds=10)
        self.engine.submit_build(req)
        self.engine.advance_time(15)
        att = self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        self.assertEqual(att.verdict, BuildVerdict.TIMEOUT)
        
    def test_complete_build_network_hermetic_tainted(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.HERMETIC, network_allowed=False)
        self.engine.submit_build(req)
        att = self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", network_accessed=True, reproducible=False)
        self.assertEqual(att.verdict, BuildVerdict.TAINTED)
        
    def test_complete_build_network_air_gapped_tainted(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.AIR_GAPPED, network_allowed=False)
        self.engine.submit_build(req)
        att = self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", network_accessed=True, reproducible=False)
        self.assertEqual(att.verdict, BuildVerdict.TAINTED)
        
    def test_complete_build_network_not_allowed_tainted(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED, network_allowed=False)
        self.engine.submit_build(req)
        att = self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", network_accessed=True, reproducible=False)
        self.assertEqual(att.verdict, BuildVerdict.TAINTED)

    def test_sign_provenance_success(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        att = self.engine.sign_provenance("b1", "signer1")
        self.assertTrue(att.provenance_signed)
        self.assertEqual(att.slsa_level, SlsaLevel.LEVEL_2)
        
    def test_sign_provenance_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.sign_provenance("b1", "signer1")
            
    def test_sign_provenance_failed_build(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED, timeout_seconds=10)
        self.engine.submit_build(req)
        self.engine.advance_time(15)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        with self.assertRaises(ValueError):
            self.engine.sign_provenance("b1", "signer1")
            
    def test_verify_build_success(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        self.engine.sign_provenance("b1", "signer1")
        res = self.engine.verify_build("b1")
        self.assertTrue(res["integrity_passed"])
        self.assertTrue(res["provenance_signed"])
        self.assertEqual(res["slsa_level"], SlsaLevel.LEVEL_2.value)
        
    def test_verify_build_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.verify_build("b1")
            
    def test_set_policy(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1)
        self.engine.set_policy(pol)
        self.assertEqual(self.engine.policy, pol)

    def test_evaluate_policy_no_policy(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy("b1")
            
    def test_evaluate_policy_unknown_build(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1)
        self.engine.set_policy(pol)
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy("b1")

    def test_evaluate_policy_compliant(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1, require_signed_provenance=False)
        self.engine.set_policy(pol)
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        res = self.engine.evaluate_policy("b1")
        self.assertTrue(res["compliant"])
        self.assertEqual(len(res["violations"]), 0)

    def test_evaluate_policy_isolation_violation(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.HERMETIC, SlsaLevel.LEVEL_1, require_signed_provenance=False)
        self.engine.set_policy(pol)
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        res = self.engine.evaluate_policy("b1")
        self.assertFalse(res["compliant"])
        self.assertIn("Isolation level", res["violations"][0])
        
    def test_evaluate_policy_slsa_violation(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_2, require_signed_provenance=False)
        self.engine.set_policy(pol)
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        res = self.engine.evaluate_policy("b1")
        self.assertFalse(res["compliant"])
        self.assertIn("SLSA level", res["violations"][0])
        
    def test_evaluate_policy_reproducible_violation(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1, require_reproducible=True, require_signed_provenance=False)
        self.engine.set_policy(pol)
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        res = self.engine.evaluate_policy("b1")
        self.assertFalse(res["compliant"])
        self.assertIn("reproducible", res["violations"][0])

    def test_evaluate_policy_signed_provenance_violation(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1, require_signed_provenance=True)
        self.engine.set_policy(pol)
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        res = self.engine.evaluate_policy("b1")
        self.assertFalse(res["compliant"])
        self.assertIn("signed", res["violations"][0])
        
    def test_evaluate_policy_builder_digest_violation(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1, require_signed_provenance=False, allowed_builder_digests=["ok_dig"])
        self.engine.set_policy(pol)
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bad_dig", "log_dig", False, False)
        res = self.engine.evaluate_policy("b1")
        self.assertFalse(res["compliant"])
        self.assertIn("Builder digest", res["violations"][0])
        
    def test_get_build_success(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        att = self.engine.get_build("b1")
        self.assertEqual(att.build_id, "b1")
        
    def test_list_builds_no_filter(self):
        req1 = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        req2 = BuildRequest("b2", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req1)
        self.engine.submit_build(req2)
        res = self.engine.list_builds()
        self.assertEqual(len(res), 2)
        
    def test_list_builds_tenant_filter(self):
        req1 = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED, tenant_id="t1")
        req2 = BuildRequest("b2", "repo", "commit", "img", BuildIsolationLevel.SHARED, tenant_id="t2")
        self.engine.submit_build(req1)
        self.engine.submit_build(req2)
        res = self.engine.list_builds(tenant_id="t1")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].build_id, "b1")

    def test_list_builds_verdict_filter(self):
        req1 = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        req2 = BuildRequest("b2", "repo", "commit", "img", BuildIsolationLevel.SHARED, timeout_seconds=10)
        self.engine.submit_build(req1)
        self.engine.submit_build(req2)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        self.engine.advance_time(15)
        self.engine.complete_build("b2", "art_dig", "bld_dig", "log_dig", False, False)
        res = self.engine.list_builds(verdict=BuildVerdict.TIMEOUT)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].build_id, "b2")

    def test_compute_slsa_level_0(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED, timeout_seconds=10)
        self.engine.submit_build(req)
        self.engine.advance_time(15)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        slsa = self.engine.compute_slsa_level("b1")
        self.assertEqual(slsa, SlsaLevel.LEVEL_0)
        
    def test_compute_slsa_level_1(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        slsa = self.engine.compute_slsa_level("b1")
        self.assertEqual(slsa, SlsaLevel.LEVEL_1)
        
    def test_compute_slsa_level_2(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        self.engine.sign_provenance("b1", "signer1")
        slsa = self.engine.compute_slsa_level("b1")
        self.assertEqual(slsa, SlsaLevel.LEVEL_2)

    def test_compute_slsa_level_3(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.TENANT_ISOLATED)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        self.engine.sign_provenance("b1", "signer1")
        slsa = self.engine.compute_slsa_level("b1")
        self.assertEqual(slsa, SlsaLevel.LEVEL_3)
        
    def test_compute_slsa_level_4(self):
        req = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.HERMETIC)
        self.engine.submit_build(req)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, True)
        self.engine.sign_provenance("b1", "signer1")
        slsa = self.engine.compute_slsa_level("b1")
        self.assertEqual(slsa, SlsaLevel.LEVEL_4)
        
    def test_detect_tainted_builds(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1, allowed_builder_digests=["ok_dig"])
        self.engine.set_policy(pol)
        req1 = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.HERMETIC)
        req2 = BuildRequest("b2", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req1)
        self.engine.submit_build(req2)
        self.engine.complete_build("b1", "art_dig", "ok_dig", "log_dig", True, False)
        self.engine.complete_build("b2", "art_dig", "bad_dig", "log_dig", False, False)
        res = self.engine.detect_tainted_builds()
        self.assertEqual(len(res), 2)
        
    def test_get_supply_chain_report(self):
        pol = BuildPolicy("p1", BuildIsolationLevel.SHARED, SlsaLevel.LEVEL_1, require_signed_provenance=True)
        self.engine.set_policy(pol)
        req1 = BuildRequest("b1", "repo", "commit", "img", BuildIsolationLevel.SHARED)
        self.engine.submit_build(req1)
        self.engine.complete_build("b1", "art_dig", "bld_dig", "log_dig", False, False)
        rep = self.engine.get_supply_chain_report()
        self.assertEqual(rep["total_builds"], 1)
        self.assertEqual(rep["verdict_counts"][BuildVerdict.PASSED.value], 1)
        self.assertEqual(rep["slsa_counts"][SlsaLevel.LEVEL_1.value], 1)
        self.assertEqual(rep["tainted_count"], 0)
        self.assertEqual(rep["policy_violations"], 1)

if __name__ == "__main__":
    unittest.main()
