package elmos.skill_execution

default allow := false

allow if {
  input.skill.status == "certified"
  input.skill.signature_valid
  input.tenant.authorized
  input.environment.owner == input.request.environment_owner
  every tool in input.request.tools { tool in input.skill.allowed_tools }
  not input.data.quarantined
  not input.skill.revoked
}

require_approval if input.request.production_write
require_approval if input.request.data_export
require_approval if input.request.permission_escalation
