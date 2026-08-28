package elmos.ai_project_factory.status_honesty
import rego.v1
default valid := false
valid if {
  input.claimed_status == input.measured_status
  input.claimed_status in {"PROVED","TESTED","BOUNDED","RUNTIME_MONITORED","WAIVED","UNKNOWN","UNSUPPORTED","REFUTED"}
}
forbidden if {
  input.claimed_status == "PROVED"
  input.measured_status in {"TESTED","BOUNDED","RUNTIME_MONITORED","WAIVED","UNKNOWN","UNSUPPORTED","REFUTED"}
}
