package elmos.fde.authority
default allow := false
allow if {
  input.lease.valid == true
  input.lease.environment_id == input.environment.id
  input.lease.tenant_id == input.tenant_id
  input.operation in input.lease.operations
  not input.executor.stale
}
