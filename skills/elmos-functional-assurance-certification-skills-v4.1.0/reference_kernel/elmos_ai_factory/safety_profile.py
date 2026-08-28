from __future__ import annotations
def residual_risk(severity,probability,control_effectiveness): return severity*probability*(1-control_effectiveness)
def safety_gate(residual,limit,fallback_verified,independent_review): return residual<=limit and fallback_verified and independent_review
