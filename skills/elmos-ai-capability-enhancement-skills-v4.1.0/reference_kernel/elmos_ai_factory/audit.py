from __future__ import annotations
def risk_weighted_sample(items,n):
 if n<=0: raise ValueError("n")
 return sorted(items,key=lambda x:(x.get("risk",0),x.get("change",0)),reverse=True)[:n]
def evidence_sufficient(required,observed): return set(required)<=set(observed)
