package elmos.certification.release_attestation_admission

import rego.v1

default allow := false

allow if {
  input.source_provenance_valid
  input.build_provenance_valid
  input.artifact_signature_valid
  input.vex_policy_satisfied
}

decision := {"allow": allow, "policy": "release_attestation_admission", "failure_mode": "fail-closed"}
