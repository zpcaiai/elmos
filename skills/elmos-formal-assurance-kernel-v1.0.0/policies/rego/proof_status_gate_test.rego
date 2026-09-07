package elmos.formal.proof_status_gate_test
import rego.v1
import data.elmos.formal.proof_status_gate

test_bounded_is_denied if {
  result := proof_status_gate.deny with input as {
    "result": {"status": "BOUNDED_NO_COUNTEREXAMPLE", "stale": false},
    "obligation": {"allowBounded": false}
  }
  count(result) == 1
}
