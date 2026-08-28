package elmos.certification.statistical_release_gate

import rego.v1

default allow := false

allow if {
  input.sample_size_sufficient
  input.confidence_threshold_met
  input.critical_regressions == 0
}

decision := {"allow": allow, "policy": "statistical_release_gate", "failure_mode": "fail-closed"}
