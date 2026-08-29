package elmos.execution

default allow := false

default require_approval := false

allow if {
  input.risk_tier == "low"
  input.network == false
  input.secret_access == false
  input.tool in {"compiler", "test-runner", "static-analyzer"}
}

require_approval if {
  input.environment == "production"
}

require_approval if {
  input.secret_access == true
}
