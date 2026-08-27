package elmos.formal.waiver_governance_test
import rego.v1
import data.elmos.formal.waiver_governance

test_one_approval_is_denied if {
  result := waiver_governance.deny with input as {
    "obligation":{"criticality":"P1","propertyKind":"LIVENESS"},
    "waiver":{"approvals":[{"approver":"a"}],"compensatingControls":["monitor"],"status":"APPROVED","risk":"HIGH"}
  }
  count(result) == 1
}
