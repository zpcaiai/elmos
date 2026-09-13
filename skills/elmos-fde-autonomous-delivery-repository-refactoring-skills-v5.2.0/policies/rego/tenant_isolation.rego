package elmos.fde.tenant_isolation
default allow := false
allow if {
  input.subject.tenant_id == input.resource.tenant_id
  input.context.verified == true
}
