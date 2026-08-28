from __future__ import annotations
def worst_case_accuracy(results):
 if not results: raise ValueError("empty")
 return min(float(x) for x in results)
def robustness_gate(baseline,stressed,max_drop):
 return baseline-stressed<=max_drop and stressed>=0
