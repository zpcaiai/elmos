package elmos.certification.dual_execution_oracle

import rego.v1

default allow := false

allow if {
  input.source_native_executed
  input.target_native_executed
  input.unexplained_differences == 0
}

decision := {"allow": allow, "policy": "dual_execution_oracle", "failure_mode": "fail-closed"}
