from __future__ import annotations
import statistics,math
def robust_location(values):
 if not values: raise ValueError("empty")
 return statistics.median(values)
def reproducibility_sd(lab_means):
 if len(lab_means)<2: raise ValueError("need two labs")
 return statistics.stdev(lab_means)
