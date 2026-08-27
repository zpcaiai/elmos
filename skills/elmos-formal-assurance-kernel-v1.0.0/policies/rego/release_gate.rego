package elmos.formal.release_gate
import rego.v1

nonpassing := {
  "REFUTED_WITH_COUNTEREXAMPLE",
  "UNKNOWN_TIMEOUT",
  "UNKNOWN_RESOURCE_LIMIT",
  "UNSUPPORTED",
  "ASSUMPTION_REQUIRED",
}

deny contains sprintf("critical obligation %s has non-passing status %s", [r.obligationId, r.status]) if {
  some r in input.results
  r.criticality == "P0"
  r.status in nonpassing
}

deny contains sprintf("critical obligation %s only has bounded evidence", [r.obligationId]) if {
  some r in input.results
  r.criticality == "P0"
  r.status == "BOUNDED_NO_COUNTEREXAMPLE"
  r.allowBounded == false
}

deny contains sprintf("evidence for %s is stale", [r.obligationId]) if {
  some r in input.results
  r.stale == true
}

deny contains "P05 deployment gate is not complete" if {
  input.requiredGate == "P05_DEPLOYMENT_COMPLETE"
  input.deploymentComplete != true
}

allow if {
  count(deny) == 0
}
