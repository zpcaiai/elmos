from __future__ import annotations
def appraise(evidence,reference,expected_nonce):
 if evidence.get("nonce")!=expected_nonce: return "REJECT"
 if evidence.get("measurement")!=reference.get("measurement"): return "REJECT"
 if not evidence.get("signature_valid"): return "REJECT"
 return "PASS"
def admission_allowed(appraisal,policy_allows): return appraisal=="PASS" and policy_allows
