package elmos.certification.clean_room_independence

import rego.v1

default allow := false

allow if {
  input.clean_environment
  input.certifier_separate_identity
  input.generator_cannot_write_result
}

decision := {"allow": allow, "policy": "clean_room_independence", "failure_mode": "fail-closed"}
