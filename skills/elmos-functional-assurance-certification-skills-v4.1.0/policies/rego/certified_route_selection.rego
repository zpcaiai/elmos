package elmos.certification.certified_route_selection

import rego.v1

default allow := false

allow if {
  input.route_exact_version_supported
  input.route_evidence_fresh
  input.critical_semantic_gaps == 0
}

decision := {"allow": allow, "policy": "certified_route_selection", "failure_mode": "fail-closed"}
