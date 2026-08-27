package elmos.autonomy.authority

default allow := false

allow {
  input.identity.verified == true
  input.tenant_id != ""
  input.account_id != ""
  input.authority.source != "conversation"
  input.request.environment_id == input.authority.environment_id
  input.request.workspace_id == input.authority.workspace_id
  input.request.fencing_token == input.authority.fencing_token
  input.authority.allowed_tools[_] == input.request.tool_id
}

deny_reason["verified identity required"] {
  not input.identity.verified
}

deny_reason["conversation is not authority"] {
  input.authority.source == "conversation"
}
