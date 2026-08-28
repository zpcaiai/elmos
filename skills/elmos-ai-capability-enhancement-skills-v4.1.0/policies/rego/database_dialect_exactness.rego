package elmos.certification.database_dialect_exactness

import rego.v1

default allow := false

allow if {
  input.source_profile_exact
  input.target_profile_exact
  input.collation_charset_locked
}

decision := {"allow": allow, "policy": "database_dialect_exactness", "failure_mode": "fail-closed"}
