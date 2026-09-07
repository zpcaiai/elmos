from __future__ import annotations
def overreliance_rate(accepted_wrong,total_wrong_advice):
 if total_wrong_advice<=0: return 0.0
 return accepted_wrong/total_wrong_advice
def safe_reliance_gate(overreliance,max_rate,override_available):
 return override_available and overreliance<=max_rate
