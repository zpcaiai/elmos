package elmos.ai_project_factory.capability_negotiation
import rego.v1
default allow := false
critical_blocked if {
  some d in input.decisions
  d.critical == true
  d.status in {"unsupported", "blocked"}
}
allow if {
  not critical_blocked
  every d in input.decisions {
    d.status in {"supported", "conditional", "emulated", "external-runtime", "external-policy"}
  }
}
decision := "BLOCKED" if critical_blocked
decision := "ALLOW_BOUNDED" if allow
