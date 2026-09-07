from __future__ import annotations
def root_cause_complete(cause): return all(cause.get(k) for k in ["problem","cause","evidence","systemic_scope"] )
def effectiveness_pass(before,after,target): return after<=target and after<before
