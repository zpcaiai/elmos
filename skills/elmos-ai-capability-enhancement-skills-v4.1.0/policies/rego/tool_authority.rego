package elmos.ai_project_factory.tool_authority
import rego.v1
default allow := false
allow if {
  input.tenant_id == input.authority.tenant_id
  input.execution_epoch == input.authority.execution_epoch
  input.lease_generation == input.authority.lease_generation
  input.fencing_token == input.authority.fencing_token
  input.tool_id in input.authority.allowed_tools
  input.path_scope_valid == true
  input.parameter_scope_valid == true
  input.approval_satisfied == true
}
deny_reason := "authority-or-fencing-invalid" if not allow
