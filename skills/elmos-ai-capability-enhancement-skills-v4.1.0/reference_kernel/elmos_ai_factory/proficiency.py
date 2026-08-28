from __future__ import annotations
def z_score(result,assigned_value,fitness_sigma):
 if fitness_sigma<=0: raise ValueError("fitness sigma")
 return (result-assigned_value)/fitness_sigma
def performance(z):
 a=abs(z)
 return "SATISFACTORY" if a<=2 else ("QUESTIONABLE" if a<3 else "UNSATISFACTORY")
