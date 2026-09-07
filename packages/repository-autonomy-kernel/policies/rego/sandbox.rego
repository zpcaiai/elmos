package elmos.autonomy.sandbox

default allow := false

allow {
  input.network_policy.deny_by_default == true
  input.workspace_profile.phase == "ANALYZE"
  count(input.secret_binding_plan.scopes) == 0
}

allow_execution {
  input.network_policy.deny_by_default == true
  input.workspace_profile.phase == "EXECUTE"
}
