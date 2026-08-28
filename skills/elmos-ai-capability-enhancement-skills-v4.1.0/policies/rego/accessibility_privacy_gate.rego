package elmos.certification.accessibility_privacy_gate

import rego.v1

default allow := false

allow if {
  input.accessibility_required_findings == 0
  input.purpose_limitations_verified
  input.deletion_propagation_verified
}

decision := {"allow": allow, "policy": "accessibility_privacy_gate", "failure_mode": "fail-closed"}
