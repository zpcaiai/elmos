package elmos.business_line_admission

default allow := false

allow if {
  input.tenant_authorized
  input.entitled
  input.version_pinned
  input.support_matrix_match
  input.baseline_available
  input.rollback_target_available
}

deny_reason contains "unsupported-or-uncertified-version" if { not input.support_matrix_match }
deny_reason contains "missing-rollback-target" if { not input.rollback_target_available }
