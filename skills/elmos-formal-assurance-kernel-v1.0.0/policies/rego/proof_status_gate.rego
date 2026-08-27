package elmos.formal.proof_status_gate
import rego.v1

proved_statuses := {
  "PROVED_CERTIFIED",
  "PROVED_INDUCTIVE",
  "PROVED_SOLVER_TRUSTED",
  "PROVED_FOR_SUPPORTED_FRAGMENT",
}

deny contains "bounded result cannot satisfy unbounded proof requirement" if {
  input.result.status == "BOUNDED_NO_COUNTEREXAMPLE"
  input.obligation.allowBounded == false
}

deny contains "unknown result cannot pass" if {
  startswith(input.result.status, "UNKNOWN_")
}

deny contains "unsupported result cannot pass" if {
  input.result.status == "UNSUPPORTED"
}

deny contains "stale evidence cannot pass" if {
  input.result.stale == true
}

allow if {
  count(deny) == 0
  input.result.status in proved_statuses
}
