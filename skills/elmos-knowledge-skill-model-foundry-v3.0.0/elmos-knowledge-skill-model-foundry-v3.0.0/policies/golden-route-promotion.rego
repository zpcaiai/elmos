package elmos.golden_route_promotion

default promote := false

promote if {
  input.evidence_level == "E5"
  input.disjoint_repository_count >= 3
  input.shadow_passed
  input.canary_passed
  input.rollback_passed
  input.long_soak_passed
  input.no_critical_security_findings
}
