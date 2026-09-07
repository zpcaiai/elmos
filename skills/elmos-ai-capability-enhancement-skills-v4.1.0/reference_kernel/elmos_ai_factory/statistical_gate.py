from __future__ import annotations
import math,statistics
def percentile(values:list[float],q:float)->float:
    if not values:raise ValueError("empty")
    x=sorted(values);p=(len(x)-1)*q;lo=math.floor(p);hi=math.ceil(p)
    return x[lo] if lo==hi else x[lo]+(x[hi]-x[lo])*(p-lo)
def mean_ci95(values:list[float])->tuple[float,float,float]:
    if len(values)<2:raise ValueError("need >=2")
    m=statistics.mean(values);se=statistics.stdev(values)/math.sqrt(len(values));d=1.96*se
    return m,m-d,m+d
def regression_gate(baseline:list[float],candidate:list[float],max_relative:float,min_samples:int=5)->dict:
    if len(baseline)<min_samples or len(candidate)<min_samples:return {"decision":"BLOCKED","reason":"insufficient-samples"}
    b=statistics.mean(baseline);c=statistics.mean(candidate);rel=(c-b)/b if b else float("inf")
    return {"decision":"PASS" if rel<=max_relative else "FAIL","relative":rel,"baselineMean":b,"candidateMean":c}
