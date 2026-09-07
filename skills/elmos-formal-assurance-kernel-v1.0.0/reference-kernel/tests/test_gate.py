from __future__ import annotations
import unittest
from datetime import datetime, timezone
from elmos_formal_assurance.gate import evaluate_release_gate, validate_result, ResultValidationError
from elmos_formal_assurance.models import (
    AssuranceLevel, Criticality, ProofObligation, ProofResult, ProofStatus, Waiver,
)

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)

def obligation(**overrides):
    data = dict(
        id="o1", criticality=Criticality.P0, property_kind="STATE_INVARIANT",
        required_assurance=AssuranceLevel.A2_SOLVER_PROVED, allow_bounded=False,
    )
    data.update(overrides)
    return ProofObligation(**data)

def result(**overrides):
    data = dict(
        obligation_id="o1", status=ProofStatus.PROVED_SOLVER_TRUSTED,
        assurance_level=AssuranceLevel.A2_SOLVER_PROVED, mode="SMT",
    )
    data.update(overrides)
    return ProofResult(**data)

class GateTests(unittest.TestCase):
    def test_proved_p0_allows(self):
        d = evaluate_release_gate([obligation()], {"o1":result()}, now=NOW)
        self.assertEqual("ALLOW", d.decision)

    def test_missing_result_denies(self):
        d = evaluate_release_gate([obligation()], {}, now=NOW)
        self.assertEqual("DENY", d.decision)
        self.assertIn("missing", d.blocking_reasons[0])

    def test_unknown_denies(self):
        r = result(status=ProofStatus.UNKNOWN_TIMEOUT, assurance_level=AssuranceLevel.NONE, mode="SMT")
        d = evaluate_release_gate([obligation()], {"o1":r}, now=NOW)
        self.assertEqual("DENY", d.decision)

    def test_bounded_cannot_inflate(self):
        r = result(status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE, assurance_level=AssuranceLevel.A1_BOUNDED,
                   mode="BOUNDED", bound={"steps":10})
        d = evaluate_release_gate([obligation()], {"o1":r}, now=NOW)
        self.assertEqual("DENY", d.decision)

    def test_bounded_explicitly_allowed_is_advisory(self):
        o = obligation(required_assurance=AssuranceLevel.A1_BOUNDED, allow_bounded=True)
        r = result(status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE, assurance_level=AssuranceLevel.A1_BOUNDED,
                   mode="BOUNDED", bound={"scope":5})
        d = evaluate_release_gate([o], {"o1":r}, now=NOW)
        self.assertEqual("ADVISORY", d.decision)

    def test_invalid_bounded_result_rejected(self):
        with self.assertRaises(ResultValidationError):
            validate_result(result(status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                                   assurance_level=AssuranceLevel.A1_BOUNDED, mode="SMT", bound={"steps":1}))

    def test_proved_from_bounded_mode_rejected(self):
        with self.assertRaises(ResultValidationError):
            validate_result(result(mode="BOUNDED", bound={"steps":1}))

    def test_stale_proof_denies(self):
        d = evaluate_release_gate([obligation()], {"o1":result(stale=True)}, now=NOW)
        self.assertEqual("DENY", d.decision)

    def test_lower_assurance_denies(self):
        r = result(assurance_level=AssuranceLevel.A1_BOUNDED)
        d = evaluate_release_gate([obligation()], {"o1":r}, now=NOW)
        self.assertEqual("DENY", d.decision)

    def test_active_waiver_yields_advisory(self):
        r = result(status=ProofStatus.UNSUPPORTED, assurance_level=AssuranceLevel.NONE, mode="RUNTIME")
        w = Waiver("o1","APPROVED","HIGH",("a","b"),("runtime monitor",),"2026-09-27T00:00:00Z")
        d = evaluate_release_gate([obligation(criticality=Criticality.P1)], {"o1":r}, {"o1":w}, now=NOW)
        self.assertEqual("ADVISORY", d.decision)

    def test_expired_waiver_denies(self):
        r = result(status=ProofStatus.UNSUPPORTED, assurance_level=AssuranceLevel.NONE, mode="RUNTIME")
        w = Waiver("o1","APPROVED","HIGH",("a","b"),("runtime monitor",),"2026-08-26T00:00:00Z")
        d = evaluate_release_gate([obligation(criticality=Criticality.P1)], {"o1":r}, {"o1":w}, now=NOW)
        self.assertEqual("DENY", d.decision)

    def test_critical_security_waiver_denies(self):
        o = obligation(property_kind="NONINTERFERENCE")
        r = result(status=ProofStatus.UNSUPPORTED, assurance_level=AssuranceLevel.NONE, mode="RUNTIME")
        w = Waiver("o1","APPROVED","CRITICAL",("a","b"),("monitor",),"2026-09-27T00:00:00Z")
        d = evaluate_release_gate([o], {"o1":r}, {"o1":w}, now=NOW)
        self.assertEqual("DENY", d.decision)

    def test_p05_incomplete_denies(self):
        d = evaluate_release_gate([obligation()], {"o1":result()},
                                  required_gate="P05_DEPLOYMENT_COMPLETE",
                                  deployment_complete=False, now=NOW)
        self.assertEqual("DENY", d.decision)

if __name__ == "__main__":
    unittest.main()
