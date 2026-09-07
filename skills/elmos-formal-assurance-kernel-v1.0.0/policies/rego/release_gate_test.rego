package elmos.formal.release_gate_test
import rego.v1
import data.elmos.formal.release_gate

test_unknown_p0_is_denied if {
  result := release_gate.deny with input as {
    "requiredGate": "E2_MODEL",
    "deploymentComplete": true,
    "results": [{"obligationId":"o1","criticality":"P0","status":"UNKNOWN_TIMEOUT","allowBounded":false,"stale":false}]
  }
  count(result) == 1
}
