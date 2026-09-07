package elmos.v3delta.capability_authority

default allow := false

allow if {
  input.lease.state == "ACTIVE"
  input.lease.invocation_id == input.invocation_id
  input.lease.environment_id == input.environment_id
  input.lease.authority_snapshot_id == input.authority_snapshot_id
  input.lease.execution_epoch == input.execution_epoch
  input.now < input.lease.expires_at
  not input.requested_authority_widening
}
