import unittest
import math
from elmos_ai_optimization.contracts import (
    ContractError, ScopeDeniedError, StaleVersionError, BudgetExceededError, ActionFenceError,
    canonical_json, canonical_digest, require_finite_float,
    RevisionBinding, TrustedScope, SourceAnchor, ContextRequest, ContextItem, EvidenceContext,
    ActionIntent, Receipt
)

class TestContracts(unittest.TestCase):
    def test_canonical_json(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')
        self.assertEqual(canonical_json(["z", "y", "x"]), '["z","y","x"]')
        
    def test_canonical_digest(self):
        # Digest of {"a":1}
        digest = canonical_digest({"a": 1})
        self.assertEqual(len(digest), 64)

    def test_require_finite_float(self):
        self.assertEqual(require_finite_float(1.0, "test"), 1.0)
        self.assertEqual(require_finite_float(1, "test"), 1.0)
        
        with self.assertRaises(ContractError):
            require_finite_float("1.0", "test")
            
        with self.assertRaises(ContractError):
            require_finite_float(float('inf'), "test")
            
        with self.assertRaises(ContractError):
            require_finite_float(float('nan'), "test")

        with self.assertRaises(ContractError):
            require_finite_float(True, "test")

    def test_revision_binding_valid(self):
        r = RevisionBinding("repo", "snap", "gen")
        self.assertEqual(r.repository, "repo")
        self.assertEqual(r.to_dict(), {"repository": "repo", "snapshot": "snap", "generation": "gen"})

    def test_revision_binding_invalid(self):
        with self.assertRaises(ContractError):
            RevisionBinding("", "snap", "gen")
        with self.assertRaises(ContractError):
            RevisionBinding("repo", 123, "gen")
        with self.assertRaises(ContractError):
            RevisionBinding("repo", "snap", "")

    def test_trusted_scope_valid(self):
        r = RevisionBinding("repo", "snap", "gen")
        t = TrustedScope("tenant", "principal", 1, "sec_ref", (r,))
        self.assertEqual(t.tenant, "tenant")
        self.assertEqual(len(t.digest), 64)

    def test_trusted_scope_invalid(self):
        r = RevisionBinding("repo", "snap", "gen")
        with self.assertRaises(ScopeDeniedError):
            TrustedScope("", "principal", 1, "sec_ref", (r,))
        with self.assertRaises(ScopeDeniedError):
            TrustedScope("tenant", "", 1, "sec_ref", (r,))
        with self.assertRaises(ScopeDeniedError):
            TrustedScope("tenant", "principal", -1, "sec_ref", (r,))
        with self.assertRaises(ScopeDeniedError):
            TrustedScope("tenant", "principal", 1, "", (r,))
        with self.assertRaises(ScopeDeniedError):
            TrustedScope("tenant", "principal", 1, "sec_ref", tuple())
        with self.assertRaises(ScopeDeniedError):
            TrustedScope("tenant", "principal", 1, "sec_ref", ("not_a_revision",))

    def test_source_anchor_valid(self):
        blob = "a" * 64
        sa = SourceAnchor("repo", "snap", "gen", "path", blob, 0, 10, "sym")
        self.assertEqual(sa.to_dict()["blob_digest"], blob)

    def test_source_anchor_invalid(self):
        blob = "a" * 64
        with self.assertRaises(ContractError):
            SourceAnchor("", "snap", "gen", "path", blob, 0, 10, "sym")
        with self.assertRaises(ContractError):
            SourceAnchor("repo", "snap", "gen", "path", "short", 0, 10, "sym")
        with self.assertRaises(ContractError):
            SourceAnchor("repo", "snap", "gen", "path", blob, -1, 10, "sym")
        with self.assertRaises(ContractError):
            SourceAnchor("repo", "snap", "gen", "path", blob, 5, 2, "sym")

    def test_context_request_valid(self):
        cr = ContextRequest("req_id", "query", "auto", 10, 1000)
        self.assertEqual(cr.request_id, "req_id")

    def test_context_request_invalid(self):
        with self.assertRaises(ContractError):
            ContextRequest("", "query", "auto", 10, 1000)
        with self.assertRaises(ContractError):
            ContextRequest("req_id", 123, "auto", 10, 1000)
        with self.assertRaises(ContractError):
            ContextRequest("req_id", "query", "invalid_mode", 10, 1000)
        with self.assertRaises(ContractError):
            ContextRequest("req_id", "query", "auto", 0, 1000)
        with self.assertRaises(ContractError):
            ContextRequest("req_id", "query", "auto", 101, 1000)
        with self.assertRaises(ContractError):
            ContextRequest("req_id", "query", "auto", 10, 0)

    def test_context_item_valid(self):
        blob = "a" * 64
        sa = SourceAnchor("repo", "snap", "gen", "path", blob, 0, 10, "sym")
        ci = ContextItem(sa, "text", False, "ref")
        self.assertTrue("anchor" in ci.to_dict())

    def test_evidence_context_valid(self):
        digest = "b" * 64
        ec = EvidenceContext("ok", digest, tuple())
        self.assertEqual(ec.status, "ok")
        self.assertEqual(ec.to_dict()["status"], "ok")

    def test_evidence_context_invalid(self):
        digest = "b" * 64
        with self.assertRaises(ContractError):
            EvidenceContext("invalid_status", digest, tuple())
        with self.assertRaises(ContractError):
            EvidenceContext("ok", "short", tuple())

    def test_action_intent_valid(self):
        ai = ActionIntent("run", "step", "rev", "digest", "artifact", "budget", "plan")
        self.assertEqual(ai.to_dict()["run_ref"], "run")

    def test_receipt_valid(self):
        r = Receipt("action_id", "SUCCEEDED", "ref")
        self.assertEqual(r.to_dict()["state"], "SUCCEEDED")
        self.assertEqual(r.to_dict()["receipt_ref"], "ref")
        
        r2 = Receipt("action_id", "FAILED")
        self.assertNotIn("receipt_ref", r2.to_dict())

    def test_receipt_invalid(self):
        with self.assertRaises(ContractError):
            Receipt("action_id", "INVALID_STATE")

if __name__ == '__main__':
    unittest.main()
