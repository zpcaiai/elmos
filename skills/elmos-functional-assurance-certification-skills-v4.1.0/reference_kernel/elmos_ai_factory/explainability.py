from __future__ import annotations
def top_k_overlap(a,b,k):
 if k<=0: raise ValueError("k")
 sa,sb=set(a[:k]),set(b[:k])
 return len(sa&sb)/max(1,len(sa|sb))
def fidelity(predictions,explanatory_predictions):
 if len(predictions)!=len(explanatory_predictions) or not predictions: raise ValueError("shape")
 return sum(a==b for a,b in zip(predictions,explanatory_predictions))/len(predictions)
