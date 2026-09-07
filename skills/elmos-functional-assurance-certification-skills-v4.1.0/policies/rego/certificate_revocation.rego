package elmos.certification.certificate_revocation

import rego.v1

default allow := false

allow if {
  input.certificate_not_revoked
  input.no_active_drift_trigger
  input.scope_matches_exact_revision
}

decision := {"allow": allow, "policy": "certificate_revocation", "failure_mode": "fail-closed"}
