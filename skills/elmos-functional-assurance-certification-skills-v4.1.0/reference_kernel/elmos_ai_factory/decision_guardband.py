from __future__ import annotations
def conformity_decision(value,limit,expanded_uncertainty,direction="max"):
 if expanded_uncertainty<0: raise ValueError("negative uncertainty")
 lo,hi=value-expanded_uncertainty,value+expanded_uncertainty
 if direction=="max":
  return "PASS" if hi<=limit else ("FAIL" if lo>limit else "INDETERMINATE")
 if direction=="min":
  return "PASS" if lo>=limit else ("FAIL" if hi<limit else "INDETERMINATE")
 raise ValueError("direction")
def guard_band(limit,expanded_uncertainty,direction="max"):
 return limit-expanded_uncertainty if direction=="max" else limit+expanded_uncertainty
