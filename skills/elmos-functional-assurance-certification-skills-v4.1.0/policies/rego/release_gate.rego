package elmos.ai_project_factory.release_gate
import rego.v1
default allow := false
critical_open if {
  some o in input.obligations
  o.criticality == "critical"
  o.status in {"UNKNOWN", "UNSUPPORTED", "REFUTED"}
}
allow if {
  input.certifier_independent == true
  input.revision_binding_exact == true
  input.evidence_bundle_sealed == true
  input.side_effects_settled == true
  not critical_open
  every gate in ["E0","E1","E2","E3","E4","E5"] {
    input.gates[gate] == "PASS"
  }
  input.p05 == "PASS"
}
decision := "CERTIFIED" if allow
decision := "BLOCKED" if not allow
