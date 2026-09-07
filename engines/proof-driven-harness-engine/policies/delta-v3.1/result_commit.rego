package elmos.v3delta.result_commit

default allow_commit := false

immutable_identity_fields := {"call_id", "invocation_id", "execution_plan_hash", "environment_id", "authority_snapshot_id"}

identity_unchanged if {
  not changed_immutable_field
}
changed_immutable_field if {
  some f in immutable_identity_fields
  input.raw.identity[f] != input.effective.identity[f]
}

allow_commit if {
  input.state == "INTERCEPTING"
  identity_unchanged
  input.interceptor_chain_verified
  input.current_generation
}
