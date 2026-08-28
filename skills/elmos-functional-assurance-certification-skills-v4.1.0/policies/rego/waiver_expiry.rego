package elmos.certification.waiver_expiry

import rego.v1

default allow := false

allow if {
  input.active_waivers_have_owner
  input.expired_waivers == 0
  input.critical_waivers_authorized
}

decision := {"allow": allow, "policy": "waiver_expiry", "failure_mode": "fail-closed"}
