#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "reference-kernel"))

from elmos_formal_assurance.models import AssuranceLevel, Criticality, ProofObligation, ProofResult, ProofStatus
from elmos_formal_assurance.gate import evaluate_release_gate

def main() -> int:
    obligation = ProofObligation(
        id="demo-nonnegative-balance", criticality=Criticality.P0,
        property_kind="STATE_INVARIANT",
        required_assurance=AssuranceLevel.A2_SOLVER_PROVED,
    )
    proved = ProofResult(
        obligation_id=obligation.id,status=ProofStatus.PROVED_SOLVER_TRUSTED,
        assurance_level=AssuranceLevel.A2_SOLVER_PROVED,mode="SMT"
    )
    bounded = ProofResult(
        obligation_id=obligation.id,status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance_level=AssuranceLevel.A1_BOUNDED,mode="BOUNDED",bound={"steps":20}
    )
    payload = {
        "proved":evaluate_release_gate([obligation],{obligation.id:proved}).decision,
        "boundedForA2":evaluate_release_gate([obligation],{obligation.id:bounded}).decision,
        "honesty":"bounded result remains bounded and is denied for an A2 obligation",
    }
    print(json.dumps(payload,indent=2))
    return 0 if payload["proved"]=="ALLOW" and payload["boundedForA2"]=="DENY" else 1

if __name__ == "__main__":
    raise SystemExit(main())
