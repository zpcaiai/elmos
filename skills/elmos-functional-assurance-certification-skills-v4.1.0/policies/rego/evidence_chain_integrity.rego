package elmos.certification.evidence_chain_integrity

import rego.v1

default allow := false

allow if {
  input.hash_chain_valid
  input.merkle_root_valid
  input.signature_valid
  input.evidence_fresh
}

decision := {"allow": allow, "policy": "evidence_chain_integrity", "failure_mode": "fail-closed"}
