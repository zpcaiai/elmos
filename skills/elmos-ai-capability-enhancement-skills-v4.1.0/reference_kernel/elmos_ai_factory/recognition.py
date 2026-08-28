from __future__ import annotations
def scope_match(cert_scope,recognized_scope): return set(cert_scope)<=set(recognized_scope)
def recognition_decision(signatory,scope_ok,scheme_ok,jurisdiction_ok):
 return "ACCEPTED" if all([signatory,scope_ok,scheme_ok,jurisdiction_ok]) else "REVIEW_OR_UNRECOGNIZED"
