package elmos.high_risk_transformation

default allow := false

allow if {
  input.risk_class != "critical"
  input.independent_verifier_available
}

allow if {
  input.risk_class == "critical"
  input.independent_verifier_available
  input.human_approval
  input.rollback_rehearsed
  input.all_hard_gates_pass
}
