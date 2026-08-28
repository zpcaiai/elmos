package elmos.certification.transaction_equivalence

import rego.v1

default allow := false

allow if {
  input.isolation_scenarios_complete
  input.unexplained_locking_differences == 0
  input.rollback_verified
}

decision := {"allow": allow, "policy": "transaction_equivalence", "failure_mode": "fail-closed"}
