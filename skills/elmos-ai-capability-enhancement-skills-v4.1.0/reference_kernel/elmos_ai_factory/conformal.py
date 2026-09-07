from __future__ import annotations
def empirical_coverage(contains):
 if not contains: raise ValueError("empty")
 return sum(bool(x) for x in contains)/len(contains)
def coverage_gate(observed,target,tolerance=0.01):
 return observed+tolerance>=target
