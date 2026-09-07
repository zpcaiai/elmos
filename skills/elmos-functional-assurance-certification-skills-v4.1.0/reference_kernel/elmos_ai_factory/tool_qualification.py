from __future__ import annotations
def qualification_level(can_insert_error,can_fail_to_detect,error_detected_elsewhere):
 if can_insert_error and not error_detected_elsewhere: return "TQL-1"
 if can_fail_to_detect and not error_detected_elsewhere: return "TQL-2"
 return "TQL-5"
def credit_allowed(level,validated,within_operational_requirements):
 return validated and within_operational_requirements and level in {"TQL-1","TQL-2","TQL-3","TQL-4","TQL-5"}
