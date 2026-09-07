from __future__ import annotations
def work_units_complete(required,results):
 return all(results.get(x)=="PASS" for x in required)
def vulnerability_gate(findings):
 return not any(x.get("severity") in {"critical","high"} and x.get("status")!="closed" for x in findings)
