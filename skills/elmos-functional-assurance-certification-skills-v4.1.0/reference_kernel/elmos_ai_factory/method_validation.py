from __future__ import annotations
def coefficient_of_variation(values):
 import statistics
 if len(values)<2 or statistics.mean(values)==0: raise ValueError("invalid values")
 return statistics.stdev(values)/abs(statistics.mean(values))
def method_authorized(metrics,thresholds):
 return all(k in metrics and metrics[k]<=v for k,v in thresholds.items())
