from __future__ import annotations
def surveillance_due(days_since,risk,material_changes,incidents):
 return material_changes or incidents>0 or days_since>=max(30,365-int(300*risk))
def certificate_action(critical_failure,scope_affected,remediated):
 if critical_failure and not remediated: return "SUSPEND" if scope_affected else "REVIEW"
 return "MAINTAIN"
