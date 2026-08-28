from __future__ import annotations
import math
def combined_standard_uncertainty(components):
 vals=[float(x) for x in components]
 if any(x<0 for x in vals): raise ValueError("uncertainty components must be non-negative")
 return math.sqrt(sum(x*x for x in vals))
def expanded_uncertainty(standard,coverage_factor=2.0):
 if standard<0 or coverage_factor<=0: raise ValueError("invalid uncertainty inputs")
 return standard*coverage_factor
