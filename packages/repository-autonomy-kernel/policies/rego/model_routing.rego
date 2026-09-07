package elmos.autonomy.model_routing

default route_allowed := false

route_allowed {
  input.profile.eval_status == "PASS"
  input.profile.max_context >= input.step.required_context
  input.provider_policy.allowed_privacy_modes[_] == input.profile.privacy_mode
}

route_allowed {
  input.risk.level == "LOW"
  input.profile.eval_status == "PASS"
  input.profile.privacy_mode == "local"
}
