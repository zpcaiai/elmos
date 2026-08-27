package elmos.formal.waiver_governance
import rego.v1

deny contains "waiver requires at least two distinct approvals" if {
  count({a.approver | some a in input.waiver.approvals}) < 2
}

deny contains "waiver must have compensating controls" if {
  count(input.waiver.compensatingControls) == 0
}

deny contains "waiver is not approved" if {
  input.waiver.status != "APPROVED"
}

deny contains "critical security or financial obligation cannot be waived by policy" if {
  input.obligation.criticality == "P0"
  input.obligation.propertyKind in {"AUTHORIZATION_DOMINANCE", "NONINTERFERENCE"}
  input.waiver.risk == "CRITICAL"
}

allow if {
  count(deny) == 0
}
