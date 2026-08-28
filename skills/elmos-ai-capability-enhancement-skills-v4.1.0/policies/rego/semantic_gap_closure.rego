package elmos.certification.semantic_gap_closure

import rego.v1

default allow := false

allow if {
  input.all_gaps_classified
  input.critical_unresolved == 0
  input.allowed_delta_authorized
}

decision := {"allow": allow, "policy": "semantic_gap_closure", "failure_mode": "fail-closed"}
