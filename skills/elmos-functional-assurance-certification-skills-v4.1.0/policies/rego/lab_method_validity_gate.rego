package elmos.certification.lab_method_validity_gate

import rego.v1

default allow := false

critical_bad_status := {"UNKNOWN", "UNSUPPORTED", "REFUTED"}

deny contains msg if {
  input.critical
  input.status in critical_bad_status
  msg := "critical unresolved proof status"
}

deny contains msg if {
  not input.revision_bound
  msg := "decision is not bound to exact RevisionSet"
}

deny contains msg if {
  not input.independent
  msg := "required independent evaluation or decision is absent"
}

deny contains msg if {
  not input.evidence_fresh
  msg := "evidence is stale or drift-invalidated"
}

deny contains msg if {
  input.side_effects_settled == false
  msg := "side effects are not settled"
}

allow if {
  count(deny) == 0
  input.method_rule_satisfied
}

# Policy intent: unvalidated or unauthorized method cannot support a conformity claim.
