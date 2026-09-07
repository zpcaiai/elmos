from __future__ import annotations
def brier_score(probabilities,labels):
 if len(probabilities)!=len(labels) or not probabilities: raise ValueError("shape")
 return sum((p-y)**2 for p,y in zip(probabilities,labels))/len(labels)
def calibration_error(bins):
 total=sum(x[2] for x in bins)
 if total<=0: raise ValueError("empty")
 return sum(abs(conf-acc)*n for conf,acc,n in bins)/total
